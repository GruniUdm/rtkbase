import sqlite3
db = '/home/basegnss/rtkbase/data/tracks.gpkg'
con = sqlite3.connect(db)
cur = con.cursor()

# Check actual zones
print('=== geozones ===')
cur.execute('SELECT id, name FROM geozones')
rows = cur.fetchall()
for zid, name in rows:
    print(f'  id={zid} name={name}')

# Check ndvi_scenes_v2 zones
print('\n=== ndvi_scenes_v2 zone_ids ===')
cur.execute('SELECT DISTINCT zone_id FROM ndvi_scenes_v2')
rows = cur.fetchall()
for (zid,) in rows:
    cur.execute('SELECT name FROM geozones WHERE id=?', (zid,))
    row = cur.fetchone()
    name = row[0] if row else 'NOT IN geozones'
    print(f'  {zid} → {name}')

# Check ndvi_scenes
print('\n=== ndvi_scenes zone_ids ===')
cur.execute('SELECT DISTINCT zone_id, zone_name FROM ndvi_scenes')
rows = cur.fetchall()
for zid, zname in rows:
    print(f'  {zid} → {zname}')

con.close()
