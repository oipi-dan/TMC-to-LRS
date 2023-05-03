import arcpy
import os
import config


def create_folders(*folders):
    for folder in folders:
        if not os.path.exists(folder):
            print(f'  Creating folder {folder}')
            path = os.path.join(os.getcwd(), folder)
            os.mkdir(folder)
        else:
            print(f'  Folder {folder} already exists')


def create_databases(*dbs, data_path=os.path.join(os.getcwd(), 'data')):
    if not os.path.exists(data_path):
        os.mkdir(data_path)

    for db in dbs:
        if not db.endswith('.gdb'):
            db = db + '.gdb'

        if not os.path.exists(os.path.join(data_path, db)):
            print(f'  Creating {db}')
            arcpy.CreateFileGDB_management(data_path, db)
        
        else:
            print(f'  {db} already exists')


def project_input_data():
    arcpy.env.overwriteOutput = True

    print(f'  Projecting the Master LRS')
    arcpy.Project_management(config._MASTER_LRS, config.MASTER_LRS, config.VIRGINIA_LAMBERT)

    print('  Creating shapefile version for GeoPandas')
    arcpy.FeatureClassToFeatureClass_conversion(config.MASTER_LRS, os.path.join(os.getcwd(), 'data'), 'lrs.shp')

    print(f'  Projecting the Overlap LRS')
    arcpy.Project_management(config._OVERLAP_LRS, config.OVERLAP_LRS, config.VIRGINIA_LAMBERT)

    print(f'  Projecting the LRS Intersections')


def setup():
    create_folders('data', 'logs')
    create_databases('input_data', 'scrap', 'intermediate')
    project_input_data()

if __name__ == '__main__':
    print('Initial Setup:')
    setup()
