// fe-origin.js — move the field origin (field.startFix). Boundary/headland stay
// in lat/lon and are untouched; everything stored in local e/n (tracks,
// sections, yieldData) is reprojected: oldPlane.inv -> newPlane.fwd, matching
// the QtAgOpenGPS LocalPlane projection.
'use strict';

var FE = window.FE || (window.FE = {});

FE.origin = { moving: false };

FE.origin.startMove = function () {
    if (!FE.field) { alert('Сначала откройте поле'); return; }
    if (FE.tool && FE.tool.active) { alert('Сначала завершите инструмент разрезания/объединения.'); return; }
    FE.origin.cancelMove();
    FE.origin.moving = true;
    FE.map.getContainer().style.cursor = 'crosshair';
    FE.origin._setHint('Кликните на карте — новое начало координат (startFix).');
    FE.map.on('click', FE.origin._onClick);
};

FE.origin._onClick = function (e) {
    var lat = FE.r7(e.latlng.lat), lon = FE.r7(e.latlng.lng);
    FE.origin.cancelMove();
    if (!window.confirm('Перенести начало координат в эту точку?\n' +
        'Граница и гон не изменятся (они в lat/lon), но все AB-линии, секции и урожайность будут пересчитаны.')) {
        return;
    }
    FE.origin.apply(lat, lon);
};

FE.origin.apply = function (newLat, newLon) {
    var d = FE.field;
    if (!d || !FE.plane) return;
    var oldPlane = FE.plane;
    var newPlane = FE.Plane(newLat, newLon);

    FE.pushUndo();
    var t0 = performance.now();

    // reproject a single {easting, northing} object in place
    function reproj(pt) {
        if (!pt) return;
        var ll = oldPlane.inv(pt.easting || 0, pt.northing || 0);
        var en = newPlane.fwd(ll[0], ll[1]);
        pt.easting = Math.round(en.e * 1000) / 1000;
        pt.northing = Math.round(en.n * 1000) / 1000;
    }

    // tracks: ptA, ptB, curvePts (headings are absolute — unchanged)
    var tracks = d.tracks || [];
    for (var i = 0; i < tracks.length; i++) {
        var t = tracks[i];
        reproj(t.ptA);
        reproj(t.ptB);
        var curve = t.curvePts || [];
        for (var c = 0; c < curve.length; c++) reproj(curve[c]);
    }

    // sections: [[colorHdr, [e,n,z], [e,n,z], ...], ...]
    var sec = (d.sections && d.sections.sections) || (Array.isArray(d.sections) ? d.sections : []);
    for (var s = 0; s < sec.length; s++) {
        var arr = sec[s];
        if (!Array.isArray(arr)) continue;
        for (var p = 1; p < arr.length; p++) {
            var pt = arr[p];
            if (!Array.isArray(pt) || pt.length < 2) continue;
            var ll2 = oldPlane.inv(pt[0], pt[1]);
            var en2 = newPlane.fwd(ll2[0], ll2[1]);
            pt[0] = Math.round(en2.e * 1000) / 1000;
            pt[1] = Math.round(en2.n * 1000) / 1000;
        }
    }

    // yieldData: cmds [.., left_e, left_n, .., right_e, right_n, ..]
    var records = (d.yieldData && d.yieldData.records) || [];
    for (var r = 0; r < records.length; r++) {
        var cmds = records[r].cmds || [];
        for (var k = 0; k < cmds.length; k++) {
            var cmd = cmds[k];
            if (!Array.isArray(cmd) || cmd.length < 9) continue;
            var l1 = oldPlane.inv(cmd[4] || 0, cmd[5] || 0);
            var e1 = newPlane.fwd(l1[0], l1[1]);
            cmd[4] = Math.round(e1.e * 1000) / 1000;
            cmd[5] = Math.round(e1.n * 1000) / 1000;
            var l2 = oldPlane.inv(cmd[7] || 0, cmd[8] || 0);
            var e2 = newPlane.fwd(l2[0], l2[1]);
            cmd[7] = Math.round(e2.e * 1000) / 1000;
            cmd[8] = Math.round(e2.n * 1000) / 1000;
        }
    }

    // move the origin itself
    if (!d.field) d.field = {};
    d.field.startFix = { lat: newLat, lon: newLon };

    // switch the working plane and re-render
    FE.plane = newPlane;
    FE.renderField();
    FE.setDirty(true);
    FE.status('Origin перенесён за ' + Math.round(performance.now() - t0) + ' мс (не забудьте сохранить)');
};

FE.origin.cancelMove = function () {
    if (!FE.origin.moving) return;
    FE.origin.moving = false;
    FE.map.off('click', FE.origin._onClick);
    FE.map.getContainer().style.cursor = '';
    FE.origin._setHint('');
};

FE.origin._setHint = function (msg) {
    var el = document.getElementById('originHint');
    if (!el) return;
    el.textContent = msg;
    el.style.display = msg ? 'block' : 'none';
};

FE.origin.init = function () {
    document.getElementById('btnOriginMove').addEventListener('click', FE.origin.startMove);
    FE.hooks.afterClose.push(function () { FE.origin.cancelMove(); });
};
