import sqlite3
db = '/home/basegnss/rtkbase/data/tracks.gpkg'
con = sqlite3.connect(db)
cur = con.cursor()

# Check tables
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [r[0] for r in cur.fetchall()]
print('Tables:', tables)

# Check all NDVI-related tables
for t in tables:
    if 'ndvi' in t.lower():
        print(f'\n=== {t} schema ===')
        cur.execute(f'PRAGMA table_info({t})')
        cols = cur.fetchall()
        for c in cols:
            print(f'  {c[1]} ({c[2]})')

# Check geozones
print('\n=== geozones ===')
cur.execute('PRAGMA table_info(geozones)')
cols = cur.fetchall()
for c in cols:
    print(f'  {c[1]} ({c[2]})')

# Count scenes per zone
print('\n=== ndvi_scenes_v2 per zone ===')
cur.execute('SELECT zone_id, COUNT(*) as cnt FROM ndvi_scenes_v2 GROUP BY zone_id ORDER BY cnt DESC')
rows = cur.fetchall()
for zid, cnt in rows:
    cur.execute('SELECT name FROM geozones WHERE id=?', (zid,))
    row = cur.fetchone()
    name = row[0] if row else 'DELETED'
    print(f'  Zone {zid} ({name}): {cnt} scenes')

# Latest scene per zone  
print('\n=== Latest scene per zone (ndvi_scenes_v2) ===')
cur.execute('''SELECT n.zone_id, z.name, n.scene_date, n.mean_ndvi, n.max_ndvi 
FROM ndvi_scenes_v2 n JOIN geozones z ON n.zone_id = z.id 
WHERE n.scene_date = (SELECT MAX(n2.scene_date) FROM ndvi_scenes_v2 n2 WHERE n2.zone_id = n.zone_id)
ORDER BY z.name''')
rows = cur.fetchall()
for zid, name, sdate, mean, mx in rows:
    print(f'  {name}: {sdate} mean={mean} max={mx}')

con.close()
