import sqlite3
conn = sqlite3.connect("/home/basegnss/rtkbase/data/tracks.gpkg")
rows = conn.execute("SELECT zone_id, scene_date FROM ndvi_scenes_v2 ORDER BY scene_date DESC LIMIT 20").fetchall()
conn.close()
for r in rows:
    print(r[0][:20], r[1])
