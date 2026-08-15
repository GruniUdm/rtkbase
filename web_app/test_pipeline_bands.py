import subprocess, os, json

# Test with PIPELINE utm coords
coords = ["466019.466200166", "5818892.20371283", "466840.543969444", "5816480.14299507"]

env = os.environ.copy()
env["GDAL_SKIP"] = "DODS"
env["CPL_VSIL_CURL_ALLOWED_EXTENSIONS"] = ".jp2,.tif"
env["GDAL_DISABLE_READDIR_ON_OPEN"] = "TRUE"

url = "https://sentinel-s2-l2a.s3.amazonaws.com/tiles/40/U/DD/2026/5/26/0/R10m/B04.jp2"
out = "/tmp/test_pipeline_b04.tif"
r = subprocess.run(["gdal_translate", "-projwin"] + coords + ["-projwin_srs", "EPSG:32640", "-of", "GTiff", url, out],
    capture_output=True, text=True, timeout=180, env=env)
print(f"B04 pipeline: rc={r.returncode} size={os.path.getsize(out) if os.path.exists(out) else 0}")
if os.path.exists(out):
    info = json.loads(subprocess.run(["gdalinfo", "-json", "-stats", out], capture_output=True, text=True, timeout=10).stdout)
    b = info["bands"][0]
    print(f"  size={info['size']} min={b.get('minimum')} max={b.get('maximum')} mean={b.get('mean')}")
    os.remove(out)

url2 = "https://sentinel-s2-l2a.s3.amazonaws.com/tiles/40/U/DD/2026/5/26/0/R10m/B08.jp2"
out2 = "/tmp/test_pipeline_b08.tif"
r2 = subprocess.run(["gdal_translate", "-projwin"] + coords + ["-projwin_srs", "EPSG:32640", "-of", "GTiff", url2, out2],
    capture_output=True, text=True, timeout=180, env=env)
print(f"B08 pipeline: rc={r2.returncode} size={os.path.getsize(out2) if os.path.exists(out2) else 0}")
if os.path.exists(out2):
    info = json.loads(subprocess.run(["gdalinfo", "-json", "-stats", out2], capture_output=True, text=True, timeout=10).stdout)
    b = info["bands"][0]
    print(f"  size={info['size']} min={b.get('minimum')} max={b.get('maximum')} mean={b.get('mean')}")
    os.remove(out2)
