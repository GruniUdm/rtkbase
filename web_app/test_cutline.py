import subprocess, json

# Create a test cutline and examine it
valid_cutline = '/home/basegnss/rtkbase/data/ndvi/test_cutline.gpkg'
gpkg = '/home/basegnss/rtkbase/data/tracks.gpkg'

# Create cutline
r = subprocess.run(['ogr2ogr', '-f', 'GPKG', '-makevalid', '-nln', 'cutline',
    valid_cutline, gpkg, 'geozones', '-where', "zone_id='zone_1779852290'"],
    capture_output=True, text=True, timeout=30)
print(f'ogr2ogr: rc={r.returncode}')

# List layers
r = subprocess.run(['ogrinfo', valid_cutline], capture_output=True, text=True, timeout=10)
print(f'Layers: {r.stdout}')

# Get geometry info
r = subprocess.run(['ogrinfo', '-json', valid_cutline, 'cutline'],
    capture_output=True, text=True, timeout=10)
if r.returncode == 0:
    info = json.loads(r.stdout)
    layers = info.get('layers', [])
    for layer in layers:
        print(f"Layer: {layer.get('name')}")
        print(f"  CRS: {layer.get('crs', {}).get('wkt', 'unknown')[:80]}")
        features = layer.get('features', [])
        print(f"  Features: {len(features)}")
        for f in features[:2]:
            geom = f.get('geometry', {})
            print(f"  Geometry type: {geom.get('type')}")

# Check extent
r = subprocess.run(['ogrinfo', '-so', valid_cutline, 'cutline'],
    capture_output=True, text=True, timeout=10)
print(f'\nExtent:')
for line in r.stdout.split('\n'):
    if 'Extent' in line or 'Geometry' in line or 'CRS' in line:
        print(f'  {line.strip()}')

import os
os.remove(valid_cutline)
