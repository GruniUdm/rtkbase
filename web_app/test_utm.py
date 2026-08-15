import subprocess, json, os

cutline = "/tmp/test_utm.gpkg"
subprocess.run(["ogr2ogr", "-f", "GPKG", "-makevalid", "-nln", "cutline",
    cutline, "/home/basegnss/rtkbase/data/tracks.gpkg", "geozones",
    "-where", "zone_id='zone_1779722414'"],
    capture_output=True, timeout=30)

for epsg in ["EPSG:32639", "EPSG:32640"]:
    r = subprocess.run(["ogr2ogr", "-f", "GeoJSON", "-t_srs", epsg,
        "/vsistdout/", cutline], capture_output=True, text=True, timeout=10)
    d = json.loads(r.stdout)
    geom = d["features"][0]["geometry"]["coordinates"][0]
    if geom and isinstance(geom[0][0], list):
        geom = geom[0]
    xs = [c[0] for c in geom]
    ys = [c[1] for c in geom]
    print(f"{epsg}: x:[{min(xs):.2f},{max(xs):.2f}] y:[{min(ys):.2f},{max(ys):.2f}]")

os.remove(cutline)
