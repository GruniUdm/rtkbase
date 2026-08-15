import sys, os, json, subprocess
sys.path.insert(0, '/home/basegnss/rtkbase/web_app')
import ndvi_helper

zone_id = 'zone_1779852290'
zone = ndvi_helper._read_zone_from_gpkg(zone_id)
polygon = zone['polygon']
bounds = [min(p[1] for p in polygon), min(p[0] for p in polygon), max(p[1] for p in polygon), max(p[0] for p in polygon)]
utm_zone = ndvi_helper._utms_from_bounds(bounds)
bbox_utm = ndvi_helper._bbox_wgs84_to_utm(bounds, utm_zone)
print(f'UTM zone: {utm_zone}')
print(f'Bbox UTM: {bbox_utm}')

# Test full cloud check flow for June 11 AWS JP2
scl_url = 'https://sentinel-s2-l2a.s3.amazonaws.com/tiles/39/V/WC/2026/6/11/0/R20m/SCL.jp2'
base_name = 'debug_cloud_test'
ndvi_dir = '/home/basegnss/rtkbase/data/ndvi'

# Step 1: crop SCL
scl_crop = os.path.join(ndvi_dir, f'{base_name}_SCL.tif')
r = subprocess.run(['gdal_translate', '-projwin',
    str(bbox_utm[0]), str(bbox_utm[1]),
    str(bbox_utm[2]), str(bbox_utm[3]),
    '-projwin_srs', f'EPSG:326{utm_zone}',
    '-of', 'GTiff', scl_url, scl_crop],
    capture_output=True, text=True, timeout=180, env=ndvi_helper.GDAL_ENV)
print(f'SCL crop: {r.returncode} (exists: {os.path.exists(scl_crop)})')

if os.path.exists(scl_crop):
    # Check SLC values
    r_info = subprocess.run(['gdalinfo', '-json', '-stats', scl_crop],
        capture_output=True, text=True, timeout=30, env=ndvi_helper.GDAL_ENV)
    if r_info.returncode == 0:
        info = json.loads(r_info.stdout)
        bands = info.get('bands', [])
        print(f'SCL bands: {len(bands)}')
        if bands:
            b = bands[0]
            print(f'SCL stats: min={b.get("minimum")} max={b.get("maximum")} mean={b.get("mean")}')
            print(f'SCL size: {b.get("size")}')

# Step 2: create cloud mask
cloud_raw = os.path.join(ndvi_dir, f'{base_name}_cloud.tif')
r_mask = subprocess.run(['gdal_calc.py', '-A', scl_crop,
    '--outfile', cloud_raw, '--calc',
    '((A==8)+(A==9)+(A==10))>0',
    '--NoDataValue', '0', '--type', 'Byte', '--overwrite'],
    capture_output=True, text=True, timeout=60, env=ndvi_helper.GDAL_ENV)
print(f'Cloud mask: {r_mask.returncode} (exists: {os.path.exists(cloud_raw)})')
if r_mask.stderr:
    print(f'  stderr: {r_mask.stderr[:200]}')

if os.path.exists(cloud_raw):
    r_info = subprocess.run(['gdalinfo', '-json', '-stats', cloud_raw],
        capture_output=True, text=True, timeout=30, env=ndvi_helper.GDAL_ENV)
    if r_info.returncode == 0:
        info = json.loads(r_info.stdout)
        bands = info.get('bands', [])
        if bands:
            b = bands[0]
            print(f'Cloud mask stats: min={b.get("minimum")} max={b.get("maximum")} mean={b.get("mean")}')

# Step 3: clip to zone polygon
cutline = os.path.join(ndvi_dir, f'{base_name}_cutline.gpkg')
subprocess.run(['ogr2ogr', '-f', 'GPKG', '-makevalid', '-nln', 'cutline',
    cutline, ndvi_helper.GPKG_PATH, 'geozones', '-where', f"zone_id='{zone_id}'"],
    capture_output=True, text=True, timeout=30)

cloud_clipped = os.path.join(ndvi_dir, f'{base_name}_cloud_clip.tif')
r_cc = subprocess.run(['gdalwarp', '-cutline', cutline, '-crop_to_cutline',
    cloud_raw, cloud_clipped],
    capture_output=True, text=True, timeout=60, env=ndvi_helper.GDAL_ENV)
print(f'Cloud clip: {r_cc.returncode} (exists: {os.path.exists(cloud_clipped)})')

if os.path.exists(cloud_clipped):
    r_info = subprocess.run(['gdalinfo', '-json', '-stats', cloud_clipped],
        capture_output=True, text=True, timeout=30, env=ndvi_helper.GDAL_ENV)
    if r_info.returncode == 0:
        info = json.loads(r_info.stdout)
        bands = info.get('bands', [])
        if bands:
            b = bands[0]
            print(f'Clipped cloud mask: min={b.get("minimum")} max={b.get("maximum")} mean={b.get("mean")} valid={b.get("valid_percent")}')

# Cleanup
for f in [scl_crop, cloud_raw, cutline, cloud_clipped]:
    if os.path.exists(f): os.remove(f)
