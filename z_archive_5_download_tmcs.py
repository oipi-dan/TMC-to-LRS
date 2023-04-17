import requests
import pandas
import os
import json
import arcpy
import config

def get_tmcs(output_csv=None):
    print('  Pulling TMC data from PDA API')
    url = f'http://pda-api.ritis.org:8080/tmc/search'
    with open('key.json') as key:
        params = json.load(key) # {"key": "key-value"}
    data = {
        'dataSourceId': 'inrix_tmc',
        # 'tmc': ['101+12345']
        'state': [
            'VA'
        ]
    }
    
    r = requests.post(url, json=data, params=params)
    df = pandas.DataFrame(json.loads(r.text))
    
    if output_csv:
        df.to_csv(output_csv, index=False)
    return df


def create_tmc_feature_class(tmc_df, gdb_path, gdb_name='input_data.gdb'):
    """ Creates a TMC feature class
    inputs:
        tmc_df - a Pandas DataFrame containing the results from the PDA API
    """
    print('  Creating feature class')
    arcpy.env.overwriteOutput = True

    # Create output gdb
    if not os.path.exists(os.path.join(gdb_path, gdb_name)):
        arcpy.CreateFileGDB_management(gdb_path, gdb_name)

    # Create output feature class
    output_gdb = os.path.join(gdb_path, gdb_name)
    arcpy.CreateFeatureclass_management(output_gdb, 'TMCs_unproj', 'Polyline', spatial_reference=config.WGS84)

    # Add required fields
    columns = tmc_df.columns
    output_fc_unproj = os.path.join(output_gdb, 'TMCs_unproj')
    for col in columns:
        if col != 'coordinates':
            arcpy.AddField_management(output_fc_unproj, col, 'TEXT')

    # Add data to fc
    newRecords = []
    def add_data(record):
        newRecord = [
            str(record['tmc']),
            str(record['type']),
            str(record['roadNumber']),
            str(record['roadName']),
            str(record['firstName']),
            str(record['funcClass']),
            str(record['county']),
            str(record['state']),
            str(record['zip']),
            str(record['direction']),
            str(record['roadClass']),
            str(record['nhsFClass']),
            str(record['startLatitude']),
            str(record['startLongitude']),
            str(record['endLatitude']),
            str(record['endLongitude']),
            str(record['length']),
            str(record['linearTmc']),
            str(record['linearId']),
            str(record['roadOrder']),
            str(record['timezoneName'])
        ]

        str_coordinates = record['coordinates'][0].split(',')
        coordinates = []
        for coord in str_coordinates:
            x, y = coord.split(' ')
            coordinates.append((float(x), float(y)))

        polyline = arcpy.Polyline(arcpy.Array([arcpy.Point(coords[0], coords[1]) for coords in coordinates]))
        newRecord.append(polyline)
        newRecords.append(newRecord)



    # Add tmcs to newRecords list
    print('  Adding data to new feature class')
    tmc_df.apply(add_data, axis=1)

    # Insert newRecords to output_fc
    fields = [
        'tmc',
        'type',
        'roadNumber',
        'roadName',
        'firstName',
        'funcClass',
        'county',
        'state',
        'zip',
        'direction',
        'roadClass',
        'nhsFClass',
        'startLatitude',
        'startLongitude',
        'endLatitude',
        'endLongitude',
        'length',
        'linearTmc',
        'linearId',
        'roadOrder',
        'timezoneName',
        'SHAPE@'
    ]
    with arcpy.da.InsertCursor(output_fc_unproj, fields) as cur:
        for record in newRecords:
            cur.insertRow(record)

    # Add status and LRS fields
    arcpy.AddField_management(output_fc_unproj, 'status', 'TEXT')
    arcpy.AddField_management(output_fc_unproj, 'rte_nm', 'TEXT')
    arcpy.AddField_management(output_fc_unproj, 'begin_msr', 'DOUBLE')
    arcpy.AddField_management(output_fc_unproj, 'end_msr', 'DOUBLE')

    print('  Projecting new feature class')
    arcpy.Project_management(output_fc_unproj, os.path.join(output_gdb, 'TMCs_work'), config.VIRGINIA_LAMBERT)
    arcpy.Delete_management(output_fc_unproj)

if __name__ == '__main__':
    # Download tmcs from api
    tmc_df = get_tmcs('data\\TMCs.csv')

    # Get previously downloaded tmcs to save time
    # tmc_df = pandas.read_csv('data\\TMCs.csv')
    create_tmc_feature_class(tmc_df, r'C:\Users\daniel.fourquet\Documents\Tasks\TMC-to-LRS\data', gdb_name='ughwork.gdb')