// fe-plane.js — LocalPlane projection (matches AgOpenGPS LocalPlane) + helpers.
// Ported from aog-feldeditor (SkaFUU, MIT).
'use strict';

var FE = window.FE || (window.FE = {});

FE.D2R = Math.PI / 180;
FE.R2D = 180 / Math.PI;

FE.mLat = function (la) {
    return 111132.92 - 559.82 * Math.cos(2 * la * FE.D2R) + 1.175 * Math.cos(4 * la * FE.D2R) - 0.0023 * Math.cos(6 * la * FE.D2R);
};

FE.mLon = function (la) {
    return 111412.84 * Math.cos(la * FE.D2R) - 93.5 * Math.cos(3 * la * FE.D2R) + 0.118 * Math.cos(5 * la * FE.D2R);
};

// Plane: lat/lon <-> local easting/northing (metres) around an origin.
FE.Plane = function (lat0, lon0) {
    var ml = FE.mLat(lat0);
    return {
        lat0: lat0,
        lon0: lon0,
        fwd: function (la, lo) {
            return { e: (lo - lon0) * FE.mLon(la), n: (la - lat0) * ml };
        },
        inv: function (e, n) {
            var la = lat0 + n / ml;
            return [la, lon0 + e / FE.mLon(la)];
        }
    };
};

FE.r3 = function (v) { return Math.round(v * 1000) / 1000; };
FE.r5 = function (v) { return Math.round(v * 100000) / 100000; };
FE.r7 = function (v) { return Math.round(v * 1e7) / 1e7; };

// Haversine distance in metres.
FE.distM = function (la1, lo1, la2, lo2) {
    var R = 6371000;
    var dLa = (la2 - la1) * FE.D2R;
    var dLo = (lo2 - lo1) * FE.D2R;
    var a = Math.sin(dLa / 2) * Math.sin(dLa / 2) +
        Math.cos(la1 * FE.D2R) * Math.cos(la2 * FE.D2R) * Math.sin(dLo / 2) * Math.sin(dLo / 2);
    return 2 * R * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
};

// Signed area (shoelace) of a ring given as [{e,n},...]; >0 = CCW.
FE.signedArea = function (pts) {
    var a = 0;
    for (var i = 0, j = pts.length - 1; i < pts.length; j = i++) {
        a += pts[j].e * pts[i].n - pts[i].e * pts[j].n;
    }
    return a / 2;
};

// Distance from point p to segment ab (all {e,n}).
FE.distToSeg = function (p, a, b) {
    var dx = b.e - a.e, dy = b.n - a.n;
    var len2 = dx * dx + dy * dy;
    if (len2 === 0) return Math.hypot(p.e - a.e, p.n - a.n);
    var t = ((p.e - a.e) * dx + (p.n - a.n) * dy) / len2;
    t = Math.max(0, Math.min(1, t));
    return Math.hypot(p.e - (a.e + t * dx), p.n - (a.n + t * dy));
};

// Nearest vertex index of pts to {e,n}.
FE.nearestIndex = function (pts, e, n) {
    var best = 0, bestD = Infinity;
    for (var i = 0; i < pts.length; i++) {
        var d = (pts[i].e - e) * (pts[i].e - e) + (pts[i].n - n) * (pts[i].n - n);
        if (d < bestD) { bestD = d; best = i; }
    }
    return best;
};
