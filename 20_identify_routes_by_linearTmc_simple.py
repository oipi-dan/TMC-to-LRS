import arcpy
import lrs_tools
import config
import statistics
from collections import Counter
import pandas as pd
import logging
import geopandas as gp

""" The input TMCs are dissolved by linearTMC, then the routes associated with those linearTmc
    are found using the following workflow:
    
    1 - Find nearby routes at the begin point, mid-point, and end point of each line
    2 - If only one route appears in all three, then it is assumed that this is the correct
        route to associate with this linearTmc
    3 - linearTmcs that have zero or more than one potential match will be evaluated in the
        next step
"""

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG) # Set the debug level here
fileHandler = logging.FileHandler('logs\\20_identify_routes_by_linearTmc_simple.log', mode='w')
log.addHandler(fileHandler)


class Linear_TMC():
    def __init__(self, linearTmc, fc_linearTmcs):
        self.linearTmc = str(linearTmc)
        self.linearTmc_geom = [row[0] for row in arcpy.da.SearchCursor(fc_linearTmcs, 'SHAPE@', f"linearTmc = '{self.linearTmc}'")][0]
        # self.roadOrders = self.get_road_orders() Not needed now that I'm using dissolved layer to identify begin/mid/end points
        self.firstPoint = self.get_first_point()
        self.lastPoint = self.get_last_point()
        self.midPoint = self.get_mid_point()
        self.routes = Counter()


    def get_first_point(self):
        """ Finds the first point of the first TMC of the linearTmc """
        try:
            return arcpy.PointGeometry(self.linearTmc_geom.firstPoint, spatial_reference=config.VIRGINIA_LAMBERT)
        except:
            return None
    
    
    def get_last_point(self):
        """ Finds the last point of the last TMC of the linearTmc """
        try:
            return arcpy.PointGeometry(self.linearTmc_geom.lastPoint, spatial_reference=config.VIRGINIA_LAMBERT)
        except:
            return None

    
    def get_mid_point(self):
        """ Finds the mid point of the middle TMC of the linearTmc """
        try:
            mid_point = self.linearTmc_geom.positionAlongLine(0.5, True)
            return arcpy.PointGeometry(mid_point.firstPoint, spatial_reference=config.VIRGINIA_LAMBERT)
        except:
            return None

    
    def __repr__(self):
        """ Returns stats for this linearTmc for logging purposes """
        return f'\n    linearTmc: {self.linearTmc}\n    firstPoint: {(self.firstPoint.firstPoint.X, self.firstPoint.firstPoint.Y) if self.firstPoint else None}\n    lastPoint: {(self.lastPoint.firstPoint.X, self.lastPoint.firstPoint.Y) if self.lastPoint else None}\n    midPoint: {(self.midPoint.firstPoint.X, self.midPoint.firstPoint.Y) if self.midPoint else None}\n    routes: {self.routes}\n'


def identify_routes_by_linearTmc_simple(*test_linearTmcs, lyrLRS=None):
    """ Attempts to match TMCs to the correct RTE_NM by grouping by linearTmc 
    
        Inputs:
            test_linearTmc - optional linearTmc values for testing.  If none,
                then this function will be applied to all TMCs
            lyrLRS - A feature layer of the master LRS.  Passing it as a
                parameter will save time, but it will be created if it does
                not exist yet
    """
    
    if not lyrLRS:
        print('  Creating MasterLRS layer')
        lyrLRS = arcpy.MakeFeatureLayer_management(config.MASTER_LRS, 'lrs')

    print('  Preparing LRS for GeoPandas')
    lrsSHP = gp.read_file(config.LRS_SHP)
    lrsSIndex = lrsSHP.sindex
    geopandas_lrs = (lrsSHP, lrsSIndex)

    print('  Preparing list of linearTmc')
    if len(test_linearTmcs) > 0:
        linearTmcs = list(test_linearTmcs)
    else:
        linearTmcs = [row[0] for row in arcpy.da.SearchCursor(config.TMCs, 'linearTmc', 'status IS NULL')]
    
    print('  Dissolving TMC layer by linearTmc')
    arcpy.env.overwriteOutput = True
    if len(linearTmcs) == 1:
        linearTmcs.append('') # To fix bug when creating valid sql statement when only one Id exists

    arcpy.FeatureClassToFeatureClass_conversion(config.TMCs, r'data\intermediate.gdb', '_10_dissolve_prep', f"linearTmc IN {tuple(linearTmcs)} AND (tmc LIKE '___+%' OR tmc LIKE '___P%')")
    arcpy.analysis.PairwiseDissolve(r'data\intermediate.gdb\_10_dissolve_prep', r'data\intermediate.gdb\_20_dissolve_by_linearTmcs', 'linearTmc')
    fc_linearTmcs = 'data//intermediate.gdb//_20_dissolve_by_linearTmcs'

    # Identify RTE_NMs by lineraId
    total = len(linearTmcs) - 1
    output = {}
    for i, linear_tmc in enumerate(linearTmcs):
        try:
            linear_group = Linear_TMC(linear_tmc, fc_linearTmcs)

            nearby_routes = []
            if linear_group.firstPoint:
                nearby_routes.extend(lrs_tools.find_nearby_routes_geopandas(linear_group.firstPoint, geopandas_lrs))

            if linear_group.midPoint:
                nearby_routes.extend(lrs_tools.find_nearby_routes_geopandas(linear_group.midPoint, geopandas_lrs))

            if linear_group.lastPoint:
                nearby_routes.extend(lrs_tools.find_nearby_routes_geopandas(linear_group.lastPoint, geopandas_lrs))
            
            linear_group.routes.update(nearby_routes)

            linear_group.routes = lrs_tools.get_most_common(linear_group.routes) 

            log.debug(linear_group)
            if len(linear_group.routes) == 1 and linear_group.routes[0][1] == 3:
                output[linear_group.linearTmc] = linear_group.routes[0][0]
            
        except Exception as e:
            log.debug(f'\nError on {linear_tmc}')
            log.debug(e)

        lrs_tools.print_progress_bar(i, total, 'Identifying RTE_NMs by linear_tmc')

    print('\n')

    # For rte_nms that were successfully identified, find the begin_msr and end_msr values
    # Update status and LRS fields in TMCs layer
    completeIds = list(output.keys())
    if len(completeIds) == 1:
        completeIds.append('') # To fix bug when creating valid sql statement when only one Id exists

    row_count = len(list(i for i in arcpy.da.SearchCursor(config.TMCs, 'linearTmc', f"linearTmc in {tuple(completeIds)}"))) - 1
    with arcpy.da.UpdateCursor(config.TMCs, ['linearTmc', 'status', 'rte_nm', 'begin_msr', 'end_msr', 'tmc', 'SHAPE@'], f"linearTmc in {tuple(completeIds)}") as cur:
        for i, row in enumerate(cur):
            if row[0] in completeIds:
                try:
                    geom = row[-1]
                    rte_nm = output[row[0]]
                    begin_msr, end_msr = lrs_tools.get_line_mp(geom, config.MASTER_LRS, rte_nm)

                    # If begin_msr and end_msr are the same, then this should be assumed to be a bad match
                    if begin_msr == end_msr:
                        row[1] = None
                        row[2] = None
                        row[3] = None
                        row[4] = None
                        cur.updateRow(row)
                        continue
                    
                    row[2] = rte_nm
                    row[3] = begin_msr
                    row[4] = end_msr
                    row[1] = 'Complete (20)'
                    cur.updateRow(row)
                except Exception as e:
                    log.debug(f'Error updating {row[-2]} in TMCs table')
                    log.debug(e)
                    row[1] = 'Error (20)'
                    cur.updateRow(row)


            
            
            lrs_tools.print_progress_bar(i, row_count, 'Locating MPs for matched routes')
    

if __name__ == '__main__':
    print('\nIdentifying routes by linearTmc')
    identify_routes_by_linearTmc_simple()