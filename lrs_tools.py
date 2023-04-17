import arcpy
import logging
import sys
import geopandas as gp
from shapely.geometry import Point

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG) # Set the debug level here
fileHandler = logging.FileHandler(f'logs\lrs_tools.log', mode='w')
log.addHandler(fileHandler)





def print_progress_bar(index, total, label):
    n_bar = 50  # Progress bar width
    progress = index / total
    sys.stdout.write('\r')
    sys.stdout.write(f"  [{'=' * int(n_bar * progress):{n_bar}s}] {int(100 * progress)}%  {label} ({index} of {total})")
    sys.stdout.flush()


def find_nearby_routes(point, lrs, segment_geometry=None, searchDistance="9 METERS", rerun=False):
    """ Given an input point, will return a list of all routes within the searchDistance """

    # Short routes require a short search distance in order to find anything
    if segment_geometry and segment_geometry.getLength() < 18:
        searchDistance = f"{segment_geometry.getLength() / 4} METERS"
    
    if rerun == True:
        searchDistance = "20 METERS"

    routes = []
    arcpy.management.SelectLayerByLocation(lrs, 'WITHIN_A_DISTANCE', point, searchDistance)
    with arcpy.da.SearchCursor(lrs, 'RTE_NM') as cur:
        for row in cur:
            routes.append(row[0])

    return routes


def find_nearby_routes_geopandas(point, geopandas_lrs, segment_geometry=None, searchDistance=9, rerun=False):
    """ Given an input point, will return a list of all routes within the searchDistance """

    # Unpack LRS GeoDataFrame and Spatial Index from geopandas_lrs
    lrsSHP, lrsSIndex = geopandas_lrs

    # Short routes require a short search distance in order to find anything
    if segment_geometry and segment_geometry.getLength() < 18:
        searchDistance = f"{segment_geometry.getLength() / 4} METERS"
    
    if rerun == True:
        searchDistance = "20 METERS"

    # Convert input point to shapely point
    point = Point(point.firstPoint.X, point.firstPoint.Y)

    # Locate nearby routes
    pointBuffer = point.buffer(searchDistance)
    possible_routes_index = list(lrsSIndex.query(pointBuffer))
    possible_routes = lrsSHP.iloc[possible_routes_index]
    routes = possible_routes[possible_routes.intersects(pointBuffer)]["RTE_NM"].tolist()

    # routes = lrsSHP[lrsSHP.intersects(pointBuffer)]["RTE_NM"].tolist()

    return routes


def get_point_mp(inputPointGeometry, lrs, rte_nm, lyrIntersections):
    """ Locates the MP value of an input point along the LRS
        ** The spatial reference of the input must match the spatial reference
           of the lrs! **
    Input:
        inputPointGeometry - an arcpy PointGeometry object
        lrs - a reference to the lrs layer
        rte_nm - the lrs rte_nm that the polyline will be placed on
    Output:
        mp - the m-value of the input point
    """
    try:
        # Get the geometry for the LRS route
        arcpy.management.SelectLayerByAttribute(lrs,'CLEAR_SELECTION')

        with arcpy.da.SearchCursor(lrs, "SHAPE@", "RTE_NM = '{}'".format(rte_nm)) as cur:
            for row in cur:
                RouteGeom = row[0]

        # Check for route multipart geometry.  If multipart, find closest part to
        # ensure that the correct MP is returned
        if RouteGeom.isMultipart:
            # Get list of parts
            parts = [arcpy.Polyline(RouteGeom[i], has_m=True) for i in range(RouteGeom.partCount)]

            # Get distances from inputPolyline's mid-point to each route part
            partDists = {inputPointGeometry.distanceTo(part):part for part in parts}

            # Replace RouteGeom with closest polyline part
            RouteGeom = partDists[min(partDists)]


        rteMeasure = RouteGeom.measureOnLine(inputPointGeometry)
        rtePosition = RouteGeom.positionAlongLine(rteMeasure)

        rtePosition, moved = move_to_closest_int(rtePosition, lyrIntersections)

        if moved:
            rteMeasure = RouteGeom.measureOnLine(rtePosition)
            rtePosition = RouteGeom.positionAlongLine(rteMeasure)

        mp = rtePosition.firstPoint.M
        return round(mp, 3)
    
    except Exception as e:
        print(e)
        print(rte_nm)
        return None


def get_points_along_line(geom, d=50, rerun=False):
    """ Find points every d distance along the input polyline geometry and
        return them as a list """
    
    segLen = geom.getLength('GEODESIC','METERS')
    log.debug(f'      segLen: {segLen}')

    # For short segments, reduce m to increase the number of test points
    if segLen <= 150:
        if rerun == False:
            d = segLen / 4
            log.debug(f'      Reduced d to {d}')
        else:            
            d = segLen / 5
            log.debug(f'      Reduced d to {d}')
    points = []

    m = 0
    while m <= segLen:
        points.append(geom.positionAlongLine(m))
        m += d

    for point in points:
        log.debug(f'        {point.firstPoint.X}, {point.firstPoint.Y}')
    
    return points


def move_to_closest_int(geom, lyrIntersections, testDistance=10):
    """ Returns input testGeom moved to the nearest intersection """
    log.debug(f"        move_to_closest_int input geom: {geom.firstPoint.X}, {geom.firstPoint.Y}")

    arcpy.SelectLayerByLocation_management(lyrIntersections, "INTERSECT", geom, testDistance)
    intersections = [row[0] for row in arcpy.da.SearchCursor(lyrIntersections, "SHAPE@")]
    if len(intersections) == 0:
        log.debug(f"        No intersections within {testDistance}m distance.  Returning testGeom.")
        moved = False
        return geom, moved
    
    if len(intersections) == 1:
        log.debug(f"        One intersection within {testDistance}m distance.  Returning intersection at {intersections[0].firstPoint.X}, {intersections[0].firstPoint.Y}.")
        moved = True
        return intersections[0].firstPoint, moved

    log.debug(f"        {len(intersections)} intersections found.  Returning closest intersection.")
    closestInt = intersections[0]
    closestIntDist = testDistance
    for intersection in intersections:
        dist = geom.distanceTo(intersection)
        if dist < closestIntDist:
            closestInt = intersection
            closestIntDist = dist
    
    log.debug(f"        Returning intersection at {closestInt.firstPoint.X}, {closestInt.firstPoint.Y}")
    moved = True
    return closestInt.firstPoint, moved


def get_most_common(c):
    """ Returns a list of the most common values found in the input counter c """
    freq_list = list(c.values())
    max_cnt = max(freq_list)
    total = freq_list.count(max_cnt)
    most_commons = c.most_common(total)
    
    return most_commons


def get_line_mp(inputPolyline, lrs, rte_nm, RouteGeom=None):
    """ Locates the begin and end MP values of an input line along the LRS
        ** The spatial reference of the input must match the spatial reference
           of the lrs! **
    Input:
        inputPolyline - an arcpy Polyline object
        lrs - a reference to the lrs layer
        rte_nm - the lrs rte_nm that the polyline will be placed on
    Output:
        (beginMP, endMP)
    """

    try:
        # Get the geometry for the LRS route
        with arcpy.da.SearchCursor(lrs, "SHAPE@", "RTE_NM = '{}'".format(rte_nm)) as cur:
            for row in cur:
                RouteGeom = row[0]

        if not RouteGeom:
            return None, None

        # Check for multipart geometry.  If multipart, find closest part to
        # ensure that the correct MP is returned
        # if RouteGeom.isMultipart:
        #     # Get list of parts
        #     parts = [arcpy.Polyline(RouteGeom[i], has_m=True) for i in range(RouteGeom.partCount)]

        #     # Get input polyline midpoint
        #     midPoint = inputPolyline.positionAlongLine(0.5, use_percentage=True)

        #     # Get distances from inputPolyline's mid-point to each route part
        #     partDists = {midPoint.distanceTo(part):part for part in parts}

        #     # Replace RouteGeom with closest polyline part
        #     RouteGeom = partDists[min(partDists)]

        def get_mp_from_point(route, point):
            """ Returns the m-value along the input route geometry
                given an input point geometry """
            rteMeasure = route.measureOnLine(point)
            rtePosition = route.positionAlongLine(rteMeasure)
            mp = rtePosition.firstPoint.M
            return mp

        beginPt = inputPolyline.firstPoint
        beginMP = get_mp_from_point(RouteGeom, beginPt)

        endPt = inputPolyline.lastPoint
        endMP = get_mp_from_point(RouteGeom, endPt)

        return round(beginMP, 3), round(endMP, 3)

    except Exception as e:
        return None, None


def find_common_intersection(rteA, rteB, lrs, intersections, TMCSeg, intDict=None, commonIntsUsed=[]):
    """ Given two rte_nms, this will return the intersection objectID if the two
        routes share a single intersection 
        
        inputs:
            rteA - RTE_NM for the first route to compare
            rteB - RTE_NM for the second route to compare
            lrs - reference to a layer object for the lrs
            intersections - reference to a layer object for the intersections
            TMCSeg - a copy of the TMC object
            intDict - a dictionary containing a list of intersection OBJECTIDs for each RTE_NM.  Providing
                this ahead of time will save time by limiting search cursor useage
            commonIntsUsed - I forget why I made this.  Whoops!  But if an intersection is provided in this
                list, it won't be considered when finding common intersections
        """

    def get_ints(rte_nm, lrs, intersections):
        if intDict and rte_nm in intDict:
            return intDict[rte_nm]

        # If no intDict or rte_nm not found.  This is significanly more time consuming
        arcpy.management.SelectLayerByAttribute(lrs,'CLEAR_SELECTION')
        arcpy.management.SelectLayerByAttribute(intersections,'CLEAR_SELECTION')

        geom = [row[0] for row in arcpy.da.SearchCursor(lrs, 'SHAPE@', f"RTE_NM = '{rte_nm}'")][0]

        arcpy.SelectLayerByLocation_management(intersections, 'WITHIN_A_DISTANCE', geom, '5 METERS', 'NEW_SELECTION')


        return list(intersections.getSelectionSet())
    try:
        rteAInts = get_ints(rteA, lrs, intersections)
        rteBInts = get_ints(rteB, lrs, intersections)

        commonInts = [rte for rte in rteAInts if rte in rteBInts]

        # Remove int as an option if it's already been used
        if len(commonIntsUsed) != 0:
            commonInts = [int for int in commonInts if int not in commonIntsUsed]

        if len(commonInts) == 1:
            log.debug(f'        One common intersection found: {commonInts}\n')
            return commonInts[0]

        if len(commonInts) > 1:
            log.debug(f'        {len(commonInts)} common intersections found: {commonInts}\n')
            # Attempt to narrow down intersections to one
            log.debug(f'        Selecting only nearby common intersections')
            arcpy.management.SelectLayerByAttribute(intersections,'CLEAR_SELECTION')
            arcpy.SelectLayerByLocation_management(intersections, "INTERSECT", TMCSeg.tmc_geom, "10 METERS")
            nearbyInts = intersections.getSelectionSet()
            commonInts2 = [int for int in nearbyInts if int in commonInts]
            if len(commonInts2) == 1:
                log.debug(f'        {len(commonInts2)} nearby common intersection found.  Returning {commonInts2[0]}')
                return commonInts2[0]

            if len(commonInts2) == 0:
                log.debug(f'        {len(commonInts2)} nearby common intersections found.  Returning None and hoping for the best')
                return None

            log.debug(f'        {len(commonInts2)} nearby common intersections found.  Returning int closest to end point and hoping for the best')
            closestInt = commonInts[0]
            closestIntDist = None
            for intersection in commonInts:
                intGeom = [row[0] for row in arcpy.da.SearchCursor(intersections,'SHAPE@',f'OBJECTID = {intersection}')][0]
                TMC_end_point = arcpy.PointGeometry(TMCSeg.tmc_geom.lastPoint,arcpy.SpatialReference(3969))
                dist = TMC_end_point.distanceTo(intGeom)
                if closestIntDist is None:
                    closestIntDist = dist
                    continue

                if dist < closestIntDist:
                    closestInt = intersection
                    closestIntDist = dist

            return closestInt
            
    except Exception as e:
        log.debug('        ERROR IN find_common_intersection')
        log.debug(f'       {e}')
        log.debug('        No common intersections found\n')
        return None
        

    log.debug('        No common intersections found\n')
    return None


def get_int_geometry_by_oid(oid, lyrIntersections):
    sql = f'OBJECTID = {oid}'
    return [row[0] for row in arcpy.da.SearchCursor(lyrIntersections, 'SHAPE@', sql)][0]