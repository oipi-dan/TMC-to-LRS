import flip_routes
import arcpy
import config

def flip_routes_again():
    # Make event layer from output of 45_identify_routes_detailed
    arcpy.env.overwriteOutput = True
    arcpy.MakeRouteEventLayer_lr(config.OVERLAP_LRS, 'RTE_NM', 'data/_45_output.csv', "rte_nm; Line; begin_msr; end_msr", 'tbl_tmc_events')
    arcpy.FeatureClassToFeatureClass_conversion('tbl_tmc_events', 'data/scrap.gdb','_50_tmc_events')
    feature_class = 'data/scrap.gdb/_50_tmc_events'
    flip_routes.run_flip_routes(' - Flipped (50)', feature_class=feature_class)


if __name__ == '__main__':
    print('\nFlipping routes identified in 45_identify_routes_detailed.py')
    flip_routes_again()