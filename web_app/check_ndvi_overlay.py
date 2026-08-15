import urllib.request, sys, os
from osgeo import gdal
import numpy as np

url = 'http://localhost:80/api/ndvi/overlay/zone_1779852290.png'
png_path = '/tmp/test_ndvi_overlay.png'

try:
    urllib.request.urlretrieve(url, png_path)
    print('Downloaded: {} bytes'.format(os.path.getsize(png_path)))
    
    ds = gdal.Open(png_path)
    if ds:
        print('Bands: {} Size: {}x{}'.format(ds.RasterCount, ds.RasterXSize, ds.RasterYSize))
        if ds.RasterCount >= 4:
            alpha = ds.GetRasterBand(4).ReadAsArray()
            print('Alpha unique: {}'.format(sorted(set(alpha.ravel()))))
            alpha_0 = int((alpha == 0).sum())
            alpha_255 = int((alpha == 255).sum())
            print('Alpha=0: {} ({:.1f}%)'.format(alpha_0, 100*alpha_0/alpha.size))
            print('Alpha=255: {} ({:.1f}%)'.format(alpha_255, 100*alpha_255/alpha.size))
        else:
            print('No alpha band: {} bands'.format(ds.RasterCount))
        ds = None
    
    os.remove(png_path)
except Exception as e:
    print('Error: {}'.format(e))
