import subprocess, os, json, sys
from osgeo import gdal
import numpy as np
sys.path.insert(0, '/home/basegnss/rtkbase/web_app')
import ndvi_helper

ndvi_dir = ndvi_helper.NDVI_DIR
gpkg = ndvi_helper.GPKG_PATH
env = ndvi_helper.GDAL_ENV
zone_id = 'zone_1779852290'

zone = ndvi_helper._read_zone_from_gpkg(zone_id)
polygon_wgs84 = zone['polygon']

bounds = [min(p[1] for p in polygon_wgs84), min(p[0] for p in polygon_wgs84),
           max(p[1] for p in polygon_wgs84), max(p[0] for p in polygon_wgs84)]
print('WGS84 bounds:', bounds)

# Get UTM bounds
lonlats = [(bounds[0], bounds[1]), (bounds[2], bounds[3])]
xs, ys = [], []
for lon, lat in lonlats:
    r = subprocess.run(['gdaltransform', '-s_srs', 'EPSG:4326', '-t_srs', 'EPSG:32639'],
        input='{} {}'.format(lon, lat), capture_output=True, text=True, timeout=10)
    pts = r.stdout.strip().split()
    xs.append(float(pts[0]))
    ys.append(float(pts[1]))
margin = 50
bbox_utm = [min(xs)-margin, max(ys)+margin, max(xs)+margin, min(ys)-margin]
print('UTM bbox:', bbox_utm)

# Crop B04 scene
b04_crop = os.path.join(ndvi_dir, 'debug_b04_crop.tif')
b04_url = 'https://sentinel-s2-l2a.s3.amazonaws.com/tiles/39/V/WC/2026/6/24/0/R10m/B04.jp2'
r = subprocess.run(['gdal_translate', '-projwin', str(bbox_utm[0]), str(bbox_utm[1]),
    str(bbox_utm[2]), str(bbox_utm[3]), '-projwin_srs', 'EPSG:32639',
    '-of', 'GTiff', b04_url, b04_crop],
    capture_output=True, text=True, timeout=180, env=env)
print('B04 crop: rc={} exists={}'.format(r.returncode, os.path.exists(b04_crop)))
if not os.path.exists(b04_crop):
    sys.exit(1)

# Create test NDVI (random)
test_ndvi = os.path.join(ndvi_dir, 'debug_ndvi_raw.tif')
r = subprocess.run(['gdal_calc.py', '-A', b04_crop, '--outfile', test_ndvi,
    '--calc', 'A.astype(float)/20000 - 0.5', '--type', 'Float32', '--overwrite'],
    capture_output=True, text=True, timeout=120, env=env)
print('Fake NDVI: rc={} exists={}'.format(r.returncode, os.path.exists(test_ndvi)))
os.remove(b04_crop)

# Create cutline (NO -t_srs, same as actual code)
valid_cutline = os.path.join(ndvi_dir, 'debug_cutline.gpkg')
r = subprocess.run(['ogr2ogr', '-f', 'GPKG', '-makevalid', '-nln', 'cutline',
    valid_cutline, gpkg, 'geozones', '-where', 'zone_id="{}"'.format(zone_id)],
    capture_output=True, text=True, timeout=30)
print('Cutline: rc={}'.format(r.returncode))

# === TEST 1: gdalwarp with -cutline WITHOUT -dstalpha ===
clipped1 = os.path.join(ndvi_dir, 'debug_clipped1.tif')
r1 = subprocess.run(['gdalwarp', '-cutline', valid_cutline, '-crop_to_cutline',
    '-of', 'GTiff', test_ndvi, clipped1],
    capture_output=True, text=True, timeout=120, env=env)
print('Test1 (no dstalpha): rc={}'.format(r1.returncode))
if os.path.exists(clipped1):
    ds = gdal.Open(clipped1)
    if ds:
        print('  bands={} type={}'.format(ds.RasterCount, gdal.GetDataTypeName(
            ds.GetRasterBand(1).DataType)))
        b1 = ds.GetRasterBand(1)
        arr = b1.ReadAsArray()
        valid = (arr != b1.GetNoDataValue()) if b1.GetNoDataValue() is not None else (arr != -9999)
        print('  valid pixels: {}'.format(int(valid.sum())))
        # Check edges for NoData
        print('  corner values: {:.4f} {:.4f} {:.4f} {:.4f}'.format(
            arr[0,0], arr[0,-1], arr[-1,0], arr[-1,-1]))
        ds = None

# === TEST 2: gdalwarp WITH -dstalpha ===
clipped2 = os.path.join(ndvi_dir, 'debug_clipped2.tif')
r2 = subprocess.run(['gdalwarp', '-cutline', valid_cutline, '-crop_to_cutline',
    '-dstalpha', '-of', 'GTiff', test_ndvi, clipped2],
    capture_output=True, text=True, timeout=120, env=env)
print('Test2 (dstalpha): rc={}'.format(r2.returncode))
if os.path.exists(clipped2):
    ds = gdal.Open(clipped2)
    if ds and ds.RasterCount >= 2:
        print('  bands={}'.format(ds.RasterCount))
        b1 = ds.GetRasterBand(1)
        b2 = ds.GetRasterBand(2)
        ndvi = b1.ReadAsArray()
        alpha = b2.ReadAsArray()
        print('  ndvi: {:.4f}..{:.4f}'.format(ndvi.min(), ndvi.max()))
        print('  alpha: {}..{} type={}'.format(alpha.min(), alpha.max(),
            gdal.GetDataTypeName(b2.DataType)))
        print('  alpha=0 count: {} ({:.1f}%)'.format(
            int((alpha==0).sum()), 100*(alpha==0).sum()/alpha.size))
        print('  alpha=255 count: {} ({:.1f}%)'.format(
            int((alpha==255).sum()), 100*(alpha==255).sum()/alpha.size))
        # Check corner ndvi values (should be nodata if outside polygon)
        print('  corner ndvi: {:.4f} {:.4f} {:.4f} {:.4f}'.format(
            ndvi[0,0], ndvi[0,-1], ndvi[-1,0], ndvi[-1,-1]))
        print('  corner alpha: {} {} {} {}'.format(
            alpha[0,0], alpha[0,-1], alpha[-1,0], alpha[-1,-1]))
        ds = None

# Check raster CRS
r = subprocess.run(['gdalsrsinfo', '-o', 'proj', test_ndvi], capture_output=True, text=True)
print('Raster CRS:', r.stdout.strip())

# Check cutline GPKG crs
r = subprocess.run(['ogrinfo', '-al', '-so', valid_cutline], capture_output=True, text=True)
print('Cutline SRS info:')
for line in r.stdout.split('\n'):
    if 'SRS' in line or 'Extent' in line or 'Geometry' in line:
        print(' ', line.strip())

# === TEST 3: gdalwarp with UTM cutline ===
utm_cutline = os.path.join(ndvi_dir, 'debug_cutline_utm.gpkg')
r = subprocess.run(['ogr2ogr', '-f', 'GPKG', '-makevalid', '-t_srs', 'EPSG:32639',
    '-nln', 'cutline', utm_cutline, gpkg, 'geozones',
    '-where', 'zone_id="{}"'.format(zone_id)],
    capture_output=True, text=True, timeout=30)
print('UTM cutline: rc={}'.format(r.returncode))

clipped3 = os.path.join(ndvi_dir, 'debug_clipped3.tif')
r3 = subprocess.run(['gdalwarp', '-cutline', utm_cutline, '-crop_to_cutline',
    '-dstalpha', '-of', 'GTiff', test_ndvi, clipped3],
    capture_output=True, text=True, timeout=120, env=env)
print('Test3 (UTM cutline): rc={}'.format(r3.returncode))
if os.path.exists(clipped3):
    ds = gdal.Open(clipped3)
    if ds and ds.RasterCount >= 2:
        b2 = ds.GetRasterBand(2)
        alpha = b2.ReadAsArray()
        print('  alpha=0: {} ({:.1f}%)  alpha=255: {} ({:.1f}%)'.format(
            int((alpha==0).sum()), 100*(alpha==0).sum()/alpha.size,
            int((alpha==255).sum()), 100*(alpha==255).sum()/alpha.size))
        ds = None

# Cleanup
for f in [test_ndvi, valid_cutline, clipped1, clipped2, utm_cutline, clipped3]:
    if os.path.exists(f): os.remove(f)
print('Done')
