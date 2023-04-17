import requests
import pandas
import os
import json
import arcpy
import config
from osgeo import ogr, osr
import lrs_tools

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


def create_tmc_geometry(tmc_df, out_path='data'):
    """ Arcpy created inconsistent results when creating geometry, but OGR just works
        This function creates a shapefile with TMC code and geometry to join to the
        gdb later
    """

    print('  Creating geometry dictionary')
    data = {}
    def add_data(record):
        tmc = record['tmc']

        str_coordinates = record['coordinates'][0].split(',')
        coordinates = []
        for coord in str_coordinates:
            x, y = coord.split(' ')
            coordinates.append((float(x), float(y)))

        data[tmc] = coordinates

    tmc_df.apply(add_data, axis=1)


    print('  Creating geometry shapefile')
    driver = ogr.GetDriverByName('ESRI Shapefile')

    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)

    data_source = driver.CreateDataSource(f'{out_path}/tmc_geom.shp')
    layer = data_source.CreateLayer('TMCs', srs, ogr.wkbLineString)

    field_name = ogr.FieldDefn('tmc', ogr.OFTString)
    field_name.SetWidth(24)
    layer.CreateField(field_name)

    for i, record in enumerate(data):
        feature = ogr.Feature(layer.GetLayerDefn())
        feature.SetField('tmc', record)
        
        # Create geometry
        line=ogr.Geometry(ogr.wkbLineString)
        for coordinate in data[record]:
            line.AddPoint(coordinate[0], coordinate[1])
        feature.SetGeometry(line)

        # Create feature in layer
        layer.CreateFeature(feature)

        lrs_tools.print_progress_bar(i, len(data) - 1, 'Creating geometry')
    
    data_source = None



def create_tmc_feature_class(tmc_df, gdb_path, gdb_name='input_data.gdb'):
    """ Creates a TMC feature class
    inputs:
        tmc_df - a Pandas DataFrame containing the results from the PDA API
    """
    print('\n\n  Creating feature class')
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
        'timezoneName'
    ]
    with arcpy.da.InsertCursor(output_fc_unproj, fields) as cur:
        for record in newRecords:
            cur.insertRow(record)

    # Add status and LRS fields
    arcpy.AddField_management(output_fc_unproj, 'status', 'TEXT')
    arcpy.AddField_management(output_fc_unproj, 'rte_nm', 'TEXT')
    arcpy.AddField_management(output_fc_unproj, 'begin_msr', 'DOUBLE')
    arcpy.AddField_management(output_fc_unproj, 'end_msr', 'DOUBLE')

    print('  Updating feature class geometry')
    dict_geom = {row[0]:row[1] for row in arcpy.da.SearchCursor('data//tmc_geom.shp', ['tmc','SHAPE@'])}
    with arcpy.da.UpdateCursor(output_fc_unproj, ['tmc','SHAPE@']) as cur:
        for row in cur:
            geom = dict_geom.get(row[0])
            row[1] = geom
            cur.updateRow(row)

    print('  Projecting new feature class')
    arcpy.Project_management(output_fc_unproj, os.path.join(output_gdb, 'TMCs'), config.VIRGINIA_LAMBERT)
    arcpy.Delete_management(output_fc_unproj)

if __name__ == '__main__': 
    print('\nDownloading TMCs')      
    tmc_df = get_tmcs(output_csv='data\\TMCs.csv')  # Download tmcs from api
    create_tmc_geometry(tmc_df)
    create_tmc_feature_class(tmc_df, r'C:\Users\daniel.fourquet\Documents\Tasks\TMC-to-LRS\data')