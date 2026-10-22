// fe-headland.js — build a headland (gon) by offsetting the outer boundary
// inward. Geometry ported from aog-feldeditor 12-geometry.js (SkaFUU, MIT).
'use strict';

var FE = window.FE || (window.FE = {});

FE.headland = { previewLayer: null };

// Offset a closed ring of {e,n} points by `dist` metres to the LEFT of the
// direction of travel (ring must be CCW for inward offset of an outer
// boundary). Returns a new ring.
FE.headland.offsetRing = function (ring, dist) {
    var n = ring.length;
    if (n < 3) return null;
    var out = [];
    for (var i = 0; i < n; i++) {
        var prev = ring[(i - 1 + n) % n];
        var cur = ring[i];
        var next = ring[(i + 1) % n];
        // edge normals (left side)
        var e1 = { e: cur.e - prev.e, n: cur.n - prev.n };
        var e2 = { e: next.e - cur.e, n: next.n - cur.n };
        var l1 = Math.hypot(e1.e, e1.n) || 1;
        var l2 = Math.hypot(e2.e, e2.n) || 1;
        var n1 = { e: -e1.n / l1, n: e1.e / l1 };
        var n2 = { e: -e2.n / l2, n: e2.e / l2 };
        // bisector
        var bx = n1.e + n2.e, by = n1.n + n2.n;
        var bl = Math.hypot(bx, by);
        if (bl < 1e-9) {
            out.push({ e: cur.e + n1.e * dist, n: cur.n + n1.n * dist });
        } else {
            bx /= bl; by /= bl;
            // scale so the offset distance is preserved across the corner
            var cosHalf = bx * n1.e + by * n1.n;
            var scale = cosHalf > 0.01 ? 1 / cosHalf : 1;
            out.push({ e: cur.e + bx * dist * scale, n: cur.n + by * dist * scale });
        }
    }
    return out;
};

// Build headland rings for all outer+inner boundaries at `dist` metres.
// Returns array of lat/lon rings.
FE.headland.build = function (dist) {
    if (!FE.field || !FE.plane) return null;
    var polys = (FE.field.boundary && FE.field.boundary.polygons) || [];
    if (!polys.length) return null;
    var rings = [];
    for (var p = 0; p < polys.length; p++) {
        var pts = polys[p].points || [];
        if (pts.length < 3) continue;
        var ring = pts.map(function (pt) { return FE.plane.fwd(pt[0], pt[1]); });
        // ensure CCW so left-offset goes inward for outer, and for inner
        // boundaries we offset outward (away from the hole) = also left if CW
        var area = FE.signedArea(ring);
        if (p === 0 && area < 0) ring = ring.slice().reverse();
        if (p > 0 && area > 0) ring = ring.slice().reverse();
        var off = FE.headland.offsetRing(ring, dist);
        if (!off) continue;
        var latlng = off.map(function (q) {
            var ll = FE.plane.inv(q.e, q.n);
            return [FE.r7(ll[0]), FE.r7(ll[1])];
        });
        rings.push(latlng);
    }
    return rings.length ? rings : null;
};

FE.headland.preview = function (dist) {
    FE.headland.clearPreview();
    var rings = FE.headland.build(dist);
    if (!rings) return null;
    var g = L.layerGroup();
    rings.forEach(function (ring) {
        L.polyline(ring.concat([ring[0]]), { color: '#f1c40f', weight: 3, opacity: 0.9 }).addTo(g);
    });
    g.addTo(FE.map);
    FE.headland.previewLayer = g;
    return rings;
};

FE.headland.clearPreview = function () {
    if (FE.headland.previewLayer) {
        try { FE.map.removeLayer(FE.headland.previewLayer); } catch (e) {}
        FE.headland.previewLayer = null;
    }
};

FE.headland.apply = function () {
    var input = document.getElementById('headlandDist');
    var dist = parseFloat(input && input.value);
    if (!dist || dist <= 0) { alert('Укажите отступ в метрах'); return; }
    var rings = FE.headland.preview(dist);
    if (!rings) { alert('Не удалось построить гон — нет границы'); return; }
    if (!window.confirm('Записать гон (' + rings.length + ' кольца, отступ ' + dist + ' м)?')) {
        FE.headland.clearPreview();
        return;
    }
    FE.pushUndo();
    FE.field.headland = rings.map(function (ring) { return { points: ring }; });
    FE.headland.clearPreview();
    FE.setDirty(true);
    FE.renderField();
    FE.status('Гон записан (не забудьте сохранить)');
};

FE.headland.clear = function () {
    if (!FE.field || !FE.field.headland || !FE.field.headland.length) return;
    if (!window.confirm('Удалить гон?')) return;
    FE.pushUndo();
    FE.field.headland = [];
    FE.setDirty(true);
    FE.renderField();
};

FE.headland.init = function () {
    document.getElementById('btnHeadlandPreview').addEventListener('click', function () {
        var input = document.getElementById('headlandDist');
        var dist = parseFloat(input && input.value);
        if (!dist || dist <= 0) { alert('Укажите отступ в метрах'); return; }
        FE.headland.preview(dist);
    });
    document.getElementById('btnHeadlandApply').addEventListener('click', FE.headland.apply);
    document.getElementById('btnHeadlandClear').addEventListener('click', FE.headland.clear);
    FE.hooks.afterClose.push(function () { FE.headland.clearPreview(); });
    FE.hooks.afterOpen.push(function () { FE.headland.clearPreview(); });
};
