import arcpy
import os
import config

gdb_path = os.path.join(os.getcwd(), 'data/final_output.gdb')
path_tmcs_complete = os.path.join(gdb_path, 'tmc_complete')
path_tmcs_failed = os.path.join(gdb_path, 'tmc_failed')

def create_output_tables():
    # Create output gdb
    if not os.path.exists(gdb_path):
        print('  Creating final_output.gdb')
        arcpy.CreateFileGDB_management(os.path.join(os.getcwd(), 'data'), 'final_output.gdb')
    

    arcpy.env.overwriteOutput = True
    def add_fields(input):
        arcpy.AddField_management(input, 'tmc', 'TEXT')
        arcpy.AddField_management(input, 'rte_nm', 'TEXT')
        arcpy.AddField_management(input, 'begin_msr', 'DOUBLE')
        arcpy.AddField_management(input, 'end_msr', 'DOUBLE')

    print('  Creating completed output table.gdb')
    arcpy.CreateTable_management(gdb_path, 'tmc_complete')
    add_fields(path_tmcs_complete)
    
    print('  Creating failed output table.gdb')
    arcpy.CreateTable_management(gdb_path, 'tmc_failed')
    add_fields(path_tmcs_failed)
    arcpy.AddField_management(path_tmcs_failed, 'Comment', 'TEXT', 500)


def add_complete_tmcs():
    print('  Adding complete tmcs to final_output.gdb')

    sql = "status IN ('Complete (10)', 'Complete (10) - Flipped (35)', 'Complete (20)', 'Complete (20) - Flipped (35)', 'Complete (30)', 'Complete (30) - Flipped (35)')"
    fields = ['tmc', 'rte_nm', 'begin_msr', 'end_msr']

    # Add single-part tmcs
    # arcpy.DeleteRows_management(path_tmcs_complete)  # Delete existing rows if rerunning
    output = [(row[0], row[1], row[2], row[3]) for row in arcpy.da.SearchCursor(config.TMCs, fields, sql)]
    with arcpy.da.InsertCursor(path_tmcs_complete, fields) as cur:
        for tmc in output:
            cur.insertRow(tmc)

    # Add potential multi-part tmcs from detailed matching
    sql = "status = 'Complete (45)'"
    detailed_tmcs = tuple(row[0] for row in arcpy.da.SearchCursor(config.TMCs, fields, sql))

    sql = f'tmc in {detailed_tmcs}'
    output = [(row[0], row[1], row[2], row[3]) for row in arcpy.da.SearchCursor('data/_45_output.csv', fields, sql)]
    with arcpy.da.InsertCursor(path_tmcs_complete, fields) as cur:
        for tmc in output:
            cur.insertRow(tmc)

    # Create event layer
    create_route_event_layer(path_tmcs_complete, 'fc_tmc_complete')

    

def add_failed_tmcs():
    print('  Adding failed tmcs to final_output.gdb')
    fields = ['tmc', 'rte_nm', 'begin_msr', 'end_msr']

    # Get null values from config.TMCs
    sql = "status is null"
    null_output = [(row[0], row[1], row[2], row[3]) for row in arcpy.da.SearchCursor(config.TMCs, fields, sql)]
    
    # Get TMCs that failed QC
    failed_tmcs = tuple(row[0] for row in arcpy.da.SearchCursor(config.TMCs, 'tmc', "status = 'Failed QC (55)'"))
    sql = f"tmc in {failed_tmcs}"
    failed_output = [(row[0], row[1], row[2], row[3]) for row in arcpy.da.SearchCursor('data/_45_output.csv', fields, sql)]
    
    # Combine outputs and add to failed table
    output = null_output + failed_output
    with arcpy.da.InsertCursor(path_tmcs_failed, fields) as cur:
        for tmc in output:
            cur.insertRow(tmc)

    # Create event layer
    create_route_event_layer(path_tmcs_failed, 'fc_tmc_failed')


def create_route_event_layer(event_table, output_name):
    arcpy.MakeRouteEventLayer_lr(config.OVERLAP_LRS, 'RTE_NM', event_table, "rte_nm; Line; begin_msr; end_msr", 'tbl_tmc_events')
    arcpy.FeatureClassToFeatureClass_conversion('tbl_tmc_events', 'data/final_output.gdb', output_name)
        
    


if __name__ == '__main__':
    create_output_tables()
    add_complete_tmcs()
    add_failed_tmcs()
