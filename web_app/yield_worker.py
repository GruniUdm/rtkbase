#!/usr/bin/env python3
"""Background worker: parse field yield data into colored polygon patches
(one quad per pair of consecutive records for the same section) and write a
line-delimited JSON cache file. Runs in its own OS process."""
import sqlite3, json, sys, os, math

GPKG_PATH = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'tracks.gpkg'))

PULSE_GAP_THRESHOLD = 3


def _local_to_latlon_rad(ref_lat, ref_lon, e, n):
    if e == 0 and n == 0:
        return (ref_lat, ref_lon)
    earth_radius = 6378137.0
    dlat = n / earth_radius
    dlon = e / (earth_radius * math.cos(math.radians(ref_lat)))
    return (ref_lat + math.degrees(dlat), ref_lon + math.degrees(dlon))


def _argb_to_hex(argb_int):
    argb_int = int(argb_int) & 0xFFFFFFFF
    r = (argb_int >> 16) & 0xFF
    g = (argb_int >> 8) & 0xFF
    b = argb_int & 0xFF
    return '#%02x%02x%02x' % (r, g, b)


def _yield_gradient_color(yield_val, y_min, y_max):
    if yield_val < 10:
        return '#e74c3c'
    elif yield_val < 20:
        return '#e67e22'
    elif yield_val < 30:
        return '#f1c40f'
    elif yield_val < 40:
        return '#2ecc71'
    else:
        return '#1a7a3a'


def main():
    name = sys.argv[1]
    out_path = sys.argv[2]
    tmp = out_path + '.tmp'

    conn = sqlite3.connect(GPKG_PATH)
    try:
        row = conn.execute(
            'SELECT data, updated FROM field_data WHERE name=?', (name,)
        ).fetchone()
    finally:
        conn.close()

    if not row:
        print('yield_worker: field not found: %s' % name)
        sys.exit(1)

    data = json.loads(row[0])
    updated = row[1]

    yield_data = data.get('yieldData')
    if not yield_data:
        print('yield_worker: no yieldData in %s' % name)
        sys.exit(0)

    records = yield_data.get('records') or []
    if not records:
        print('yield_worker: empty yieldData in %s' % name)
        sys.exit(0)

    start_fix = data.get('field', {}).get('startFix', {})
    ref_lat = start_fix.get('lat')
    ref_lon = start_fix.get('lon')
    if ref_lat is None or ref_lon is None:
        boundary = data.get('boundary', {})
        polygons = boundary.get('polygons', [])
        if polygons:
            pts = polygons[0].get('points', [])
            if pts and isinstance(pts[0], (list, tuple)) and len(pts[0]) >= 2:
                ref_lat, ref_lon = pts[0][0], pts[0][1]
    if ref_lat is None:
        ref_lat = ref_lon = 0

    yield_vals = []
    for r in records:
        try:
            yield_vals.append(float(r.get('yieldCenHa', 0)))
        except (TypeError, ValueError):
            yield_vals.append(0)
    y_min = min(yield_vals) if yield_vals else 0
    y_max = max(yield_vals) if yield_vals else 1

    prev_by_section = {}
    quads = []

    for i, rec in enumerate(records):
        cmds = rec.get('cmds') or []
        if not cmds:
            continue
        cmd = cmds[0]
        if not isinstance(cmd, (list, tuple)) or len(cmd) < 11:
            continue

        cmd_type = int(cmd[0])
        cmd_index = int(cmd[1])
        left_x = float(cmd[4])
        left_y = float(cmd[5])
        right_x = float(cmd[7])
        right_y = float(cmd[8])
        color_argb = int(cmd[10])
        pulse = int(rec.get('pulseCount', 0))
        y_val = yield_vals[i] if i < len(yield_vals) else 0

        key = (cmd_type, cmd_index)
        prev = prev_by_section.get(key)

        if prev is not None:
            prev_pulse = prev['pulse']
            if abs(pulse - prev_pulse) > PULSE_GAP_THRESHOLD:
                prev_by_section[key] = {
                    'left_x': left_x, 'left_y': left_y,
                    'right_x': right_x, 'right_y': right_y,
                    'pulse': pulse, 'color': color_argb, 'yield': y_val
                }
                continue

            ll_tl = _local_to_latlon_rad(ref_lat, ref_lon, prev['left_x'], prev['left_y'])
            ll_tr = _local_to_latlon_rad(ref_lat, ref_lon, prev['right_x'], prev['right_y'])
            ll_br = _local_to_latlon_rad(ref_lat, ref_lon, right_x, right_y)
            ll_bl = _local_to_latlon_rad(ref_lat, ref_lon, left_x, left_y)

            ring = [
                [ll_tl[1], ll_tl[0]],
                [ll_tr[1], ll_tr[0]],
                [ll_br[1], ll_br[0]],
                [ll_bl[1], ll_bl[0]],
                [ll_tl[1], ll_tl[0]]
            ]

            avg_yield = (prev['yield'] + y_val) / 2.0
            color_aog = _argb_to_hex(prev['color'])
            color_grad = _yield_gradient_color(avg_yield, y_min, y_max)
            if color_aog == '#000000':
                color_aog = color_grad

            quads.append({
                'color_aog': color_aog,
                'color_gradient': color_grad,
                'yield': round(avg_yield, 2),
                'ring': [ring]
            })

        prev_by_section[key] = {
            'left_x': left_x, 'left_y': left_y,
            'right_x': right_x, 'right_y': right_y,
            'pulse': pulse, 'color': color_argb, 'yield': y_val
        }

    with open(tmp, 'w') as f:
        header = {
            'updated': updated,
            'total': len(quads),
            'version': 1,
            'yield_min': round(y_min, 2),
            'yield_max': round(y_max, 2)
        }
        f.write(json.dumps(header) + '\n')
        for q in quads:
            f.write(json.dumps(q) + '\n')

    os.replace(tmp, out_path)
    print('yield_worker: done %s, %d quads, yield %.1f-%.1f c/ha' % (name, len(quads), y_min, y_max))


if __name__ == '__main__':
    main()
