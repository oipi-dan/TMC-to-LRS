import arcpy
import os
import config

def create_output_tables():
    # Create output gdb
    path = os.path.join(os.getcwd(), 'data/final_output.gdb')
    if not os.path.exists(path):
        print('  Creating final_output.gdb')
        arcpy.CreateFileGDB_management(os.path.join(os.getcsd(), 'data'), 'final_output.gdb')
    
    arcpy.env.overwriteOutput = True
    def add_fields(input):
        arcpy.AddField_management(input, 'tmc', 'TEXT')
        arcpy.AddField_management(input, 'rte_nm', 'TEXT')
        arcpy.AddField_management(input, 'begin_msr', 'DOUBLE')
        arcpy.AddField_management(input, 'end_msr', 'DOUBLE')

    print('  Creating completed output table.gdb')
    path_tmcs_complete = os.path.join(os.getcwd(), 'data/final_output.gdb/tmc_complete')
    arcpy.CreateTable_management(path, 'tmc_complete')
    add_fields(path_tmcs_complete)

    
    print('  Creating failed output table.gdb')
    path_tmcs_failed = os.path.join(os.getcwd(), 'data/final_output.gdb/tmc_failed')
    arcpy.CreateTable_management(path, 'tmc_failed')
    add_fields(path_tmcs_failed)


def add_complete_tmcs():
    path_tmcs_complete = os.path.join(os.getcwd(), 'data/final_output.gdb/tmc_complete')
    sql = "status in ("
    output = [(tmc, rte_nm, begin_msr, end_msr) for row in arcpy.da.SearchCursor(config.TMCs, ['tmc', 'rte_nm', 'begin_msr', 'end_msr'])]
    


if __name__ == '__main__':
    create_output_tables()

