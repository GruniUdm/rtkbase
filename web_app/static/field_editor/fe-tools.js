// fe-tools.js — measure tool: click points on the map, shows segment and
// total distances, double-click or Esc to finish.
'use strict';

var FE = window.FE || (window.FE = {});

FE.measure = {
    active: false,
    points: [],   // [[lat, lon], ...]
    markers: [],
    line: null,
    label: null
};

FE.measure.start = function () {
    if (FE.measure.active) { FE.measure.stop(); return; }
    if (FE.tool && FE.tool.active) { alert('Сначала завершите инструмент разрезания/объединения.'); return; }
    FE.measure.active = true;
    FE.measure.points = [];
    FE.map.getContainer().style.cursor = 'crosshair';
    FE.measure._setHint('Клики — точки измерения. Dblclick или Esc — завершить.');
    document.getElementById('btnMeasure').textContent = 'Закончить мерку';
    FE.map.on('click', FE.measure._onClick);
    FE.map.on('dblclick', FE.measure._onDblClick);
    window.addEventListener('keydown', FE.measure._onKey);
};

FE.measure.stop = function () {
    if (!FE.measure.active) return;
    FE.measure.active = false;
    FE.map.off('click', FE.measure._onClick);
    FE.map.off('dblclick', FE.measure._onDblClick);
    window.removeEventListener('keydown', FE.measure._onKey);
    FE.measure.markers.forEach(function (m) { try { FE.map.removeLayer(m); } catch (e) {} });
    FE.measure.markers = [];
    if (FE.measure.line) { try { FE.map.removeLayer(FE.measure.line); } catch (e) {} FE.measure.line = null; }
    FE.measure.points = [];
    FE.map.getContainer().style.cursor = '';
    FE.measure._setHint('');
    FE.measure._setLabel('');
    document.getElementById('btnMeasure').textContent = 'Мерка';
};

FE.measure._onClick = function (e) {
    var m = FE.measure;
    if (!m.active) return;
    var ll = [e.latlng.lat, e.latlng.lng];
    m.points.push(ll);
    m.markers.push(L.circleMarker(ll, { radius: 3, color: '#16a085', fillColor: '#1abc9c', fillOpacity: 1 }).addTo(FE.map));
    m._redraw();
};

FE.measure._onDblClick = function () {
    FE.measure.stop();
};

FE.measure._onKey = function (e) {
    if (e.key === 'Escape') FE.measure.stop();
};

FE.measure._redraw = function () {
    var m = FE.measure;
    if (m.line) { try { FE.map.removeLayer(m.line); } catch (e) {} m.line = null; }
    if (m.points.length < 1) { m._setLabel(''); return; }
    if (m.points.length >= 2) {
        m.line = L.polyline(m.points, { color: '#16a085', weight: 2, dashArray: '5,4' }).addTo(FE.map);
    }
    // totals
    var total = 0, segs = [];
    for (var i = 1; i < m.points.length; i++) {
        var a = m.points[i - 1], b = m.points[i];
        var d = FE.distM(a[0], a[1], b[0], b[1]);
        segs.push(d);
        total += d;
    }
    var txt;
    if (!m.points.length) txt = '';
    else if (m.points.length === 1) txt = 'Точек: 1';
    else {
        txt = 'Всего ' + (total >= 1000 ? (total / 1000).toFixed(3) + ' км' : total.toFixed(2) + ' м');
        if (segs.length > 1) txt += ' (последний отрезок ' + segs[segs.length - 1].toFixed(2) + ' м)';
        txt += ' · точек: ' + m.points.length;
    }
    m._setLabel(txt);
};

FE.measure._setLabel = function (msg) {
    var el = document.getElementById('measureInfo');
    if (!el) return;
    el.textContent = msg;
    el.style.display = msg ? 'block' : 'none';
};

FE.measure._setHint = function (msg) {
    var el = document.getElementById('measureHint');
    if (!el) return;
    el.textContent = msg;
    el.style.display = msg ? 'block' : 'none';
};

FE.measure.init = function () {
    document.getElementById('btnMeasure').addEventListener('click', FE.measure.start);
    FE.hooks.afterClose.push(function () { FE.measure.stop(); });
};
