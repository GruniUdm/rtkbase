import sqlite3, tempfile, os, sys
sys.path.insert(0, '/home/basegnss/rtkbase/web_app')
from osgeo import gdal
import numpy as np
import ndvi_helper

zone_id = 'zone_1779852290'
gpkg = ndvi_helper.GPKG_PATH

# Check stored BLOB
conn = sqlite3.connect(gpkg)
row = conn.execute('SELECT file_path, scene_date, length(raster_data), min_ndvi, max_ndvi, mean_ndvi FROM ndvi_scenes_v2 WHERE zone_id=? ORDER BY scene_date DESC LIMIT 1', (zone_id,)).fetchone()

if row:
    tif_path, scene_date, blob_len, min_ndvi, max_ndvi, mean_ndvi = row
    print('Stored overlay for {}:'.format(zone_id))
    print('  scene_date:', scene_date)
    print('  file_path:', tif_path)
    print('  raster_data length:', blob_len)
    print('  NDVI: min={:.4f} max={:.4f} mean={:.4f}'.format(min_ndvi, max_ndvi, mean_ndvi))
    
    if blob_len and blob_len > 0:
        blob = conn.execute('SELECT raster_data FROM ndvi_scenes_v2 WHERE zone_id=? ORDER BY scene_date DESC LIMIT 1', (zone_id,)).fetchone()[0]
        conn.close()
        
        if blob:
            with tempfile.NamedTemporaryFile(suffix='.tif', delete=False) as f:
                f.write(blob)
                tmp_path = f.name
            print('\nTemporary TIF:', tmp_path)
            
            ds = gdal.Open(tmp_path)
            if ds:
                print('  bands={} size={}x{}'.format(ds.RasterCount, ds.RasterXSize, ds.RasterYSize))
                for i in range(ds.RasterCount):
                    b = ds.GetRasterBand(i+1)
                    arr = b.ReadAsArray()
                    print('  Band {}: {}..{} type={}'.format(i+1, int(arr.min()), int(arr.max()),
                        gdal.GetDataTypeName(b.DataType)))
                
                if ds.RasterCount >= 4:
                    alpha = ds.GetRasterBand(4).ReadAsArray()
                    uv = sorted(set(alpha.ravel()))
                    print('\nAlpha:')
                    print('  Unique: {}'.format(uv))
                    print('  =0: {} ({:.1f}%)'.format(int((alpha==0).sum()), 100*(alpha==0).sum()/alpha.size))
                    print('  =255: {} ({:.1f}%)'.format(int((alpha==255).sum()), 100*(alpha==255).sum()/alpha.size))
                    
                    # Also check band 2 (should be green, might have cloud mask)
                    b2 = ds.GetRasterBand(2).ReadAsArray()
                    b3 = ds.GetRasterBand(3).ReadAsArray()
                    print('\nCheck for gray (cloud) pixels:')
                    gray = (b2 == 180) & (b3 == 180)
                    print('  Gray pixels (R=180,G=180): {} ({:.1f}%)'.format(
                        int(gray.sum()), 100*gray.sum()/gray.size))
                ds = None
            else:
                print('  Failed to open TIF')
            
            os.remove(tmp_path)
    else:
        conn.close()
        print('  No BLOB data')
else:
    conn.close()
    print('No stored overlay for', zone_id)
