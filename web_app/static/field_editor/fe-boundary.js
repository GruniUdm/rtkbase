// fe-boundary.js — boundary point editing: drag/insert/delete, ghost+offset,
// draw new outer/inner boundaries. Points in the field JSON are [lat, lon].
// Geometry helpers ported from aog-feldeditor (SkaFUU, MIT).
'use strict';

var FE = window.FE || (window.FE = {});

FE.boundary = {
    editing: false,     // edit mode active
    polyIndex: 0,       // which polygon is being edited (0 = outer)
    markers: [],        // circle markers for the edited polygon
    line: null,         // polyline of the edited polygon
    ghostLine: null,    // dashed old-boundary ghost while dragging
    ghostMarker: null,  // old position marker while dragging
    dragInfo: null,     // {lat, lon} position before drag
    drawing: null       // {mode:'outer'|'inner', latlngs:[], markers:[], line:null}
};

// -------- helpers --------

FE.boundary.polyPoints = function (idx) {
    var polys = (FE.field && FE.field.boundary && FE.field.boundary.polygons) || [];
    var p = polys[idx];
    return (p && p.points) || null;
};

FE.boundary.latLngToEN = function (lat, lon) {
    return FE.plane.fwd(lat, lon);
};

FE.boundary.enToLatLng = function (e, n) {
    var ll = FE.plane.inv(e, n);
    return [ll[0], ll[1]];
};

// -------- edit mode --------

FE.boundary.startEdit = function (polyIndex) {
    if (!FE.field) { alert('Сначала откройте поле'); return; }
    if (FE.tool && FE.tool.active) { alert('Сначала завершите инструмент разрезания/объединения.'); return; }
    FE.boundary.stopEdit();
    var pts = FE.boundary.polyPoints(polyIndex);
    if (!pts || pts.length < 3) {
        alert('В этой границе нет точек для редактирования');
        return;
    }
    FE.boundary.editing = true;
    FE.boundary.polyIndex = polyIndex;

    // hide the static boundary layer while editing (we draw our own)
    var key = polyIndex === 0 ? 'boundary' : 'inner';
    if (FE.layers[key] && FE.map.hasLayer(FE.layers[key])) FE.map.removeLayer(FE.layers[key]);

    var g = L.layerGroup().addTo(FE.map);
    FE.boundary.editGroup = g;
    FE.boundary._rebuildEditLayer();
    FE.boundary._setHint('Перетаскивайте точки, клик по линии — вставить точку, правый клик по точке — удалить. Ctrl+Z — отмена.');
    document.getElementById('btnBoundaryEdit').textContent = 'Закончить редактирование';
};

FE.boundary._rebuildEditLayer = function () {
    var b = FE.boundary;
    var pts = b.polyPoints(b.polyIndex);
    if (!pts) return;

    // clear old markers/line
    b.markers.forEach(function (m) { b.editGroup.removeLayer(m); });
    b.markers = [];
    if (b.line) { b.editGroup.removeLayer(b.line); b.line = null; }

    var latlngs = pts.map(function (p) { return [p[0], p[1]]; });
    b.line = L.polyline(latlngs.concat([latlngs[0]]), {
        color: '#e74c3c', weight: 3, fill: false
    }).addTo(b.editGroup);

    // insert point when clicking the line
    b.line.on('click', function (e) {
        FE.boundary._insertPointAt(e.latlng);
    });

    pts.forEach(function (p, i) {
        var m = L.circleMarker([p[0], p[1]], {
            radius: 5, color: '#c0392b', fillColor: '#e74c3c', fillOpacity: 1, weight: 1
        }).addTo(b.editGroup);
        m.on('contextmenu', function (e) {
            L.DomEvent.stopPropagation(e);
            FE.boundary._deletePoint(i);
        });
        m.on('mousedown', function (e) {
            L.DomEvent.stopPropagation(e);
            FE.boundary._startDrag(m, i, e);
        });
        b.markers.push(m);
    });
};

FE.boundary._startDrag = function (marker, index, e) {
    var b = FE.boundary;
    FE.map.dragging.disable();
    var pts = b.polyPoints(b.polyIndex);
    var orig = pts[index].slice();

    FE.pushUndo();
    b.dragInfo = { index: index, orig: orig, moved: false };

    // ghost: dashed old position + dashed old line
    b.ghostMarker = L.circleMarker([orig[0], orig[1]], {
        radius: 4, color: '#888', fill: false, dashArray: '2,2', interactive: false
    }).addTo(b.editGroup);
    var oldLatlngs = pts.map(function (p) { return [p[0], p[1]]; });
    oldLatlngs[index] = [orig[0], orig[1]];
    b.ghostLine = L.polyline(oldLatlngs.concat([oldLatlngs[0]]), {
        color: '#999', weight: 1, dashArray: '4,4', fill: false, interactive: false
    }).addTo(b.editGroup);

    function onMove(ev) {
        var ll = ev.latlng;
        pts[b.dragInfo.index] = [ll.lat, ll.lng];
        marker.setLatLng(ll);
        b.line.setLatLngs(pts.map(function (p) { return [p[0], p[1]]; }).concat([[pts[0][0], pts[0][1]]]));
        b.dragInfo.moved = true;
        b._showOffset(orig, ll.lat, ll.lng);
    }
    function onUp() {
        FE.map.off('mousemove', onMove);
        FE.map.off('mouseup', onUp);
        FE.map.dragging.enable();
        if (b.dragInfo && b.dragInfo.moved) {
            FE.setDirty(true);
            FE.boundary._hintOffset(orig, pts[b.dragInfo.index]);
        } else {
            // no movement — drop the undo snapshot
            FE.undoStack.pop();
            FE.updateUndoButton();
            b._hideGhost();
        }
        b.dragInfo = null;
    }
    FE.map.on('mousemove', onMove);
    FE.map.on('mouseup', onUp);
};

FE.boundary._hideGhost = function () {
    var b = FE.boundary;
    if (b.ghostMarker) { b.editGroup.removeLayer(b.ghostMarker); b.ghostMarker = null; }
    if (b.ghostLine) { b.editGroup.removeLayer(b.ghostLine); b.ghostLine = null; }
};

FE.boundary._insertPointAt = function (latlng) {
    var b = FE.boundary;
    var pts = b.polyPoints(b.polyIndex);
    if (!pts) return;
    // find nearest segment in local coordinates
    var pEN = b.latLngToEN(latlng.lat, latlng.lng);
    var best = 0, bestD = Infinity;
    for (var i = 0; i < pts.length; i++) {
        var j = (i + 1) % pts.length;
        var a = b.latLngToEN(pts[i][0], pts[i][1]);
        var c = b.latLngToEN(pts[j][0], pts[j][1]);
        var d = FE.distToSeg(pEN, a, c);
        if (d < bestD) { bestD = d; best = i; }
    }
    // only insert if the click is reasonably close (< 15 m)
    if (bestD > 15) return;
    FE.pushUndo();
    pts.splice(best + 1, 0, [FE.r7(latlng.lat), FE.r7(latlng.lng)]);
    b._rebuildEditLayer();
    FE.setDirty(true);
};

FE.boundary._deletePoint = function (index) {
    var b = FE.boundary;
    var pts = b.polyPoints(b.polyIndex);
    if (!pts) return;
    if (pts.length <= 3) { alert('Минимум 3 точки'); return; }
    if (!window.confirm('Удалить точку #' + (index + 1) + '?')) return;
    FE.pushUndo();
    pts.splice(index, 1);
    b._rebuildEditLayer();
    FE.setDirty(true);
};

FE.boundary._showOffset = function (origLatLon, lat, lon) {
    var b = FE.boundary;
    var el = document.getElementById('boundaryOffsetInfo');
    if (!el) return;
    var o = b.latLngToEN(origLatLon[0], origLatLon[1]);
    var n = b.latLngToEN(lat, lon);
    var de = n.e - o.e, dn = n.n - o.n;
    var dist = Math.hypot(de, dn);
    var ns = dn >= 0 ? 'С' : 'Ю';
    var ew = de >= 0 ? 'В' : 'З';
    el.textContent = 'Δ ' + dist.toFixed(2) + ' м (' + ns + ' ' + Math.abs(dn).toFixed(1) +
        ', ' + ew + ' ' + Math.abs(de).toFixed(1) + ')';
    el.style.display = 'inline';
};

FE.boundary._hintOffset = function (origLatLon, newLatLon) {
    var b = FE.boundary;
    var el = document.getElementById('boundaryOffsetInfo');
    if (!el) return;
    var o = b.latLngToEN(origLatLon[0], origLatLon[1]);
    var n = b.latLngToEN(newLatLon[0], newLatLon[1]);
    var de = n.e - o.e, dn = n.n - o.n;
    var dist = Math.hypot(de, dn);
    if (dist < 0.01) { el.style.display = 'none'; return; }
    var ns = dn >= 0 ? 'С' : 'Ю';
    var ew = de >= 0 ? 'В' : 'З';
    el.textContent = 'Точка сдвинута на ' + dist.toFixed(2) + ' м (' + ns + ' ' + Math.abs(dn).toFixed(1) +
        ', ' + ew + ' ' + Math.abs(de).toFixed(1) + ')';
    el.style.display = 'inline';
};

FE.boundary.stopEdit = function () {
    var b = FE.boundary;
    if (!b.editing) return;
    b._hideGhost();
    b.markers.forEach(function (m) { if (b.editGroup) b.editGroup.removeLayer(m); });
    b.markers = [];
    if (b.line && b.editGroup) b.editGroup.removeLayer(b.line);
    b.line = null;
    if (b.editGroup) FE.map.removeLayer(b.editGroup);
    b.editGroup = null;
    b.editing = false;
    b._setHint('');
    var el = document.getElementById('boundaryOffsetInfo');
    if (el) el.style.display = 'none';
    document.getElementById('btnBoundaryEdit').textContent = 'Редактировать границу';
    // re-render static layers from data
    FE.renderField();
};

FE.boundary._setHint = function (msg) {
    var el = document.getElementById('boundaryHint');
    if (!el) return;
    el.textContent = msg;
    el.style.display = msg ? 'block' : 'none';
};

// -------- draw a new boundary --------

FE.boundary.startDraw = function (mode) { // 'outer' | 'inner'
    if (!FE.field) { alert('Сначала откройте поле'); return; }
    if (FE.boundary.editing) FE.boundary.stopEdit();
    FE.boundary.cancelDraw();
    var b = FE.boundary;
    b.drawing = { mode: mode, latlngs: [], markers: [], line: null };
    FE.map.getContainer().style.cursor = 'crosshair';
    b._setHint(mode === 'outer'
        ? 'Клики по карте — точки новой внешней границы. Dblclick или кнопка «Готово» — завершить.'
        : 'Клики по карте — точки новой внутренней границы. Dblclick или кнопка «Готово» — завершить.');
    document.getElementById('btnDrawFinish').style.display = 'inline-block';
    document.getElementById('btnDrawCancel').style.display = 'inline-block';
    FE.map.on('click', b._onDrawClick);
    FE.map.on('dblclick', b._onDrawDblClick);
};

FE.boundary._onDrawClick = function (e) {
    var b = FE.boundary;
    if (!b.drawing) return;
    var ll = [e.latlng.lat, e.latlng.lng];
    b.drawing.latlngs.push(ll);
    var m = L.circleMarker(ll, { radius: 4, color: '#2980b9', fillColor: '#3498db', fillOpacity: 1 })
        .addTo(FE.map);
    if (!b.drawing.line) {
        b.drawing.line = L.polyline(b.drawing.latlngs, { color: '#2980b9', weight: 2, dashArray: '4,3' }).addTo(FE.map);
    } else {
        b.drawing.line.setLatLngs(b.drawing.latlngs);
    }
    b.drawing.markers.push(m);
};

FE.boundary._onDrawDblClick = function () {
    FE.boundary.finishDraw();
};

FE.boundary.finishDraw = function () {
    var b = FE.boundary;
    if (!b.drawing) return;
    var latlngs = b.drawing.latlngs;
    var mode = b._lastDrawMode || 'outer';
    b.cancelDraw();
    // dblclick fires two extra click events — drop near-duplicate tail points
    while (latlngs.length > 1) {
        var a = latlngs[latlngs.length - 1];
        var c = latlngs[latlngs.length - 2];
        if (FE.distM(a[0], a[1], c[0], c[1]) < 0.5) latlngs.pop();
        else break;
    }
    if (latlngs.length < 3) { alert('Минимум 3 точки'); return; }
    FE.pushUndo();
    var pts = latlngs.map(function (p) { return [FE.r7(p[0]), FE.r7(p[1])]; });
    if (mode === 'outer') {
        if (!FE.field.boundary) FE.field.boundary = {};
        if (!FE.field.boundary.polygons) FE.field.boundary.polygons = [];
        if (FE.field.boundary.polygons.length) {
            if (!window.confirm('Заменить внешнюю границу?')) { FE.undoStack.pop(); FE.updateUndoButton(); return; }
            FE.field.boundary.polygons[0] = { points: pts };
        } else {
            FE.field.boundary.polygons[0] = { points: pts };
        }
    } else {
        if (!FE.field.boundary) FE.field.boundary = {};
        if (!FE.field.boundary.polygons) FE.field.boundary.polygons = [];
        if (!FE.field.boundary.polygons.length) {
            alert('Сначала нужна внешняя граница');
            FE.undoStack.pop();
            FE.updateUndoButton();
            return;
        }
        FE.field.boundary.polygons.push({ points: pts });
    }
    FE.renderField();
    FE.setDirty(true);
    FE.boundary._setHint('');
    FE.boundary.updateInnerList();
};

FE.boundary.cancelDraw = function () {
    var b = FE.boundary;
    if (!b.drawing) return;
    b.drawing.markers.forEach(function (m) { FE.map.removeLayer(m); });
    if (b.drawing.line) FE.map.removeLayer(b.drawing.line);
    b.drawing = null;
    FE.map.getContainer().style.cursor = '';
    FE.map.off('click', b._onDrawClick);
    FE.map.off('dblclick', b._onDrawDblClick);
    document.getElementById('btnDrawFinish').style.display = 'none';
    document.getElementById('btnDrawCancel').style.display = 'none';
    b._setHint('');
};

// remember draw mode (startDraw stores it here because cancelDraw clears b.drawing)
var _origStartDraw = FE.boundary.startDraw;
FE.boundary.startDraw = function (mode) {
    if (FE.tool && FE.tool.active) { alert('Сначала завершите инструмент разрезания/объединения.'); return; }
    FE.boundary._lastDrawMode = mode;
    _origStartDraw(mode);
};

// -------- inner boundary management --------

FE.boundary.deleteInner = function (idx) {
    var polys = (FE.field && FE.field.boundary && FE.field.boundary.polygons) || [];
    if (idx < 1 || idx >= polys.length) return;
    if (!window.confirm('Удалить внутреннюю границу #' + idx + '?')) return;
    FE.pushUndo();
    polys.splice(idx, 1);
    FE.renderField();
    FE.setDirty(true);
    FE.boundary.updateInnerList();
};

FE.boundary.updateInnerList = function () {
    var el = document.getElementById('boundaryInnerList');
    if (!el) return;
    var polys = (FE.field && FE.field.boundary && FE.field.boundary.polygons) || [];
    if (polys.length <= 1) {
        el.innerHTML = '<div class="text-muted" style="font-size:0.85em;">Нет внутренних границ</div>';
        return;
    }
    var html = '';
    for (var i = 1; i < polys.length; i++) {
        var n = (polys[i].points || []).length;
        html += '<div class="d-flex justify-content-between align-items-center" style="font-size:0.85em;padding:2px 0;">' +
            '<span>#' + i + ' (' + n + ' т.)</span>' +
            '<span>' +
            '<button class="btn btn-xs btn-outline-secondary" style="padding:0 4px;font-size:0.75em;" onclick="FE.boundary.startEdit(' + i + ')">Править</button> ' +
            '<button class="btn btn-xs btn-outline-danger" style="padding:0 4px;font-size:0.75em;" onclick="FE.boundary.deleteInner(' + i + ')">✕</button>' +
            '</span></div>';
    }
    el.innerHTML = html;
};

// -------- wiring --------

FE.boundary.init = function () {
    document.getElementById('btnBoundaryEdit').addEventListener('click', function () {
        if (FE.boundary.editing) FE.boundary.stopEdit();
        else FE.boundary.startEdit(0);
    });
    document.getElementById('btnDrawOuter').addEventListener('click', function () {
        FE.boundary.startDraw('outer');
    });
    document.getElementById('btnDrawInner').addEventListener('click', function () {
        FE.boundary.startDraw('inner');
    });
    document.getElementById('btnDrawFinish').addEventListener('click', function () {
        FE.boundary.finishDraw();
    });
    document.getElementById('btnDrawCancel').addEventListener('click', function () {
        FE.boundary.cancelDraw();
    });

    // Ctrl+Z undo (same as global undo button)
    window.addEventListener('keydown', function (e) {
        if ((e.ctrlKey || e.metaKey) && e.key === 'z' && !e.shiftKey) {
            // don't steal undo from inputs
            var t = e.target.tagName;
            if (t === 'INPUT' || t === 'TEXTAREA') return;
            e.preventDefault();
            FE.undo();
        }
    });

    FE.hooks.afterOpen.push(function () { FE.boundary.updateInnerList(); });
    FE.hooks.afterUndo.push(function () {
        if (FE.boundary.editing) {
            // rebuild edit layer from restored data
            FE.boundary._rebuildEditLayer();
        }
        FE.boundary.updateInnerList();
    });
    FE.hooks.afterClose.push(function () {
        FE.boundary.stopEdit();
        FE.boundary.updateInnerList();
    });
};
