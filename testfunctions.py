""" These are functions to paste into Pro's python window to aid in QC """

TMCLayer = 'TMCs'
Conflation = 'TMC_Events'

testlist = [row[0] for row in arcpy.da.SearchCursor(TMCLayer, 'tmc')]
current = None

def next():
    global current
    if current:
        testlist.pop(0)
    current = testlist[0]
    sd(current)

def set_df(layerName, sql):
    prj = arcpy.mp.ArcGISProject('CURRENT')
    map = prj.listMaps()[0]
    layer = map.listLayers(layerName)[0]
    
    layer.definitionQuery = sql

def sd(tmc=''):
    if tmc == '':
        set_df(TMCLayer, '')
        set_df(Conflation, '')
    else:
        set_df(TMCLayer, f"tmc = '{tmc}'")
        set_df(Conflation, f"tmc = '{tmc}'")
        zoom_to_layer(TMCLayer)

def zoom_to_layer(layerName):
    """ Zooms to the selected features of the input layer.  The layerName
        attribute is a string representing the layer name as it appears
        in the table of contents 
        
        Important caveat - the Map tab must be selected for this to work
        (if something else like the attributes table is active, it will return
        an error).  This is a built-in limitation of arcpy. """
    prj = arcpy.mp.ArcGISProject("CURRENT")
    map = prj.listMaps()[0]

    mapView = prj.activeView
    camera = mapView.camera

    layer = map.listLayers(layerName)[0]
    newExtent = mapView.getLayerExtent(layer)
    camera.setExtent(newExtent)