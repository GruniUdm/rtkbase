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

# Crop SCL
scl_crop = os.path.join(ndvi_dir, 'debug_SCL.tif')
subprocess.run(['gdal_translate', '-projwin',
    str(bbox_utm[0]), str(bbox_utm[1]),
    str(bbox_utm[2]), str(bbox_utm[3]),
    '-projwin_srs', f'EPSG:326{utm_zone}',
    '-of', 'GTiff', scl_url, scl_crop],
    capture_output=True, text=True, timeout=180, env=ndvi_helper.GDAL_ENV)

# Test different calc expressions
expressions = [
    '((A==8)+(A==9)+(A==10))>0',          # addition approach
    '(A==8)|(A==9)|(A==10)',              # bitwise OR
    '((A==8)*1+(A==9)*1+(A==10)*1)>=1',   # multiplication approach
]

for i, expr in enumerate(expressions):
    out = os.path.join(ndvi_dir, f'debug_mask_{i}.tif')
    subprocess.run(['gdal_calc.py', '-A', scl_crop,
        '--outfile', out, '--calc', expr,
        '--NoDataValue', '0', '--type', 'Byte', '--overwrite'],
        capture_output=True, text=True, timeout=60, env=ndvi_helper.GDAL_ENV)

    r = subprocess.run(['gdalinfo', '-json', '-stats', out],
        capture_output=True, text=True, timeout=30, env=ndvi_helper.GDAL_ENV)
    if r.returncode == 0:
        info = json.loads(r.stdout)
        bands = info.get('bands', [])
        if bands:
            b = bands[0]
            print(f'Expr {i} ({expr[:30]}...): min={b.get("minimum")} max={b.get("maximum")} mean={b.get("mean")}')
    os.remove(out)

# Also test: just copy SCL values to see what's happening
copy_out = os.path.join(ndvi_dir, 'debug_copy.tif')
subprocess.run(['gdal_calc.py', '-A', scl_crop,
    '--outfile', copy_out, '--calc', 'A',
    '--NoDataValue', '0', '--type', 'Byte', '--overwrite'],
    capture_output=True, text=True, timeout=60, env=ndvi_helper.GDAL_ENV)
r = subprocess.run(['gdalinfo', '-json', '-stats', copy_out],
    capture_output=True, text=True, timeout=30, env=ndvi_helper.GDAL_ENV)
if r.returncode == 0:
    info = json.loads(r.stdout)
    bands = info.get('bands', [])
    if bands:
        b = bands[0]
        print(f'Copy A: min={b.get("minimum")} max={b.get("maximum")} mean={b.get("mean")}')
os.remove(copy_out)

os.remove(scl_crop)
