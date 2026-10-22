// fe-split.js — split field by a 2-point cut line, and combine two fields
// into a new one. Geometry ported from aog-feldeditor 08-split-combine.js
// (SkaFUU, MIT); operates in the current plane's local e/n ({e, n} objects).
'use strict';

var FE = window.FE || (window.FE = {});

// -------- shared geometry (local e/n) --------

FE.geom = {};

FE.geom.dSq = function (a, b) {
    var dx = a.e - b.e, dy = a.n - b.n;
    return dx * dx + dy * dy;
};

FE.geom.ll = function (p) {
    return FE.plane.inv(p.e, p.n);
};

FE.geom.pathLen = function (pts) {
    var s = 0;
    for (var i = 1; i < pts.length; i++) s += Math.hypot(pts[i].e - pts[i - 1].e, pts[i].n - pts[i - 1].n);
    return s;
};

FE.geom.areaOf = function (P) {
    return Math.abs(FE.signedArea(P));
};

FE.geom.centroid = function (P) {
    var e = 0, n = 0;
    for (var i = 0; i < P.length; i++) { e += P[i].e; n += P[i].n; }
    return { e: e / P.length, n: n / P.length };
};

FE.geom.inPoly = function (q, P) {
    var inside = false;
    for (var i = 0, j = P.length - 1; i < P.length; j = i++) {
        var a = P[i], b = P[j];
        if (((a.n > q.n) !== (b.n > q.n)) &&
            (q.e < (b.e - a.e) * (q.n - a.n) / (b.n - a.n) + a.e)) inside = !inside;
    }
    return inside;
};

// Nearest point on polyline R (array of {e,n}, wrap-closed) to q.
// Returns {e, n, i, s, d}: projection point, segment start index,
// squared distance to that vertex and squared distance to the projection.
FE.geom.nearestOnRing = function (q, R) {
    var best = null, bd = Infinity;
    for (var i = 0; i < R.length; i++) {
        var a = R[i], b = R[(i + 1) % R.length];
        var dx = b.e - a.e, dy = b.n - a.n;
        var len2 = dx * dx + dy * dy;
        var t = len2 ? ((q.e - a.e) * dx + (q.n - a.n) * dy) / len2 : 0;
        t = Math.max(0, Math.min(1, t));
        var px = a.e + t * dx, py = a.n + t * dy;
        var d = (q.e - px) * (q.e - px) + (q.n - py) * (q.n - py);
        if (d < bd) {
            bd = d;
            best = {
                e: px, n: py, i: i,
                s: (a.e - px) * (a.e - px) + (a.n - py) * (a.n - py),
                d: bd
            };
        }
    }
    return best;
};

FE.geom.snapPx = function (n) {
    return FE.map.distance(FE.map.containerPointToLatLng([0, 0]), FE.map.containerPointToLatLng([n, 0]));
};

FE.geom.nearVertex = function (q, R) {
    var best = null, bd = Infinity;
    for (var i = 0; i < R.length; i++) {
        var d = FE.geom.dSq(q, R[i]);
        if (d < bd) { bd = d; best = R[i]; }
    }
    return best && Math.sqrt(bd) <= FE.geom.snapPx(10) ? best : null;
};

// Snap a map click to a ring: vertex (<=10px) first, then the nearest point
// on the line (<=15px); otherwise the raw point.
FE.geom.snapToRing = function (latlng, R) {
    var q = FE.plane.fwd(latlng.lat, latlng.lng);
    var v = FE.geom.nearVertex(q, R);
    if (v) return v;
    var s2 = FE.geom.nearestOnRing(q, R);
    var snapD = FE.geom.snapPx(15);
    return s2 && s2.d <= snapD * snapD ? { e: s2.e, n: s2.n } : q;
};

// Always snap to the nearest point on the ring (no distance limit) —
// used by combine where every click must land on a field border.
FE.geom.onRing = function (q, R) {
    var v = FE.geom.nearVertex(q, R);
    if (v) return v;
    var s2 = FE.geom.nearestOnRing(q, R);
    return s2 ? { e: s2.e, n: s2.n } : q;
};

// -------- cut ring by a line through p1,p2 ({e,n}) --------
// Returns [A, B] rings or null; part ordering is up to the caller.
// Port of aog-feldeditor cutRing.
FE.geom.cutRing = function (P, p1, p2) {
    var n = P.length;
    var d = { e: p2.e - p1.e, n: p2.n - p1.n };
    var L2 = d.e * d.e + d.n * d.n;
    if (L2 < 1) return null;
    var X = [];
    for (var i = 0; i < n; i++) {
        var a = P[i], b = P[(i + 1) % n];
        var r = { e: b.e - a.e, n: b.n - a.n };
        var den = d.e * r.n - d.n * r.e;
        if (Math.abs(den) < 1e-12) continue;
        var t1 = ((a.e - p1.e) * r.n - (a.n - p1.n) * r.e) / den;
        var s1 = ((a.e - p1.e) * d.n - (a.n - p1.n) * d.e) / den;
        if (s1 >= -1e-9 && s1 < 1 + 1e-9) X.push({ t: t1, i: i, q: { e: p1.e + d.e * t1, n: p1.n + d.n * t1 } });
    }
    X.sort(function (x, y) { return x.t - y.t; });
    for (var j = X.length - 1; j > 0; j--) {
        if (Math.abs(X[j].t - X[j - 1].t) * Math.sqrt(L2) < 1e-6) X.splice(j, 1);
    }
    var k = -1;
    for (var j2 = 0; j2 + 1 < X.length; j2 += 2) {
        if (X[j2].t <= 0.5 + 1e-9 && X[j2 + 1].t >= 0.5 - 1e-9) k = j2;
    }
    if (k < 0) return null;
    var I1 = X[k], I2 = X[k + 1];
    if (I1.i === I2.i) return null;
    var arc = function (x, y) {
        var o = [x.q];
        for (var jj = (x.i + 1) % n; ; jj = (jj + 1) % n) { o.push(P[jj]); if (jj === y.i) break; }
        o.push(y.q);
        return o.filter(function (p, kk) { return !kk || FE.geom.dSq(p, o[kk - 1]) > 1e-6; });
    };
    var A = arc(I1, I2), B = arc(I2, I1);
    return A.length > 2 && B.length > 2 ? [A, B] : null;
};

// -------- merge two rings via two connection pairs (aog mergeRings) --------
// pa1/pa2: points on ring A; pb1/pb2: points on ring B.
FE.geom.mergeRings = function (A, B, pa1, pb1, pa2, pb2) {
    var near = function (R, c) {
        var best = null;
        for (var i = 0; i < R.length; i++) {
            var a = R[i], b = R[(i + 1) % R.length];
            var q = FE.geom.nearestOnRing(c, [a, b]);
            var qq = { e: q.e, n: q.n };
            var d = FE.geom.dSq(c, qq);
            if (!best || d < best.d) best = { d: d, i: i, q: qq, s: FE.geom.dSq(a, qq) };
        }
        return best;
    };
    var arc = function (R, x, y) {
        var n = R.length, o = [x.q];
        if (x.i === y.i && x.s <= y.s) return o.concat([y.q]);
        for (var j = (x.i + 1) % n; ; j = (j + 1) % n) { o.push(R[j]); if (j === y.i) break; }
        o.push(y.q);
        return o;
    };
    var away = function (P, O) {
        var Oc = O.concat([O[0]]);
        var s1 = 0;
        P.forEach(function (p) { s1 += Math.sqrt(FE.geom.nearestOnRing(p, Oc).d); });
        return s1 / P.length;
    };
    var a1 = near(A, pa1), a2 = near(A, pa2), b1 = near(B, pb1), b2 = near(B, pb2);
    var pa = [arc(A, a1, a2), arc(A, a2, a1).reverse()];
    var pb = [arc(B, b2, b1), arc(B, b1, b2).reverse()];
    var PA = away(pa[0], B) > away(pa[1], B) ? pa[0] : pa[1];
    var PB = away(pb[0], A) > away(pb[1], A) ? pb[0] : pb[1];
    return PA.concat(PB);
};

// -------- fit tracks to a part (port of fitTracks, e/n in place of LL) --------
// tracks: FE.field.tracks entries ({ptA, ptB, curvePts, mode} in local e/n).
// P: part ring {e,n}[] whose first/last points are the cut line ends.
// Returns [{idx, src, entry}] — one entry per surviving track; tracks absent
// from the result lie fully in the other part. entry === null means the src
// track is kept unchanged (no intersection with the cut line).
FE.geom.fitTracks = function (tracks, P) {
    var c1 = P[0], c2 = P[P.length - 1];
    var d = { e: c2.e - c1.e, n: c2.n - c1.n };
    var Ld = Math.hypot(d.e, d.n) || 1;
    var u = { e: d.e / Ld, n: d.n / Ld };
    var s1 = { e: c1.e - u.e * 2, n: c1.n - u.n * 2 };
    var s2 = { e: c2.e + u.e * 2, n: c2.n + u.n * 2 };
    var side = function (q) { return Math.sign((q.e - c1.e) * d.n - (q.n - c1.n) * d.e); };
    var mine = side(FE.geom.centroid(P));

    var hit = function (a, b) {
        var r = { e: b.e - a.e, n: b.n - a.n };
        var w = { e: s2.e - s1.e, n: s2.n - s1.n };
        var den = r.e * w.n - r.n * w.e;
        if (Math.abs(den) < 1e-12) return null;
        var t1 = ((s1.e - a.e) * w.n - (s1.n - a.n) * w.e) / den;
        var t2 = ((s1.e - a.e) * r.n - (s1.n - a.n) * r.e) / den;
        return t1 >= 0 && t1 < 1 && t2 >= 0 && t2 <= 1 ? { e: a.e + r.e * t1, n: a.n + r.n * t1 } : null;
    };
    var ext = function (a, b, cnt) {
        var L1 = Math.hypot(b.e - a.e, b.n - a.n) || 1;
        var v = { e: (b.e - a.e) / L1, n: (b.n - a.n) / L1 };
        var o = [];
        for (var i = 1; i <= cnt; i++) o.push({ e: b.e + v.e * i, n: b.n + v.n * i });
        return o;
    };
    var headingsOf = function (pts) {
        var H = [];
        for (var i = 0; i < pts.length; i++) {
            var a = pts[Math.max(0, i - 1)], b = pts[Math.min(pts.length - 1, i + 1)];
            var h = Math.atan2(b.e - a.e, b.n - a.n);
            H.push(h < 0 ? h + 2 * Math.PI : h);
        }
        return H;
    };

    var out = [];
    tracks.forEach(function (tr, idx) {
        var isCurve = tr.curvePts && tr.curvePts.length > 2 && tr.mode !== 2;
        if (!isCurve) {
            // straight AB (or a degenerate curve — treat as AB)
            var a = { e: (tr.ptA && tr.ptA.easting) || 0, n: (tr.ptA && tr.ptA.northing) || 0 };
            var b = { e: (tr.ptB && tr.ptB.easting) || 0, n: (tr.ptB && tr.ptB.northing) || 0 };
            var L1 = Math.hypot(b.e - a.e, b.n - a.n) || 1;
            var v = { e: (b.e - a.e) / L1, n: (b.n - a.n) / L1 };
            var X = hit({ e: a.e - v.e * 5000, n: a.n - v.n * 5000 }, { e: a.e + v.e * 5000, n: a.n + v.n * 5000 });
            var sa = side(a) === mine, sb = side(b) === mine;
            var A2 = a, B2 = b;
            if (X && !sa && sb) A2 = X;
            if (X && sa && !sb) B2 = X;
            if (X && !sa && !sb) {
                var inward = side({ e: X.e + v.e, n: X.n + v.n }) === mine ? 1 : -1;
                if (inward > 0) { A2 = X; B2 = { e: X.e + v.e * L1, n: X.n + v.n * L1 }; }
                else { A2 = { e: X.e - v.e * L1, n: X.n - v.n * L1 }; B2 = X; }
            }
            if (!X && !sa && !sb) return;
            if (Math.hypot(B2.e - A2.e, B2.n - A2.n) < 2) return;
            var heading = Math.atan2(B2.e - A2.e, B2.n - A2.n);
            if (heading < 0) heading += 2 * Math.PI;
            out.push({
                idx: idx, src: tr,
                entry: {
                    mode: 2, ptA: { easting: FE.r3(A2.e), northing: FE.r3(A2.n) },
                    ptB: { easting: FE.r3(B2.e), northing: FE.r3(B2.n) },
                    heading: heading, curvePts: [], name: tr.name,
                    isVisible: tr.isVisible, nudgeDistance: tr.nudgeDistance || 0
                }
            });
        } else {
            // curve (mode 4)
            var Q = tr.curvePts.map(function (cp) {
                return { e: cp.easting || 0, n: cp.northing || 0 };
            });
            var nq = Q.length;
            var pcs = [], cur = { pts: [Q[0]], cutStart: false, cutEnd: false };
            for (var i = 1; i < nq; i++) {
                var x = hit(Q[i - 1], Q[i]);
                if (x) { cur.pts.push(x); cur.cutEnd = true; pcs.push(cur); cur = { pts: [x], cutStart: true, cutEnd: false }; }
                cur.pts.push(Q[i]);
            }
            pcs.push(cur);
            if (pcs.length === 1) {
                // no intersection: keep the whole curve if most points lie on our side
                var on = Q.filter(function (q) { return side(q) === mine; }).length;
                if (on * 2 >= nq) out.push({ idx: idx, src: tr, entry: null });
                return;
            }
            var mineP = pcs.filter(function (p) {
                var m = p.pts[p.pts.length >> 1];
                return side(m) === mine;
            }).sort(function (x2, y) { return FE.geom.pathLen(y.pts) - FE.geom.pathLen(x2.pts); })[0];
            if (!mineP || FE.geom.pathLen(mineP.pts) < 5) return;
            var R = mineP.pts;
            if (mineP.cutStart) R = ext(R[1], R[0], 99).reverse().concat(R);
            if (mineP.cutEnd) R = R.concat(ext(R[R.length - 2], R[R.length - 1], 99));
            var H = headingsOf(R);
            var hx = 0, hy = 0;
            H.forEach(function (h) { hx += Math.cos(h); hy += Math.sin(h); });
            var havg = Math.atan2(hy, hx);
            if (havg < 0) havg += 2 * Math.PI;
            var curveOut = R.map(function (p, ii) {
                return { easting: FE.r3(p.e), northing: FE.r3(p.n), heading: H[ii] };
            });
            out.push({
                idx: idx, src: tr,
                entry: {
                    mode: 4, ptA: { easting: curveOut[0].easting, northing: curveOut[0].northing },
                    ptB: { easting: curveOut[curveOut.length - 1].easting, northing: curveOut[curveOut.length - 1].northing },
                    heading: havg, curvePts: curveOut, name: tr.name,
                    isVisible: tr.isVisible, nudgeDistance: tr.nudgeDistance || 0
                }
            });
        }
    });
    return out;
};

// Apply fit results to a track list: surviving tracks replaced by their
// fitted entry (or kept as-is when entry is null), others dropped.
FE.geom.applyFit = function (tracks, results) {
    var byIdx = {};
    results.forEach(function (r) { byIdx[r.idx] = r; });
    var out = [];
    tracks.forEach(function (tr, idx) {
        var r = byIdx[idx];
        if (!r) return;
        out.push(r.entry || tr);
    });
    return out;
};

// Reproject another field's track entry from its plane into the current one.
FE.geom.reprojectEntry = function (entry, otherPlane) {
    var cp = function (pt) {
        var ll = otherPlane.inv(pt.easting || 0, pt.northing || 0);
        var en = FE.plane.fwd(ll[0], ll[1]);
        return { easting: FE.r3(en.e), northing: FE.r3(en.n) };
    };
    var out = JSON.parse(JSON.stringify(entry));
    if (out.ptA) out.ptA = cp(out.ptA);
    if (out.ptB) out.ptB = cp(out.ptB);
    if (out.curvePts && out.curvePts.length) out.curvePts = out.curvePts.map(function (p) {
        var en = cp(p);
        return { easting: en.easting, northing: en.northing, heading: p.heading };
    });
    return out;
};

// -------- shared tool UI (hint / name input / select / ok / cancel) --------

FE._tui = {};

FE._tui.hint = function (html) {
    var el = document.getElementById('toolHint');
    if (!el) return;
    el.innerHTML = html || '';
    el.style.display = html ? 'block' : 'none';
};

FE._tui.nameRow = function (show, label, value, onInput) {
    var row = document.getElementById('toolNameRow');
    var lab = document.getElementById('toolNameLabel');
    var inp = document.getElementById('toolName');
    if (!row) return;
    if (show) {
        if (lab && label != null) lab.textContent = label;
        if (inp) {
            inp.value = value || '';
            inp.oninput = onInput || null;
        }
        row.style.display = 'block';
    } else {
        row.style.display = 'none';
        if (inp) inp.oninput = null;
    }
};

FE._tui.selectRow = function (show, options, value, onChange) {
    var row = document.getElementById('toolSelectRow');
    var sel = document.getElementById('toolSelect');
    if (!row) return;
    if (show && sel) {
        sel.innerHTML = '';
        var o0 = document.createElement('option');
        o0.value = '';
        o0.textContent = '— выберите поле —';
        sel.appendChild(o0);
        (options || []).forEach(function (opt) {
            var o = document.createElement('option');
            o.value = opt;
            o.textContent = opt;
            sel.appendChild(o);
        });
        sel.value = value || '';
        sel.onchange = onChange || null;
        row.style.display = 'block';
    } else {
        row.style.display = 'none';
        if (sel) sel.onchange = null;
    }
};

FE._tui.okBtn = function (show, label, enabled, onClick) {
    var btn = document.getElementById('btnToolOk');
    if (!btn) return;
    if (show) {
        btn.textContent = label || 'Выполнить';
        btn.disabled = !enabled;
        btn.style.display = 'block';
        btn.onclick = onClick || null;
    } else {
        btn.style.display = 'none';
        btn.onclick = null;
    }
};

FE._tui.cancelBtn = function (show) {
    var btn = document.getElementById('btnToolCancel');
    if (!btn) return;
    btn.style.display = show ? 'block' : 'none';
    btn.onclick = show ? function () {
        var t = FE.tool.active && FE[FE.tool.active];
        if (t && t.busy) return;
        if (t && t.stop) t.stop();
    } : null;
};

FE._tui.reset = function () {
    FE._tui.hint('');
    FE._tui.nameRow(false);
    FE._tui.selectRow(false);
    FE._tui.okBtn(false);
    FE._tui.cancelBtn(false);
};

// -------- guards --------

FE._toolBusy = function () {
    if (!FE.field) { FE._tui.hint('Сначала откройте поле.'); return true; }
    if (!FE.field.boundary || !FE.field.boundary.polygons || !FE.field.boundary.polygons[0] ||
        !FE.field.boundary.polygons[0].points || FE.field.boundary.polygons[0].points.length < 3) {
        FE._tui.hint('У поля нет внешней границы.');
        return true;
    }
    if (FE.boundary.editing || FE.boundary.drawing) { FE._tui.hint('Сначала закончите редактирование границы.'); return true; }
    if (FE.origin.moving) { FE._tui.hint('Сначала завершите перенос startFix.'); return true; }
    return false;
};

FE._toolRing = function () {
    return FE.field.boundary.polygons[0].points.map(function (p) { return FE.plane.fwd(p[0], p[1]); });
};

FE._toolInnerRings = function () {
    var polys = FE.field.boundary.polygons || [];
    return polys.slice(1).filter(function (p) { return p.points && p.points.length >= 3; });
};

FE._toolNameOk = function (nm, other) {
    var names = (typeof FE_lastList !== 'undefined' && FE_lastList) ? FE_lastList.map(function (f) { return f.name; }) : [];
    var t2 = (nm || '').trim();
    if (!t2) return false;
    if (/[\\/:*?"<>|]/.test(t2)) return false;
    var low = t2.toLowerCase();
    if (other && low === (other || '').trim().toLowerCase()) return false;
    if (FE.field && low === FE.field.__name.toLowerCase()) return false;
    return !names.some(function (x) { return x.toLowerCase() === low; });
};

// -------- number badge / vertex dots / drag pin --------

FE._toolBadge = function (group, ll, label) {
    L.marker(ll, {
        interactive: false,
        icon: L.divIcon({
            className: '',
            html: '<div style="background:#ffd400;color:#333;border:1px solid #333;border-radius:50%;' +
                'width:22px;height:22px;line-height:22px;text-align:center;font-size:12px;font-weight:700;">' + label + '</div>',
            iconSize: [22, 22], iconAnchor: [11, 11]
        })
    }).addTo(group);
};

FE._toolDots = function (group, R, color) {
    var canvas = FE._toolCanvas || (FE._toolCanvas = L.canvas({ padding: 0.3 }));
    R.forEach(function (p) {
        L.circleMarker(FE.geom.ll(p), {
            renderer: canvas, radius: 3, weight: 1, color: '#000',
            fillColor: color, fillOpacity: 1, interactive: false
        }).addTo(group);
    });
};

// Draggable pin snapped to a ring: snap(latlng) -> {e,n}, onMove(q), onEnd().
FE._toolPin = function (group, q, color, snap, onMove, onEnd) {
    var m = L.marker(FE.geom.ll(q), {
        draggable: true, zIndexOffset: 3000,
        icon: L.divIcon({
            className: '',
            html: '<div style="background:' + color + ';width:14px;height:14px;border-radius:50%;' +
                'border:2px solid #fff;box-shadow:0 0 3px #000;"></div>',
            iconSize: [14, 14], iconAnchor: [7, 7]
        })
    }).addTo(group);
    m.on('click', function (e) { L.DomEvent.stopPropagation(e); });
    m.on('drag', function (e) {
        var s = snap(e.latlng);
        m.setLatLng(FE.geom.ll(s));
        onMove(s);
    });
    m.on('dragend', function () { if (onEnd) onEnd(); });
    return m;
};

// -------- split tool --------

FE.split = {
    active: false,
    group: null,
    pts: [],        // [{e,n}, ...] cut points (max 2)
    parts: null,    // [ring0, ring1], ring0 = larger
    keep: 0,        // index of the part that stays in the current field
    name: '',
    nameTouched: false,
    busy: false,
    R: null         // outer ring in e/n
};

FE.split.start = function () {
    var s = FE.split;
    if (s.active) { s.stop(); return; }
    if (FE.tool.active) { if (FE[FE.tool.active] && FE[FE.tool.active].stop) FE[FE.tool.active].stop(); }
    if (FE._toolBusy()) return;
    if (FE.measure.active) FE.measure.stop();

    s.active = true;
    FE.tool.active = 'split';
    s.pts = []; s.parts = null; s.keep = 0;
    s.nameTouched = false;
    s.name = FE.field.__name + ' 2';
    s.R = FE._toolRing();
    s.group = L.layerGroup().addTo(FE.map);
    FE.map.getContainer().style.cursor = 'crosshair';
    FE.map.on('click', s._onClick);
    window.addEventListener('keydown', s._onKey);
    document.getElementById('btnSplit').textContent = 'Отменить разрезание';
    FE._tui.cancelBtn(true);
    s._refresh();
    s._draw();
};

FE.split.stop = function () {
    var s = FE.split;
    if (!s.active) return;
    s.active = false;
    FE.tool.active = null;
    FE.map.off('click', s._onClick);
    window.removeEventListener('keydown', s._onKey);
    if (s.group) { try { FE.map.removeLayer(s.group); } catch (e) {} s.group = null; }
    s.pts = []; s.parts = null; s.R = null; s.busy = false;
    FE.map.getContainer().style.cursor = '';
    FE._tui.reset();
    document.getElementById('btnSplit').textContent = 'Разрезать поле';
};

FE.split._onKey = function (e) {
    if (e.key === 'Escape' && !FE.split.busy) FE.split.stop();
};

FE.split._onClick = function (e) {
    var s = FE.split;
    if (s.active && !s.busy) s._click(e.latlng);
};

FE.split._click = function (latlng) {
    var s = FE.split;
    if (s.pts.length === 2 && s.parts) {
        var q = FE.plane.fwd(latlng.lat, latlng.lng);
        var k = FE.geom.inPoly(q, s.parts[0]) ? 0 : (FE.geom.inPoly(q, s.parts[1]) ? 1 : -1);
        if (k >= 0) {
            s.keep = k;
            if (!s.nameTouched) s.name = FE.field.__name + (k === 0 ? ' 2' : ' 1');
            s._refresh();
            s._draw();
            return;
        }
        // click outside both parts: start a new cut — unless the click was on
        // the border itself (points on the ring are ambiguous for inPoly)
        var nearRing = FE.geom.nearestOnRing(q, s.R);
        var snapD = FE.geom.snapPx(15);
        if (nearRing && nearRing.d <= snapD * snapD) return;
        s.pts = [];
        s.parts = null;
    } else if (s.pts.length === 2) {
        s.pts = [];
        s.parts = null;
    }
    s.pts.push(FE.geom.snapToRing(latlng, s.R));
    if (s.pts.length === 2) s._cut();
    s._refresh();
    s._draw();
};

FE.split._cut = function () {
    var s = FE.split;
    var parts = FE.geom.cutRing(s.R, s.pts[0], s.pts[1]);
    if (parts && FE.geom.areaOf(parts[1]) > FE.geom.areaOf(parts[0])) parts.reverse();
    s.parts = parts;
    s.keep = 0;
    if (!s.nameTouched) s.name = FE.field.__name + ' 2';
};

FE.split._ha = function (P) {
    return (FE.geom.areaOf(P) / 10000).toFixed(2);
};

FE.split._refresh = function () {
    var s = FE.split;
    var html = '';
    if (s.pts.length < 2) {
        html = (s.pts.length ? 'Кликните <b>вторую</b> точку на внешней границе.' :
            'Кликните <b>первую</b> точку на внешней границе (метки можно перетаскивать).') +
            '<br>Esc или кнопка ниже — отмена.';
    } else if (!s.parts) {
        html = '<span style="color:#c0392b;">Линия разреза не пересекает поле — кликните заново.</span>';
    } else {
        html = 'Часть 1: <b>' + s._ha(s.parts[0]) + ' га</b> · Часть 2: <b>' + s._ha(s.parts[1]) + ' га</b><br>' +
            'Кликните по части, которая <b>останется</b> в текущем поле (по умолчанию — большая).<br>' +
            'Текущее поле станет выбранной частью, вторая часть — новым полем.<br>' +
            '<span style="color:#c0392b;">Гон, секции и урожайность в новое поле не переносятся; ' +
            'гон у текущего поля будет очищен.</span>';
    }
    FE._tui.hint(html);
    FE._tui.nameRow(!!s.parts, 'Имя нового поля', s.name, function () {
        s.name = this.value;
        s.nameTouched = true;
        s._refreshOk();
    });
    s._refreshOk();
};

FE.split._refreshOk = function () {
    var s = FE.split;
    var ok = !!s.parts && FE._toolNameOk(s.name);
    FE._tui.okBtn(true, 'Разрезать', ok && !s.busy, ok && !s.busy ? function () { s._ok(); } : null);
};

FE.split._draw = function () {
    var s = FE.split;
    if (s.group) { try { FE.map.removeLayer(s.group); } catch (e) {} }
    s.group = L.layerGroup().addTo(FE.map);
    var g = s.group;

    if (s.parts) {
        var colors = ['#ffd400', '#00e5ff'];
        s.parts.forEach(function (P, i) {
            var kept = i === s.keep;
            var pg = L.polygon(P.map(FE.geom.ll), {
                color: colors[i], weight: 2, fillColor: colors[i],
                fillOpacity: kept ? 0.35 : 0.15, dashArray: kept ? null : '6,4',
                interactive: true, bubblingMouseEvents: false
            }).addTo(g);
            pg.on('click', function () {
                if (s.busy) return;
                s.keep = i;
                if (!s.nameTouched) s.name = FE.field.__name + (i === 0 ? ' 2' : ' 1');
                s._refresh();
                s._draw();
            });
            FE._toolBadge(g, FE.geom.ll(FE.geom.centroid(P)), String(i + 1));
        });
    }
    FE._toolDots(g, s.R, '#ffffff');
    var reCut = function () {
        if (s.busy) return;
        s._cut();
        s._refresh();
        s._draw();
    };
    s.pts.forEach(function (q, i) {
        FE._toolPin(g, q, '#ff5a5a', function (ll) { return FE.geom.snapToRing(ll, s.R); },
            function (qq) {
                if (s.busy) return;
                s.pts[i] = qq;
                if (s._line) s._line.setLatLngs(s.pts.map(FE.geom.ll));
            },
            reCut);
    });
    s._line = null;
    if (s.pts.length === 2) {
        s._line = L.polyline(s.pts.map(FE.geom.ll), { color: '#ff5a5a', weight: 3, interactive: false }).addTo(g);
    }
};

FE.split._ok = function () {
    var s = FE.split;
    if (s.busy || !s.parts) return;
    if (!FE._toolNameOk(s.name)) { alert('Недопустимое имя нового поля.'); return; }
    var newName = s.name.trim();
    var K = s.parts[s.keep], N = s.parts[s.keep === 0 ? 1 : 0];
    var inners = FE._toolInnerRings();
    var insidePart = function (P, ring) {
        var p0 = FE.plane.fwd(ring.points[0][0], ring.points[0][1]);
        return FE.geom.inPoly(p0, P);
    };
    var innersK = inners.filter(function (r) { return insidePart(K, r); });
    var innersN = inners.filter(function (r) { return insidePart(N, r); });

    var fitK = FE.geom.fitTracks(FE.field.tracks || [], K);
    var fitN = FE.geom.fitTracks(FE.field.tracks || [], N);

    var startFix = (FE.field.field && FE.field.field.startFix) || {};
    var newData = {
        field: { startFix: { lat: startFix.lat, lon: startFix.lon } },
        boundary: {
            polygons: [{ points: N.map(function (p) { return FE.geom.ll(p); }) }]
                .concat(innersN.map(function (r) { return { points: r.points.slice() }; }))
        },
        tracks: FE.geom.applyFit(FE.field.tracks || [], fitN),
        headland: [],
        headLines: [],
        sections: { sections: [] },
        yieldData: { records: [] }
    };

    s.busy = true;
    s._refreshOk();
    FE._tui.hint('Создаю поле «' + FE.escapeHtml(newName) + '»…');

    FE.api.createField(newName, newData).then(function () {
        // current field becomes the kept part
        FE.pushUndo();
        FE.field.boundary.polygons =
            [{ points: K.map(function (p) { return FE.geom.ll(p); }) }]
                .concat(innersK.map(function (r) { return { points: r.points.slice() }; }));
        FE.field.tracks = FE.geom.applyFit(FE.field.tracks || [], fitK);
        FE.field.headland = [];
        FE.renderField();
        FE.setDirty(true);
        s.stop();
        return FE.save().then(function () {
            FE.status('Поле разрезано: часть осталась здесь, вторая часть — «' + newName + '»');
        });
    }).then(function () {
        if (FE.dirty) {
            alert('Новое поле «' + newName + '» создано, но текущее поле сохранить не удалось. ' +
                'Обновите страницу и проверьте результат.');
        }
        FE.loadFieldList();
    }).catch(function (e) {
        if (s.active) {
            s.busy = false;
            s._refreshOk();
            FE._tui.hint('<span style="color:#c0392b;">Ошибка: ' + FE.escapeHtml(e.message || e) + '</span>');
        }
        alert('Не удалось создать новое поле: ' + (e.message || e));
    });
};

// -------- combine tool --------

FE.combine = {
    active: false,
    group: null,
    otherName: null,
    otherData: null,
    otherPlane: null,
    O: null,        // other outer ring in current plane e/n
    pts: [],        // [{q:{e,n}, f:'A'|'O'}, ...] max 4
    merged: null,
    name: '',
    nameTouched: false,
    busy: false,
    A: null
};

FE.combine.start = function () {
    var c = FE.combine;
    if (c.active) { c.stop(); return; }
    if (FE.tool.active) { if (FE[FE.tool.active] && FE[FE.tool.active].stop) FE[FE.tool.active].stop(); }
    if (FE._toolBusy()) return;
    if (FE.measure.active) FE.measure.stop();

    c.active = true;
    FE.tool.active = 'combine';
    c.otherName = null; c.otherData = null; c.otherPlane = null;
    c.O = null; c.pts = []; c.merged = null;
    c.nameTouched = false;
    c.name = '';
    c.A = FE._toolRing();
    c.group = L.layerGroup().addTo(FE.map);
    FE.map.getContainer().style.cursor = 'crosshair';
    FE.map.on('click', c._onClick);
    window.addEventListener('keydown', c._onKey);
    document.getElementById('btnCombine').textContent = 'Отменить объединение';
    FE._tui.cancelBtn(true);
    c._refresh();
    c._draw();
};

FE.combine.stop = function () {
    var c = FE.combine;
    if (!c.active) return;
    c.active = false;
    FE.tool.active = null;
    FE.map.off('click', c._onClick);
    window.removeEventListener('keydown', c._onKey);
    if (c.group) { try { FE.map.removeLayer(c.group); } catch (e) {} c.group = null; }
    c.O = null; c.pts = []; c.merged = null; c.A = null; c.busy = false;
    c.otherName = null; c.otherData = null; c.otherPlane = null;
    FE.map.getContainer().style.cursor = '';
    FE._tui.reset();
    document.getElementById('btnCombine').textContent = 'Объединить поля';
};

FE.combine._onKey = function (e) {
    if (e.key === 'Escape' && !FE.combine.busy) FE.combine.stop();
};

FE.combine._onClick = function (e) {
    var c = FE.combine;
    if (!c.active || c.busy || !c.O) return;
    if (c.pts.length === 4) { c.pts = []; c.merged = null; }
    var q = FE.plane.fwd(e.latlng.lat, e.latlng.lng);
    // first point of a pair goes to the nearer field, second always to the other
    var f = c.pts.length % 2
        ? (c.pts[c.pts.length - 1].f === 'A' ? 'O' : 'A')
        : (FE.geom.dSq(q, FE.geom.onRing(q, c.A)) <= FE.geom.dSq(q, FE.geom.onRing(q, c.O)) ? 'A' : 'O');
    var R = f === 'A' ? c.A : c.O;
    c.pts.push({ q: FE.geom.onRing(q, R), f: f });
    if (c.pts.length === 4) {
        var g2 = function (k, fl) { return c.pts[k].f === fl ? c.pts[k].q : c.pts[k + 1].q; };
        c.merged = FE.geom.mergeRings(c.A, c.O, g2(0, 'A'), g2(0, 'O'), g2(2, 'A'), g2(2, 'O'));
    }
    c._refresh();
    c._draw();
};

FE.combine._onSelect = function () {
    var c = FE.combine;
    var sel = document.getElementById('toolSelect');
    var name = sel ? sel.value : '';
    if (!name) {
        c.otherName = null; c.otherData = null; c.otherPlane = null;
        c.O = null; c.pts = []; c.merged = null;
        c._refresh();
        c._draw();
        return;
    }
    FE._tui.hint('Загружаю поле «' + FE.escapeHtml(name) + '»…');
    FE.api.loadField(name, null).then(function (data) {
        if (!c.active) return;
        var polys = data.boundary && data.boundary.polygons;
        if (!polys || !polys[0] || !polys[0].points || polys[0].points.length < 3) {
            c.otherName = null; c.O = null;
            FE._tui.hint('<span style="color:#c0392b;">У поля «' + FE.escapeHtml(name) + '» нет внешней границы.</span>');
            return;
        }
        var sf = (data.field && data.field.startFix) || {};
        var refLat = sf.lat, refLon = sf.lon;
        if (refLat == null) { refLat = polys[0].points[0][0]; refLon = polys[0].points[0][1]; }
        c.otherData = data;
        c.otherName = name;
        c.otherPlane = FE.Plane(refLat, refLon);
        // other ring is stored in lat/lon — project into the CURRENT plane
        c.O = polys[0].points.map(function (p) { return FE.plane.fwd(p[0], p[1]); });
        c.pts = []; c.merged = null;
        if (!c.nameTouched) c.name = FE.field.__name + ' + ' + name;
        try { FE.map.fitBounds(L.latLngBounds(c.A.concat(c.O).map(FE.geom.ll)), { padding: [40, 40] }); } catch (e) {}
        c._refresh();
        c._draw();
    }).catch(function (e) {
        if (!c.active) return;
        FE._tui.hint('<span style="color:#c0392b;">Ошибка загрузки: ' + FE.escapeHtml(e.message || e) + '</span>');
    });
};

FE.combine._ha = function (P) {
    return (FE.geom.areaOf(P) / 10000).toFixed(2);
};

FE.combine._refresh = function () {
    var c = FE.combine;
    var html;
    if (!c.O) {
        html = 'Выберите второе поле — оно останется нетронутым, результат будет третьим полем.<br>Esc или кнопка ниже — отмена.';
    } else if (c.pts.length < 4) {
        html = 'Кликните точку соединения <b>' + (c.pts.length + 1) + ' из 4</b> — поочерёдно на границах двух полей ' +
            '(первая — на ближайшей границе, дальше по очереди).<br>Метки можно перетаскивать.';
        if (c.merged === null && c.pts.length === 4) {
            html = '<span style="color:#c0392b;">Не удалось объединить границы.</span>';
        }
    } else {
        html = 'Результат: <b>' + c._ha(c.merged) + ' га</b> · текущее поле: <b>' + c._ha(c.A) + ' га</b> · ' +
            FE.escapeHtml(c.otherName) + ': <b>' + c._ha(c.O) + ' га</b><br>' +
            'Оба исходных поля останутся без изменений.<br>' +
            '<span style="color:#c0392b;">Гон и секции/урожайность второго поля не переносятся; ' +
            'гон нового поля будет пустым.</span>';
    }
    FE._tui.hint(html);

    var options = ((typeof FE_lastList !== 'undefined' && FE_lastList) ? FE_lastList : [])
        .map(function (f) { return f.name; })
        .filter(function (n) { return !FE.field || n !== FE.field.__name; });
    FE._tui.selectRow(true, options, c.otherName || '', function () { c._onSelect(); });
    FE._tui.nameRow(!!c.O, 'Имя нового поля', c.name, function () {
        c.name = this.value;
        c.nameTouched = true;
        c._refreshOk();
    });
    c._refreshOk();
};

FE.combine._refreshOk = function () {
    var c = FE.combine;
    var ok = !!c.O && !!c.merged && c.merged.length > 2 && FE._toolNameOk(c.name);
    FE._tui.okBtn(true, 'Объединить', ok && !c.busy, ok && !c.busy ? function () { c._ok(); } : null);
};

FE.combine._draw = function () {
    var c = FE.combine;
    if (c.group) { try { FE.map.removeLayer(c.group); } catch (e) {} }
    c.group = L.layerGroup().addTo(FE.map);
    var g = c.group;
    if (!c.A) return;
    L.polygon(c.A.map(FE.geom.ll), { color: '#ff5a5a', weight: 2, fillOpacity: 0.08, interactive: false }).addTo(g);
    FE._toolDots(g, c.A, '#ff5a5a');
    if (c.O) {
        L.polygon(c.O.map(FE.geom.ll), { color: '#00e5ff', weight: 2, fillOpacity: 0.08, interactive: false }).addTo(g);
        FE._toolDots(g, c.O, '#00e5ff');
    }
    if (c.merged && c.merged.length > 2) {
        L.polygon(c.merged.map(FE.geom.ll), {
            color: '#ffd400', weight: 3, fillColor: '#ffd400', fillOpacity: 0.2, interactive: false
        }).addTo(g);
    }
    var lines = [];
    for (var k = 0; k + 1 < c.pts.length; k += 2) {
        lines[k >> 1] = L.polyline([FE.geom.ll(c.pts[k].q), FE.geom.ll(c.pts[k + 1].q)],
            { color: '#ffffff', weight: 3, dashArray: '6,5', interactive: false }).addTo(g);
    }
    var reMerged = function () {
        if (c.busy) return;
        if (c.pts.length === 4) {
            var g2 = function (k2, fl) { return c.pts[k2].f === fl ? c.pts[k2].q : c.pts[k2 + 1].q; };
            c.merged = FE.geom.mergeRings(c.A, c.O, g2(0, 'A'), g2(0, 'O'), g2(2, 'A'), g2(2, 'O'));
        }
        c._refresh();
        c._draw();
    };
    c.pts.forEach(function (pt, i) {
        var Rf = pt.f === 'A' ? c.A : c.O;
        FE._toolPin(g, pt.q, pt.f === 'A' ? '#ff5a5a' : '#00e5ff',
            function (ll) { return FE.geom.onRing(FE.plane.fwd(ll.lat, ll.lng), Rf); },
            function (qq) {
                if (c.busy) return;
                pt.q = qq;
                var ln = lines[i >> 1];
                if (ln) ln.setLatLngs([FE.geom.ll(c.pts[i & ~1].q), FE.geom.ll(c.pts[i | 1].q)]);
            },
            reMerged);
    });
};

FE.combine._ok = function () {
    var c = FE.combine;
    if (c.busy || !c.merged || !c.O || !c.otherData) return;
    if (!FE._toolNameOk(c.name)) { alert('Недопустимое имя нового поля.'); return; }
    var newName = c.name.trim();

    var inners = FE._toolInnerRings().map(function (r) { return { points: r.points.slice() }; });
    var oPolys = (c.otherData.boundary && c.otherData.boundary.polygons) || [];
    for (var i = 1; i < oPolys.length; i++) {
        if (oPolys[i].points && oPolys[i].points.length >= 3) inners.push({ points: oPolys[i].points.slice() });
    }

    var tracks = JSON.parse(JSON.stringify(FE.field.tracks || []));
    (c.otherData.tracks || []).forEach(function (tr) {
        tracks.push(FE.geom.reprojectEntry(tr, c.otherPlane));
    });

    // headLines (coverage lines) are stored in lat/lon — safe to concatenate
    var hl = JSON.parse(JSON.stringify(FE.field.headLines || []));
    (c.otherData.headLines || []).forEach(function (h) { hl.push(h); });

    var startFix = (FE.field.field && FE.field.field.startFix) || {};
    var newData = {
        field: { startFix: { lat: startFix.lat, lon: startFix.lon } },
        boundary: {
            polygons: [{ points: c.merged.map(function (p) { return FE.geom.ll(p); }) }].concat(inners)
        },
        tracks: tracks,
        headland: [],          // old gon does not fit the merged border
        headLines: hl,
        sections: JSON.parse(JSON.stringify(FE.field.sections || { sections: [] })),
        yieldData: JSON.parse(JSON.stringify(FE.field.yieldData || { records: [] }))
    };

    c.busy = true;
    c._refreshOk();
    FE._tui.hint('Создаю поле «' + FE.escapeHtml(newName) + '»…');

    FE.api.createField(newName, newData).then(function () {
        var otherName = c.otherName;
        c.stop();
        FE.status('Создано объединённое поле «' + newName + '» из «' +
            FE.field.__name + '» и «' + otherName + '»');
        return FE.openField(newName, null);
    }).catch(function (e) {
        if (c.active) {
            c.busy = false;
            c._refreshOk();
            FE._tui.hint('<span style="color:#c0392b;">Ошибка: ' + FE.escapeHtml(e.message || e) + '</span>');
        }
        alert('Не удалось создать объединённое поле: ' + (e.message || e));
    });
};

// -------- wiring --------

FE.tool = { active: null };

FE.split.init = function () {
    document.getElementById('btnSplit').addEventListener('click', FE.split.start);
    document.getElementById('btnCombine').addEventListener('click', FE.combine.start);
    FE.hooks.afterClose.push(function () {
        FE.split.stop();
        FE.combine.stop();
    });
};
