import arcpy
import lrs_tools
import config
import json
from collections import Counter
import pandas as pd
import logging
import traceback
from datetime import datetime
import geopandas as gp

""" All of the straight-forward TMCs have already been matched in the previous steps.
The remainder falls into three main categories:
    1 - TMCs that span multiple jurisdictions and, therefore, more than one LRS route
    2 - TMCs in areas where the roads are too complex to identify with the simple techinques
    3 - Ramps

This script will attempt to match routes using a more detailed and time consuming approach.
    1 - Points are identified every 10 meters along the input TMC
    2 - For each point, the nearby routes are identified
    3 - The nearby routes are counted and routes that most likely participate in the TMC are
        identified.  Only routes that create a continuous segment (eg they each intersect at
        least one of the others in a logical order) are included
    4 - The events are flipped and QC'd as in previous steps.  Any remaining TMCs will either
        need to be manually matched to the LRS or they may not exist in the LRS.
"""

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG) # Set the debug level here
fileHandler = logging.FileHandler('logs\\45_identify_routes_detailed.log', mode='w')
log.addHandler(fileHandler)





class TMC():
    def __init__(self, tmc_id):
        self.tmc = str(tmc_id)
        self.tmc_geom = [row[0] for row in arcpy.da.SearchCursor(config.TMCs, 'SHAPE@', f"tmc = '{self.tmc}'")][0]
        self.points = lrs_tools.get_points_along_line(self.tmc_geom, 30)  # Points along line every 30m used to identify nearby routes
        self.first_route = None  # The most common route for the first 3 points
        self.last_route = None  # The most common route for the last 3 points
        self.routes = Counter()
        self.mapped_routes = []  # Route objects that participate in this tmc that will be turned into event records


    def __repr__(self):
        """ Returns stats for this LinearId for logging purposes """
        return f'\n    linearID: {self.linearId}\n    firstPoint: {(self.firstPoint.firstPoint.X, self.firstPoint.firstPoint.Y) if self.firstPoint else None}\n    lastPoint: {(self.lastPoint.firstPoint.X, self.lastPoint.firstPoint.Y) if self.lastPoint else None}\n    midPoint: {(self.midPoint.firstPoint.X, self.midPoint.firstPoint.Y) if self.midPoint else None}\n    routes: {self.routes}\n'


class Route():
    def __init__(self, tmc_id, rte_nm, begin_point=None, end_point=None):
        self.tmc = tmc_id
        self.rte_nm = rte_nm
        self.begin_point = begin_point
        self.end_point = end_point
        self.begin_msr = None
        self.end_msr = None

    
    def locate_on_lrs(self, lyrLRS, lyrIntersections):
        self.begin_msr = lrs_tools.get_point_mp(self.begin_point, lyrLRS, self.rte_nm, lyrIntersections)
        self.end_msr = lrs_tools.get_point_mp(self.end_point, lyrLRS, self.rte_nm, lyrIntersections)

    def __repr__(self):
        return f'<Route\trte_nm: {self.rte_nm}\t\t\tbegin_point: {(self.begin_point.firstPoint.X, self.begin_point.firstPoint.Y) if self.begin_point else None}\tend_point: {(self.end_point.firstPoint.X, self.end_point.firstPoint.Y) if self.end_point else None}>'


def identify_routes_detailed(*test_TMCs, lyrLRS=None, lyrIntersections=None):
    """ Attempts to match TMCs to the correct RTE_NM(s) 
    
        Inputs:
            test_linearIds - optional tmc values for testing.  If none,
                then this function will be applied to all TMCs with a
                null value in the Status field.
            lyrLRS - A feature layer of the master LRS.  Passing it as a
                parameter may save time, but it will be created if it does
                not exist yet.
            lyrIntersections - A feature layer of the intersections.  Passing it as a
                parameter may save time, but it will be created if it does
                not exist yet.
    """
        
    if not lyrLRS:
        print('  Creating MasterLRS layer')
        lyrLRS = arcpy.MakeFeatureLayer_management(config.MASTER_LRS, 'lrs').getOutput(0)
    
    print('  Building LRS Geometry Dictionary')
    lrs_geom_dict = {row[0]:row[1] for row in arcpy.da.SearchCursor(lyrLRS, ['RTE_NM', 'SHAPE@'])}

    print('  Preparing LRS for GeoPandas')
    lrsSHP = gp.read_file(config.LRS_SHP)
    lrsSIndex = lrsSHP.sindex
    geopandas_lrs = (lrsSHP, lrsSIndex)
    
    if not lyrIntersections:
        print('  Creating Intersections layer')
        lyrIntersections = arcpy.MakeFeatureLayer_management(config.INTERSECTIONS, 'intersections').getOutput(0)

    # These serve no purpose other than to fix a stuid bug in arcpy that prevents
    # select by attributes and select by location from working on these layers.
    # The only fix I've found is to hit them both with a search cursor first.
    print('  Building Intersection Geometry Dictionary')
    intersections_geom_dict = {row[0]:row[1] for row in arcpy.da.SearchCursor(lyrIntersections, ['OBJECTID', 'SHAPE@'])}


    print('  Preparing list of tmcs')
    if len(test_TMCs) > 0:
        tmcs = list(test_TMCs)
        if len(tmcs) == 1:
            tmcs.append('') # To fix bug when creating valid sql statement when only one Id exists

    else:
        tmcs = [row[0] for row in arcpy.da.SearchCursor(config.TMCs, 'tmc', 'status is null')]


    try:
        with open('data\\rte_int_dict.json','r') as file:
            rte_int_dict = json.load(file)
    except:
        print('\n  Error loading rte_int_dict.json.  Continuing without it (more time consuming)')
        rte_int_dict = None
    start = datetime.now()

    # Identify RTE_NMs by tmc
    total = len(tmcs) - 1
    output = []
    for i, tmc_id in enumerate(tmcs):
        try:
            log.debug(f'\n\nTMC: {tmc_id}')
            tmc = TMC(tmc_id)

            # Identify nearby routes for each 15m along the tmc
            nearby_routes = []
            first_routes = Counter() # Used to identify the first route along this TMC
            last_routes = Counter()
            for pt, point in enumerate(tmc.points):
                routes = lrs_tools.find_nearby_routes_geopandas(point, geopandas_lrs, tmc.tmc_geom)
                nearby_routes.extend(routes)
                if pt < 3:
                    for route in routes:
                        first_routes[route] += 1
                if pt > len(tmc.points) - 3:
                    for route in routes:
                        last_routes[route] += 1
                        
            tmc.routes.update(nearby_routes)
            all_potential_routes = [route for route in tmc.routes if tmc.routes[route] > 1]
            log.debug(f'    All Nearby Routes: {nearby_routes}')
            log.debug(f'    {len(all_potential_routes)} potential routes found:')
            log.debug(f'        Potential Routes: {all_potential_routes}')
            

            # Identify first route
            tmc.first_route = lrs_tools.get_most_common(first_routes)[0][0]
            tmc.mapped_routes.append(Route(
                                        tmc_id=tmc_id, 
                                        rte_nm=tmc.first_route,
                                        begin_point=arcpy.PointGeometry(tmc.tmc_geom.firstPoint, 
                                                                        spatial_reference=config.VIRGINIA_LAMBERT)
                                        )
                                    )
            # Identify last route
            tmc.last_route = lrs_tools.get_most_common(last_routes)[0][0]

            log.debug(f'    {tmc.first_route} identified as the first route')
            log.debug(f'    {tmc.last_route} identified as the last route')

            # All potential routes must share an intersection with 2 other potential routes, except begin and end routes
            log.debug('        Finding common intersection counts for each potential route:')
            potential_routes = []
            for route in all_potential_routes:
                common_intersection_count = 0
                for rte in all_potential_routes:
                    if route == rte:
                        continue
                    common_intersection = lrs_tools.find_common_intersection(route, rte, lyrLRS, lyrIntersections, tmc, rte_int_dict)
                    if common_intersection:
                        common_intersection_count += 1
                
                log.debug(f'            {route}: {common_intersection_count} common intersections')
                if common_intersection_count >=2:
                    potential_routes.append(route)
            

            log.debug(f'        Potential Routes: {potential_routes}')
            if tmc.first_route in potential_routes:
                potential_routes.remove(tmc.first_route)
            if tmc.last_route not in potential_routes:
                potential_routes.append(tmc.last_route)


            current_route = tmc.mapped_routes[0]  # The route that will be used to find the next route in the sequence
            while True:
                for route in potential_routes:
                    common_intersection = lrs_tools.find_common_intersection(current_route.rte_nm, route, lyrLRS, lyrIntersections, tmc, rte_int_dict)
                    if common_intersection:
                        common_intersection_geom = intersections_geom_dict[common_intersection]
                        current_route.end_point = common_intersection_geom
                        next_route = Route(tmc_id=tmc_id, rte_nm=route, begin_point=common_intersection_geom)
                        
                        tmc.mapped_routes.append(next_route)

                        log.debug(f'    {next_route.rte_nm} identified as the next route')
                        potential_routes.remove(route)
                        log.debug(f'        Potential Routes: {potential_routes}')
                        break
                    

                if current_route == tmc.mapped_routes[-1]:
                    break

                current_route = tmc.mapped_routes[-1]

            if tmc.mapped_routes[-1].end_point == None:
                tmc.mapped_routes[-1].end_point = arcpy.PointGeometry(tmc.tmc_geom.lastPoint, spatial_reference=config.VIRGINIA_LAMBERT)




            log.debug(f'\n  Nearby Routes: {Counter(nearby_routes)}')
            log.debug(f'  Potential Routes: {potential_routes}')
            log.debug(f'  First Routes: {first_routes}')
            log.debug(f'  Mapped Routes:')
            for route in tmc.mapped_routes:
                route.locate_on_lrs(lyrLRS, lyrIntersections)
                if route.begin_msr == route.end_msr:
                    continue

                output_event = {
                    'tmc': tmc_id,
                    'rte_nm': route.rte_nm,
                    'begin_msr': route.begin_msr,
                    'end_msr': route.end_msr,
                    'status': 'Complete (45)'
                }
                log.debug(route)
                output.append(output_event)


        except Exception as e:
            log.debug(f'\nError on {tmc_id}')
            log.debug(e)
            log.debug(traceback.format_exc())

        lrs_tools.print_progress_bar(i, total, 'Identifying RTE_NMs by tmc (detailed)')

    print('\n')

    # For rte_nms that were successfully identified, find the begin_msr and end_msr values
    # Update status and LRS fields in TMCs layer
    completeIds = list(set([tmc['tmc'] for tmc in output]))
    if len(completeIds) == 1:
        completeIds.append('') # To fix bug when creating valid sql statement when only one Id exists

    row_count = len(list(i for i in arcpy.da.SearchCursor(config.TMCs, 'tmc', f"tmc in {tuple(completeIds)}")))

    df = pd.DataFrame(output)
    df.to_csv('data//_45_output.csv', index=False)
    
    with arcpy.da.UpdateCursor(config.TMCs, ['tmc', 'status', 'rte_nm'], f"tmc in {tuple(completeIds)}") as cur:
        for i, row in enumerate(cur):
            if row[0] in completeIds:
                try:
                    row[1] = 'Complete (45)'
                    cur.updateRow(row)
                except Exception as e:
                    log.debug(f'Error updating {row[0]} in TMCs table')
                    log.debug(e)

           
            
            lrs_tools.print_progress_bar(i, row_count, 'Locating MPs for matched routes')
    
    
    end = datetime.now()
    print(f'\n  Run time: {end - start}')
    

if __name__ == '__main__':
    print('\nIdentifying remaining routes - detailed')
    identify_routes_detailed()
