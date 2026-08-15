import sys
sys.path.insert(0, "/home/basegnss/rtkbase/web_app")
import ndvi_helper
b04, b08, sd = ndvi_helper._find_best_tile_and_date([30.7, 52.85, 30.8, 52.92])
print(f"B04: {b04}")
print(f"B08: {b08}")
print(f"Date: {sd}")
