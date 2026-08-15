import sys, json, time
sys.path.insert(0, '/home/basegnss/rtkbase/web_app')
import ndvi_helper

# Delete old wrong NDVI scenes from the new test (June 24 with broken cloud mask)
import sqlite3
db = '/home/basegnss/rtkbase/data/tracks.gpkg'
con = sqlite3.connect(db)
con.execute("DELETE FROM ndvi_scenes_v2 WHERE zone_id=? AND scene_date='2026-06-24'", ('zone_1779852290',))
con.execute("DELETE FROM ndvi_scenes WHERE zone_id=?", ('zone_1779852290',))
con.commit()
con.close()
print('Deleted old (broken) June 24 scene')

print('Recalculating for Скотомогильник with FIXED cloud mask...')
t0 = time.time()
result = ndvi_helper.calc_ndvi_for_zone('zone_1779852290')
elapsed = time.time() - t0
print(f'Elapsed: {elapsed:.0f}s')
print('Result:', json.dumps(result, indent=2, default=str))

# Verify the stored raster
if result.get('zone_id'):
    con = sqlite3.connect(db)
    row = con.execute("SELECT scene_date, mean_ndvi, max_ndvi, length(raster_data) FROM ndvi_scenes_v2 WHERE zone_id=? ORDER BY scene_date DESC LIMIT 1", 
        ('zone_1779852290',)).fetchone()
    if row:
        print(f'\nStored: date={row[0]} mean={row[1]:.3f} max={row[2]:.3f} blob={row[3]}B')
    con.close()
