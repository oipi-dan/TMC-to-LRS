import arcpy
import lrs_tools
import config
import statistics
from collections import Counter
import pandas as pd
import logging
import geopandas as gp
import json
import difflib

""" This iteration is similar to 10_identify_routes_by_linearId_simple.py, but it goes into more detail:
        - It searches for RTE_NM at the individual TMC level rather than TMC groups (linearId or linearTmc)
        - It considers the first quarter and third quarter points in addition to the first, mid, and last when
          identifying RTE_NMs
        - It makes use of the roadNumber and roadName fields to help identify the correct route in cases where
          more than one might be present
        - If a route cannot be identified by number or name, it will assign to any other route that meets the
          location criteria.  If the match is incorrect, these will be removed in autoQC.
"""

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG) # Set the debug level here
fileHandler = logging.FileHandler('logs\\31_identify_routes_by_number_and_name.log', mode='w')
log.addHandler(fileHandler)


class TMC():
    def __init__(self, tmc, roadNumber, roadName, fc_TMCs, route_nbr_map):
        self.tmc = tmc
        self.roadNumber = str(roadNumber)
        self.roadName = roadName
        self.geom = [row[0] for row in arcpy.da.SearchCursor(fc_TMCs, 'SHAPE@', f"tmc = '{self.tmc}'")][0]
        self.firstPoint = self.get_first_point()
        self.lastPoint = self.get_last_point()
        self.midPoint = self.get_mid_point()
        self.firstQuarter = self.get_mid_point(percent=0.25)
        self.thirdQuarter = self.get_mid_point(percent=0.75)
        self.potentialRoutes_byNumber = route_nbr_map # Potential routes limited by route number
        self.potentialRoutes_byName = []
        self.routes_byNumber = Counter()
        self.routes_byName = Counter()
        self.routes_Other = Counter() # Routes that don't match name or number.  If only one and no other matches, then use this route

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

    
    def get_mid_point(self, percent=0.5):
        """ Finds the mid point of the TMC """
        try:
            mid_point = self.geom.positionAlongLine(0.5, True)
            return arcpy.PointGeometry(mid_point.firstPoint, spatial_reference=config.VIRGINIA_LAMBERT)
        except:
            return None

    
    def find_potential_routes_by_name(self, nearby_routes):
        if self.roadName is None:
            self.potentialRoutes_byName = []
            return

        potential_routes = difflib.get_close_matches(self.roadName, nearby_routes)
        
        if len(set(potential_routes)) > 1:
            potential_routes = filter(lambda rte: True if rte[7:9] == 'PR' else False, potential_routes)
        
        self.potentialRoutes_byName = list(potential_routes)

    
    def __repr__(self):
        """ Returns stats for this LinearId for logging purposes """
        return f'\n    tmc: {self.tmc}\n\
                firstPoint: {(self.firstPoint.firstPoint.X, self.firstPoint.firstPoint.Y) if self.firstPoint else None}\n\
                lastPoint: {(self.lastPoint.firstPoint.X, self.lastPoint.firstPoint.Y) if self.lastPoint else None}\n\
                midPoint: {(self.midPoint.firstPoint.X, self.midPoint.firstPoint.Y) if self.midPoint else None}\n\
                routes_byNumber: {self.routes_byNumber}\n\
                routes_byName: {self.routes_byName}\n\
                routes_Other: {self.routes_Other}\n'


def identify_routes_by_number_name(*test_tmcs, lyrLRS=None):
    """ Attempts to match TMCs to the correct RTE_NM by route number
    """
    
    print('Attempting to match TMCs to the correct RTE_NM by grouping by roadNumber')
    
    if not lyrLRS:
        print('  Creating MasterLRS layer')
        lyrLRS = arcpy.MakeFeatureLayer_management(config.OVERLAP_LRS, 'lrs')

    print('  Preparing LRS for GeoPandas')
    lrsSHP = gp.read_file(config.LRS_SHP)
    lrsSIndex = lrsSHP.sindex
    geopandas_lrs = (lrsSHP, lrsSIndex)

    with open('route_nbr_map.json','r') as file:
        roadNumber_to_RTE_NMs = json.load(file)

    print('  Preparing list of TMCs')
    if len(test_tmcs) > 0:
        tmcs = list(test_tmcs)
    else:
        sql = 'status is null' # Only run on tmcs that have not been identified yet
        tmcs = [row[0] for row in arcpy.da.SearchCursor(config.TMCs, 'tmc', sql)]

    print('  Mapping TMCs to roadNumbers')
    roadNumber_dict = {row[0]: row[1].split('-')[1] for row in arcpy.da.SearchCursor(config.TMCs, ['tmc', 'roadNumber']) if row[1] != 'None'}

    print('  Mapping TMCs to roadNames')
    roadName_dict = {row[0]: row[1] for row in arcpy.da.SearchCursor(config.TMCs, ['tmc', 'roadName']) if row[1] != 'None'}


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
            roadNumber = roadNumber_dict.get(tmc_code)
            roadName = roadName_dict.get(tmc_code)
            tmc = TMC(tmc_code, roadNumber, roadName, fc_TMCs, roadNumber_to_RTE_NMs.get(roadNumber))

            nearby_routes = []
            if tmc.firstPoint:
                nearby_routes.extend(lrs_tools.find_nearby_routes_geopandas(tmc.firstPoint, geopandas_lrs))

            if tmc.firstQuarter:
                nearby_routes.extend(lrs_tools.find_nearby_routes_geopandas(tmc.firstQuarter, geopandas_lrs))

            if tmc.midPoint:
                nearby_routes.extend(lrs_tools.find_nearby_routes_geopandas(tmc.midPoint, geopandas_lrs))

            if tmc.thirdQuarter:
                nearby_routes.extend(lrs_tools.find_nearby_routes_geopandas(tmc.thirdQuarter, geopandas_lrs))

            if tmc.lastPoint:
                nearby_routes.extend(lrs_tools.find_nearby_routes_geopandas(tmc.lastPoint, geopandas_lrs))
            
            # Find potential routes by name based on nearby_routes
            tmc.find_potential_routes_by_name(nearby_routes)

            nearby_routes_byNumber = [route for route in nearby_routes if route in tmc.potentialRoutes_byNumber] if tmc.potentialRoutes_byNumber else []
            nearby_routes_byName = [route for route in nearby_routes if route in tmc.potentialRoutes_byName] if tmc.potentialRoutes_byName else []
            tmc.routes_byNumber.update(nearby_routes_byNumber)
            tmc.routes_byName.update(nearby_routes_byName)


            tmc.routes_byNumber = lrs_tools.get_most_common(tmc.routes_byNumber) if len(tmc.routes_byNumber) > 0 else []
            if len(tmc.routes_byNumber) == 2:
                # Potentially both directions of the same route.  Try to reduce to just prime direction
                routesByNumber = list(filter(lambda rte: True if rte[0][7:9] == 'PR' or rte[0][14:16] in ('NB', 'EB') else False, tmc.routes_byNumber))
                tmc.routes_byNumber = routesByNumber if len(Counter(routesByNumber)) > 0 else []

            tmc.routes_byName = lrs_tools.get_most_common(tmc.routes_byName)  if len(tmc.routes_byName) > 0 else []
            if len(tmc.routes_byName) == 2:
                # Potentially both directions of the same route.  Try to reduce to just prime direction
                routesByName = list(filter(lambda rte: True if rte[0][7:9] == 'PR' or rte[0][14:16] in ('NB', 'EB') else False, tmc.routes_byName))
                tmc.routes_byName = routesByNumber if len(Counter(routesByName)) > 0 else []
            
            # If no suitable matches by name or number, check other nearby routes
            # If only one other route matches 3 times, then map to that route
            otherRoutes = [route for route in nearby_routes if (route not in nearby_routes_byNumber) and (route not in nearby_routes_byName)]
            tmc.routes_Other.update(otherRoutes)
            tmc.routes_Other = lrs_tools.get_most_common(tmc.routes_Other)  if len(tmc.routes_Other) > 0 else []
            
            if len(tmc.routes_Other) > 2:
                # Try to remove S routes
                otherRoutes = list(filter(lambda rte: True if rte.startswith('R-VA') else False, otherRoutes))
                tmc.routes_Other = lrs_tools.get_most_common(Counter(otherRoutes))  if len(Counter(otherRoutes)) > 0 else []
                
            
            if len(tmc.routes_Other) == 2:
                # Potentially both directions of the same route.  Try to reduce to just prime direction
                otherRoutes = list(filter(lambda rte: True if rte[7:9] == 'PR' or rte[14:16] in ('NB', 'EB') else False, otherRoutes))
                tmc.routes_Other = lrs_tools.get_most_common(Counter(otherRoutes))  if len(Counter(otherRoutes)) > 0 else []

            log.debug(tmc)

            # If exactly one route is in each category and that route appears exactly 3 times,
            # then map to that route.  The priority for checking will be in this order:
            #    - Match by number
            #    - Match by name
            #    - Other match
            if len(tmc.routes_byNumber) == 1 and tmc.routes_byNumber[0][1] >= 3:
                output[tmc.tmc] = tmc.routes_byNumber[0][0]
            elif len(tmc.routes_byName) == 1 and tmc.routes_byName[0][1] >= 3:
                output[tmc.tmc] = tmc.routes_byName[0][0]
            elif len(tmc.routes_Other) == 1 and tmc.routes_Other[0][1] >= 3:
                output[tmc.tmc] = tmc.routes_Other[0][0]
            
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
                    begin_msr, end_msr = lrs_tools.get_line_mp(geom, config.OVERLAP_LRS, rte_nm)

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
                    row[1] = 'Complete (30)'
                    cur.updateRow(row)
                except Exception as e:
                    log.debug(f'Error updating {row[-2]} in TMCs table')
                    log.debug(e)
                    row[1] = 'Error (30)'
                    cur.updateRow(row)


            
            
            lrs_tools.print_progress_bar(i, row_count, f'Locating MPs for matched routes')


if __name__ == '__main__':
    print('\nIdentifying routes by number and name')
    identify_routes_by_number_name()