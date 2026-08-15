import subprocess, os, json, sys
import numpy as np
from osgeo import gdal

sys.path.insert(0, '/home/basegnss/rtkbase/web_app')
import ndvi_helper

env = ndvi_helper.GDAL_ENV
gpkg = "/home/basegnss/rtkbase/data/tracks.gpkg"
ndvi_dir = "/home/basegnss/rtkbase/data/ndvi"
zone_id = "zone_1779852290"
utm_zone = 39

# Create UTM cutline
utm_cutline = os.path.join(ndvi_dir, "test_cutline_utm.gpkg")
r = subprocess.run(["ogr2ogr", "-f", "GPKG", "-makevalid", "-t_srs", f"EPSG:326{utm_zone}", "-nln", "cutline",
    utm_cutline, gpkg, "geozones", "-where", f'zone_id="{zone_id}"'],
    capture_output=True, text=True, timeout=30)
print(f"ogr2ogr rc={r.returncode}")

r2 = subprocess.run(["ogrinfo", "-al", "-so", utm_cutline], capture_output=True, text=True)
print(f"Cutline: {r2.stdout[:500]}")

# Create test raster
test_ndvi = os.path.join(ndvi_dir, "test_ndvi_raw.tif")
drv = gdal.GetDriverByName("GTiff")
ds = drv.Create(test_ndvi, 100, 100, 1, gdal.GDT_Float32)
ds.SetProjection(f"EPSG:326{utm_zone}")
gt = (589000.0, 10.0, 0.0, 6261500.0, 0.0, -10.0)
ds.SetGeoTransform(gt)
arr = np.random.rand(100, 100).astype(np.float32)
ds.GetRasterBand(1).WriteArray(arr)
ds = None
print("Test raster created")

# Test gdalwarp with UTM cutline - WITHOUT -crop_to_cutline first
clipped = os.path.join(ndvi_dir, "test_clipped_utm.tif")
r3 = subprocess.run(["gdalwarp", "-cutline", utm_cutline,
    "-dstalpha", "-of", "GTiff", test_ndvi, clipped],
    capture_output=True, text=True, timeout=60, env=env)
print(f"gdalwarp (no crop) rc={r3.returncode} stderr={r3.stderr[:300]}")

if os.path.exists(clipped):
    ds = gdal.Open(clipped)
    if ds and ds.RasterCount >= 2:
        alpha = ds.GetRasterBand(2).ReadAsArray()
        print(f"Alpha (no crop): min={alpha.min()} max={alpha.max()} mean={alpha.mean():.2f}")
        print(f"  Unique: {sorted(set(alpha.ravel()))}")
    ds = None
    os.remove(clipped)

# Test with -crop_to_cutline
clipped2 = os.path.join(ndvi_dir, "test_clipped_utm2.tif")
r4 = subprocess.run(["gdalwarp", "-cutline", utm_cutline, "-crop_to_cutline",
    "-dstalpha", "-of", "GTiff", test_ndvi, clipped2],
    capture_output=True, text=True, timeout=60, env=env)
print(f"gdalwarp (crop) rc={r4.returncode} stderr={r4.stderr[:300]}")

if os.path.exists(clipped2):
    ds = gdal.Open(clipped2)
    if ds and ds.RasterCount >= 2:
        alpha = ds.GetRasterBand(2).ReadAsArray()
        print(f"Alpha (crop): min={alpha.min()} max={alpha.max()} mean={alpha.mean():.2f}")
        print(f"  Unique: {sorted(set(alpha.ravel()))}")
    ds = None
    os.remove(clipped2)

# Also test with original WGS84 cutline
wgs84_cutline = os.path.join(ndvi_dir, "test_cutline_wgs84.gpkg")
r5 = subprocess.run(["ogr2ogr", "-f", "GPKG", "-makevalid", "-nln", "cutline",
    wgs84_cutline, gpkg, "geozones", "-where", f'zone_id="{zone_id}"'],
    capture_output=True, text=True, timeout=30)
print(f"WGS84 ogr2ogr rc={r5.returncode}")

clipped3 = os.path.join(ndvi_dir, "test_clipped_wgs84.tif")
r6 = subprocess.run(["gdalwarp", "-cutline", wgs84_cutline, "-crop_to_cutline",
    "-dstalpha", "-of", "GTiff", test_ndvi, clipped3],
    capture_output=True, text=True, timeout=60, env=env)
print(f"gdalwarp WGS84 rc={r6.returncode} stderr={r6.stderr[:300]}")

if os.path.exists(clipped3):
    ds = gdal.Open(clipped3)
    if ds and ds.RasterCount >= 2:
        alpha = ds.GetRasterBand(2).ReadAsArray()
        print(f"Alpha (WGS84): min={alpha.min()} max={alpha.max()} mean={alpha.mean():.2f}")
        print(f"  Unique: {sorted(set(alpha.ravel()))}")
    ds = None
    os.remove(clipped3)

# Cleanup
for f in [utm_cutline, test_ndvi, wgs84_cutline]:
    if os.path.exists(f): os.remove(f)
print("Done")
