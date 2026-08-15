import sys, subprocess, os, json
sys.path.insert(0, "/home/basegnss/rtkbase/web_app")
import ndvi_helper

zone_id = "zone_1779722414"
zone = ndvi_helper._read_zone_from_gpkg(zone_id)
poly = zone["polygon"]
zone_name = zone["name"]

# Build bounds correctly
bounds = [min(p[0] for p in poly), min(p[1] for p in poly), max(p[0] for p in poly), max(p[1] for p in poly)]
print(f"bounds: {bounds}")

# UTM
utm_zone = ndvi_helper._utms_from_bounds(bounds)
bbox_utm = list(ndvi_helper._bbox_wgs84_to_utm(bounds, utm_zone))
print(f"utm zone: {utm_zone}, utm bbox: {bbox_utm}")

# Find tile
b04_url, b08_url, sd = ndvi_helper._find_best_tile_and_date(bounds)
print(f"b04: {b04_url}")
print(f"b08: {b08_url}")
print(f"date: {sd}")

# Manual crop bands
import tempfile, re, time
ts = time.strftime("%Y%m%d_%H%M%S")
base = f"test_{ts}"

env = os.environ.copy()
env["GDAL_SKIP"] = "DODS"
env["CPL_VSIL_CURL_ALLOWED_EXTENSIONS"] = ".jp2,.tif"
env["GDAL_DISABLE_READDIR_ON_OPEN"] = "TRUE"

b04_c = f"/tmp/{base}_B04.tif"
b08_c = f"/tmp/{base}_B08.tif"

def crop(url, out):
    r = subprocess.run(["gdal_translate", "-projwin",
        str(bbox_utm[0]), str(bbox_utm[1]),
        str(bbox_utm[2]), str(bbox_utm[3]),
        "-projwin_srs", f"EPSG:326{utm_zone}",
        "-of", "GTiff", url, out],
        capture_output=True, text=True, timeout=180, env=env)
    return r.returncode == 0 and os.path.exists(out)

ok04 = crop(b04_url, b04_c)
ok08 = crop(b08_url, b08_c)
print(f"crop B04: {ok04} size={os.path.getsize(b04_c) if ok04 else 0}")
print(f"crop B08: {ok08} size={os.path.getsize(b08_c) if ok08 else 0}")

if ok04 and ok08:
    # NDVI calc
    ndvi_raw = f"/tmp/{base}_raw.tif"
    r = subprocess.run(["gdal_calc.py", "-A", b04_c, "-B", b08_c,
        "--outfile", ndvi_raw, "--calc",
        "(B.astype(float)-A.astype(float))/(B.astype(float)+A.astype(float)+1e-10)",
        "--NoDataValue", "-9999", "--type", "Float32", "--overwrite"],
        capture_output=True, text=True, timeout=300, env=env)
    print(f"gdal_calc: rc={r.returncode} exists={os.path.exists(ndvi_raw)}")
    if os.path.exists(ndvi_raw):
        info = json.loads(subprocess.run(["gdalinfo", "-json", "-stats", ndvi_raw], capture_output=True, text=True, timeout=10).stdout)
        b = info["bands"][0]
        print(f"  raw NDVI: min={b.get('minimum')} max={b.get('maximum')} mean={b.get('mean')}")
        
        # Clip to zone polygon
        cutline = f"/tmp/{base}_cutline.gpkg"
        subprocess.run(["ogr2ogr", "-f", "GPKG", "-makevalid", "-nln", "cutline",
            cutline, ndvi_helper.GPKG_PATH, "geozones", "-where", f"zone_id='{zone_id}'"],
            capture_output=True, timeout=30)
        ndvi_clip = f"/tmp/{base}_clip.tif"
        r2 = subprocess.run(["gdalwarp", "-cutline", cutline, "-crop_to_cutline",
            "-dstalpha", "-of", "GTiff", ndvi_raw, ndvi_clip],
            capture_output=True, text=True, timeout=120, env=env)
        print(f"gdalwarp: rc={r2.returncode} exists={os.path.exists(ndvi_clip)}")
        if os.path.exists(ndvi_clip):
            info2 = json.loads(subprocess.run(["gdalinfo", "-json", "-stats", ndvi_clip], capture_output=True, text=True, timeout=10).stdout)
            b2 = info2["bands"][0]
            print(f"  clipped NDVI: min={b2.get('minimum')} max={b2.get('maximum')} mean={b2.get('mean')}")
            for f_ref in [cutline, ndvi_clip]:
                if os.path.exists(f_ref): os.remove(f_ref)
        
        os.remove(ndvi_raw)
    
    for f_ref in [b04_c, b08_c]:
        if os.path.exists(f_ref): os.remove(f_ref)

print("DONE")
