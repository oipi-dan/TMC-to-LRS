import arcpy
import lrs_tools
import config
import statistics
from collections import Counter
import pandas as pd
import logging
import os
import json
import difflib

""" The input TMCs are dissolved by linearId, then the routes associated with those linearIds
    are found using the following workflow:
    
    1 - Find nearby routes at the begin point, mid-point, and end point of each line
    2 - If only one route appears in all three, then it is assumed that this is the correct
        route to associate with this linearId
    3 - LinearIds that have zero or more than one potential match will be evaluated in the
        next step
"""

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG) # Set the debug level here
fileHandler = logging.FileHandler('logs\\30_identify_routes_by_number.log', mode='w')
log.addHandler(fileHandler)


class TMC():
    def __init__(self, tmc, roadNumber, fc_TMCs, route_nbr_map):
        self.tmc = tmc
        self.roadNumber = str(roadNumber)
        self.geom = [row[0] for row in arcpy.da.SearchCursor(fc_TMCs, 'SHAPE@', f"tmc = '{self.tmc}'")][0]
        self.firstPoint = self.get_first_point()
        self.lastPoint = self.get_last_point()
        self.midPoint = self.get_mid_point()
        self.potentialRoutes = route_nbr_map # Potential routes limited by route number
        self.routes = Counter()

    def get_first_point(self):
        """ Finds the first point of the TMC """
        try:
            return arcpy.PointGeometry(self.geom.firstPoint, spatial_reference=config.VIRGINIA_LAMBERT)
        except:
            return None
    
    
    def get_last_point(self):
        """ Finds the last point of the TMC """
        try:
            return arcpy.PointGeometry(self.geom.lastPoint, spatial_reference=config.VIRGINIA_LAMBERT)
        except:
            return None

    
    def get_mid_point(self):
        """ Finds the mid point of the TMC """
        try:
            mid_point = self.geom.positionAlongLine(0.5, True)
            return arcpy.PointGeometry(mid_point.firstPoint, spatial_reference=config.VIRGINIA_LAMBERT)
        except:
            return None

    
    def __repr__(self):
        """ Returns stats for this LinearId for logging purposes """
        return f'\n    tmc: {self.tmc}\n    firstPoint: {(self.firstPoint.firstPoint.X, self.firstPoint.firstPoint.Y) if self.firstPoint else None}\n    lastPoint: {(self.lastPoint.firstPoint.X, self.lastPoint.firstPoint.Y) if self.lastPoint else None}\n    midPoint: {(self.midPoint.firstPoint.X, self.midPoint.firstPoint.Y) if self.midPoint else None}\n    routes: {self.routes}\n'


def identify_routes_by_roadNumber_and_name_simple(*test_tmcs, lyrLRS=None):
    """ Attempts to match TMCs to the correct RTE_NM by route number
    """
    
    print('Attempting to match TMCs to the correct RTE_NM by grouping by roadNumber')
    
    if not lyrLRS:
        print('  Creating MasterLRS layer')
        lyrLRS = arcpy.MakeFeatureLayer_management(config.MASTER_LRS, 'lrs')

    with open('route_nbr_map.json','r') as file:
        roadNumber_to_RTE_NMs = json.load(file)

    print('  Preparing list of TMCs')
    if len(test_tmcs) > 0:
        tmcs = list(test_tmcs)
    else:
        tmcs = [row[0] for row in arcpy.da.SearchCursor(config.TMCs, 'tmc')]

    print('  Mapping TMCs to roadNumbers')
    roadNumber_dict = {row[0]: row[1].split('-')[1] for row in arcpy.da.SearchCursor(config.TMCs, ['tmc', 'roadNumber']) if row[1] != 'None'}

    # print('  Dissolving TMC layer by lineraIds')
    arcpy.env.overwriteOutput = True
    if len(tmcs) == 1:
        tmcs.append('') # To fix bug when creating valid sql statement when only one Id exists

    # arcpy.FeatureClassToFeatureClass_conversion(config.TMCs, r'data\intermediate.gdb', '_10_dissolve_prep', f"linearId IN {tuple(linearIds)} AND (tmc LIKE '___+%' OR tmc LIKE '___P%')")
    # arcpy.analysis.PairwiseDissolve(r'data\intermediate.gdb\_10_dissolve_prep', r'data\intermediate.gdb\_10_dissolve_by_linearIds', 'linearId')
    fc_TMCs = config.TMCs

    # Identify RTE_NMs by roadNumber
    total = len(tmcs) - 1
    output = {}
    for i, tmc_code in enumerate(tmcs):
        try:
            roadNumber = roadNumber_dict[tmc_code]
            tmc = TMC(tmc_code, roadNumber, fc_TMCs, roadNumber_to_RTE_NMs[roadNumber])

            nearby_routes = []
            if tmc.firstPoint:
                nearby_routes.extend(lrs_tools.find_nearby_routes(tmc.firstPoint, lyrLRS))

            if tmc.midPoint:
                nearby_routes.extend(lrs_tools.find_nearby_routes(tmc.midPoint, lyrLRS))

            if tmc.lastPoint:
                nearby_routes.extend(lrs_tools.find_nearby_routes(tmc.lastPoint, lyrLRS))
            
            nearby_routes = [route for route in nearby_routes if route in tmc.potentialRoutes]
            tmc.routes.update(nearby_routes)

            tmc.routes = lrs_tools.get_most_common(tmc.routes) 

            log.debug(tmc)
            if len(tmc.routes) == 1 and tmc.routes[0][1] == 3:
                output[tmc.tmc] = tmc.routes[0][0]
        except Exception as e:
            log.debug(f'\nError on {tmc}')
            log.debug(e)

        lrs_tools.print_progress_bar(i, total, f'Identifying RTE_NMs by routeNumber')

    print('\n')

    # For rte_nms that were successfully identified, find the begin_msr and end_msr values
    # Update status and LRS fields in TMCs layer
    completeIds = list(output.keys())

    if len(completeIds) == 1:
        completeIds.append('') # To fix bug when creating valid sql statement when only one Id exists

    row_count = len(list(i for i in arcpy.da.SearchCursor(config.TMCs, 'tmc', f"tmc in {tuple(completeIds)}"))) - 1
    if row_count == 0:
        row_count = 1 # To fix bug when creating valid sql statement when only one Id exists
    with arcpy.da.UpdateCursor(config.TMCs, ['tmc', 'status', 'rte_nm', 'begin_msr', 'end_msr','SHAPE@'], f"tmc in {tuple(completeIds)}") as cur:
        for i, row in enumerate(cur):
            if row[0] in completeIds:
                try:
                    geom = row[-1]
                    rte_nm = output[row[0]]
                    begin_msr, end_msr = lrs_tools.get_line_mp(geom, config.MASTER_LRS, rte_nm)
                    row[2] = rte_nm
                    row[3] = begin_msr
                    row[4] = end_msr
                    row[1] = 'Complete (30)'
                    cur.updateRow(row)
                except Exception as e:
                    log.debug(f'Error updating {row[-2]} in TMCs table')
                    log.debug(e)
                    row[1] = 'Error (30)'
                    cur.updateRow(row)


            
            
            lrs_tools.print_progress_bar(i, row_count, f'Locating MPs for matched routes')


if __name__ == '__main__':
    identify_routes_by_roadNumber_and_name_simple()