import sys, subprocess, os, json
sys.path.insert(0, "/home/basegnss/rtkbase/web_app")
import ndvi_helper

zone_id = "zone_1779722414"
result = ndvi_helper.calc_ndvi_for_zone(zone_id)
print(f"Result: {result}")
