import sys, os, json, time
sys.path.insert(0, '/home/basegnss/rtkbase/web_app')
import ndvi_helper

# Clean old temp files
for f in os.listdir('/home/basegnss/rtkbase/data/ndvi/'):
    if f.endswith('.tif') and ('debug_' in f or '20260630' in f):
        os.remove(os.path.join('/home/basegnss/rtkbase/data/ndvi/', f))

print('Testing calc_ndvi_for_zone for Скотомогильник...')
t0 = time.time()
result = ndvi_helper.calc_ndvi_for_zone('zone_1779852290')
elapsed = time.time() - t0
print(f'\nElapsed: {elapsed:.0f}s')
print('Result:', json.dumps(result, indent=2, default=str))
