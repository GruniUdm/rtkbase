import subprocess, os, json

# Download B04 for zone_1779722414
url_b04 = "https://sentinel-s2-l2a.s3.amazonaws.com/tiles/40/U/DD/2026/5/26/0/R10m/B04.jp2"
out = "/tmp/zone_test_b04.tif"

env = os.environ.copy()
env["GDAL_SKIP"] = "DODS"
env["CPL_VSIL_CURL_ALLOWED_EXTENSIONS"] = ".jp2,.tif"
env["GDAL_DISABLE_READDIR_ON_OPEN"] = "TRUE"

r = subprocess.run(["gdal_translate", "-projwin",
    "466119.466200166", "5818792.20371283",
    "466740.543969444", "5816580.14299507",
    "-projwin_srs", "EPSG:32640",
    "-of", "GTiff", url_b04, out],
    capture_output=True, text=True, timeout=180, env=env)
print(f"rc={r.returncode} size={os.path.getsize(out) if os.path.exists(out) else 0}")

if os.path.exists(out):
    r_info = subprocess.run(["gdalinfo", "-json", "-stats", out], capture_output=True, text=True, timeout=10)
    info = json.loads(r_info.stdout)
    b = info["bands"][0]
    print(f"B04: size={info["size"]}, min={b.get('minimum')}, max={b.get('maximum')}, mean={b.get('mean')}")
    os.remove(out)

# Also B08
url_b08 = "https://sentinel-s2-l2a.s3.amazonaws.com/tiles/40/U/DD/2026/5/26/0/R10m/B08.jp2"
out2 = "/tmp/zone_test_b08.tif"
r2 = subprocess.run(["gdal_translate", "-projwin",
    "466119.466200166", "5818792.20371283",
    "466740.543969444", "5816580.14299507",
    "-projwin_srs", "EPSG:32640",
    "-of", "GTiff", url_b08, out2],
    capture_output=True, text=True, timeout=180, env=env)
print(f"rc={r2.returncode} size={os.path.getsize(out2) if os.path.exists(out2) else 0}")

if os.path.exists(out2):
    r_info = subprocess.run(["gdalinfo", "-json", "-stats", out2], capture_output=True, text=True, timeout=10)
    info = json.loads(r_info.stdout)
    b = info["bands"][0]
    print(f"B08: size={info["size"]}, min={b.get('minimum')}, max={b.get('maximum')}, mean={b.get('mean')}")
    os.remove(out2)
