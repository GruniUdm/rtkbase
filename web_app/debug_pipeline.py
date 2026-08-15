import sys
sys.path.insert(0, "/home/basegnss/rtkbase/web_app")
import ndvi_helper, subprocess, os, json

# Manually run each step for a zone
zone_id = "zone_1779722414"
zone = ndvi_helper._read_zone_from_gpkg(zone_id)
poly = zone["polygon"]
bounds = [min(p[0] for p in poly), min(p[1] for p in poly), max(p[0] for p in poly), max(p[1] for p in poly)]
print(f"WGS84 bounds: {bounds}")

# Find tile
b04_url, b08_url, scene_date = ndvi_helper._find_best_tile_and_date(bounds)
print(f"B04: {b04_url}")
print(f"B08: {b08_url}")
print(f"Date: {scene_date}")

# UTM bbox
utm_zone = ndvi_helper._utms_from_bounds(bounds)
bbox_utm = ndvi_helper._bbox_wgs84_to_utm(bounds, utm_zone)
print(f"UTM zone: {utm_zone}, bbox: {bbox_utm}")

# Crop B04
import tempfile
tmp = tempfile.mkdtemp()
b04_crop = os.path.join(tmp, "b04.tif")
r = subprocess.run(["gdal_translate", "-projwin",
    str(bbox_utm[0]), str(bbox_utm[1]),
    str(bbox_utm[2]), str(bbox_utm[3]),
    "-projwin_srs", f"EPSG:326{utm_zone}",
    "-of", "GTiff", b04_url, b04_crop],
    capture_output=True, text=True, timeout=180)
print(f"gdal_translate B04: rc={r.returncode}, stderr={r.stderr[:200]}")
if os.path.exists(b04_crop):
    r_info = subprocess.run(["gdalinfo", "-stats", b04_crop], capture_output=True, text=True, timeout=10)
    for line in r_info.stdout.split("\n"):
        if "Minimum" in line or "Maximum" in line or "Mean" in line or "Size" in line:
            print(f"  {line.strip()}")

# Cleanup
import shutil
shutil.rmtree(tmp, ignore_errors=True)
