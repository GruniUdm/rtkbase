import subprocess, os, json

env = os.environ.copy()
env["GDAL_SKIP"] = "DODS"
env["CPL_VSIL_CURL_ALLOWED_EXTENSIONS"] = ".jp2,.tif"
env["GDAL_DISABLE_READDIR_ON_OPEN"] = "TRUE"

# Step 1: Download bands
coords = ["466019.466200166", "5818892.20371283", "466840.543969444", "5816480.14299507"]
b04_f = "/tmp/test_b04.tif"
b08_f = "/tmp/test_b08.tif"

url04 = "https://sentinel-s2-l2a.s3.amazonaws.com/tiles/40/U/DD/2026/5/26/0/R10m/B04.jp2"
url08 = "https://sentinel-s2-l2a.s3.amazonaws.com/tiles/40/U/DD/2026/5/26/0/R10m/B08.jp2"

for url, out in [(url04, b04_f), (url08, b08_f)]:
    subprocess.run(["gdal_translate", "-projwin"] + coords + ["-projwin_srs", "EPSG:32640", "-of", "GTiff", url, out],
        capture_output=True, timeout=180, env=env)

# Step 2: gdal_calc NDVI
ndvi_raw = "/tmp/test_ndvi_raw.tif"
calc_cmd = ["gdal_calc.py", "-A", b04_f, "-B", b08_f,
    "--outfile", ndvi_raw,
    "--calc", "(B.astype(float)-A.astype(float))/(B.astype(float)+A.astype(float)+1e-10)",
    "--NoDataValue", "-9999", "--type", "Float32", "--overwrite"]
r = subprocess.run(calc_cmd, capture_output=True, text=True, timeout=300, env=env)
print(f"gdal_calc: rc={r.returncode} exists={os.path.exists(ndvi_raw)}")
if os.path.exists(ndvi_raw):
    info = json.loads(subprocess.run(["gdalinfo", "-json", "-stats", ndvi_raw], capture_output=True, text=True, timeout=10).stdout)
    b = info["bands"][0]
    print(f"  size={info['size']} min={b.get('minimum')} max={b.get('maximum')} mean={b.get('mean')}")
    os.remove(ndvi_raw)

# Cleanup
for f in [b04_f, b08_f]:
    if os.path.exists(f): os.remove(f)
