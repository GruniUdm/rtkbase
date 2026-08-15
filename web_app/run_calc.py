import sys
sys.path.insert(0, '/home/basegnss/rtkbase/web_app')
import ndvi_helper
result = ndvi_helper.calc_ndvi_for_zone('zone_1779852290')
print('Result:', result)
