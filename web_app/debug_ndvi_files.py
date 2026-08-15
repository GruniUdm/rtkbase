import subprocess, os, json, sys
from osgeo import gdal
sys.path.insert(0, '/home/basegnss/rtkbase/web_app')
import ndvi_helper

ndvi_dir = ndvi_helper.NDVI_DIR
zone_id = "zone_1779852290"

files = [f for f in os.listdir(ndvi_dir) if zone_id in f]
print(f"Files for {zone_id}:")
for f in sorted(files):
    sz = os.path.getsize(os.path.join(ndvi_dir, f))
    fpath = os.path.join(ndvi_dir, f)
    ds = gdal.Open(fpath)
    if ds:
        info = {"size": f"{ds.RasterXSize}x{ds.RasterYSize}", "bands": ds.RasterCount}
        if ds.RasterCount >= 2:
            try:
                alpha = ds.GetRasterBand(2).ReadAsArray()
                info["alpha_unique"] = sorted(set(alpha.ravel()))[:10]
                info["alpha_all_255"] = int((alpha == 255).all())
                info["alpha_any_0"] = int((alpha == 0).any())
            except Exception as e:
                info["alpha_error"] = str(e)
        else:
            try:
                b = ds.GetRasterBand(1)
                arr = b.ReadAsArray()
                info["b1_minmax"] = f"{float(arr.min()):.4f}-{float(arr.max()):.4f}"
            except Exception as e:
                info["b1_error"] = str(e)
        ds = None
    else:
        info = {"error": "cannot open"}
    print(f"  {f}: size={sz} {json.dumps(info, default=str)}")
