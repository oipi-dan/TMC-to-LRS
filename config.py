import os
import arcpy

###############
# Source Data #
#             ##############################################
# These will be projected and stored in the input_data.gdb
# in 0_initial_setup.py

# SDE_VDOT_RTE_MASTER_LRS
_MASTER_LRS = r'C:\Users\daniel.fourquet\Documents\ArcGIS\LRS.gdb\SDE_VDOT_RTE_MASTER_LRS_DY'

# SDE_VDOT_RTE_OVERLAP_LRS
_OVERLAP_LRS = r'C:\Users\daniel.fourquet\Documents\ArcGIS\LRS.gdb\SDE_VDOT_RTE_OVERLAP_LRS_DY'

# SDE_VDOT_INTERSECTION_W_XY
_INTERSECTIONS = r'C:\Users\daniel.fourquet\Documents\ArcGIS\LRS.gdb\SDE_VDOT_INTERSECTION_W_XY_DY'

############################################################



############
# Settings # 
#          #################################################

# Geographic spatial reference
WGS84 = arcpy.SpatialReference(4326)

# Projected spatial reference
VIRGINIA_LAMBERT = arcpy.SpatialReference(3969)




##############
# Input Data #
#            ###############################################
# These are the data that were created by 0_initial_setup.py

MASTER_LRS = os.path.join(os.getcwd(), 'data\\input_data.gdb\\master_lrs')
OVERLAP_LRS = os.path.join(os.getcwd(), 'data\\input_data.gdb\\overlap_lrs')
INTERSECTIONS = os.path.join(os.getcwd(), 'data\\input_data.gdb\\intersections')
LRS_SHP = os.path.join(os.getcwd(), 'data\\lrs.shp')
TMCs = os.path.join(os.getcwd(), 'data\\input_data.gdb\\TMCs')
# TMCs = os.path.join(os.getcwd(), 'data\\input_data.gdb\\testTMCs2')

############################################################
