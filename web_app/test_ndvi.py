import sys, os, json
sys.path.insert(0, '/home/basegnss/rtkbase/web_app')
import ndvi_helper

# Test with one zone
result = ndvi_helper.calc_ndvi_for_zone('zone_1779852290')
print('\n=== Result ===')
print(json.dumps(result, indent=2, default=str))
