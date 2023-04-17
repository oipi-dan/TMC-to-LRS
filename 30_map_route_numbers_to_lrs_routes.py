import config
import arcpy
import json

def map_route_numbers_to_lrs_routes():
    TMCs = config.TMCs
    LRS = config.OVERLAP_LRS

    road_numbers = list(set([row[0] for row in arcpy.da.SearchCursor(TMCs, 'roadNumber')]))
    number_dict = {}
    for road in road_numbers:
        if road != 'None':
            road_number = road.split('-')[1]
            number_dict[road_number] = []

    lrs_rte_nbr_dict = {}
    with arcpy.da.SearchCursor(config.OVERLAP_LRS, ['rte_nbr', 'rte_nm'], "RTE_NBR IS NOT NULL") as cur:
        for row in cur:
            if str(row[0]) in lrs_rte_nbr_dict:
                lrs_rte_nbr_dict[str(row[0])].append(row[1])
            else:
                lrs_rte_nbr_dict[str(row[0])] = [row[1]]

    # Add rte_nms by number to number_dict
    for nbr in number_dict:
        if nbr in lrs_rte_nbr_dict:
            number_dict[nbr] = lrs_rte_nbr_dict[nbr]

    # Remove duplicate values
    for nbr in number_dict:
        nbr_set = list(set(number_dict[nbr]))
        number_dict[nbr] = nbr_set

    with open('route_nbr_map.json','w') as file:
        json.dump(number_dict, file)
    

    


if __name__ == '__main__':
    print('\nMapping route numbers to lrs routes')
    map_route_numbers_to_lrs_routes()