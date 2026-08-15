# Fix STAC bbox order + sort order in ndvi_helper.py
with open('/home/basegnss/rtkbase/web_app/ndvi_helper.py', 'r') as f:
    c = f.read()

# Fix 1: STAC bbox order [west, south, east, north]
old1 = "    # Planetary Computer expects [lat, lon, lat, lon] order\n    pc_bbox = [bbox[1], bbox[0], bbox[3], bbox[2]]"
new1 = "    # STAC API expects [west, south, east, north] = [lon_min, lat_min, lon_max, lat_max]\n    pc_bbox = [bbox[0], bbox[1], bbox[2], bbox[3]]"

if old1 in c:
    c = c.replace(old1, new1)
    print("Fix 1 applied (bbox order)")
else:
    print("Fix 1: NOT FOUND")

# Fix 2: sort order - matching UTM first, then by datetime descending
old2 = "    results.sort(key=lambda r: (0 if r['tile'][:2].lstrip('0') == str(target_utm) else 1, r['datetime'] or ''), reverse=True)"
new2 = "    results.sort(key=lambda r: r['datetime'] or '', reverse=True)\n    results.sort(key=lambda r: 0 if r['tile'][:2].lstrip('0') == str(target_utm) else 1)"

if old2 in c:
    c = c.replace(old2, new2)
    print("Fix 2 applied (sort order)")
else:
    print("Fix 2: NOT FOUND")

with open('/home/basegnss/rtkbase/web_app/ndvi_helper.py', 'w') as f:
    f.write(c)
print("Done")
