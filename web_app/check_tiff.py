import json, subprocess, os

tif = '/home/basegnss/rtkbase/data/ndvi/ndvi________________20260630_100608_0_color.tif'
if not os.path.exists(tif):
    print(f'File not found: {tif}')
    # Look for most recent
    ndvi_dir = '/home/basegnss/rtkbase/data/ndvi'
    files = sorted([f for f in os.listdir(ndvi_dir) if f.endswith('_color.tif')])
    if files:
        print('Available files:')
        for f in files[-5:]:
            print(f'  {f}')
    exit()

r = subprocess.run(['gdalinfo', '-json', tif], capture_output=True, text=True, timeout=10)
if r.returncode == 0:
    info = json.loads(r.stdout)
    bands = info.get('bands', [])
    print(f'Bands: {len(bands)}')
    for i, b in enumerate(bands):
        print(f'  Band {i+1}: type={b.get("type")} color={b.get("colorInterpretation")}')
        if b.get('computedStatistics'):
            s = b['computedStatistics']
            print(f'    min={s.get("minimum")} max={s.get("maximum")} mean={s.get("mean")}')
    print(f'Size: {info.get("sizeX")} x {info.get("sizeY")}')

# Also check if PNG conversion preserves alpha
import tempfile
out_png = os.path.join(tempfile.gettempdir(), 'test_ndvi_alpha.png')
subprocess.run(['gdal_translate', '-of', 'PNG', tif, out_png], 
    capture_output=True, text=True, timeout=30)

r2 = subprocess.run(['gdalinfo', '-json', out_png], capture_output=True, text=True, timeout=10)
if r2.returncode == 0:
    info2 = json.loads(r2.stdout)
    bands2 = info2.get('bands', [])
    print(f'\nPNG bands: {len(bands2)}')
    for i, b in enumerate(bands2):
        print(f'  Band {i+1}: type={b.get("type")} color={b.get("colorInterpretation")}')
    print(f'PNG Size: {info2.get("sizeX")} x {info2.get("sizeY")}')
os.remove(out_png)
