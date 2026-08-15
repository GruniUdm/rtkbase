#!/usr/bin/env python3
"""Background worker: parse field sections into outline polygon rings (one per
section, area-identical to the triangle strip) and write a line-delimited JSON
cache file. Runs in its own OS process so the web server is never blocked."""
import sqlite3, json, sys, os, math

GPKG_PATH = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'tracks.gpkg'))


def _local_to_latlon_rad(ref_lat, ref_lon, e, n):
    if e == 0 and n == 0:
        return (ref_lat, ref_lon)
    earth_radius = 6378137.0
    dlat = n / earth_radius
    dlon = e / (earth_radius * math.cos(math.radians(ref_lat)))
    return (ref_lat + math.degrees(dlat), ref_lon + math.degrees(dlon))


def _section_color(sec):
    if not isinstance(sec, (list, tuple)) or len(sec) < 1:
        return None
    hdr = sec[0]
    if isinstance(hdr, (list, tuple)) and len(hdr) >= 3:
        return '#%02x%02x%02x' % tuple(int(c) & 0xFF for c in hdr[:3])
    return None


def _ring_points(sec):
    if not isinstance(sec, (list, tuple)) or len(sec) < 4:
        return None
    color = _section_color(sec)
    pts = sec[1:]
    evens = [p for p in pts[0::2] if isinstance(p, (list, tuple)) and len(p) >= 2]
    odds = [p for p in pts[1::2] if isinstance(p, (list, tuple)) and len(p) >= 2]
    if len(evens) + len(odds) < 3:
        return None
    return (color, evens, odds)


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
        print('sections_worker: field not found: %s' % name)
        sys.exit(1)

    data = json.loads(row[0])
    updated = row[1]

    boundary = data.get('boundary', {})
    polygons = boundary.get('polygons', [])
    boundary_pts = []
    if polygons:
        boundary_pts = [[p[0], p[1]] for p in (polygons[0].get('points', []) if polygons else [])
                        if isinstance(p, (list, tuple)) and len(p) >= 2]

    start_fix = data.get('field', {}).get('startFix', {})
    ref_lat = start_fix.get('lat')
    ref_lon = start_fix.get('lon')
    if ref_lat is None or ref_lon is None:
        if boundary_pts:
            ref_lat, ref_lon = boundary_pts[0][0], boundary_pts[0][1]
    if ref_lat is None:
        ref_lat = ref_lon = 0

    sections_data = data.get('sections', {})
    inner = sections_data.get('sections', []) if isinstance(sections_data, dict) else sections_data
    if not isinstance(inner, list):
        inner = []

    ring_lists = [_ring_points(sec) for sec in inner]
    total = sum(1 for r in ring_lists if r is not None)

    with open(tmp, 'w') as f:
        f.write(json.dumps({'updated': updated, 'total': total, 'version': 2}) + '\n')
        for rp in ring_lists:
            if rp is None:
                continue
            color, evens, odds = rp
            ring_pts = evens + list(reversed(odds))
            ring = []
            for p in ring_pts:
                ll = _local_to_latlon_rad(ref_lat, ref_lon, p[0], p[1])
                ring.append([ll[1], ll[0]])
            if len(ring) < 3:
                continue
            ring.append(ring[0])
            f.write(json.dumps({'color': color, 'ring': [ring]}) + '\n')

    os.replace(tmp, out_path)
    print('sections_worker: done %s, %d rings' % (name, total))


if __name__ == '__main__':
    main()
