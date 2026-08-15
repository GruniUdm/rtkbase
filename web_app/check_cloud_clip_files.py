from osgeo import gdal
import numpy as np
import os

ndvi_dir = "/home/basegnss/rtkbase/data/ndvi"

for f in sorted(os.listdir(ndvi_dir)):
    if f.endswith("_cloud_clip.tif") or f.endswith("_cloud.tif"):
        path = os.path.join(ndvi_dir, f)
        if os.path.getsize(path) > 500:
            ds = gdal.Open(path)
            if ds:
                b = ds.GetRasterBand(1)
                arr = b.ReadAsArray()
                print("File: {}".format(f.replace("ndvi________________","...")))
                print("  size={}x{} values={}..{} mean={:.2f}".format(
                    ds.RasterXSize, ds.RasterYSize, int(arr.min()), int(arr.max()), float(arr.mean())))
                uv = sorted(set(arr.ravel()))[:10]
                print("  unique: {}".format(uv))
                ds = None
