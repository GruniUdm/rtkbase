"""Coverage path planner for agricultural fields.
Generates boustrophedon (lawnmower) pattern paths for field coverage.
Features: boundary offset (swath_width/2), double-arc turns for tight radii,
concave polygon routing with boundary offset.
"""
import math
import json
from osgeo import ogr, osr

_utm_cache = {}
def _latlon_to_utm(lat, lon):
    key = (int(lat), int(lon))
    if key in _utm_cache:
        ref, ct = _utm_cache[key]
    else:
        zone = int((lon + 180) / 6) + 1
        if lat < 0:
            zone += 100  # South
        ref = osr.SpatialReference()
        ref.ImportFromEPSG(4326)
        utm = osr.SpatialReference()
        utm.SetWellKnownGeogCS('WGS84')
        utm.SetUTM(zone, lat >= 0)
        ct = osr.CoordinateTransformation(ref, utm)
        _utm_cache[key] = (ref, ct)
    x, y, _ = ct.TransformPoint(lon, lat, 0)
    return x, y

def _utm_to_latlon(easting, northing, zone=None):
    if not zone:
        zone = 39  # Default zone
    ref = osr.SpatialReference()
    ref.ImportFromEPSG(4326)
    utm = osr.SpatialReference()
    utm.SetWellKnownGeogCS('WGS84')
    utm.SetUTM(zone, True)
    ct = osr.CoordinateTransformation(utm, ref)
    lon, lat, _ = ct.TransformPoint(easting, northing, 0)
    return lat, lon


def _dist_to_segment(px, py, ax, ay, bx, by):
    dx = bx - ax
    dy = by - ay
    denom = dx * dx + dy * dy
    if denom > 0:
        t = ((px - ax) * dx + (py - ay) * dy) / denom
        t = max(0.0, min(1.0, t))
    else:
        t = 0.0
    nx = ax + t * dx
    ny = ay + t * dy
    return (px - nx) ** 2 + (py - ny) ** 2, nx, ny


def snap_to_polygon(points_4326, lat, lon):
    """Snap a point to the nearest polygon boundary edge."""
    lats = [p[0] for p in points_4326]
    lons = [p[1] for p in points_4326]
    clat = sum(lats) / len(lats)
    clon = sum(lons) / len(lons)
    rlat = math.radians(clat)
    scale = 111320.0
    coslat = math.cos(rlat)

    def to_local(la, lo):
        return (lo - clon) * scale * coslat, (la - clat) * scale

    local_pts = [to_local(la, lo) for la, lo in points_4326]
    px, py = to_local(lat, lon)

    best_d2 = float('inf')
    best_nx, best_ny = px, py

    for i in range(len(local_pts)):
        ax, ay = local_pts[i]
        bx, by = local_pts[(i + 1) % len(local_pts)]
        d2, nx, ny = _dist_to_segment(px, py, ax, ay, bx, by)
        if d2 < best_d2:
            best_d2, best_nx, best_ny = d2, nx, ny

    dist_m = math.sqrt(best_d2)
    snapped = dist_m <= 0.25
    lon_res = best_nx / (scale * coslat) + clon
    lat_res = best_ny / scale + clat
    return lat_res, lon_res, round(dist_m, 3), snapped


def _generate_turn_pts(A, B, i, R, n_arc=16):
    """Generate a single 180-degree arc turn from A to B."""
    pts = []
    cx, cy = A[0], A[1] + R
    if i % 2 == 1:
        for j in range(n_arc + 1):
            t = j / n_arc
            theta = -1.57079632679 - 3.14159265359 * t
            pts.append((cx + R * math.cos(theta), cy + R * math.sin(theta)))
    else:
        for j in range(n_arc + 1):
            t = j / n_arc
            theta = -1.57079632679 + 3.14159265359 * t
            pts.append((cx + R * math.cos(theta), cy + R * math.sin(theta)))
    arc_end = pts[-1]
    for j in range(1, 6):
        t = j / 6
        pts.append((arc_end[0] + t * (B[0] - arc_end[0]),
                    arc_end[1] + t * (B[1] - arc_end[1])))
    return pts


def _generate_double_arc(A, B, i, R, n_arc=16):
    """Arc-straight-arc turn: quarter-circle → straight → quarter-circle.
    Used when turning_radius < swath_width/2 for smoother path.
    Both quarter-circles turn in the same direction (left for even, right for odd)
    with a straight segment between them of length W - 2R.
    """
    total_y = B[1] - A[1]
    straight_len = total_y - 2 * R
    half = max(2, n_arc // 2)

    pts = []
    c1x, c1y = A[0], A[1] + R

    if i % 2 == 1:
        # Odd: approach heading west, right-turn (CW) up, then east
        for j in range(half + 1):
            t = j / half
            theta = -1.57079632679 - 1.57079632679 * t
            pts.append((c1x + R * math.cos(theta), c1y + R * math.sin(theta)))

        mid = pts[-1]
        sx, sy = mid[0], mid[1] + straight_len
        for j in range(1, half + 1):
            t = j / half
            pts.append((mid[0] + t * (sx - mid[0]),
                        mid[1] + t * (sy - mid[1])))

        c2x, c2y = A[0], sy
        for j in range(1, half + 1):
            t = j / half
            theta = 3.14159265359 - 1.57079632679 * t
            pts.append((c2x + R * math.cos(theta), c2y + R * math.sin(theta)))
    else:
        # Even: approach heading east, left-turn (CCW) up, then west
        for j in range(half + 1):
            t = j / half
            theta = -1.57079632679 + 1.57079632679 * t
            pts.append((c1x + R * math.cos(theta), c1y + R * math.sin(theta)))

        mid = pts[-1]
        sx, sy = mid[0], mid[1] + straight_len
        for j in range(1, half + 1):
            t = j / half
            pts.append((mid[0] + t * (sx - mid[0]),
                        mid[1] + t * (sy - mid[1])))

        c2x, c2y = A[0], sy
        for j in range(1, half + 1):
            t = j / half
            theta = 0.0 + 1.57079632679 * t
            pts.append((c2x + R * math.cos(theta), c2y + R * math.sin(theta)))

    # Blend from arc end to B (handles case where B.x != A.x)
    arc_end = pts[-1]
    if abs(arc_end[0] - B[0]) > 1e-10 or abs(arc_end[1] - B[1]) > 1e-10:
        for j in range(1, 6):
            t = j / 6
            pts.append((arc_end[0] + t * (B[0] - arc_end[0]),
                        arc_end[1] + t * (B[1] - arc_end[1])))
    return pts


def _fillet_ring(pts, R, n_arc=8):
    """Round the corners of a closed ring with fillets of radius R."""
    if R <= 0 or len(pts) < 3:
        return list(pts)
    out = []
    m = len(pts)
    for i in range(m):
        p_prev = pts[(i - 1) % m]
        p_cur = pts[i]
        p_next = pts[(i + 1) % m]
        dx1, dy1 = p_cur[0] - p_prev[0], p_cur[1] - p_prev[1]
        dx2, dy2 = p_next[0] - p_cur[0], p_next[1] - p_cur[1]
        len1 = math.sqrt(dx1 * dx1 + dy1 * dy1)
        len2 = math.sqrt(dx2 * dx2 + dy2 * dy2)
        if len1 < 0.01 or len2 < 0.01:
            out.append(p_cur)
            continue
        u1 = (dx1 / len1, dy1 / len1)
        u2 = (dx2 / len2, dy2 / len2)
        dot = (-u1[0]) * u2[0] + (-u1[1]) * u2[1]
        dot = max(-1.0, min(1.0, dot))
        alpha = math.acos(dot)
        if alpha > 3.13159 or alpha < 0.01:
            out.append(p_cur)
            continue
        d = R / math.tan(alpha / 2)
        max_d = min(len1, len2) * 0.5
        if d > max_d:
            d = max_d
        T1 = (p_cur[0] - u1[0] * d, p_cur[1] - u1[1] * d)
        T2 = (p_cur[0] + u2[0] * d, p_cur[1] + u2[1] * d)
        bis = (-u1[0] + u2[0], -u1[1] + u2[1])
        bl = math.sqrt(bis[0] * bis[0] + bis[1] * bis[1])
        if bl < 0.001:
            out.append(p_cur)
            continue
        bu = (bis[0] / bl, bis[1] / bl)
        cd = R / math.sin(alpha / 2)
        Cx = p_cur[0] + bu[0] * cd
        Cy = p_cur[1] + bu[1] * cd
        t1 = math.atan2(T1[1] - Cy, T1[0] - Cx)
        t2 = math.atan2(T2[1] - Cy, T2[0] - Cx)
        cross = u1[0] * u2[1] - u1[1] * u2[0]
        if cross > 0:
            if t2 < t1:
                t2 += 6.28318530718
        else:
            if t2 > t1:
                t2 -= 6.28318530718
        nn = max(2, n_arc)
        for j in range(nn + 1):
            tt = j / nn
            th = t1 + (t2 - t1) * tt
            out.append((Cx + R * math.cos(th), Cy + R * math.sin(th)))
    return out


def _offset_point(ring, idx, offset, n):
    """Calculate a point offset perpendicular to the boundary ring."""
    rx, ry = ring.GetX(idx), ring.GetY(idx)
    pi = idx - 1 if idx > 0 else n - 2
    ni = idx + 1 if idx < n - 1 else 0
    pix, piy = ring.GetX(pi), ring.GetY(pi)
    nix, niy = ring.GetX(ni), ring.GetY(ni)
    e1x, e1y = rx - pix, ry - piy
    e2x, e2y = nix - rx, niy - ry
    el1 = math.sqrt(e1x * e1x + e1y * e1y) or 1
    el2 = math.sqrt(e2x * e2x + e2y * e2y) or 1
    n1x, n1y = -e1y / el1, e1x / el1
    n2x, n2y = -e2y / el2, e2x / el2
    nx = (n1x + n2x) * 0.5
    ny = (n1y + n2y) * 0.5
    nl = math.sqrt(nx * nx + ny * ny) or 1
    return (rx + nx / nl * offset, ry + ny / nl * offset)


def _clip_path_to_polygon(path_pts, poly):
    """Clip path points to ensure they stay within the polygon."""
    if not path_pts or not poly:
        return path_pts

    result = [path_pts[0]]

    for i in range(1, len(path_pts)):
        pt = path_pts[i]
        prev = result[-1]

        # Skip identical consecutive points
        if abs(pt[0] - prev[0]) < 1e-10 and abs(pt[1] - prev[1]) < 1e-10:
            continue

        line = ogr.Geometry(ogr.wkbLineString)
        line.AddPoint(prev[0], prev[1])
        line.AddPoint(pt[0], pt[1])
        line.FlattenTo2D()
        inter = poly.Intersection(line)

        if inter and not inter.IsEmpty():
            inter.FlattenTo2D()
            gt = inter.GetGeometryType()

            if gt == ogr.wkbPoint:
                x, y = inter.GetX(0), inter.GetY(0)
                if abs(x - prev[0]) > 1e-10 or abs(y - prev[1]) > 1e-10:
                    result.append((x, y))
            elif gt in (ogr.wkbLineString, ogr.wkbLineString25D):
                n = inter.GetPointCount()
                start = 1 if (n > 1 and abs(inter.GetX(0) - prev[0]) < 0.001
                              and abs(inter.GetY(0) - prev[1]) < 0.001) else 0
                for k in range(start, n):
                    p = (inter.GetX(k), inter.GetY(k))
                    if not result or abs(p[0] - result[-1][0]) > 1e-10 or abs(p[1] - result[-1][1]) > 1e-10:
                        result.append(p)
            elif gt in (ogr.wkbMultiLineString, ogr.wkbMultiLineString25D):
                for j in range(inter.GetGeometryCount()):
                    g = inter.GetGeometryRef(j)
                    g.FlattenTo2D()
                    ng = g.GetPointCount()
                    gstart = 1 if (j == 0 and ng > 1
                                   and abs(g.GetX(0) - prev[0]) < 0.001
                                   and abs(g.GetY(0) - prev[1]) < 0.001) else 0
                    for k in range(gstart, ng):
                        p = (g.GetX(k), g.GetY(k))
                        if not result or abs(p[0] - result[-1][0]) > 1e-10 or abs(p[1] - result[-1][1]) > 1e-10:
                            result.append(p)
            elif gt == ogr.wkbMultiPoint:
                for j in range(inter.GetGeometryCount()):
                    p = inter.GetGeometryRef(j)
                    p.FlattenTo2D()
                    x, y = p.GetX(0), p.GetY(0)
                    if abs(x - prev[0]) > 1e-10 or abs(y - prev[1]) > 1e-10:
                        result.append((x, y))

    # Second pass: snap any remaining outside points to boundary
    ring = poly.GetGeometryRef(0)
    nring = ring.GetPointCount()
    cleaned = [result[0]]
    for i in range(1, len(result)):
        p = result[i]
        pt_g = ogr.Geometry(ogr.wkbPoint)
        pt_g.AddPoint(p[0], p[1])
        pt_g.FlattenTo2D()
        if poly.Contains(pt_g) or poly.Intersects(pt_g):
            cleaned.append(p)
        else:
            # Snap to nearest point on boundary ring
            best_d2 = float('inf')
            best = p
            for j in range(nring - 1):
                x1, y1 = ring.GetX(j), ring.GetY(j)
                x2, y2 = ring.GetX(j + 1), ring.GetY(j + 1)
                edx, edy = x2 - x1, y2 - y1
                elen2 = edx * edx + edy * edy
                if elen2 < 1e-20:
                    d2 = (p[0] - x1) ** 2 + (p[1] - y1) ** 2
                    if d2 < best_d2:
                        best_d2 = d2
                        best = (x1, y1)
                else:
                    t = ((p[0] - x1) * edx + (p[1] - y1) * edy) / elen2
                    t = max(0.0, min(1.0, t))
                    px, py = x1 + t * edx, y1 + t * edy
                    d2 = (p[0] - px) ** 2 + (p[1] - py) ** 2
                    if d2 < best_d2:
                        best_d2 = d2
                        best = (px, py)
            if abs(best[0] - cleaned[-1][0]) > 1e-10 or abs(best[1] - cleaned[-1][1]) > 1e-10:
                cleaned.append(best)

    if len(cleaned) < 2:
        return path_pts
    return cleaned


def _route_via_boundary(poly, p1, p2, offset=0):
    """Route from p1 to p2 within the polygon, following boundary if needed
    with optional offset from the boundary.
    """
    ring = poly.GetGeometryRef(0)
    n = ring.GetPointCount()
    if n < 3:
        return [p1, p2]

    line = ogr.Geometry(ogr.wkbLineString)
    line.AddPoint(p1[0], p1[1])
    line.AddPoint(p2[0], p2[1])
    line.FlattenTo2D()
    if poly.Contains(line):
        return [p1, p2]

    boundary_pts = {}
    for label, pt in [('p1', p1), ('p2', p2)]:
        for direction, sign in [('up', 1), ('down', -1)]:
            test_line = ogr.Geometry(ogr.wkbLineString)
            test_line.AddPoint(pt[0], pt[1])
            test_line.AddPoint(pt[0], pt[1] + sign * 10000.0)
            test_line.FlattenTo2D()
            inter = poly.Intersection(test_line)
            if inter and not inter.IsEmpty():
                inter.FlattenTo2D()
                gt = inter.GetGeometryType()
                pts = []
                if gt in (ogr.wkbLineString, ogr.wkbLineString25D):
                    pts = [(inter.GetX(k), inter.GetY(k))
                           for k in range(inter.GetPointCount())]
                elif gt in (ogr.wkbMultiLineString, ogr.wkbMultiLineString25D):
                    for j in range(inter.GetGeometryCount()):
                        g = inter.GetGeometryRef(j)
                        g.FlattenTo2D()
                        for k in range(g.GetPointCount()):
                            pts.append((g.GetX(k), g.GetY(k)))
                if pts:
                    if sign > 0:
                        boundary_pts[label + '_' + direction] = max(
                            pts, key=lambda p: p[1])
                    else:
                        boundary_pts[label + '_' + direction] = min(
                            pts, key=lambda p: p[1])

    def _boundary_path(ring, start_pt, end_pt, clockwise=True):
        def closest_idx(pt):
            best, best_i = float('inf'), 0
            for i in range(n):
                rx, ry = ring.GetX(i), ring.GetY(i)
                d2 = (pt[0] - rx) ** 2 + (pt[1] - ry) ** 2
                if d2 < best:
                    best, best_i = d2, i
            return best_i

        si = closest_idx(start_pt)
        ei = closest_idx(end_pt)
        result = [start_pt]
        step = 1 if clockwise else -1
        i = (si + step) % (n - 1)
        while i != ei:
            if offset > 0:
                result.append(_offset_point(ring, i, offset, n - 1))
            else:
                result.append((ring.GetX(i), ring.GetY(i)))
            i = (i + step) % (n - 1)
        result.append(end_pt)
        return result

    best_path = None
    best_len = float('inf')

    for bpt1_key, bpt1 in [('p1_up', boundary_pts.get('p1_up')),
                            ('p1_down', boundary_pts.get('p1_down'))]:
        if bpt1 is None:
            continue
        for bpt2_key, bpt2 in [('p2_up', boundary_pts.get('p2_up')),
                                ('p2_down', boundary_pts.get('p2_down'))]:
            if bpt2 is None:
                continue
            if ('_up' in bpt1_key) != ('_up' in bpt2_key):
                continue
            for clockwise in [True, False]:
                bp = _boundary_path(ring, bpt1, bpt2, clockwise)
                full = [p1, bpt1] + bp[1:] + [bpt2, p2]
                length = 0.0
                for k in range(1, len(full)):
                    dx = full[k][0] - full[k - 1][0]
                    dy = full[k][1] - full[k - 1][1]
                    length += math.sqrt(dx * dx + dy * dy)
                if length < best_len:
                    best_len = length
                    best_path = full

    if best_path:
        return best_path
    return [p1, p2]


def generate_coverage_path(points_4326, swath_width, angle_deg,
                           turning_radius=0, offset=0, boundary_pass=False):
    """Generate a boustrophedon coverage path for a field polygon.

    Args:
        points_4326: List of (lat, lon) polygon vertices
        swath_width: Width of each implement pass in meters
        angle_deg: Direction of swaths in degrees (0=north, 90=east)
        turning_radius: Vehicle turning radius in meters (0 = no smoothing)
        offset: Additional boundary offset beyond swath_width/2
        boundary_pass: If True, add an outer boundary perimeter pass

    Returns:
        GeoJSON FeatureCollection with LineString path, or None if failed
    """
    lats = [p[0] for p in points_4326]
    lons = [p[1] for p in points_4326]
    clat = sum(lats) / len(lats)
    clon = sum(lons) / len(lons)

    rlat = math.radians(clat)
    scale = 111320.0
    coslat = math.cos(rlat)

    local_pts = []
    for lat, lon in points_4326:
        x = (lon - clon) * scale * coslat
        y = (lat - clat) * scale
        local_pts.append((x, y))

    rot = math.radians(angle_deg - 90)

    def _rotate(x, y, a):
        c = math.cos(a)
        s = math.sin(a)
        return x * c - y * s, x * s + y * c

    rotated_pts = [_rotate(x, y, rot) for x, y in local_pts]

    ring = ogr.Geometry(ogr.wkbLinearRing)
    for x, y in rotated_pts:
        ring.AddPoint(x, y)
    ring.CloseRings()
    poly = ogr.Geometry(ogr.wkbPolygon)
    poly.AddGeometry(ring)
    poly.FlattenTo2D()
    poly = poly.MakeValid()
    orig_poly = poly

    # Apply boundary offset: swath lines should be at least swath_width/2
    # from the polygon boundary for complete coverage without overlap.
    total_offset = max(0, swath_width / 2.0 + offset)
    if total_offset > 0:
        buffered = poly.Buffer(-total_offset)
        if buffered is not None and not buffered.IsEmpty() and buffered.IsValid():
            poly = buffered

    # If buffer made polygon empty, fall back to original
    if poly.IsEmpty():
        poly = orig_poly

    env = poly.GetEnvelope()
    minx, maxx, miny, maxy = env[0], env[1], env[2], env[3]

    # Shortcut: if buffered polygon is too small even for one swath,
    # use original but offset starting y
    if maxy - miny < swath_width * 0.1:
        poly = orig_poly
        env = poly.GetEnvelope()
        minx, maxx, miny, maxy = env[0], env[1], env[2], env[3]

    # Generate swath lines
    swaths = []
    y = miny
    while y <= maxy:
        line = ogr.Geometry(ogr.wkbLineString)
        line.AddPoint(minx - swath_width, y)
        line.AddPoint(maxx + swath_width, y)
        line.FlattenTo2D()
        clipped = poly.Intersection(line)
        if clipped and not clipped.IsEmpty():
            clipped.FlattenTo2D()
            gtype = clipped.GetGeometryType()
            if gtype in (ogr.wkbLineString, ogr.wkbLineString25D):
                pts = [(clipped.GetX(i), clipped.GetY(i))
                       for i in range(clipped.GetPointCount())]
                if len(pts) >= 2:
                    swaths.append(pts)
            elif gtype in (ogr.wkbMultiLineString, ogr.wkbMultiLineString25D):
                segments = []
                for j in range(clipped.GetGeometryCount()):
                    g = clipped.GetGeometryRef(j)
                    g.FlattenTo2D()
                    pts = [(g.GetX(i), g.GetY(i))
                           for i in range(g.GetPointCount())]
                    if len(pts) >= 2:
                        segments.append(pts)
                if not segments:
                    continue
                segments.sort(key=lambda seg: min(p[0] for p in seg))
                if len(segments) == 1:
                    swaths.append(segments[0])
                else:
                    swaths.append(('group', segments, y))
        y += swath_width

    if not swaths:
        return None

    # Determine arc strategy: double-arc if turning_radius < swath_width/2
    min_turn_radius = swath_width / 2.0
    use_double_arc = turning_radius > 0 and turning_radius < min_turn_radius
    effective_R = turning_radius if turning_radius > 0 else 0

    path_points = []
    for i, swath in enumerate(swaths):
        # Handle grouped segments from concave polygons
        if isinstance(swath, tuple) and swath[0] == 'group':
            segments = swath[1]
            if i % 2 == 0:
                segments = list(reversed(segments))
            for seg_i, seg in enumerate(segments):
                if seg_i % 2 == 0:
                    seg = list(reversed(seg))
                if not path_points:
                    path_points.extend(seg)
                else:
                    A = path_points[-1]
                    B = seg[0]
                    # Gap in concave polygon - route via boundary
                    if abs(A[1] - B[1]) < 0.01 and abs(A[0] - B[0]) > 0.01:
                        boundary_route = _route_via_boundary(
                            orig_poly, A, B, total_offset)
                        if boundary_route:
                            path_points.extend(boundary_route[1:])
                        else:
                            path_points.append(path_points[-1])
                            path_points.append(B)
                    else:
                        if effective_R > 0:
                            if use_double_arc:
                                turn_pts = _generate_double_arc(
                                    A, B, i + seg_i, effective_R)
                            else:
                                turn_pts = _generate_turn_pts(
                                    A, B, i + seg_i, effective_R)
                            path_points.extend(turn_pts[1:])
                        else:
                            path_points.append(path_points[-1])
                            path_points.append(B)
                    path_points.extend(seg[1:])
            continue

        # Regular single-segment swath
        if i % 2 == 0:
            swath = list(reversed(swath))
        if path_points:
            if effective_R > 0:
                A = path_points[-1]
                B = swath[0]
                if use_double_arc:
                    turn_pts = _generate_double_arc(A, B, i, effective_R)
                else:
                    turn_pts = _generate_turn_pts(A, B, i, effective_R)
                path_points.extend(turn_pts[1:])
                # Skip swath[0] (B) — already last point of turn_pts
                path_points.extend(swath[1:])
            else:
                path_points.append(path_points[-1])
                path_points.append(swath[0])
                path_points.extend(swath[1:])
        else:
            path_points.extend(swath)

    # Clip path to original polygon to prevent arcs from extending outside boundary
    if effective_R > 0:
        path_points = _clip_path_to_polygon(path_points, orig_poly)

    unrot = math.radians(90 - angle_deg)
    path_local = [_rotate(x, y, unrot) for x, y in path_points]

    path_4326 = []
    for x, y in path_local:
        lon = x / (scale * coslat) + clon
        lat = y / scale + clat
        path_4326.append((lat, lon))

    total_len = 0.0
    for i in range(1, len(path_local)):
        dx = path_local[i][0] - path_local[i - 1][0]
        dy = path_local[i][1] - path_local[i - 1][1]
        total_len += math.sqrt(dx * dx + dy * dy)

    # Boundary perimeter pass (additional pass around the edge)
    if boundary_pass:
        bp_dist = total_offset if total_offset > 0 else swath_width / 2.0
        bp_poly = orig_poly.Buffer(-bp_dist)
        if bp_poly and not bp_poly.IsEmpty() and bp_poly.IsValid():
            ring = bp_poly.GetGeometryRef(0)
            n = ring.GetPointCount()
            if n >= 3:
                bp_rot = [(ring.GetX(i), ring.GetY(i))
                          for i in range(n - 1)]
                if effective_R > 0:
                    bp_rot = _fillet_ring(bp_rot, effective_R)
                ex, ey = path_points[-1]
                bi = min(range(len(bp_rot)),
                         key=lambda k: (bp_rot[k][0] - ex) ** 2 +
                         (bp_rot[k][1] - ey) ** 2)
                bp_order = bp_rot[bi:] + bp_rot[:bi] + [bp_rot[bi]]
                path_points.append(bp_order[0])
                path_points.extend(bp_order[1:])
                path_points.extend(bp_order)
                # Recompute unrotated path
                path_local = [_rotate(x, y, unrot) for x, y in path_points]
                path_4326 = [(y / scale + clat,
                              x / (scale * coslat) + clon)
                             for x, y in path_local]
                total_len = 0.0
                for i in range(1, len(path_points)):
                    dx = path_local[i][0] - path_local[i - 1][0]
                    dy = path_local[i][1] - path_local[i - 1][1]
                    total_len += math.sqrt(dx * dx + dy * dy)

    coords = [[lon, lat] for lat, lon in path_4326]
    return {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": coords
            },
            "properties": {
                "num_swaths": len(swaths),
                "swath_width": swath_width,
                "angle": angle_deg,
                "total_length_m": round(total_len, 1),
                "offset_m": total_offset
            }
        }]
    }


def calculate_ab_curve(points_4326, a_lat, a_lon, b_lat, b_lon, extend_m=100):
    """Calculate AB Curve path following field boundary.

    Projects A and B onto nearest boundary edges, extracts boundary segment
    between them, extends straight beyond each endpoint along tangent.
    """
    lats = [p[0] for p in points_4326]
    lons = [p[1] for p in points_4326]
    clat = sum(lats) / len(lats)
    clon = sum(lons) / len(lons)
    rlat = math.radians(clat)
    scale = 111320.0
    coslat = math.cos(rlat)

    def to_local(la, lo):
        return (lo - clon) * scale * coslat, (la - clat) * scale

    def to_wgs84(x, y):
        return y / scale + clat, x / (scale * coslat) + clon

    local_pts = [to_local(la, lo) for la, lo in points_4326]
    n = len(local_pts)

    # Find closest vertex index for A and B
    pax, pay = to_local(a_lat, a_lon)
    pbx, pby = to_local(b_lat, b_lon)

    def closest_vertex_idx(px, py):
        best_d2 = float('inf')
        best_i = 0
        for i, (vx, vy) in enumerate(local_pts):
            d2 = (px - vx)**2 + (py - vy)**2
            if d2 < best_d2:
                best_d2 = d2
                best_i = i
        return best_i

    vi_a = closest_vertex_idx(pax, pay)
    vi_b = closest_vertex_idx(pbx, pby)

    # Walk along boundary from vi_a to vi_b (try both directions, pick shorter)
    def walk_vertices(start, end, clockwise=True):
        pts = []
        i = start
        step = 1 if clockwise else -1
        while True:
            pts.append(local_pts[i % n])
            if i % n == end:
                break
            i = (i + step) % n
            if len(pts) > n:
                break
        return pts

    cw = walk_vertices(vi_a, vi_b, True)
    ccw = walk_vertices(vi_a, vi_b, False)

    def path_length(path):
        return sum(math.sqrt((path[k][0]-path[k-1][0])**2 + (path[k][1]-path[k-1][1])**2) for k in range(1, len(path)))

    curve_local = cw if path_length(cw) <= path_length(ccw) else ccw

    # Convert curve to WGS84
    curve_pts = [to_wgs84(x, y) for x, y in curve_local]

    # Calculate tangents at endpoints
    if len(curve_local) >= 2:
        dx_a, dy_a = curve_local[1][0] - curve_local[0][0], curve_local[1][1] - curve_local[0][1]
        dx_b, dy_b = curve_local[-1][0] - curve_local[-2][0], curve_local[-1][1] - curve_local[-2][1]
    else:
        dx_a, dy_a = pbx - pax, pby - pay
        dx_b, dy_b = dx_a, dy_a

    len_a = math.sqrt(dx_a*dx_a + dy_a*dy_a) or 1
    len_b = math.sqrt(dx_b*dx_b + dy_b*dy_b) or 1
    ux_a, uy_a = dx_a/len_a, dy_a/len_a
    ux_b, uy_b = dx_b/len_b, dy_b/len_b

    # Extend beyond A (backward) and B (forward)
    ext_a = (curve_local[0][0] - ux_a * extend_m, curve_local[0][1] - uy_a * extend_m)
    ext_b = (curve_local[-1][0] + ux_b * extend_m, curve_local[-1][1] + uy_b * extend_m)

    # Full line: ext_a -> curve -> ext_b
    full_local = [ext_a] + curve_local + [ext_b]
    full_line = [to_wgs84(x, y) for x, y in full_local]

    # Curve length
    dist_m = path_length(curve_local)

    # Heading (direction from first to last curve point, 0=north)
    dx_h = curve_local[-1][0] - curve_local[0][0]
    dy_h = curve_local[-1][1] - curve_local[0][1]
    heading_deg = math.degrees(math.atan2(dx_h, dy_h))
    if heading_deg < 0:
        heading_deg += 360

    return {
        'curve_pts': [[lat, lon] for lat, lon in curve_pts],
        'ab_line': [[lat, lon] for lat, lon in full_line],
        'heading': round(heading_deg, 2),
        'dist_m': round(dist_m, 1)
    }

def generate_parallel_passes(ab_line_4326, width_m, num_passes=0, both_sides=True):
    """Generate parallel passes offset from an AB line.

    Args:
        ab_line_4326: List of (lat, lon) for the AB line
        width_m: Swath width in meters
        num_passes: Number of passes on each side (0 = auto)
        both_sides: Generate on both sides of AB line

    Returns:
        List of lists of (lat, lon) for each parallel pass
    """
    if len(ab_line_4326) < 2:
        return []

    lats = [p[0] for p in ab_line_4326]
    lons = [p[1] for p in ab_line_4326]
    clat = sum(lats) / len(lats)
    clon = sum(lons) / len(lons)
    rlat = math.radians(clat)
    scale = 111320.0
    coslat = math.cos(rlat)

    def to_local(la, lo):
        return (lo - clon) * scale * coslat, (la - clat) * scale

    def to_wgs84(x, y):
        return y / scale + clat, x / (scale * coslat) + clon

    local_line = [to_local(la, lo) for la, lo in ab_line_4326]

    # Find perpendicular direction (rotate 90 deg)
    dx = local_line[-1][0] - local_line[0][0]
    dy = local_line[-1][1] - local_line[0][1]
    line_len = math.sqrt(dx*dx + dy*dy) or 1
    # Perpendicular unit vector
    perp_x, perp_y = -dy/line_len, dx/line_len

    passes = []
    max_passes = num_passes or 10

    for side in [-1, 1] if both_sides else [1]:
        for p in range(1, max_passes + 1):
            offset = p * width_m * side
            pass_pts = [(x + perp_x * offset, y + perp_y * offset) for x, y in local_line]
            pass_wgs84 = [to_wgs84(x, y) for x, y in pass_pts]
            passes.append(pass_wgs84)

    return passes
