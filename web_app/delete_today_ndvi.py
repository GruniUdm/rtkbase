import sqlite3, os
gpkg = "/home/basegnss/rtkbase/data/tracks.gpkg"

conn = sqlite3.connect(gpkg)
conn.execute("DELETE FROM ndvi_scenes_v2 WHERE zone_id=? AND scene_date=?", ("zone_1779852290", "2026-06-30"))
conn.commit()
conn.close()
print("Deleted June 30 entry")

ndvi_dir = "/home/basegnss/rtkbase/data/ndvi"
for f in os.listdir(ndvi_dir):
    fp = os.path.join(ndvi_dir, f)
    if f.startswith("ndvi________________20260630") and not f.endswith(".aux.xml"):
        if os.path.isfile(fp):
            os.remove(fp)
            print("Removed temp:", f)
print("Done")
