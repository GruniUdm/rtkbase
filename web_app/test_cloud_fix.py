import sys, os, json, subprocess
sys.path.insert(0, '/home/basegnss/rtkbase/web_app')
import ndvi_helper

zone_id = 'zone_1779852290'
zone = ndvi_helper._read_zone_from_gpkg(zone_id)
polygon = zone['polygon']
bounds = [min(p[1] for p in polygon), min(p[0] for p in polygon), max(p[1] for p in polygon), max(p[0] for p in polygon)]
utm_zone = ndvi_helper._utms_from_bounds(bounds)
bbox_utm = ndvi_helper._bbox_wgs84_to_utm(bounds, utm_zone)

scl_url = 'https://sentinel-s2-l2a.s3.amazonaws.com/tiles/39/V/WC/2026/6/11/0/R20m/SCL.jp2'
ndvi_dir = '/home/basegnss/rtkbase/data/ndvi'

scl_crop = os.path.join(ndvi_dir, 'debug_SCL2.tif')
subprocess.run(['gdal_translate', '-projwin',
    str(bbox_utm[0]), str(bbox_utm[1]),
    str(bbox_utm[2]), str(bbox_utm[3]),
    '-projwin_srs', f'EPSG:326{utm_zone}',
    '-of', 'GTiff', scl_url, scl_crop],
    capture_output=True, text=True, timeout=180, env=ndvi_helper.GDAL_ENV)

# Create cloud mask WITHOUT NoData
cloud_raw = os.path.join(ndvi_dir, 'debug_cloud2.tif')
subprocess.run(['gdal_calc.py', '-A', scl_crop,
    '--outfile', cloud_raw, '--calc',
    '((A==8)|(A==9)|(A==10))*1',
    '--type', 'Byte', '--overwrite'],
    capture_output=True, text=True, timeout=60, env=ndvi_helper.GDAL_ENV)

print('=== Cloud mask stats (fresh, no NoData) ===')
r = subprocess.run(['gdalinfo', '-json', '-stats', cloud_raw],
    capture_output=True, text=True, timeout=30, env=ndvi_helper.GDAL_ENV)
if r.returncode == 0:
    info = json.loads(r.stdout)
    bands = info.get('bands', [])
    if bands:
        b = bands[0]
        print(f'min={b.get("minimum")} max={b.get("maximum")} mean={b.get("mean")}')
        print(f'Cloud cover in bbox: {b.get("mean", 0) * 100:.1f}%')

# Clip to zone
cutline = os.path.join(ndvi_dir, 'debug_cutline2.gpkg')
subprocess.run(['ogr2ogr', '-f', 'GPKG', '-makevalid', '-nln', 'cutline',
    cutline, ndvi_helper.GPKG_PATH, 'geozones', '-where', f"zone_id='{zone_id}'"],
    capture_output=True, text=True, timeout=30)

cloud_clipped = os.path.join(ndvi_dir, 'debug_cloud_clip2.tif')
subprocess.run(['gdalwarp', '-cutline', cutline, '-crop_to_cutline',
    cloud_raw, cloud_clipped],
    capture_output=True, text=True, timeout=60, env=ndvi_helper.GDAL_ENV)

print('\n=== Cloud mask stats (clipped to zone) ===')
r = subprocess.run(['gdalinfo', '-json', '-stats', cloud_clipped],
    capture_output=True, text=True, timeout=30, env=ndvi_helper.GDAL_ENV)
if r.returncode == 0:
    info = json.loads(r.stdout)
    bands = info.get('bands', [])
    if bands:
        b = bands[0]
        print(f'min={b.get("minimum")} max={b.get("maximum")} mean={b.get("mean")}')
        print(f'Cloud cover in zone: {b.get("mean", 0) * 100:.1f}%')

for f in [scl_crop, cloud_raw, cutline, cloud_clipped]:
    if os.path.exists(f): os.remove(f)
