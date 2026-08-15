import subprocess, os, json, sys, sqlite3
from osgeo import gdal
import numpy as np
sys.path.insert(0, '/home/basegnss/rtkbase/web_app')
import ndvi_helper

ndvi_dir = ndvi_helper.NDVI_DIR
gpkg = ndvi_helper.GPKG_PATH
env = ndvi_helper.GDAL_ENV
zone_id = 'zone_1779852290'

# Read zone polygon
conn = sqlite3.connect(gpkg)
row = conn.execute("SELECT name, polygon FROM geozones WHERE zone_id=?", (zone_id,)).fetchone()
conn.close()
polygon_wgs84 = json.loads(row[1])

# Calculate bbox in UTM 39
bounds = [min(p[1] for p in polygon_wgs84), min(p[0] for p in polygon_wgs84), max(p[1] for p in polygon_wgs84), max(p[0] for p in polygon_wgs84)]
print('WGS84 bounds:', bounds)

# Get UTM bounds
lonlats = [(bounds[0], bounds[1]), (bounds[2], bounds[3])]
xs, ys = [], []
for lon, lat in lonlats:
    r = subprocess.run(['gdaltransform', '-s_srs', 'EPSG:4326', '-t_srs', 'EPSG:32639'],
        input=f'{lon} {lat}', capture_output=True, text=True, timeout=10)
    pts = r.stdout.strip().split()
    xs.append(float(pts[0]))
    ys.append(float(pts[1]))
margin = 50
bbox_utm = [min(xs)-margin, max(ys)+margin, max(xs)+margin, min(ys)-margin]
print('UTM bbox:', bbox_utm)

# Crop B04
b04_crop = os.path.join(ndvi_dir, 'debug_b04_crop.tif')
b04_url = 'https://sentinel-s2-l2a.s3.amazonaws.com/tiles/39/V/WC/2026/6/24/0/R10m/B04.jp2'
r = subprocess.run(['gdal_translate', '-projwin', str(bbox_utm[0]), str(bbox_utm[1]), str(bbox_utm[2]), str(bbox_utm[3]),
    '-projwin_srs', 'EPSG:32639', '-of', 'GTiff', b04_url, b04_crop],
    capture_output=True, text=True, timeout=180, env=env)
print('B04 crop rc={} exists={}'.format(r.returncode, os.path.exists(b04_crop)))

if not os.path.exists(b04_crop):
    print('Failed to get B04, exiting')
    sys.exit(1)

# Fake NDVI
test_ndvi = os.path.join(ndvi_dir, 'debug_ndvi_raw.tif')
r = subprocess.run(['gdal_calc.py', '-A', b04_crop, '--outfile', test_ndvi,
    '--calc', 'A.astype(float)/20000 - 0.5', '--type', 'Float32', '--overwrite'],
    capture_output=True, text=True, timeout=120, env=env)
print('Fake NDVI rc={} exists={}'.format(r.returncode, os.path.exists(test_ndvi)))

# Cutline
valid_cutline = os.path.join(ndvi_dir, 'debug_cutline.gpkg')
r = subprocess.run(['ogr2ogr', '-f', 'GPKG', '-makevalid', '-nln', 'cutline',
    valid_cutline, gpkg, 'geozones', '-where', 'zone_id="{}"'.format(zone_id)],
    capture_output=True, text=True, timeout=30)
print('cutline rc={}'.format(r.returncode))

# gdalwarp with cutline
clipped = os.path.join(ndvi_dir, 'debug_clipped.tif')
r = subprocess.run(['gdalwarp', '-cutline', valid_cutline, '-crop_to_cutline',
    '-dstalpha', '-of', 'GTiff', test_ndvi, clipped],
    capture_output=True, text=True, timeout=120, env=env)
print('gdalwarp rc={}'.format(r.returncode))

# Check result
if os.path.exists(clipped):
    ds = gdal.Open(clipped)
    if ds:
        print('Clipped: bands={} size={}x{}'.format(ds.RasterCount, ds.RasterXSize, ds.RasterYSize))
        if ds.RasterCount >= 2:
            b2 = ds.GetRasterBand(2)
            alpha = b2.ReadAsArray()
            print('Alpha: type={} min={} max={} mean={:.2f}'.format(
                gdal.GetDataTypeName(b2.DataType), alpha.min(), alpha.max(), alpha.mean()))
            uv = sorted(set(alpha.ravel()))
            print('  Unique: {}'.format(uv[:20]))
        b1 = ds.GetRasterBand(1)
        ndvi = b1.ReadAsArray()
        print('NDVI: type={} min={:.4f} max={:.4f}'.format(
            gdal.GetDataTypeName(b1.DataType), ndvi.min(), ndvi.max()))
        # Count zero alpha pixels
        print('  Alpha=0 count: {} ({:.1f}%)'.format(
            int((alpha==0).sum()), 100 * (alpha==0).sum() / alpha.size))
        ds = None

# Cleanup
for f in [b04_crop, test_ndvi, valid_cutline, clipped]:
    if os.path.exists(f): os.remove(f)
print('Done')
