import arcpy, pandas as pd
import logging
import json
import config

outputEvents = {}

countFlipped = 0
countNotFlipped = 0
countError = 0
errorList = []

LRS_RTE_ERRORS__REVERSED_MP = [
    'R-VA000SC06624NB'
]

try:
    with open('LRS_RTE_ERRORS__REVERSED_MP.json', 'r') as file:
        LRS_RTE_ERRORS__REVERSED_MP += json.load(file)
except Exception as e:
    print(e)


log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG) # Set the debug level here
fileHandler = logging.FileHandler(r'logs/flipRoutes.log', mode='w')
log.addHandler(fileHandler)

def add_to_event_table(objectId, id, needsFlip, rte_nm, begin_mp, end_mp):
    event = {
        'tmc': id,
        'flipped': needsFlip,
        'rte_nm': rte_nm,
        'begin_msr': begin_mp,
        'end_msr': end_mp
    }

    outputEvents[objectId] = event


def get_msr(inputPolyline, lrs, rte_nm):
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
        RouteGeom = None
        
        try:
            RouteGeom = lrs[rte_nm]
        except:
            log.debug(f'  Route "{rte_nm}" not found')
            return None, None

        if not RouteGeom:
            log.debug(f'  Route "{rte_nm}" not found')
            return None, None

        

        def get_mp_from_point(route, point):
            """ Returns the m-value along the input route geometry
                given an input point geometry """

            # Check for multipart geometry.  If multipart, find closest part to
            # ensure that the correct MP is returned
            if route.isMultipart:
                # Get list of parts
                parts = [arcpy.Polyline(route[i], has_m=True) for i in range(route.partCount)]

                # Get distances from inputPolyline's mid-point to each route part
                partDists = {point.distanceTo(part):part for part in parts}

                # Replace RouteGeom with closest polyline part
                route = partDists[min(partDists)]

            rteMeasure = route.measureOnLine(point)
            rtePosition = route.positionAlongLine(rteMeasure)
            mp = rtePosition.firstPoint.M
            return mp

        beginPt = arcpy.PointGeometry(inputPolyline.firstPoint)
        beginMP = get_mp_from_point(RouteGeom, beginPt)

        endPt = arcpy.PointGeometry(inputPolyline.lastPoint)
        endMP = get_mp_from_point(RouteGeom, endPt)

        return round(beginMP, 3), round(endMP, 3)

    except Exception as e:
        print(e)
        return None, None





def run_flip_routes(step_name, sql=None, feature_class=None):
    # If feature_class=None, run on config.TMCs.  Otherwise run on feature_class
    if not feature_class:
        feature_class = config.TMCs
    else:
        fields = [field.name for field in arcpy.ListFields(feature_class)]
        if 'status' not in fields:
            arcpy.AddField_management(feature_class, 'status', 'TEXT')
    global countFlipped
    global countNotFlipped
    global countError
    global errorList
    global outputEvents

    outputEvents = {}

    fileHandler = logging.FileHandler(f'logs/flipRoutes.log', mode='w')
    log.addHandler(fileHandler)

    # Create a dictionary of opposite direction routes
    print('  Creating opposite direction route dict')
    inputRoutes = list(set([row[0] for row in arcpy.da.SearchCursor(feature_class, 'rte_nm', sql)]))

    if len(inputRoutes) == 1:
        inputRoutes.append("")

    oppRteDict = {}
    
    with arcpy.da.SearchCursor(config.OVERLAP_LRS, ['RTE_NM', 'RTE_OPPOSITE_DIRECTION_RTE_NM']) as cur:
        for rte_nm, opp_rte_nm in cur:
            if rte_nm in inputRoutes:
                oppRteDict[rte_nm] = opp_rte_nm

    # Create dictionary for LRS Geometries to save time on search cursors
    print('  Creating LRS geometry dict')
    inputRoutesAndOpposites = inputRoutes.copy()
    inputRoutesAndOpposites.extend(oppRteDict.values())
    LRSGeomDict = {row[0]:row[1] for row in arcpy.da.SearchCursor(config.OVERLAP_LRS, ['RTE_NM','SHAPE@']) if row[0] in inputRoutesAndOpposites}

    print('  Flipping Routes...')

    # For each record in input layer, if the begin_mp > end_mp, move to the opposite route.  Otherwise, keep the same
    with arcpy.da.SearchCursor(feature_class, ['tmc', 'rte_nm', 'begin_msr', 'end_msr', 'SHAPE@', 'OID@'], sql) as cur:
        for id, rte_nm, begin_mp, end_mp, geom, objectId in cur:
            log.debug(f'\nProcessing {id}')
            try:
                needsFlip = False
                if rte_nm not in oppRteDict.keys():
                    log.debug(f"  '{rte_nm}' does not have an opposite route and doesn't need to be flipped")
                    add_to_event_table(objectId, id, needsFlip, rte_nm, begin_mp, end_mp)
                    countNotFlipped += 1

                    continue

                if rte_nm.startswith('S-VA') and (begin_mp < end_mp or begin_mp == end_mp) and (rte_nm[7:9] == 'PR'):
                    if rte_nm in LRS_RTE_ERRORS__REVERSED_MP:
                        log.debug(f"  rte_nm '{rte_nm}' is digitized backwards and needs to be flipped")
                        needsFlip = True
                    else:
                        add_to_event_table(objectId, id, needsFlip, rte_nm, begin_mp, end_mp)
                        countNotFlipped += 1
                        log.debug(f"  rte_nm '{rte_nm}' is a PR with ascending MP and does not need to be flipped")

                        continue

                if rte_nm.startswith('S-VA') and (begin_mp > end_mp or begin_mp == end_mp) and (rte_nm[7:9] == 'NP'):
                    if rte_nm in LRS_RTE_ERRORS__REVERSED_MP:
                        log.debug(f"  rte_nm '{rte_nm}' is digitized backwards and needs to be flipped")
                        needsFlip = True
                    else:
                        add_to_event_table(objectId, id, needsFlip, rte_nm, begin_mp, end_mp)
                        countNotFlipped += 1
                        log.debug(f"  rte_nm '{rte_nm}' is a NP with descending MP and does not need to be flipped")

                        continue


                if rte_nm in LRS_RTE_ERRORS__REVERSED_MP and needsFlip == False:
                    log.debug(f"  rte_nm '{rte_nm}' is digitized backwards and does not needs to be flipped")
                    add_to_event_table(objectId, id, needsFlip, rte_nm, begin_mp, end_mp)
                    countNotFlipped += 1

                    continue

                if 'RMP' in rte_nm:
                    add_to_event_table(objectId, id, needsFlip, rte_nm, begin_mp, end_mp)
                    countNotFlipped += 1
                    log.debug(f"  rte_nm '{rte_nm}' is a ramp and does not need to be flipped")

                    continue

                if rte_nm.startswith('R-VA') and ('PA' in rte_nm):
                    add_to_event_table(objectId, id, needsFlip, rte_nm, begin_mp, end_mp)
                    countNotFlipped += 1
                    log.debug(f"  rte_nm '{rte_nm}' is a PA route and does not need to be flipped")

                    continue

                if rte_nm.startswith('R-VA') and (begin_mp < end_mp or begin_mp == end_mp) and ('NB' in rte_nm or 'EB' in rte_nm):
                    add_to_event_table(objectId, id, needsFlip, rte_nm, begin_mp, end_mp)
                    countNotFlipped += 1
                    log.debug(f"  rte_nm '{rte_nm}' does not need to be flipped")

                    continue

                if rte_nm.startswith('R-VA') and (begin_mp > end_mp or begin_mp == end_mp) and ('SB' in rte_nm or 'WB' in rte_nm):
                    add_to_event_table(objectId, id, needsFlip, rte_nm, begin_mp, end_mp)
                    countNotFlipped += 1
                    log.debug(f"  rte_nm '{rte_nm}' does not need to be flipped")

                    continue


                log.debug(f"  rte_nm '{rte_nm}' needs to be flipped - begin_msr = {begin_mp}  end_msr = {end_mp}")
                needsFlip = True
                new_rte_nm = oppRteDict[rte_nm]
                log.debug(f"    New rte_nm: '{new_rte_nm}'")
                new_begin_mp, new_end_mp = get_msr(geom, LRSGeomDict, new_rte_nm)
                log.debug(f"    New begin and end msr: {new_begin_mp}, {new_end_mp}")
                add_to_event_table(objectId, id, needsFlip, new_rte_nm, new_begin_mp, new_end_mp)
                countFlipped += 1

            except Exception as e:
                log.debug(e)
                log.debug(f'  Error processing {id}')
                add_to_event_table(objectId, id, needsFlip, rte_nm, begin_mp, end_mp)
                countError += 1
                errorList.append(id)

    totalSegments = sum([countNotFlipped, countFlipped, countError])
    log.debug(f'Flip Complete\n-------------')
    log.debug(f'    Total Segments: {totalSegments}')
    log.debug(f'        Not Flipped: {countNotFlipped}, {round(countNotFlipped/totalSegments*100)}%')
    log.debug(f'        Flipped: {countFlipped}, {round(countFlipped/totalSegments*100)}%')
    log.debug(f'        Errors: {countError}, {round(countError/totalSegments*100)}%')
    log.debug(f'        Error List: {errorList}')

    print('Updating status and LRS values')
    with arcpy.da.UpdateCursor(feature_class, ['OID@', 'rte_nm', 'begin_msr', 'end_msr', 'status']) as cur:
        for row in cur:
            if row[0] in outputEvents and outputEvents[row[0]]['flipped'] == True:
                oid = row[0]
                if outputEvents[oid]['rte_nm'] == None:
                    continue
                row[1] = outputEvents[oid]['rte_nm']
                row[2] = outputEvents[oid]['begin_msr']
                row[3] = outputEvents[oid]['end_msr']
                if not row[4]:
                    row[4] = step_name
                else:
                    row[4] = row[4] + step_name
                
                cur.updateRow(row)


if __name__ == '__main__':
    sql = "linearId = '33'"
    run_flip_routes('test flip', sql)