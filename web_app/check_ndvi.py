import sqlite3, sys
sys.path.insert(0, '/home/basegnss/rtkbase/web_app')

db = '/home/basegnss/rtkbase/data/tracks.gpkg'
con = sqlite3.connect(db)
cur = con.cursor()

print('=== Current NDVI scenes per zone ===')
cur.execute('SELECT z.id, z.name, COUNT(n.zone_id) as cnt FROM geozones z LEFT JOIN ndvi_scenes_v2 n ON z.id = n.zone_id GROUP BY z.id ORDER BY z.name')
for zid, zname, cnt in cur.fetchall():
    print(f'  Zone {zid} ({zname}): {cnt} scenes')

print()
print('=== Latest scene per zone ===')
cur.execute('SELECT n.zone_id, z.name, n.scene_date, n.mean_ndvi, n.max_ndvi, n.cloud_cover FROM ndvi_scenes_v2 n JOIN geozones z ON n.zone_id = z.id WHERE n.scene_date = (SELECT MAX(n2.scene_date) FROM ndvi_scenes_v2 n2 WHERE n2.zone_id = n.zone_id) ORDER BY z.name')
for zid, zname, sdate, mean, mx, cloud in cur.fetchall():
    print(f'  {zname}: {sdate} mean={mean:.4f} max={mx:.4f} cloud={cloud:.2f}%')

con.close()
