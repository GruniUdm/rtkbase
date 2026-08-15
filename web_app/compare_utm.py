import sys
sys.path.insert(0, "/home/basegnss/rtkbase/web_app")
import ndvi_helper

# Exact same call as in calc_ndvi_for_zone
bounds = [56.5009158, 52.4983388, 56.509844, 52.5181885]
utm_zone = ndvi_helper._utms_from_bounds(bounds)
print(f"utm_zone: {utm_zone}")

bbox_utm = list(ndvi_helper._bbox_wgs84_to_utm(bounds, utm_zone))
print(f"bbox_utm: {bbox_utm}")
