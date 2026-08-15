import sqlite3
conn = sqlite3.connect("/home/basegnss/rtkbase/data/tracks.gpkg")
zones = conn.execute("SELECT zone_id, name FROM geozones ORDER BY zone_id").fetchall()
print(f"{len(zones)} geozones:")
for z in zones:
    print(f"  {z[0]}: {z[1]}")
conn.close()
