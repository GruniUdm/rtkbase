import sqlite3, subprocess, json, os, tempfile
import numpy as np
from osgeo import gdal

db = '/home/basegnss/rtkbase/data/tracks.gpkg'
con = sqlite3.connect(db)

# Get latest NDVI for Скотомогильник
row = con.execute("SELECT raster_data FROM ndvi_scenes_v2 WHERE zone_id=? ORDER BY scene_date DESC LIMIT 1",
    ('zone_1779852290',)).fetchone()
con.close()

if not row or not row[0]:
    print('No raster data found')
    exit()

# Write to temp file
tmp = tempfile.NamedTemporaryFile(suffix='.tif', delete=False)
tmp.write(row[0])
tmp.close()

ds = gdal.Open(tmp.name)
if ds is None:
    print('Failed to open')
    exit()

print(f'Bands: {ds.RasterCount}')
print(f'Size: {ds.RasterXSize} x {ds.RasterYSize}')

# Read each band
for i in range(1, ds.RasterCount + 1):
    band = ds.GetRasterBand(i)
    data = band.ReadAsArray()
    print(f'\nBand {i}:')
    print(f'  dtype={data.dtype} min={data.min()} max={data.max()} mean={data.mean():.2f}')
    if data.size < 100000:
        print(f'  unique values: {sorted(set(data.ravel()))[:20]}')

# Specifically check: how many pixels are gray (180,180,180)?
r = ds.GetRasterBand(1).ReadAsArray()
g = ds.GetRasterBand(2).ReadAsArray()
b = ds.GetRasterBand(3).ReadAsArray()
a = ds.GetRasterBand(4).ReadAsArray()

gray_pixels = (r == 180) & (g == 180) & (b == 180)
print(f'\nGray pixels: {gray_pixels.sum()} / {a.size} ({100*gray_pixels.sum()/a.size:.1f}%)')

# Transparent pixels
transparent = a == 0
print(f'Transparent pixels: {transparent.sum()} / {a.size} ({100*transparent.sum()/a.size:.1f}%)')

# Check: are gray pixels inside or outside the transparent area?
gray_and_transparent = gray_pixels & transparent
print(f'Gray + transparent: {gray_and_transparent.sum()}')

# Check: what color are the non-gray, non-transparent pixels?
valid = ~transparent & ~gray_pixels
if valid.any():
    print(f'\nSample valid pixel colors:')
    print(f'  R: {r[valid][:5]}')
    print(f'  G: {g[valid][:5]}')
    print(f'  B: {b[valid][:5]}')

ds = None
os.remove(tmp.name)
