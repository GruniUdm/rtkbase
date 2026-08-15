import sys
sys.path.insert(0, "/home/basegnss/rtkbase/web_app")
import ndvi_helper, json

# Get the zone polygon and bounds
zone = ndvi_helper._read_zone_from_gpkg("zone_1779722414")
poly = zone["polygon"]
minx = min(p[0] for p in poly)
miny = min(p[1] for p in poly)
maxx = max(p[0] for p in poly)
maxy = max(p[1] for p in poly)
print(f"POLYGON bounds: [{minx}, {miny}, {maxx}, {maxy}]")
print(f"CORRECT lon/lat: [{minx}, {miny}, {maxx}, {maxy}]")

# Search with correct bbox
b04, b08, sd = ndvi_helper._find_best_tile_and_date([minx, miny, maxx, maxy])
print(f"\nResult: B04={b04}")
print(f"B08={b08}")
print(f"Date: {sd}")

# Also extract tile from URL
if b04:
    parts = b04.split("/")
    tile = parts[-4]
    utm = tile[:2]
    print(f"\nTile: {tile}, UTM zone: {utm}")
