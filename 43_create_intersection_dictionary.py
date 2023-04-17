""" This script will create a dictionary using RTE_NM as key and a list of
    intersections by OBJECTID as values.  The dictionary will be saved
    as a json file to be loaded in 45_identify_routes_detailed.py.  This
    only needs to be run once unless the LRS version is updated. """

import arcpy
import config
import json
import lrs_tools


# Create layers
print('  Creating LRS layer')
lyrLRS = arcpy.MakeFeatureLayer_management(config.MASTER_LRS, 'lrs').getOutput(0)

print('  Creating Intersections layer')
lyrIntersections = arcpy.MakeFeatureLayer_management(config.INTERSECTIONS, 'intersections').getOutput(0)

print('  Creating TMC layer')
lyrTMC = arcpy.MakeFeatureLayer_management(config.TMCs, 'tmcs').getOutput(0)

print('  Get list of RTE_NMs near TMCs')
arcpy.SelectLayerByLocation_management(lyrLRS, 'WITHIN_A_DISTANCE', lyrTMC, '10 METERS', 'NEW_SELECTION')
rte_nms = tuple([row[0] for row in arcpy.da.SearchCursor(lyrLRS, 'RTE_NM')])
sql = f"RTE_NM IN {rte_nms}"


# Fixes bug where arcpy won't recognize this layer for selection unless its referenced elsewhere first
with arcpy.da.SearchCursor(lyrIntersections, 'SHAPE@') as cur:
    for row in cur:
        break

# Create and load route intersection dictionary
def get_ints(geom, intersections):
    arcpy.management.SelectLayerByAttribute(intersections,'CLEAR_SELECTION')
    arcpy.SelectLayerByLocation_management(intersections, 'WITHIN_A_DISTANCE', geom, '5 METERS', 'NEW_SELECTION')

    return list(intersections.getSelectionSet())

total = len([row for row in arcpy.da.SearchCursor(config.MASTER_LRS, 'RTE_NM', sql)])
rte_int_dict = {}
with arcpy.da.SearchCursor(config.MASTER_LRS, ['RTE_NM','SHAPE@'], sql) as cur:
    for i, row in enumerate(cur):
        rte_nm, geom = row
        ints = get_ints(geom, lyrIntersections)
        rte_int_dict[rte_nm] = ints

        lrs_tools.print_progress_bar(i+1, total, 'Building rte_int_dict')

with open('data//rte_int_dict.json','w') as file:
    json.dump(rte_int_dict, file)