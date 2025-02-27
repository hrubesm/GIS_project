# Importing python modules
import arcpy
import os
import random

# Workspace settings
arcpy.env.overwriteOutput = True
arcpy.env.workspace = "Q:\\"

# Input and output data path
world_cover = 'world_cover_export.tif'
dynamic_world = 'dynamic_world_export.tif'
clip_polygon = 'Ostrava_32633.shp'
temp_multi = 'temp_multi.shp'
train_data = 'train_data.shp'
check_tab = 'check_tab.dbf'
selection_train = 'selection_train.shp'

# LULUCF legend for ESA WorldCover and Dynamic World databases
wc_leg = {10: 1, 20: 99, 30: 3, 40: 2, 50: 5, 60: 99, 80: 4, 90: 4}
dw_leg = {0: 4, 1: 1, 2: 3, 3: 4, 4: 2, 5: 99, 6: 5, 7: 99, 8: 99}

### FUNCTIONS

# Raster to vector conversion and vector clipping function
def rast2vect(input_raster, clip_polygon):
    # Creation of temporary layer and reading of input layers name
    temp_vec = "in_memory/temp_vec"
    input_name = os.path.splitext(os.path.basename(input_raster))[0]
    clip_name = os.path.splitext(os.path.basename(clip_polygon))[0]

    # Raster to vector conversion
    arcpy.RasterToPolygon_conversion(
        in_raster=input_raster, 
        out_polygon_features=temp_vec, 
        simplify=True)
    print(f"Conversion of {input_name} successful.")

    # Clipping of created vector data by region of interest
    temp_clip = f"in_memory/{input_name}_temp_clip"
    arcpy.Clip_analysis(in_features=temp_vec, 
                        clip_features=clip_polygon, 
                        out_feature_class=temp_clip)
    arcpy.Delete_management(temp_vec)  
    print(f"Clipping of {input_name} by {clip_name} successful.")
    return temp_clip
    
# LULUCF legend update function
def update_tab(input_layer, lul_def):
    # Creation of new field
    new_field = "lulucf"
    arcpy.AddField_management(
        in_table=input_layer, 
        field_name=new_field, 
        field_type="LONG"
    )

    # Inserting values of LULUCF legend based on gridcode field (field with LULUCF values in input databases)
    with arcpy.da.UpdateCursor(input_layer, ['gridcode', new_field]) as cursor:
        for row in cursor:
            gridcode_value = row[0]
            row[1] = lul_def.get(gridcode_value, 99)  # Value 99 for null fields
            cursor.updateRow(row)
    print(f"Successful update of LULUCF values in {input_layer[10:]}.")
    return input_layer
    
# Intersect and selection of polygons with identical LULUCF category function
def intersect(layer1, layer2):
    # Intersect of both databases
    temp_intersect = "in_memory/temp_intersect"
    arcpy.Intersect_analysis([layer1, layer2], temp_intersect)

    # Selection of polygons with identical LULUCF category for both databases
    field_1 = "lulucf"
    field_2 = "lulucf_1"
    where_cause = f"{field_1} = {field_2} AND {field_1} < 10"
    common_lul = arcpy.MakeFeatureLayer_management(temp_intersect, "common_lul", where_cause)
    print("Selecting of polygons with identical LULUCF category for both databases successful.")
    return common_lul
    

# Negative buffer and area calculation function
def buffer(intersect):
  # Warning and temporary layers creation
    print("Starting negative buffer application.")
    print("WARNING! This step can take a long time!")
    temp_buffer = "in_memory/temp_buffer"
    temp_single = "in_memory/temp_single"
    
    # Setting buffer distance a buffer application
    buffer_distance = -50
    arcpy.Buffer_analysis(intersect, temp_buffer, buffer_distance)
    arcpy.CopyFeatures_management(temp_buffer, temp_multi)
    arcpy.Delete_management(temp_buffer)  
    print("Negative buffer application successful.")

    # Division of multipolygons to single polygons
    arcpy.management.MultipartToSinglepart(temp_multi, temp_single)

    # Calculation of polygons area in m²
    new_field = "area" 
    arcpy.AddField_management(temp_single, new_field, "DOUBLE")
    arcpy.CalculateField_management(temp_single, new_field, "!shape.area@SQUAREMETERS!", "PYTHON3")  
    arcpy.Delete_management(temp_multi)
    print("Calculation of area successful.")
    return temp_single
    
# Train data creation function 
def train(temp_single):
    # Selection of polygons, which are greater than 1 000 000 m²
    temp_big = "in_memory/temp_big"
    where_cause1 = "area > 1000000"
    temp_big= arcpy.MakeFeatureLayer_management(temp_single, "temp_big", where_cause1)

    # Tessellation parameters
    temp_tes = "in_memory/temp_tes"
    cell_shape = "SQUARE" # Type of tessellation  
    cell_size = 1000000  # Tessellation cell size in m² 

    # Finding coordinates of area, wicht contain selected big polygons
    extent = arcpy.Describe(temp_big).extent
    extent_str = f"{extent.XMin} {extent.YMin} {extent.XMax} {extent.YMax}"

    # Tessellation generating
    arcpy.management.GenerateTessellation(temp_tes, extent_str, cell_shape, cell_size)
    
    # Intersect of tessellation and selected big polygons
    temp_tesbig = "in_memory/temp_intersect"
    arcpy.Intersect_analysis([temp_tes, temp_big], temp_tesbig)

    # Selection of polygons, which are less than or equal to 1 000 000 m²
    temp_small= arcpy.MakeFeatureLayer_management(temp_single, "temp_big",  "NOT (" + where_cause1 + ")") 

    # Merge of intersected big polygons and small polygons
    temp_merge = "in_memory/temp_merge"
    temp_mersin = "in_memory/temp_mersin"
    arcpy.management.Merge([temp_small, temp_tesbig], temp_merge)

    # Division of multipolygons to single polygons
    arcpy.management.MultipartToSinglepart(temp_merge, temp_mersin)

    # Selection of polygons, which are equal to or greater than 1800 m² (Minimal Mapping Unit)
    new_field = "area" 
    arcpy.CalculateField_management(temp_mersin, new_field, "!shape.area@SQUAREMETERS!", "PYTHON3")  
    where_cause2 = "area >= 1800"
    temp_train = arcpy.MakeFeatureLayer_management(temp_mersin, "temp_train", where_cause2)
 
    # Saving of final layer and deleting of temporary layers
    arcpy.CopyFeatures_management(temp_train, train_data)
    arcpy.Delete_management(temp_single)
    arcpy.Delete_management(temp_big)
    arcpy.Delete_management(temp_tes)
    arcpy.Delete_management(temp_tesbig)
    arcpy.Delete_management(temp_merge)
    arcpy.Delete_management(temp_train)
    print("Creation of train data shapefile successful")

# Finding name of layer identifier function
def id_name(input_layer):
    # Reading of all column names
    with arcpy.da.SearchCursor(input_layer, "*") as cursor:
        field_names = cursor.fields

    # Trying to find column whose name is one of three possible names 
    id_field = None
    for field in field_names:
        if field.lower() in ['objectid', 'oid', 'fid']: 
            id_field = field
            return id_field
    print(f"ID field not found. Check name of your identifier for {os.path.basename(input_layer)}.")
    exit()

# Repair and geometry check function
def repair_check(train_data):
    # Repairing of incorrect geometry
    print("Repairing geometry of train data polygons started.")
    try:    
        arcpy.management.RepairGeometry(train_data, delete_null="DELETE_NULL")
        print("The geometry repair was successful.")
    except arcpy.ExecuteError:
        print("Geometry repair error.")  
        print(arcpy.GetMessages(2))     

    # Checking if the geometry is correct
    try:
        arcpy.management.CheckGeometry(train_data, check_tab)
        id_field = id_name(check_tab)
        with arcpy.da.SearchCursor(check_tab, [id_field]) as cursor:
            is_empty = not any(cursor)
            
        # Checking result
        if is_empty:
            print("Error check table is empty. No geometry errors were found.")
        else:
            print("Error check table contains records. Geometric errors were found.")          
    except arcpy.ExecuteError:
        print(f"Error while working with table: {arcpy.GetMessages(2)}")
    except Exception as e:
        print(f"Unexpected error: {e}")

# Random selection from train data function
def random_selection(train_data, num_sel):
    # Creating of empty dictionary, where dictionary keys are LULUCF values and dictionary values are train data polygons identifiers
    id_dict = {1: [], 2: [], 3: [], 4: [], 5: []}
    # Finding identifier column name
    id_field = id_name(train_data)

    # Sorting identifiers of all polygons into the dictionary by LULUCF value
    with arcpy.da.SearchCursor(train_data, [id_field, 'lulucf']) as cursor:
        for row in cursor:
            lulucf_value = row[1]  
            if lulucf_value in id_dict:  
                id_dict[lulucf_value].append(row[0])  

    # Setting seed for to get the same result regardless of repeated execution
    random.seed(42)
    # Creation of empty list of all selected polygons from train data
    all_selected_ids = []
    # Finding identifier column name
    #id_field = id_name(train_data)

    # Randomization of identifiers order in each LULUCF category list and selection according to input numbers for each LULUCF category
    for lulucf_value, id_list in id_dict.items():
        random.shuffle(id_list)
        selected_ids = id_list[:num_sel[lulucf_value]] 
        all_selected_ids.extend(selected_ids)  

    # Creation of SQL query for selecting of polygons selected by list of all randomly selected identifiers
    where_clause = f"{id_field} IN ({','.join(map(str, all_selected_ids))})"
   
    # Selection of train data polygons by SQL query
    temp_select = arcpy.management.MakeFeatureLayer(train_data, "temp_select", where_clause)

    # Saving selected polygons and deleting of temporary layers
    arcpy.CopyFeatures_management(temp_select, selection_train)
    arcpy.management.Delete(temp_select)

### END OF FUNCTIONS


### START OF THE PROGRAM

# Conversion and LULUCF category update of both databases
world_vec = rast2vect(world_cover, clip_polygon)
dynamic_vec = rast2vect(dynamic_world, clip_polygon)
world_vec = update_tab(world_vec, wc_leg)                         
dynamic_vec = update_tab(dynamic_vec, dw_leg)

# Selecting of polygons with identical LULUCF category and creation of train data shapefile
wd_intersect = intersect(world_vec, dynamic_vec)
buf_single = buffer(wd_intersect)          
train(buf_single)

# Repairing geometry of polygons from train data shapefile
repair_check(train_data)

# Numbers of selected polygons for each LULUCF category (1 - Forest land, 2 - Cropland, 3 - Grassland, 4 - Wetlands, 5 - Settlements)
# For each category will be randomly select x polygons, where number x is defined by equation:
# x = 80 + 400 * (total_area_of_category / total_area_of_all_categories)
# Totally 800 polygons for following manual control
num_of_sel = {1: 341, 2: 192, 3: 101, 4: 84, 5: 82}

# Selection of train data based on previous dictionary of numbers for each LULUCF category
random_selection(train_data, num_of_sel)
print()
print("ALL PROCESSES WERE EXECUTED SUCCESSFULLY.")
print("SELECTED POLYGONS FROM TRAIN DATA SHAPEFILE ARE READY FOR MANUAL CONTROL.")

### END OF THE PROGRAM