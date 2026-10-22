// fe-tracks.js — AB line / curve tracks: list, create by two clicks on the
// boundary (via the server builder, preview only — saved with the field),
// rename, delete, show/hide, smooth.
'use strict';

var FE = window.FE || (window.FE = {});

FE.tracks = {
    creating: null,   // {type:'ab'|'curve', ptA:null, points:[]}
    markers: [],
    previewLayer: null
};

// -------- list panel --------

FE.tracks.updateList = function () {
    var el = document.getElementById('tracksList');
    if (!el) return;
    var tracks = (FE.field && FE.field.tracks) || [];
    if (!tracks.length) {
        el.innerHTML = '<div class="text-muted" style="font-size:0.85em;">Нет треков</div>';
        return;
    }
    var html = '';
    tracks.forEach(function (t, i) {
        var name = FE.escapeHtml(t.name || ('Трек #' + (i + 1)));
        var mode = t.mode === 2 ? 'AB' : (t.mode === 4 ? 'Кривая' : '?' + (t.mode || ''));
        var hidden = t.isVisible === false;
        html += '<div class="d-flex justify-content-between align-items-center" style="font-size:0.85em;padding:2px 0;border-bottom:1px solid #eee;">' +
            '<span style="cursor:pointer;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;' +
            (hidden ? 'opacity:0.5;' : '') + '" onclick="FE.tracks.focusTrack(' + i + ')" title="Показать на карте">' +
            '<b>' + mode + '</b> ' + name + '</span>' +
            '<span style="white-space:nowrap;">' +
            '<button class="btn btn-xs btn-outline-secondary" style="padding:0 4px;font-size:0.75em;" title="Скрыть/показать" onclick="FE.tracks.toggleVisible(' + i + ')">' + (hidden ? '✕' : '👁') + '</button> ' +
            '<button class="btn btn-xs btn-outline-secondary" style="padding:0 4px;font-size:0.75em;" title="Переименовать" onclick="FE.tracks.rename(' + i + ')">✎</button> ' +
            '<button class="btn btn-xs btn-outline-secondary" style="padding:0 4px;font-size:0.75em;" title="Сгладить" onclick="FE.tracks.smooth(' + i + ')">≈</button> ' +
            '<button class="btn btn-xs btn-outline-danger" style="padding:0 4px;font-size:0.75em;" title="Удалить" onclick="FE.tracks.remove(' + i + ')">✕</button>' +
            '</span></div>';
    });
    el.innerHTML = html;
};

FE.tracks.focusTrack = function (index) {
    var t = ((FE.field && FE.field.tracks) || [])[index];
    if (!t || !FE.plane) return;
    var coords = FE.trackEntryLatLngs(t);
    if (coords.length < 2) return;
    try { FE.map.fitBounds(L.latLngBounds(coords).pad(0.3)); } catch (e) {}
};

FE.tracks.toggleVisible = function (index) {
    var t = ((FE.field && FE.field.tracks) || [])[index];
    if (!t) return;
    FE.pushUndo();
    t.isVisible = (t.isVisible === false);
    FE.setDirty(true);
    FE.renderField();
    FE.tracks.updateList();
};

FE.tracks.rename = function (index) {
    var t = ((FE.field && FE.field.tracks) || [])[index];
    if (!t) return;
    var name = window.prompt('Новое имя трека:', t.name || '');
    if (name === null) return;
    FE.pushUndo();
    t.name = name;
    FE.setDirty(true);
    FE.tracks.updateList();
};

FE.tracks.remove = function (index) {
    var tracks = (FE.field && FE.field.tracks) || [];
    if (index < 0 || index >= tracks.length) return;
    var t = tracks[index];
    if (!window.confirm('Удалить трек «' + (t.name || index) + '»?')) return;
    FE.pushUndo();
    tracks.splice(index, 1);
    FE.setDirty(true);
    FE.renderField();
    FE.tracks.updateList();
};

// -------- smooth (moving average on curvePts) --------

FE.tracks.smooth = function (index) {
    var t = ((FE.field && FE.field.tracks) || [])[index];
    if (!t) return;
    var curve = t.curvePts || [];
    if (curve.length < 5) { alert('Точка слишком мало для сглаживания (нужна кривая)'); return; }
    var strength = parseFloat(window.prompt('Сила сглаживания (1-10):', '3'));
    if (!strength || strength < 1) return;
    strength = Math.min(10, strength);
    FE.pushUndo();
    var radius = Math.round(strength);
    var n = curve.length;
    var out = [];
    for (var i = 0; i < n; i++) {
        var se = 0, sn = 0, sh = 0, cnt = 0;
        for (var j = Math.max(0, i - radius); j <= Math.min(n - 1, i + radius); j++) {
            se += curve[j].easting || 0;
            sn += curve[j].northing || 0;
            sh += curve[j].heading || 0;
            cnt++;
        }
        out.push({ easting: se / cnt, northing: sn / cnt, heading: sh / cnt });
    }
    // recompute headings from geometry (keep last heading pattern simple)
    for (var k = 1; k < out.length - 1; k++) {
        var de = out[k + 1].easting - out[k - 1].easting;
        var dn = out[k + 1].northing - out[k - 1].northing;
        var h = Math.atan2(de, dn);
        if (h < 0) h += 2 * Math.PI;
        out[k].heading = h;
    }
    t.curvePts = out;
    // refresh ptA/ptB from curve ends
    if (out.length) {
        t.ptA = { easting: out[0].easting, northing: out[0].northing };
        t.ptB = { easting: out[out.length - 1].easting, northing: out[out.length - 1].northing };
    }
    FE.setDirty(true);
    FE.renderField();
    FE.status('Трек сглажен');
};

// -------- create AB / curve by two clicks --------

FE.tracks.startCreate = function (type) { // 'ab' | 'curve'
    if (!FE.field) { alert('Сначала откройте поле'); return; }
    FE.tracks.cancelCreate();
    FE.tracks.creating = { type: type, ptA: null, points: [] };
    FE.map.getContainer().style.cursor = 'crosshair';
    FE.tracks._setHint(type === 'curve'
        ? 'Кривая: кликните 2 точки на границе поля'
        : 'AB-линия: кликните 2 точки на границе поля (или где угодно)');
    FE.map.on('click', FE.tracks._onCreateClick);
};

FE.tracks._onCreateClick = function (e) {
    var c = FE.tracks.creating;
    if (!c) return;
    var ll = [e.latlng.lat, e.latlng.lng];
    c.points.push(ll);
    var m = L.circleMarker(ll, { radius: 5, color: '#8e44ad', fillColor: '#9b59b6', fillOpacity: 1 }).addTo(FE.map);
    FE.tracks.markers.push(m);
    if (c.points.length === 2) {
        FE.map.off('click', FE.tracks._onCreateClick);
        FE.tracks._buildFromPoints(c.type, c.points[0], c.points[1]);
    }
};

FE.tracks._buildFromPoints = function (type, ptA, ptB) {
    FE.tracks.cancelCreate();
    FE.status('Построение трека...');
    fetch('/api/fields/' + encodeURIComponent(FE.field.__name) + '/abline', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: type === 'curve' ? 'curve' : 'ab', ptA: ptA, ptB: ptB })
    }).then(function (r) {
        return r.json().then(function (body) {
            if (!r.ok) throw new Error(body.error || 'HTTP ' + r.status);
            return body;
        });
    }).then(function (res) {
        if (!res.entry) throw new Error('Сервер не вернул трек');
        FE.pushUndo();
        if (!FE.field.tracks) FE.field.tracks = [];
        FE.field.tracks.push(res.entry);
        FE.setDirty(true);
        FE.renderField();
        FE.tracks.updateList();
        FE.status(type === 'curve'
            ? 'Кривая добавлена (не забудьте сохранить)'
            : 'AB-линия добавлена (не забудьте сохранить)');
    }).catch(function (e) {
        alert('Ошибка: ' + e.message);
        FE.status('');
    });
};

FE.tracks.cancelCreate = function () {
    var c = FE.tracks.creating;
    FE.tracks.creating = null;
    FE.map.off('click', FE.tracks._onCreateClick);
    FE.tracks.markers.forEach(function (m) { try { FE.map.removeLayer(m); } catch (e) {} });
    FE.tracks.markers = [];
    if (c) FE.map.getContainer().style.cursor = '';
    FE.tracks._setHint('');
};

FE.tracks._setHint = function (msg) {
    var el = document.getElementById('tracksHint');
    if (!el) return;
    el.textContent = msg;
    el.style.display = msg ? 'block' : 'none';
};

// -------- wiring --------

FE.tracks.init = function () {
    document.getElementById('btnCreateAB').addEventListener('click', function () {
        FE.tracks.startCreate('ab');
    });
    document.getElementById('btnCreateCurve').addEventListener('click', function () {
        FE.tracks.startCreate('curve');
    });
    FE.hooks.afterOpen.push(function () { FE.tracks.updateList(); });
    FE.hooks.afterUndo.push(function () { FE.tracks.updateList(); });
    FE.hooks.afterClose.push(function () {
        FE.tracks.cancelCreate();
        FE.tracks.updateList();
    });
};
