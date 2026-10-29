// fe-core.js — map init, field list, field loading/rendering, save/undo.
'use strict';

var FE = window.FE || (window.FE = {});

// -------- global state --------
FE.map = null;
FE.field = null;        // loaded field json (with __name, __updated)
FE.plane = null;        // Plane at field origin (startFix)
FE.dirty = false;
FE.undoStack = [];
FE.undoLimit = 30;

FE.layers = {};         // L.LayerGroup per group key
FE.layerVisibility = {
    boundary: true, inner: true, headland: true, headLines: true, abLine: true,
    origin: true, cadastre: false
};

// hooks: arrays of callbacks { afterOpen: [], afterUndo: [], afterClose: [] }
FE.hooks = { afterOpen: [], afterUndo: [], afterClose: [] };
FE._runHooks = function (name) {
    (FE.hooks[name] || []).forEach(function (f) { try { f(); } catch (e) { console.error(e); } });
};

// -------- init --------
FE.initMap = function (baseCoordinates) {
    var map = L.map('map').setView({ lat: baseCoordinates.lat, lon: baseCoordinates.lon }, 14);
    var osm = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap contributors'
    });
    var sat = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
        attribution: '&copy; Esri'
    });
    var s2 = L.tileLayer.wms('https://tiles.maps.eox.at/wms?', {
        layers: 's2cloudless-2024_3857',
        format: 'image/jpeg',
        transparent: false,
        attribution: '&copy; EOX / Copernicus Sentinel'
    });
    osm.addTo(map);
    L.control.layers({ 'Map': osm, 'Satellite': sat, 'Sentinel-2': s2 }, null, { position: 'bottomleft' }).addTo(map);

    // Public cadastre map (EGRN parcels) served through our tile proxy.
    FE.cadastreLayer = L.tileLayer('/api/cadastre/tile/{z}/{x}/{y}.png', {
        attribution: '&copy; Росреестр / НСПД',
        maxNativeZoom: 17,
        maxZoom: 20,
        opacity: 0.7
    });
    if (FE.layerVisibility.cadastre) FE.cadastreLayer.addTo(map);
    var baseIcon = L.icon({
        iconUrl: '/static/images/iconmonstr-crosshair-6-64.png',
        iconSize: [24, 24],
        iconAnchor: [12, 12]
    });
    L.marker(baseCoordinates, { icon: baseIcon }).addTo(map).bindTooltip('Базовая станция');
    FE.map = map;
    return map;
};

// -------- field list --------
FE.loadFieldList = function () {
    return FE.api.listFields().then(function (fields) {
        FE.renderFieldList(fields);
        return fields;
    }).catch(function (e) {
        document.getElementById('fieldList').innerHTML =
            '<div class="text-muted" style="padding:8px;">Ошибка загрузки: ' + FE.escapeHtml(e.message) + '</div>';
    });
};

FE.renderFieldList = function (fields) {
    var el = document.getElementById('fieldList');
    if (!fields || !fields.length) {
        el.innerHTML = '<div class="text-muted" style="padding:8px;">Нет полей</div>';
        return;
    }
    var html = '';
    fields.forEach(function (f) {
        var active = FE.field && FE.field.__name === f.name;
        html += '<div class="fe-field-item' + (active ? ' active' : '') + '" data-name="' + FE.escapeHtml(f.name) + '">' +
            FE.escapeHtml(f.name) + '</div>';
    });
    el.innerHTML = html;
};

FE.escapeHtml = function (s) {
    return String(s).replace(/[&<>"']/g, function (c) {
        return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
};

// -------- load field --------
FE.openField = function (name, updated) {
    if (FE.tool && FE.tool.active && FE[FE.tool.active] && FE[FE.tool.active].busy) {
        alert('Дождитесь завершения текущей операции.');
        return Promise.resolve();
    }
    if (FE.dirty && !window.confirm('Есть несохранённые изменения. Продолжить без сохранения?')) {
        return Promise.resolve();
    }
    return FE.api.loadField(name, updated).then(function (data) {
        FE.closeField();
        FE.field = data;
        var sf = (data.field && data.field.startFix) || {};
        var refLat = sf.lat, refLon = sf.lon;
        if (refLat == null && data.boundary && data.boundary.polygons && data.boundary.polygons[0]) {
            var p0 = data.boundary.polygons[0].points && data.boundary.polygons[0].points[0];
            if (p0) { refLat = p0[0]; refLon = p0[1]; }
        }
        if (refLat == null) { refLat = 0; refLon = 0; }
        FE.plane = FE.Plane(refLat, refLon);
        FE.renderField();
        FE.fitFieldBounds();
        FE.setDirty(false);
        FE.undoStack = [];
        FE.updateTitle();
        FE.loadFieldList().then(function (fields) { FE_lastList = fields || []; });
        FE._runHooks('afterOpen');
    }).catch(function (e) {
        alert('Ошибка загрузки поля: ' + e.message);
    });
};

FE.closeField = function () {
    FE._runHooks('afterClose');
    Object.keys(FE.layers).forEach(function (k) {
        if (FE.layers[k]) { try { FE.map.removeLayer(FE.layers[k]); } catch (e) {} }
    });
    FE.layers = {};
    FE.field = null;
    FE.plane = null;
    FE.setDirty(false);
    FE.updateTitle();
};

// -------- rendering --------
FE.renderField = function () {
    var data = FE.field;
    if (!data || !FE.map) return;
    Object.keys(FE.layers).forEach(function (k) {
        if (FE.layers[k]) { try { FE.map.removeLayer(FE.layers[k]); } catch (e) {} }
    });
    FE.layers = {};

    var boundary = data.boundary || {};
    var polygons = boundary.polygons || [];

    // outer boundary
    if (polygons[0] && polygons[0].points && polygons[0].points.length >= 3) {
        var outer = polygons[0].points.map(function (p) { return [p[0], p[1]]; });
        var g = L.layerGroup();
        L.polygon(outer, { color: '#e74c3c', weight: 3, fill: false }).addTo(g);
        if (FE.layerVisibility.boundary) g.addTo(FE.map);
        FE.layers.boundary = g;
    }

    // inner boundaries
    if (polygons.length > 1) {
        var gi = L.layerGroup();
        for (var i = 1; i < polygons.length; i++) {
            var pts = polygons[i].points || [];
            if (pts.length < 3) continue;
            L.polygon(pts.map(function (p) { return [p[0], p[1]]; }),
                { color: '#f39c12', weight: 2, dashArray: '4,4', fill: false }).addTo(gi);
        }
        if (FE.layerVisibility.inner) gi.addTo(FE.map);
        FE.layers.inner = gi;
    }

    // headland (gon) — list of {points:[[lat,lon]]} or bare lists
    var headland = data.headland || [];
    if (headland.length) {
        var gh = L.layerGroup();
        headland.forEach(function (hl) {
            var pts = (hl && hl.points) ? hl.points : hl;
            if (pts && pts.length >= 2) {
                L.polyline(pts.map(function (p) { return [p[0], p[1]]; }),
                    { color: '#e67e22', weight: 2, dashArray: '6,4' }).addTo(gh);
            }
        });
        if (FE.layerVisibility.headland) gh.addTo(FE.map);
        FE.layers.headland = gh;
    }

    // headLines (tracks from QtAgOpenGPS coverage / AB curves list)
    var headLines = data.headLines || [];
    if (headLines.length) {
        var gl = L.layerGroup();
        headLines.forEach(function (hl) {
            var pts = (hl && hl.points) ? hl.points : hl;
            if (pts && pts.length >= 2) {
                L.polyline(pts.map(function (p) { return [p[0], p[1]]; }),
                    { color: '#3498db', weight: 2 }).addTo(gl);
            }
        });
        if (FE.layerVisibility.headLines) gl.addTo(FE.map);
        FE.layers.headLines = gl;
    }

    // AB lines / curves (tracks with ptA/ptB in local e/n)
    var tracks = data.tracks || [];
    if (tracks.length) {
        var ga = L.layerGroup();
        tracks.forEach(function (t) {
            if (t.isVisible === false) return;
            var coords = FE.trackEntryLatLngs(t);
            if (coords.length >= 2) {
                L.polyline(coords, { color: '#e74c3c', weight: 2, dashArray: '8,4' }).addTo(ga);
            }
        });
        if (FE.layerVisibility.abLine) ga.addTo(FE.map);
        FE.layers.abLine = ga;
    }

    // origin marker + 500 m circle
    if (data.field && data.field.startFix && data.field.startFix.lat != null) {
        var go = L.layerGroup();
        var origin = [data.field.startFix.lat, data.field.startFix.lon];
        L.circleMarker(origin, { radius: 5, color: '#8e44ad', fill: false }).addTo(go);
        L.circle(origin, { radius: 500, color: '#8e44ad', weight: 1, dashArray: '2,6', fill: false, interactive: false }).addTo(go);
        if (FE.layerVisibility.origin) go.addTo(FE.map);
        FE.layers.origin = go;
    }
};

// Convert a track entry (local e/n) to [lat,lng] array for Leaflet.
FE.trackEntryLatLngs = function (t) {
    var curve = t.curvePts || [];
    if (curve.length > 2) {
        return curve.map(function (cp) {
            var ll = FE.plane.inv(cp.easting || 0, cp.northing || 0);
            return [ll[0], ll[1]];
        });
    }
    var a = t.ptA || {}, b = t.ptB || {};
    var la = FE.plane.inv(a.easting || 0, a.northing || 0);
    var lb = FE.plane.inv(b.easting || 0, b.northing || 0);
    return [[la[0], la[1]], [lb[0], lb[1]]];
};

FE.fitFieldBounds = function () {
    var data = FE.field;
    if (!data) return;
    var b = data.boundary || {};
    var polygons = b.polygons || [];
    if (polygons[0] && polygons[0].points && polygons[0].points.length >= 3) {
        try {
            FE.map.fitBounds(L.polygon(polygons[0].points.map(function (p) { return [p[0], p[1]]; })).getBounds().pad(0.15));
        } catch (e) {}
    }
};

// -------- layer toggles --------
FE.toggleLayer = function (key, visible) {
    FE.layerVisibility[key] = visible;
    if (key === 'cadastre') {
        if (!FE.cadastreLayer) return;
        if (visible) FE.cadastreLayer.addTo(FE.map);
        else if (FE.map.hasLayer(FE.cadastreLayer)) FE.map.removeLayer(FE.cadastreLayer);
        return;
    }
    var g = FE.layers[key];
    if (!g) return;
    if (visible) { if (!FE.map.hasLayer(g)) g.addTo(FE.map); }
    else if (FE.map.hasLayer(g)) FE.map.removeLayer(g);
};

// -------- undo / dirty --------
FE.pushUndo = function () {
    if (!FE.field) return;
    FE.undoStack.push(JSON.stringify(FE.field));
    if (FE.undoStack.length > FE.undoLimit) FE.undoStack.shift();
    FE.updateUndoButton();
};

FE.undo = function () {
    if (!FE.undoStack.length || !FE.field) return;
    var snap = JSON.parse(FE.undoStack.pop());
    var name = FE.field.__name, updated = FE.field.__updated;
    snap.__name = name;
    snap.__updated = updated;
    FE.field = snap;
    FE.renderField();
    FE.setDirty(true);
    FE.updateUndoButton();
    FE._runHooks('afterUndo');
};

FE.updateUndoButton = function () {
    var btn = document.getElementById('btnUndo');
    if (btn) btn.disabled = FE.undoStack.length === 0;
};

FE.setDirty = function (v) {
    FE.dirty = v;
    var saveBtn = document.getElementById('btnSave');
    if (saveBtn) {
        saveBtn.disabled = !v;
        saveBtn.textContent = v ? 'Сохранить *' : 'Сохранить';
    }
    FE.updateTitle();
};

FE.updateTitle = function () {
    var el = document.getElementById('currentFieldName');
    if (!el) return;
    el.textContent = FE.field ? FE.field.__name + (FE.dirty ? ' *' : '') : '—';
};

// -------- save --------
FE.save = function () {
    if (!FE.field || !FE.dirty) return Promise.resolve();
    var name = FE.field.__name;
    var baseUpdated = FE.field.__updated;
    FE.setSaveBusy(true);
    return FE.api.saveField(name, FE.field, baseUpdated).then(function (res) {
        FE.field.__updated = res.updated;
        FE.setDirty(false);
        FE.undoStack = [];
        FE.updateUndoButton();
        FE.status('Сохранено');
        FE.loadFieldList();
        if (FE.backups && FE.backups.updateList) FE.backups.updateList();
    }).catch(function (e) {
        if (e.status === 409) {
            alert('Поле было изменено вне редактора (например, загружен новый импорт).\n' +
                'Обновите страницу и повторите изменения.');
        } else {
            alert('Ошибка сохранения: ' + e.message);
        }
    }).then(function () {
        FE.setSaveBusy(false);
    });
};

FE.setSaveBusy = function (busy) {
    var saveBtn = document.getElementById('btnSave');
    if (saveBtn) saveBtn.disabled = busy || !FE.dirty;
    var undoBtn = document.getElementById('btnUndo');
    if (undoBtn) undoBtn.disabled = busy || FE.undoStack.length === 0;
};

FE.status = function (msg) {
    var el = document.getElementById('feStatus');
    if (el) el.textContent = msg;
};

// -------- wiring --------
var FE_lastList = null;

FE.boot = function (baseCoordinates) {
    FE.initMap(baseCoordinates);
    FE.loadFieldList().then(function (fields) { FE_lastList = fields || []; });

    document.getElementById('fieldList').addEventListener('click', function (e) {
        var item = e.target.closest('.fe-field-item');
        if (!item) return;
        var name = item.getAttribute('data-name');
        var entry = (FE_lastList || []).filter(function (f) { return f.name === name; })[0];
        FE.openField(name, entry ? entry.updated : null);
    });

    document.getElementById('btnSave').addEventListener('click', FE.save);
    document.getElementById('btnUndo').addEventListener('click', FE.undo);
    document.getElementById('btnReload').addEventListener('click', function () {
        if (!FE.field) return;
        var name = FE.field.__name;
        var entry = (FE_lastList || []).filter(function (f) { return f.name === name; })[0];
        FE.openField(name, entry ? entry.updated : null);
    });

    // layer checkboxes
    var boxes = document.querySelectorAll('.fe-layer-toggle');
    for (var i = 0; i < boxes.length; i++) {
        (function (box) {
            box.addEventListener('change', function () {
                FE.toggleLayer(box.getAttribute('data-layer'), box.checked);
            });
        })(boxes[i]);
    }

    window.addEventListener('beforeunload', function (e) {
        if (FE.dirty) { e.preventDefault(); e.returnValue = ''; }
    });
};
