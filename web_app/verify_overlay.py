import sqlite3, tempfile, os, sys
sys.path.insert(0, '/home/basegnss/rtkbase/web_app')
from osgeo import gdal
import numpy as np
import ndvi_helper

zone_id = 'zone_1779852290'
gpkg = ndvi_helper.GPKG_PATH

conn = sqlite3.connect(gpkg)
row = conn.execute('SELECT file_path, scene_date, length(raster_data), min_ndvi, max_ndvi, mean_ndvi FROM ndvi_scenes_v2 WHERE zone_id=? ORDER BY scene_date DESC LIMIT 1', (zone_id,)).fetchone()
conn.close()

if row:
    tif_path, scene_date, blob_len, min_ndvi, max_ndvi, mean_ndvi = row
    print('Stored overlay: scene_date={} blob_len={}'.format(scene_date, blob_len))
    
    conn2 = sqlite3.connect(gpkg)
    blob = conn2.execute('SELECT raster_data FROM ndvi_scenes_v2 WHERE zone_id=? ORDER BY scene_date DESC LIMIT 1', (zone_id,)).fetchone()[0]
    conn2.close()
    
    if blob:
        with tempfile.NamedTemporaryFile(suffix='.tif', delete=False) as f:
            f.write(blob)
            tmp_path = f.name
        
        ds = gdal.Open(tmp_path)
        if ds and ds.RasterCount >= 4:
            print('TIF: bands={} size={}x{}'.format(ds.RasterCount, ds.RasterXSize, ds.RasterYSize))
            alpha = ds.GetRasterBand(4).ReadAsArray()
            print('Alpha unique: {}'.format(sorted(set(alpha.ravel()))))
            print('Alpha=0: {} ({:.1f}%)'.format(int((alpha==0).sum()), 100*(alpha==0).sum()/alpha.size))
            print('Alpha=255: {} ({:.1f}%)'.format(int((alpha==255).sum()), 100*(alpha==255).sum()/alpha.size))
            b2 = ds.GetRasterBand(2).ReadAsArray()
            gray = (ds.GetRasterBand(1).ReadAsArray() == 180) & (b2 == 180)
            print('Gray (cloud) pixels: {} ({:.1f}%)'.format(int(gray.sum()), 100*gray.sum()/gray.size))
        ds = None
        os.remove(tmp_path)
    else:
        print('No BLOB')
else:
    print('No overlay found')
