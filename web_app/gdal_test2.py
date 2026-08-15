import subprocess, os

env = os.environ.copy()
env["GDAL_SKIP"] = "DODS"
env["CPL_VSIL_CURL_ALLOWED_EXTENSIONS"] = ".jp2,.tif"
env["GDAL_DISABLE_READDIR_ON_OPEN"] = "TRUE"
env["CPL_VSIL_CURL_NON_CACHED"] = "TRUE"

url = "https://sentinel-s2-l2a.s3.amazonaws.com/tiles/40/U/DD/2026/5/26/0/R10m/B04.jp2"
out = "/tmp/test_b04.tif"
r = subprocess.run(["gdal_translate", "-projwin",
    "466119.466200166", "5818792.20371283",
    "466740.543969444", "5816580.14299507",
    "-projwin_srs", "EPSG:32640",
    "-of", "GTiff", url, out],
    capture_output=True, text=True, timeout=180, env=env)
print(f"rc={r.returncode}")
if r.returncode != 0:
    print(f"stderr: {r.stderr[:500]}")
if os.path.exists(out):
    sz = os.path.getsize(out)
    print(f"Output size: {sz}")
    os.remove(out)
