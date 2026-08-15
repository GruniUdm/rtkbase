import subprocess, os, tempfile, json
from osgeo import gdal
import numpy as np

tmpdir = tempfile.gettempdir()
tif_path = os.path.join(tmpdir, "test_rgba.tif")
png_path = os.path.join(tmpdir, "test_rgba.png")

drv = gdal.GetDriverByName("GTiff")
ds = drv.Create(tif_path, 10, 10, 4, gdal.GDT_Byte)
data = np.zeros((4, 10, 10), dtype=np.uint8)
data[0] = 255
data[3, 2:8, 2:8] = 128
for i in range(4):
    ds.GetRasterBand(i+1).WriteArray(data[i])
ds = None

r = subprocess.run(["gdal_translate", "-of", "PNG", tif_path, png_path],
    capture_output=True, timeout=30)
print("gdal_translate rc={}".format(r.returncode))

ds = gdal.Open(png_path)
if ds:
    print("PNG: bands={} size={}x{}".format(ds.RasterCount, ds.RasterXSize, ds.RasterYSize))
    for i in range(ds.RasterCount):
        b = ds.GetRasterBand(i+1)
        arr = b.ReadAsArray()
        print("  Band {}: {}..{} type={}".format(i+1, int(arr.min()), int(arr.max()),
            gdal.GetDataTypeName(b.DataType)))
    ds = None

r = subprocess.run(["gdalinfo", "-json", png_path], capture_output=True, text=True)
if r.returncode == 0:
    info = json.loads(r.stdout)
    for b in info.get("bands", []):
        print("  Band {}: CI={}".format(b["band"], b.get("colorInterpretation", "?")))

os.remove(tif_path)
os.remove(png_path)
print("Done")
