import sqlite3, sys
sys.path.insert(0, '/home/basegnss/rtkbase/web_app')
import ndvi_helper

db = '/home/basegnss/rtkbase/data/tracks.gpkg'
con = sqlite3.connect(db)
cur = con.cursor()

cur.execute('SELECT zone_id, name FROM geozones ORDER BY name')
zones = cur.fetchall()

for zid_text, zname in zones:
    print(f'\n=== {zname} ({zid_text}) ===')
    zone = ndvi_helper._read_zone_from_gpkg(zid_text)
    if not zone:
        print('  FAILED to read zone')
        continue
    polygon = zone['polygon']
    bounds = [
        min(p[1] for p in polygon),
        min(p[0] for p in polygon),
        max(p[1] for p in polygon),
        max(p[0] for p in polygon),
    ]
    print(f'  Bounds: {[round(b, 4) for b in bounds]}')
    
    # STAC search
    results = ndvi_helper._stac_search(bounds)
    if results:
        print(f'  Found {len(results)} scenes')
        for r in results[:8]:
            target_utm = ndvi_helper._utms_from_bounds(bounds)
            match = r['tile'][:2].lstrip('0') == str(target_utm)
            match_str = '✓' if match else '✗'
            print(f'  {match_str} {r["datetime"][:10]} cloud={r["cloud"]:.2f}% tile={r["tile"]} UTM={r["tile"][:2]}')
    else:
        print('  NO RESULTS from STAC')
    
    # Best tile
    b04, b08, scl, sd = ndvi_helper._find_best_tile_and_date(bounds)
    if b04:
        print(f'  Best scene: {sd}')
    else:
        print('  No suitable scene')

con.close()
