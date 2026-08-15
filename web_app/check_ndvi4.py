import sqlite3
db = '/home/basegnss/rtkbase/data/tracks.gpkg'
con = sqlite3.connect(db)
cur = con.cursor()

print('=== geozones full info ===')
cur.execute('SELECT fid, id, zone_id, name FROM geozones')
rows = cur.fetchall()
for fid, zid, zone_id_text, name in rows:
    print(f'  fid={fid} id={zid} zone_id={zone_id_text} name={name}')

# Check ndvi scenes data for one zone
print('\n=== Скотомогильник scenes ===')
cur.execute('SELECT zone_id, scene_date, mean_ndvi, max_ndvi FROM ndvi_scenes_v2 WHERE zone_id = (SELECT zone_id FROM geozones WHERE name="Скотомогильник") ORDER BY scene_date')
rows = cur.fetchall()
for zid, sdate, mean, mx in rows:
    print(f'  {sdate} mean={mean} max={mx}')

con.close()
