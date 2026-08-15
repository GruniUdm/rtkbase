import subprocess, json, os

cutline = "/tmp/test_crs_order.gpkg"
subprocess.run(["ogr2ogr", "-f", "GPKG", "-makevalid", "-nln", "cutline",
    cutline, "/home/basegnss/rtkbase/data/tracks.gpkg", "geozones",
    "-where", "zone_id='zone_1779722414'"],
    capture_output=True, timeout=30)

env = os.environ.copy()
env["OGR_CT_FORCE_TRADITIONAL_GIS_ORDER"] = "YES"
r = subprocess.run(["ogr2ogr", "-f", "GeoJSON", "-t_srs", "EPSG:32640",
    "/vsistdout/", cutline], capture_output=True, text=True, timeout=10, env=env)
d = json.loads(r.stdout)
geom = d["features"][0]["geometry"]["coordinates"][0]
if geom and isinstance(geom[0][0], list):
    geom = geom[0]
xs = [c[0] for c in geom]
ys = [c[1] for c in geom]
print(f"WITH var: x:[{min(xs):.2f},{max(xs):.2f}] y:[{min(ys):.2f},{max(ys):.2f}]")

r2 = subprocess.run(["ogr2ogr", "-f", "GeoJSON", "-t_srs", "EPSG:32640",
    "/vsistdout/", cutline], capture_output=True, text=True, timeout=10)
d2 = json.loads(r2.stdout)
geom2 = d2["features"][0]["geometry"]["coordinates"][0]
if geom2 and isinstance(geom2[0][0], list):
    geom2 = geom2[0]
xs2 = [c[0] for c in geom2]
ys2 = [c[1] for c in geom2]
print(f"WOUT var: x:[{min(xs2):.2f},{max(xs2):.2f}] y:[{min(ys2):.2f},{max(ys2):.2f}]")

os.remove(cutline)
