"""Tests for path_planner.py"""
import sys
sys.path.insert(0, '/home/basegnss/rtkbase/web_app')
import path_planner as pp


def test_rect():
    """Simple rectangle"""
    rect = [(56.5, 52.5), (56.5, 52.505), (56.49, 52.505), (56.49, 52.5)]
    res = pp.generate_coverage_path(rect, 24, 90, turning_radius=12)
    assert res, "Test 1 failed"
    coords = res['features'][0]['geometry']['coordinates']
    lats = [c[1] for c in coords]
    lons = [c[0] for c in coords]
    print(f'Test 1 (rect, tr=12): OK — {len(coords)} coords, len={res["features"][0]["properties"]["total_length_m"]}m')
    assert min(lats) >= 56.489, f'lat out of bounds: {min(lats)}'
    assert max(lats) <= 56.501, f'lat out of bounds: {max(lats)}'
    assert min(lons) >= 52.499, f'lon out of bounds: {min(lons)}'
    assert max(lons) <= 52.506, f'lon out of bounds: {max(lons)}'
    print(f'  clip OK: lat [{min(lats):.6f}..{max(lats):.6f}], lon [{min(lons):.6f}..{max(lons):.6f}]')


def test_double_arc():
    """Small rectangle, double-arc"""
    rect2 = [(56.5, 52.5), (56.5, 52.502), (56.49, 52.502), (56.49, 52.5)]
    res = pp.generate_coverage_path(rect2, 24, 0, turning_radius=6)
    assert res, "Test 2 failed"
    coords = res['features'][0]['geometry']['coordinates']
    print(f'Test 2 (small rect, double-arc tr=6): OK — {len(coords)} coords')


def test_no_turn():
    """No turning radius"""
    rect = [(56.5, 52.5), (56.5, 52.505), (56.49, 52.505), (56.49, 52.5)]
    res = pp.generate_coverage_path(rect, 24, 90)
    assert res, "Test 3 failed"
    coords = res['features'][0]['geometry']['coordinates']
    print(f'Test 3 (no turn): OK — {len(coords)} coords')


def test_boundary_pass():
    """Boundary perimeter pass"""
    rect = [(56.5, 52.5), (56.5, 52.505), (56.49, 52.505), (56.49, 52.5)]
    res = pp.generate_coverage_path(rect, 24, 90, turning_radius=12, boundary_pass=True)
    assert res, "Test 4 failed"
    coords = res['features'][0]['geometry']['coordinates']
    print(f'Test 4 (boundary_pass): OK — {len(coords)} coords')


def test_concave():
    """Concave polygon (L-shape)"""
    concave = [(56.5, 52.5), (56.5, 52.506), (56.495, 52.506), (56.495, 52.503), (56.49, 52.503), (56.49, 52.5)]
    res = pp.generate_coverage_path(concave, 24, 90, turning_radius=12)
    assert res, "Test 5 failed"
    coords = res['features'][0]['geometry']['coordinates']
    lats = [c[1] for c in coords]
    lons = [c[0] for c in coords]
    print(f'Test 5 (concave, tr=12): OK — {len(coords)} coords, lat [{min(lats):.6f}..{max(lats):.6f}], lon [{min(lons):.6f}..{max(lons):.6f}]')


def test_sad_polygon():
    """'Sad' test polygon"""
    sad = [(56.497, 52.508), (56.499, 52.508), (56.5, 52.51), (56.501, 52.512),
           (56.5, 52.514), (56.499, 52.516), (56.498, 52.518), (56.497, 52.52),
           (56.496, 52.522), (56.495, 52.524), (56.494, 52.525), (56.493, 52.524),
           (56.492, 52.522), (56.49, 52.515), (56.49, 52.51)]
    res = pp.generate_coverage_path(sad, 24, 90, turning_radius=12)
    assert res, "Test 6 failed"
    coords = res['features'][0]['geometry']['coordinates']
    lats = [c[1] for c in coords]
    lons = [c[0] for c in coords]
    print(f'Test 6 (Sad, tr=12): OK — {len(coords)} coords, len={res["features"][0]["properties"]["total_length_m"]}m')
    print(f'  lat [{min(lats):.6f}..{max(lats):.6f}], lon [{min(lons):.6f}..{max(lons):.6f}]')


def test_sad_offset():
    """'Sad' with offset=2"""
    sad = [(56.497, 52.508), (56.499, 52.508), (56.5, 52.51), (56.501, 52.512),
           (56.5, 52.514), (56.499, 52.516), (56.498, 52.518), (56.497, 52.52),
           (56.496, 52.522), (56.495, 52.524), (56.494, 52.525), (56.493, 52.524),
           (56.492, 52.522), (56.49, 52.515), (56.49, 52.51)]
    res = pp.generate_coverage_path(sad, 24, 90, turning_radius=12, offset=2)
    assert res, "Test 7 failed"
    coords = res['features'][0]['geometry']['coordinates']
    print(f'Test 7 (Sad, tr=12, offset=2): OK — {len(coords)} coords, len={res["features"][0]["properties"]["total_length_m"]}m')


def test_sad_angle0():
    """'Sad' with angle=0"""
    sad = [(56.497, 52.508), (56.499, 52.508), (56.5, 52.51), (56.501, 52.512),
           (56.5, 52.514), (56.499, 52.516), (56.498, 52.518), (56.497, 52.52),
           (56.496, 52.522), (56.495, 52.524), (56.494, 52.525), (56.493, 52.524),
           (56.492, 52.522), (56.49, 52.515), (56.49, 52.51)]
    res = pp.generate_coverage_path(sad, 24, 0, turning_radius=12)
    assert res, "Test 8 failed"
    coords = res['features'][0]['geometry']['coordinates']
    lats = [c[1] for c in coords]
    lons = [c[0] for c in coords]
    print(f'Test 8 (Sad, angle=0, tr=12): OK — {len(coords)} coords, len={res["features"][0]["properties"]["total_length_m"]}m')
    print(f'  lat [{min(lats):.6f}..{max(lats):.6f}], lon [{min(lons):.6f}..{max(lons):.6f}]')


def test_sad_no_turn():
    """'Sad' with no turning radius"""
    sad = [(56.497, 52.508), (56.499, 52.508), (56.5, 52.51), (56.501, 52.512),
           (56.5, 52.514), (56.499, 52.516), (56.498, 52.518), (56.497, 52.52),
           (56.496, 52.522), (56.495, 52.524), (56.494, 52.525), (56.493, 52.524),
           (56.492, 52.522), (56.49, 52.515), (56.49, 52.51)]
    res = pp.generate_coverage_path(sad, 24, 90)
    assert res, "Test 9 failed"
    coords = res['features'][0]['geometry']['coordinates']
    print(f'Test 9 (Sad, no turn): OK — {len(coords)} coords, len={res["features"][0]["properties"]["total_length_m"]}m')


if __name__ == '__main__':
    tests = [
        test_rect,
        test_double_arc,
        test_no_turn,
        test_boundary_pass,
        test_concave,
        test_sad_polygon,
        test_sad_offset,
        test_sad_angle0,
        test_sad_no_turn,
    ]
    failures = 0
    for t in tests:
        try:
            t()
        except Exception as e:
            print(f'{t.__name__}: FAIL — {e}')
            failures += 1
    print(f'\n{len(tests) - failures}/{len(tests)} passed')
    sys.exit(1 if failures else 0)
