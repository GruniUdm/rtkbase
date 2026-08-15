import sys
sys.path.insert(0, "/home/basegnss/rtkbase/web_app")
import ndvi_helper, subprocess, json

# For zone_1779722414 at ~56.5?E, 52.5?N
bounds = [56.5009158, 52.4983388, 56.509844, 52.5181885]
print(f"Bounds (lon_min, lat_min, lon_max, lat_max): {bounds}")

# UTM zone from centroid
center_lon = (bounds[0] + bounds[2]) / 2
utm_zone = int((center_lon + 180) / 6) + 1
print(f"Center lon: {center_lon}, UTM zone: {utm_zone}")

# Transform bounds to UTM
srs = f"EPSG:326{utm_zone}"
coords = [
    f"{bounds[0]} {bounds[1]}",
    f"{bounds[2]} {bounds[1]}",
    f"{bounds[2]} {bounds[3]}",
    f"{bounds[0]} {bounds[3]}",
]
xs, ys = [], []
for c in coords:
    r = subprocess.run(["gdaltransform", "-s_srs", "EPSG:4326", "-t_srs", srs],
        input=c, capture_output=True, text=True, timeout=10)
    if r.returncode == 0:
        parts = r.stdout.strip().split()
        if len(parts) >= 2:
            xs.append(float(parts[0]))
            ys.append(float(parts[1]))
print(f"UTM xs: {xs}")
print(f"UTM ys: {ys}")
print(f"UTM bbox: [{min(xs)}, {max(ys)}, {max(xs)}, {min(ys)}]")
