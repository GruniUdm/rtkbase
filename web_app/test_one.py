import sys
sys.path.insert(0, "/home/basegnss/rtkbase/web_app")
import ndvi_helper

# Test first zone
result = ndvi_helper.calc_ndvi_for_zone("zone_1779722414")
print(f"Result: {result}")
