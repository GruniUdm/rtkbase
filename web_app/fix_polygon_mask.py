with open('/home/basegnss/rtkbase/web_app/ndvi_helper.py', 'r') as f:
    c = f.read()

# Replace the gdalwarp -cutline NDVI clip with gdal_rasterize based approach
old = """    # 3. Clip to polygon using GPKG layer directly, with makevalid
    ndvi_clipped = os.path.join(NDVI_DIR, f'{base_name}.tif')
    # First make the cutline valid using ogr2ogr
    valid_cutline = os.path.join(NDVI_DIR, f'{base_name}_cutline.gpkg')
    subprocess.run(['ogr2ogr', '-f', 'GPKG', '-makevalid', '-nln', 'cutline',
        valid_cutline, GPKG_PATH, 'geozones', '-where', f"zone_id='{zone_id}'"],
        capture_output=True, text=True, timeout=30)
    warp_cmd = ['gdalwarp', '-cutline', valid_cutline, '-crop_to_cutline',
        '-dstalpha', '-of', 'GTiff', ndvi_raw, ndvi_clipped]
    r = subprocess.run(warp_cmd, capture_output=True, text=True, timeout=120, env=GDAL_ENV)

    # Also clip cloud mask to the same boundary while cutline exists
    if cloud_mask and r.returncode == 0:
        cloud_clipped = os.path.join(NDVI_DIR, f'{base_name}_cloud_clip.tif')
        r_c = subprocess.run(['gdalwarp', '-cutline', valid_cutline, '-crop_to_cutline',
            cloud_mask, cloud_clipped],
            capture_output=True, text=True, timeout=60, env=GDAL_ENV)
        if r_c.returncode == 0 and os.path.exists(cloud_clipped):
            os.remove(cloud_mask)
            cloud_mask = cloud_clipped
        else:
            if os.path.exists(cloud_clipped): os.remove(cloud_clipped)

    if os.path.exists(valid_cutline):
        os.remove(valid_cutline)
    if r.returncode != 0 or not os.path.exists(ndvi_clipped):
        if os.path.exists(ndvi_clipped):
            os.remove(ndvi_clipped)
        if cloud_mask and os.path.exists(cloud_mask): os.remove(cloud_mask)
        return {'error': f'gdalwarp failed: {r.stderr[:200]}'}
    os.remove(ndvi_raw)"""

new = """    # 3. Create zone polygon mask by rasterizing the zone shape
    ndvi_clipped = os.path.join(NDVI_DIR, f'{base_name}.tif')
    
    # Get the zone polygon as GeoJSON in UTM projection
    r_utm = subprocess.run(['ogr2ogr', '-f', 'GeoJSON', '-t_srs', f'EPSG:326{utm_zone}',
        '/vsistdout/', GPKG_PATH, 'geozones', '-where', f"zone_id='{zone_id}'"],
        capture_output=True, text=True, timeout=30)
    if r_utm.returncode != 0:
        if os.path.exists(ndvi_raw): os.remove(ndvi_raw)
        return {'error': 'Failed to extract zone polygon'}
    
    zone_geojson_utm = r_utm.stdout
    
    # Get ndvi_raw size for matching mask
    info_r = subprocess.run(['gdalinfo', '-json', ndvi_raw],
        capture_output=True, text=True, timeout=10, env=GDAL_ENV)
    if info_r.returncode != 0:
        os.remove(ndvi_raw)
        return {'error': 'Failed to get ndvi_raw info'}
    raw_info = json.loads(info_r.stdout)
    sx = raw_info.get('sizeX', 0)
    sy = raw_info.get('sizeY', 0)
    gt = raw_info.get('geoTransform', [])
    if not sx or not sy or not gt:
        os.remove(ndvi_raw)
        return {'error': 'Invalid ndvi_raw dimensions'}
    
    # Rasterize polygon to create alpha mask
    alpha_mask = os.path.join(NDVI_DIR, f'{base_name}_alpha_mask.tif')
    r_raster = subprocess.run(['gdal_rasterize', '-burn', '255', '-ot', 'Byte',
        '-ts', str(sx), str(sy),
        '-te', str(gt[0]), str(gt[3] + sy * gt[5]), str(gt[0] + sx * gt[1]), str(gt[3]),
        '-of', 'GTiff', '/vsistdin/', alpha_mask],
        input=zone_geojson_utm, capture_output=True, text=True, timeout=60, env=GDAL_ENV)
    
    if r_raster.returncode != 0 or not os.path.exists(alpha_mask):
        os.remove(ndvi_raw)
        return {'error': f'gdal_rasterize failed: {r_raster.stderr[:200]}'}
    
    # Crop ndvi_raw to polygon bbox + apply alpha mask via gdal_calc
    # First set NoData where mask is 0
    masked_ndvi = os.path.join(NDVI_DIR, f'{base_name}_masked.tif')
    r_calc = subprocess.run(['gdal_calc.py', '-A', ndvi_raw, '-B', alpha_mask,
        '--outfile', masked_ndvi, '--calc', 'A*(B>0)',
        '--NoDataValue', '0', '--type', 'Float32', '--overwrite'],
        capture_output=True, text=True, timeout=120, env=GDAL_ENV)
    
    if r_calc.returncode != 0 or not os.path.exists(masked_ndvi):
        for f in [ndvi_raw, alpha_mask]:
            if os.path.exists(f): os.remove(f)
        return {'error': f'gdal_calc mask failed: {r_calc.stderr[:200]}'}
    
    os.remove(ndvi_raw)
    
    # Now crop extent to polygon bounding box
    # Get polygon UTM bbox from the GeoJSON
    feat = json.loads(zone_geojson_utm)['features'][0]
    coords = feat['geometry']['coordinates'][0]
    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    poly_xmin, poly_xmax = min(xs), max(xs)
    poly_ymin, poly_ymax = min(ys), max(ys)
    margin = 5
    crop_bbox = (poly_xmin - margin, poly_ymax + margin, poly_xmax + margin, poly_ymin - margin)
    
    r_crop = subprocess.run(['gdal_translate', '-projwin',
        str(crop_bbox[0]), str(crop_bbox[1]),
        str(crop_bbox[2]), str(crop_bbox[3]),
        '-of', 'GTiff', masked_ndvi, ndvi_clipped],
        capture_output=True, text=True, timeout=60, env=GDAL_ENV)
    
    if os.path.exists(masked_ndvi): os.remove(masked_ndvi)
    
    # Also clip cloud mask to the same boundary
    if cloud_mask and os.path.exists(cloud_mask):
        cloud_clipped = os.path.join(NDVI_DIR, f'{base_name}_cloud_clip.tif')
        r_cc = subprocess.run(['gdal_translate', '-projwin',
            str(crop_bbox[0]), str(crop_bbox[1]),
            str(crop_bbox[2]), str(crop_bbox[3]),
            '-of', 'GTiff', cloud_mask, cloud_clipped],
            capture_output=True, text=True, timeout=60, env=GDAL_ENV)
        if r_cc.returncode == 0 and os.path.exists(cloud_clipped):
            # Also mask the cloud mask with the zone polygon
            cloud_masked = os.path.join(NDVI_DIR, f'{base_name}_cloud_masked.tif')
            r_cm = subprocess.run(['gdal_calc.py', '-A', cloud_clipped, '-B', alpha_mask,
                '--outfile', cloud_masked, '--calc', 'A*(B>0)',
                '--type', 'Byte', '--overwrite'],
                capture_output=True, text=True, timeout=60, env=GDAL_ENV)
            if r_cm.returncode == 0 and os.path.exists(cloud_masked):
                os.remove(cloud_mask)
                os.remove(cloud_clipped)
                cloud_mask = cloud_masked
            else:
                if os.path.exists(cloud_clipped): os.remove(cloud_clipped)
        else:
            if os.path.exists(cloud_clipped): os.remove(cloud_clipped)
    
    os.remove(alpha_mask)
    
    if r_crop.returncode != 0 or not os.path.exists(ndvi_clipped):
        if os.path.exists(ndvi_clipped): os.remove(ndvi_clipped)
        if cloud_mask and os.path.exists(cloud_mask): os.remove(cloud_mask)
        return {'error': f'gdal_translate crop failed: {r_crop.stderr[:200]}'}"""

assert old in c, 'Old text not found'
c = c.replace(old, new)
print('Replaced gdalwarp -cutline with gdal_rasterize approach')

# Also fix the _combine_rgba to use the alpha mask instead of -dstalpha band
# The ndvi_clipped now has only 1 band (NDVI values), no alpha band from -dstalpha
# We need to create the alpha band from the alpha_mask
# Actually, _combine_rgba reads alpha from alpha_path which is ndvi_alpha 
# ndvi_alpha was extracted from ndvi_clipped band 2 (the -dstalpha band)
# Now ndvi_clipped only has 1 band, so we need to change this

# Find the section that extracts alpha and colorized NDVI
old2 = """    # 5. Extract NDVI band for colorization
    ndvi_band = os.path.join(NDVI_DIR, f'{base_name}_b1.tif')
    r1 = subprocess.run(['gdal_translate', '-b', '1', ndvi_clipped, ndvi_band],
        capture_output=True, timeout=30, env=GDAL_ENV)"""

new2 = """    # 5. Extract NDVI band for colorization
    ndvi_band = os.path.join(NDVI_DIR, f'{base_name}_b1.tif')
    r1 = subprocess.run(['gdal_translate', '-b', '1', ndvi_clipped, ndvi_band],
        capture_output=True, timeout=30, env=GDAL_ENV)
    # The alpha mask is recreated from the zone GeoJSON in _combine_rgba step"""

assert old2 in c, 'Old2 text not found'
c = c.replace(old2, new2)
print('Updated ndvi_band extraction comment')

# Fix the alpha extraction: instead of band 2 of ndvi_clipped, 
# re-rasterize the polygon to create the alpha mask
old3 = """    # 7. Extract alpha mask from clipped raster
    ndvi_alpha = os.path.join(NDVI_DIR, f'{base_name}_alpha.tif')
    r3 = subprocess.run(['gdal_translate', '-b', '2', ndvi_clipped, ndvi_alpha],
        capture_output=True, timeout=30, env=GDAL_ENV)
    if r3.returncode != 0 or not os.path.exists(ndvi_alpha):
        for f in [ndvi_clipped, ndvi_rgb]:
            if os.path.exists(f): os.remove(f)
        if cloud_mask and os.path.exists(cloud_mask): os.remove(cloud_mask)
        return {'error': 'Failed to extract alpha band'}
    os.remove(ndvi_clipped)"""

new3 = """    # 7. Create alpha mask by rasterizing zone polygon
    ndvi_alpha = os.path.join(NDVI_DIR, f'{base_name}_alpha.tif')
    # Get zone polygon in UTM
    r_utm2 = subprocess.run(['ogr2ogr', '-f', 'GeoJSON', '-t_srs', f'EPSG:326{utm_zone}',
        '/vsistdout/', GPKG_PATH, 'geozones', '-where', f"zone_id='{zone_id}'"],
        capture_output=True, text=True, timeout=30)
    if r_utm2.returncode != 0:
        for f in [ndvi_clipped, ndvi_rgb]:
            if os.path.exists(f): os.remove(f)
        if cloud_mask and os.path.exists(cloud_mask): os.remove(cloud_mask)
        return {'error': 'Failed to get zone for alpha mask'}
    
    # Get ndvi_clipped dimensions for matching mask
    info_a = subprocess.run(['gdalinfo', '-json', ndvi_clipped],
        capture_output=True, text=True, timeout=10, env=GDAL_ENV)
    if info_a.returncode != 0:
        for f in [ndvi_clipped, ndvi_rgb]:
            if os.path.exists(f): os.remove(f)
        if cloud_mask and os.path.exists(cloud_mask): os.remove(cloud_mask)
        return {'error': 'Failed to get ndvi_clipped info'}
    a_info = json.loads(info_a.stdout)
    a_sx = a_info.get('sizeX', 0)
    a_sy = a_info.get('sizeY', 0)
    a_gt = a_info.get('geoTransform', [])
    
    if a_sx and a_sy and a_gt:
        r_raster_a = subprocess.run(['gdal_rasterize', '-burn', '255', '-ot', 'Byte',
            '-ts', str(a_sx), str(a_sy),
            '-te', str(a_gt[0]), str(a_gt[3] + a_sy * a_gt[5]), str(a_gt[0] + a_sx * a_gt[1]), str(a_gt[3]),
            '-of', 'GTiff', '/vsistdin/', ndvi_alpha],
            input=r_utm2.stdout, capture_output=True, text=True, timeout=60, env=GDAL_ENV)
        alpha_ok = r_raster_a.returncode == 0 and os.path.exists(ndvi_alpha)
    else:
        alpha_ok = False
    
    if not alpha_ok:
        for f in [ndvi_clipped, ndvi_rgb]:
            if os.path.exists(f): os.remove(f)
        if cloud_mask and os.path.exists(cloud_mask): os.remove(cloud_mask)
        return {'error': 'Failed to create alpha mask'}
    os.remove(ndvi_clipped)"""

assert old3 in c, 'Old3 text not found'
c = c.replace(old3, new3)
print('Replaced alpha extraction with gdal_rasterize')

with open('/home/basegnss/rtkbase/web_app/ndvi_helper.py', 'w') as f:
    f.write(c)
print('Written')
