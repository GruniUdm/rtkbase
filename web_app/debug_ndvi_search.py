import subprocess, json, time, sys
sys.path.insert(0, '/home/basegnss/rtkbase/web_app')
import ndvi_helper

# Test with Скотомогильник zone
zone = ndvi_helper._read_zone_from_gpkg('zone_1779852290')
print("Zone:", zone['name'])
polygon = zone['polygon']
bounds = [
    min(p[1] for p in polygon),
    min(p[0] for p in polygon),
    max(p[1] for p in polygon),
    max(p[0] for p in polygon),
]
print("Bounds:", bounds)

# 1. Test STAC search
print("\n=== STAC search (last 60 days) ===")
results = ndvi_helper._stac_search(bounds)
if results:
    print(f"Found {len(results)} scenes")
    for r in results[:10]:
        print(f"  {r['datetime'][:10]} cloud={r['cloud']}% tile={r['tile']} UTM={r['tile'][:2]}")
else:
    print("NO RESULTS")

# 2. Test _find_best_tile_and_date
print("\n=== _find_best_tile_and_date ===")
b04, b08, scl, sd = ndvi_helper._find_best_tile_and_date(bounds)
if b04:
    print(f"Best scene: {sd}")
    print(f"  B04: {b04[:80]}...")
    print(f"  B08: {b08[:80]}...")
else:
    print("No suitable scene found")

# 3. Test SAS token
print("\n=== SAS token ===")
token = ndvi_helper._get_sas_token()
if token:
    print(f"Token: {token[:30]}... (len={len(token)})")
else:
    print("TOKEN FAILED")

# 4. Test direct STAC API call 
print("\n=== Direct STAC API call ===")
lon_center = (bounds[0] + bounds[2]) / 2
lat_center = (bounds[1] + bounds[3]) / 2
target_utm = int((lon_center + 180) / 6) + 1
print(f"Center: {lat_center:.4f}, {lon_center:.4f} (UTM {target_utm})")

pc_bbox = [bounds[1], bounds[0], bounds[3], bounds[2]]
body = {
    'collections': ['sentinel-2-l2a'],
    'bbox': pc_bbox,
    'datetime': '2026-05-01T00:00:00Z/2026-06-30T23:59:59Z',
    'limit': 5,
    'query': {'eo:cloud_cover': {'lt': 30}},
    'fields': {'include': ['id', 'properties.datetime', 'properties.eo:cloud_cover', 'bbox']},
    'sortby': [{'field': 'properties.datetime', 'direction': 'desc'}]
}
r = subprocess.run(['curl', '-s', '--connect-timeout', '30', '-m', '60', '-X', 'POST', 
    'https://planetarycomputer.microsoft.com/api/stac/v1/search',
    '-H', 'Content-Type: application/json', '-d', json.dumps(body)],
    capture_output=True, text=True, timeout=90)
if r.returncode == 0:
    data = json.loads(r.stdout)
    features = data.get('features', [])
    print(f"Direct STAC: {len(features)} features")
    for f in features[:5]:
        props = f['properties']
        print(f"  {props.get('datetime','')[:10]} cloud={props.get('eo:cloud_cover','?')}%")
else:
    print(f"STAC curl failed: {r.stderr[:200]}")
    print(f"stdout: {r.stdout[:200]}")
