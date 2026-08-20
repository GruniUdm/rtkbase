var map;
var tractorMarkers = {};
var tractorTracks = {};
var trackHidden = {};
var trackLoadSeq = {};
var trackLastReload = {};
var expandedSessionCache = {};
var expandedSessions = {};
var _lastTractorsData = null;
var tractorPrevPos = {};
var geozoneLayers = {};
var geozoneTrackLayers = {};
var fieldDetailLayers = {};
var activeTrackZone = null;
var fieldPreview = null;
var _fieldPreviewSeq = 0;
var _savedDetailVisibility = {};
var fieldPreviewSectionLoading = false;
var fieldPreviewYieldLoading = false;
var yieldColorMode = 'gradient';
var _fieldFileClickTimer = null;
var drawMode = false;
var drawPoints = [];
var drawMarkers = [];
var drawPolyline = null;
var previewLineType = 'ab';
var previewABActive = false;
var previewABPoints = [];
var previewABGroup = null;
var previewABName = '';
var editingZoneId = null;
var savedOriginalPoints = null;
var currentZoneId = null;

function setBaseLayer(name) {
    if (!map || !window._whLayers || !window._whLayers[name]) return;
    if (window._whActive === name) return;
    map.removeLayer(window._whLayers[window._whActive]);
    window._whLayers[name].addTo(map);
    window._whActive = name;
    var radios = document.querySelectorAll('.leaflet-control-layers-base input[type="radio"]');
    for (var j = 0; j < radios.length; j++) radios[j].checked = false;
    for (var i = 0; i < radios.length; i++) {
        var sp = radios[i].parentNode.querySelector('span');
        if (sp && sp.textContent.indexOf(name) !== -1) { radios[i].checked = true; break; }
    }
    if (name === 'Sentinel-2') showAllNdviOverlays(); else hideAllNdviOverlays();
}

function toggleNdviPanel(hdr) {
    var body = document.getElementById('ndviBody');
    var hidden = !body || body.style.display === 'none';
    if (hidden) {
        if (body) body.style.display = '';
        setBaseLayer('Sentinel-2');
    } else {
        if (body) body.style.display = 'none';
        setBaseLayer('Map');
    }
    if (hdr) {
        var ic = hdr.querySelector('.collapse-icon');
        if (ic) ic.classList.toggle('collapsed');
    }
}

$(document).ready(function () {
    map = L.map('map').setView({
        lon: baseCoordinates.lon,
        lat: baseCoordinates.lat
    }, 15);

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
    var layerControl = L.control.layers({'Map': osm, 'Satellite': sat, 'Sentinel-2': s2}, null, {position: 'bottomleft'}).addTo(map);
    window._whLayers = {'Map': osm, 'Satellite': sat, 'Sentinel-2': s2};
    window._whActive = 'Map';

    map.on("baselayerchange", function(e) {
        window._whActive = e.name;
        if (e.name === "Sentinel-2") {
            showAllNdviOverlays();
        } else {
            hideAllNdviOverlays();
        }
    });

    var baseIcon = L.icon({
        iconUrl: '/static/images/iconmonstr-crosshair-6-64.png',
        iconSize: [24, 24],
        iconAnchor: [12, 12]
    });
    L.marker(baseCoordinates, {icon: baseIcon}).addTo(map)
        .bindTooltip('Base Station');

    // Draw button
    $('#drawBtn').on('click', toggleDrawMode);
    $('#saveGeozoneBtn').on('click', function() {
        if (drawMode && drawPoints.length >= 3) finishDraw();
    });
    $('#savePointsBtn').on('click', saveEditedPoints);
    $('#cancelPointsBtn').on('click', cancelEditPoints);

    // Import KML button
    $('#importKmlBtn').on('click', function() { $('#kmlFileInput').click(); });
    $('#kmlFileInput').on('change', function(e) {
        var file = e.target.files[0];
        if (!file) return;
        var reader = new FileReader();
        reader.onload = function(ev) { importKml(ev.target.result); };
        reader.readAsText(file);
        this.value = '';
    });

    // Load geozones
    loadGeozones();
    map.on('dblclick', onMapDblClick);

    // Load tracks from URL params and localStorage (run immediately and on socket connect)
    function loadTracksFromParams() {
        var params = new URLSearchParams(window.location.search);
        var trackIp = params.get('track');
        if (trackIp) { loadAndShowTrack(trackIp); }
        var tracksParam = params.get('tracks');
        if (tracksParam) {
            tracksParam.split(',').forEach(function(ip) { if (ip) loadAndShowTrack(ip); });
        }
    }
    function loadTracksFromStorage() {
        try {
            var stored = JSON.parse(localStorage.getItem('tractor_tracks_show') || '[]');
            stored.forEach(function(ip) { loadAndShowTrack(ip); });
        } catch(e) {}
    }
    loadTracksFromParams();
    setTimeout(loadTracksFromStorage, 500);

    var socket = io.connect('/test');
    socket.on('tractors update', function(data) {
        updateTractors(JSON.parse(data));
    });
    socket.on('connect', function() {
        console.log('Connected to RTKBase');
        loadTracksFromParams();
        loadTracksFromStorage();
    });

    // Fetch known tractors on page load
    fetchKnownTractors();
});

// -------- Geozone Drawing --------

function toggleDrawMode() {
    if (editingZoneId) { cancelEditPoints(); }
    drawMode = !drawMode;
    var btn = $('#drawBtn');
    var info = $('#drawInfo');
    var saveBtn = $('#saveGeozoneBtn');
    if (drawMode) {
        if (previewABActive) exitPreviewAB();
        btn.text('Cancel').addClass('draw-active');
        info.show();
        map.getContainer().style.cursor = 'crosshair';
        map.on('click', onDrawClick);
        map.doubleClickZoom.disable();
    } else {
        cancelDraw();
        btn.text('Draw Geozone').removeClass('draw-active');
        info.hide();
        saveBtn.hide();
        map.getContainer().style.cursor = '';
        map.off('click', onDrawClick);
        map.doubleClickZoom.enable();
    }
}

function cancelDraw() {
    drawPoints = [];
    if (drawPolyline) { map.removeLayer(drawPolyline); drawPolyline = null; }
    drawMarkers.forEach(function(m) { map.removeLayer(m); });
    drawMarkers = [];
    $('#saveGeozoneBtn').hide();
}

function redrawDrawPolyline() {
    if (drawPolyline) { map.removeLayer(drawPolyline); drawPolyline = null; }
    if (drawPoints.length === 0) return;
    var pts = drawPoints.concat([drawPoints[0]]);
    drawPolyline = L.polyline(pts, {
        color: '#e74c3c', weight: 2, dashArray: '5,5'
    }).addTo(map);
}

function onDrawClick(e) {
    var latlng = e.latlng;
    var idx = drawPoints.length;
    drawPoints.push([latlng.lat, latlng.lng]);

    if (editingZoneId) {
        createEditMarker([latlng.lat, latlng.lng], idx);
        redrawDrawPolyline();
        return;
    }

    var icon = L.divIcon({
        className: '',
        html: '<div style="width:12px;height:12px;border-radius:50%;border:2px solid #e74c3c;background:#fff;margin:-6px 0 0 -6px;cursor:pointer;"></div>',
        iconSize: [12, 12],
        iconAnchor: [6, 6]
    });
    var marker = L.marker(latlng, {icon: icon, draggable: true}).addTo(map);

    marker.on('drag', function() {
        var pos = marker.getLatLng();
        drawPoints[idx] = [pos.lat, pos.lng];
        redrawDrawPolyline();
    });

    marker.on('click', function() {
        if (drawPoints.length === 0) return;
        drawPoints.pop();
        var last = drawMarkers.pop();
        if (last) map.removeLayer(last);
        redrawDrawPolyline();
    });

    drawMarkers.push(marker);
    redrawDrawPolyline();

    if (drawPoints.length >= 3) { $('#saveGeozoneBtn').show(); }
}

function onMapDblClick(e) {
    if (!drawMode || drawPoints.length < 3) return;
    finishDraw();
}

function finishDraw() {
    if (drawPoints.length < 3) {
        cancelDraw();
        toggleDrawMode();
        return;
    }
    var name = prompt('Enter geozone name:', 'Zone ' + (Object.keys(geozoneLayers).length + 1));
    if (!name) { cancelDraw(); toggleDrawMode(); return; }

    var payload = JSON.stringify({name: name, points: drawPoints});
    fetch('/api/geozones', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: payload
    })
    .then(function(r) { return r.json(); })
    .then(function(zone) {
        cancelDraw();
        toggleDrawMode();
        closeFieldPreview();
        addGeozoneToMap(zone);
        renderGeozoneList();
    });
}

function loadGeozones() {
    fetch('/api/geozones')
        .then(function(r) { return r.json(); })
        .then(function(zones) {
            zones.forEach(addGeozoneToMap);
            renderGeozoneList();
            zones.forEach(function(z) { loadGeozoneDetails(z.id); });
        });
}

function addGeozoneToMap(zone) {
    var closedPoints = zone.points.concat([zone.points[0]]);
    var boundary = L.polyline(closedPoints, {
        color: zone.color,
        weight: 3,
        opacity: 0.8
    }).addTo(map);

    var center = boundary.getBounds().getCenter();
    var label = L.marker(center, {
        icon: L.divIcon({
            html: '<div style="background:' + zone.color + ';color:#fff;padding:2px 8px;border-radius:3px;font-size:0.85em;white-space:nowrap;text-shadow:0 0 2px #000,0 0 2px #000;">' + escapeHtml(zone.name) + '</div>',
            className: '',
            iconSize: [0, 0],
            iconAnchor: [0, 0]
        }),
        interactive: false
    }).addTo(map);

    geozoneLayers[zone.id] = {polygon: boundary, label: label, data: zone, _hide: false};
}

function toggleGeozone(id) {
    closeFieldPreview();
    var layer = geozoneLayers[id];
    if (!layer) return;
    layer._hide = !layer._hide;
    if (layer._hide) {
        map.removeLayer(layer.polygon);
        map.removeLayer(layer.label);
        clearTrackLayersForZone(id);
        clearDetailLayers(id);
        if (activeTrackZone === id) activeTrackZone = null;
        renderGeozoneList();
    } else {
        map.addLayer(layer.polygon);
        map.addLayer(layer.label);
        // re-show detail layers if any
        var details = fieldDetailLayers[id];
        if (details) {
            for (var k in details) {
                map.addLayer(details[k]);
            }
        }
    }
}

function renderGeozoneList() {
    var html = '';
    var hasZones = false;
    var detailLabels = {'tracks': 'Треки', 'headland': 'Гон', 'sections': 'Секции', 'abLine': 'AB линии'};
    for (var id in geozoneLayers) {
        hasZones = true;
        var z = geozoneLayers[id].data;
        var checked = geozoneLayers[id]._hide ? '' : ' checked';
        var isActive = activeTrackZone === id ? ' active-zone' : '';
        html += '<div class="geozone-item' + isActive + '" onclick="focusGeozone(\'' + id + '\')" ondblclick="event.stopPropagation();editGeozone(\'' + id + '\')">' +
            '<input type="checkbox"' + checked + ' onclick="event.stopPropagation();" onchange="toggleGeozone(\'' + id + '\');" style="vertical-align:middle;margin-right:4px;">' +
            '<span class="geozone-color-dot" style="background:' + z.color + '"></span>' +
            escapeHtml(z.name) +
            '<span class="geozone-del" onclick="event.stopPropagation();deleteGeozone(\'' + id + '\');return false;">&times;</span>' +
            '</div>';
        var details = fieldDetailLayers[id];
        if (details) {
            html += '<div style="padding-left:24px;font-size:0.8em;">';
            for (var dt in details) {
                var label = detailLabels[dt] || dt;
                var hasLayer = map.hasLayer(details[dt]);
                var cb = hasLayer ? ' checked' : '';
                html += '<label style="display:inline-block;margin-right:8px;cursor:pointer;font-weight:400;">' +
                    '<input type="checkbox"' + cb + ' onchange="toggleDetailLayer(\'' + id + '\',\'' + dt + '\')" style="vertical-align:middle;margin-right:2px;"> ' +
                    label +
                    '</label>';
            }
            html += '</div>';
        }
    }
    $('#geozoneList').html(hasZones ? html : '<div class="text-muted" style="padding:8px;">No geozones</div>');
}

function clearTrackLayersForZone(zoneId) {
    var layers = geozoneTrackLayers[zoneId];
    if (layers) {
        for (var k in layers) {
            if (layers[k]) { try { map.removeLayer(layers[k]); } catch(e) {} }
        }
        delete geozoneTrackLayers[zoneId];
    }
}

function loadGeozoneTracks(zoneId) {
    if (activeTrackZone === zoneId) {
        activeTrackZone = null;
        clearTrackLayersForZone(zoneId);
        renderGeozoneList();
        return;
    }
    if (activeTrackZone) {
        clearTrackLayersForZone(activeTrackZone);
    }
    activeTrackZone = zoneId;
    renderGeozoneList();
    fetch('/api/geozones/' + zoneId + '/tracks')
        .then(function(r) { return r.json(); })
        .then(function(tracks) {
            if (activeTrackZone !== zoneId) return;
            var layers = {};
            tracks.forEach(function(t) {
                var color = t.mode === 4 ? '#e67e22' : '#3498db';
                var latlngs = [];
                if (t.mode === 4 && t.curve_pts && t.curve_pts.length > 1) {
                    latlngs = t.curve_pts.map(function(p) { return [p[0], p[1]]; });
                } else {
                    latlngs = [t.point_a, t.point_b];
                }
                var displayLine = extendLineToBounds(latlngs, map.getBounds());
                var polyline = L.polyline(displayLine, {
                    color: color, weight: 3, opacity: 0.8,
                    dashArray: t.mode === 4 ? '8, 4' : null
                }).addTo(map);
                polyline.bindPopup('<b>' + escapeHtml(t.name) + '</b><br>Mode: ' + (t.mode === 4 ? 'Curve' : 'AB') + '<br>Heading: ' + t.heading + '&deg;');
                layers[t.id] = polyline;
                if (t.point_a && t.point_b) {
                    var aMrk = L.circleMarker(t.point_a, {radius:5,color:'#e74c3c',fillColor:'#e74c3c',fillOpacity:1,weight:2}).addTo(map);
                    aMrk.bindTooltip('A:' + escapeHtml(t.name), {permanent:false,className:'ab-point-label'});
                    layers[t.id + '_A'] = aMrk;
                    var bMrk = L.circleMarker(t.point_b, {radius:5,color:'#e74c3c',fillColor:'#e74c3c',fillOpacity:1,weight:2}).addTo(map);
                    bMrk.bindTooltip('B:' + escapeHtml(t.name), {permanent:false,className:'ab-point-label'});
                    layers[t.id + '_B'] = bMrk;
                }
                if (t.mode === 2 && t.point_a && t.point_b) {
                    var passes = generateParallelPasses(t.point_a, t.point_b, t.width || 10, 3);
                    passes.forEach(function(pass, pi) {
                        var passLine = extendLineToBounds(pass, map.getBounds());
                        var passPoly = L.polyline(passLine, {
                            color: pi % 2 === 0 ? '#2ecc71' : '#f39c12', weight: 1.5, opacity: 0.5, dashArray: '4, 6'
                        }).addTo(map);
                        layers[t.id + '_pass_' + pi] = passPoly;
                    });
                }
            });
            geozoneTrackLayers[zoneId] = layers;
        })
        .catch(function(e) { console.error('Load tracks error:', e); });
}

function loadGeozoneDetails(zoneId) {
    fetch('/api/geozones/' + zoneId + '/details')
        .then(function(r) { return r.json(); })
        .then(function(details) {
            clearDetailLayers(zoneId);
            var layers = {};
            details.forEach(function(d) {
                var geo = d.geometry_geojson;
                if (!geo) return;
                var style = d.style || {};
                var opts = {
                    color: style.color || '#3498db',
                    weight: style.weight || 2,
                    opacity: style.opacity || 0.8,
                    fillOpacity: style.fillOpacity || 0,
                    dashArray: style.dashArray || null
                };
                if (d.type === 'sections') {
                    opts.fillOpacity = style.fillOpacity || 0.3;
                    opts.fillColor = style.color || '#27ae60';
                }
                var layer;
                if (geo.type === 'MultiLineString' || geo.type === 'LineString' || geo.type === 'MultiPolygon') {
                    var gjLayer = L.geoJSON(geo, {
                        style: function() { return opts; }
                    }).addTo(map);
                    gjLayer._detailType = d.type;
                    layer = gjLayer;
                }
                if (layer) {
                    layers[d.type] = layer;
                }
            });
            fieldDetailLayers[zoneId] = layers;
            renderGeozoneList();
        })
        .catch(function(e) { console.error('Load details error:', e); });
}

function clearDetailLayers(zoneId) {
    var layers = fieldDetailLayers[zoneId];
    if (layers) {
        for (var k in layers) {
            if (layers[k]) { try { map.removeLayer(layers[k]); } catch(e) {} }
        }
        delete fieldDetailLayers[zoneId];
    }
}

function toggleDetailLayer(zoneId, type) {
    var layers = fieldDetailLayers[zoneId];
    if (!layers) {
        loadGeozoneDetails(zoneId);
        return;
    }
    if (!layers[type]) return;
    if (map.hasLayer(layers[type])) {
        map.removeLayer(layers[type]);
    } else {
        map.addLayer(layers[type]);
    }
}

function focusGeozone(id) {
    closeFieldPreview();
    var layer = geozoneLayers[id];
    if (!layer) return;
    map.fitBounds(layer.polygon.getBounds().pad(0.2));
    var pts = layer.data.points;
    var areaHa = calculateArea(pts);
    var perimM = calculatePerimeter(pts);
    var html = '<b>' + escapeHtml(layer.data.name) + '</b><br>' +
        'Area: ' + areaHa.toFixed(2) + ' ha<br>' +
        'Crop: ' + escapeHtml(layer.data.crop || '-');
    layer.polygon.unbindPopup();
    layer.polygon.bindPopup(html).openPopup();
    loadGeozoneTracks(id);
}

function deleteGeozone(id) {
    if (!confirm('Delete this geozone?')) return;
    fetch('/api/geozones/' + id, {method: 'DELETE'})
        .then(function() {
            if (geozoneLayers[id]) {
                map.removeLayer(geozoneLayers[id].polygon);
                map.removeLayer(geozoneLayers[id].label);
                delete geozoneLayers[id];
            }
            clearTrackLayersForZone(id);
            clearDetailLayers(id);
            if (activeTrackZone === id) activeTrackZone = null;
            renderGeozoneList();
        });
}

function editGeozone(id) {
    closeFieldPreview();
    var layer = geozoneLayers[id];
    if (!layer) return;
    var z = layer.data;
    currentZoneId = id;
    $('#editZoneName').val(z.name || '');
    $('#editZoneCrop').val(z.crop || '');
    $('#editZonePlanted').val(z.planted_date || '');
    $('#editZoneChemDate').val(z.last_chemical || '');
    $('#editZoneChemName').val(z.chemical_name || '');
    $('#gpSaveMsg').text('');
    openGeozonePanel(id);
    loadNdviStatus(id);
    loadYieldSummary(id);
    loadFieldOps(id);
}

function openGeozonePanel(id) {
    var layer = geozoneLayers[id];
    if (!layer) return;
    var z = layer.data;
    $('#gpColorDot').css('background', z.color);
    $('#gpName').text(z.name || '');
    var areaHa = calculateArea(z.points);
    var perimM = calculatePerimeter(z.points);
    $('#gpArea').text(areaHa.toFixed(2));
    $('#gpPerimeter').text(Math.round(perimM));
    var crop = z.crop || '';
    if (crop) {
        $('#gpCropBadge').text(crop).css('background', z.color).css('color', '#fff').show();
    } else {
        $('#gpCropBadge').hide();
    }
    var m = document.getElementById('map');
    var w = document.getElementById('weatherHistoryPanel');
    var p = document.getElementById('geozonePanel');
    if (m) m.style.display = 'none';
    if (w) w.style.display = 'none';
    if (p) p.style.display = 'block';
    if (p) p.scrollTop = 0;
    setTimeout(function() { drawMiniMap(z); }, 80);
}

function closeGeozonePanel() {
    var lastId = currentZoneId;
    currentZoneId = null;
    _pendingAlertId = null;
    _pendingAlertIp = null;
    if (lastId) hideNdviOverlay(lastId);
    var p = document.getElementById('geozonePanel');
    if (p) p.style.display = 'none';
    var w = document.getElementById('weatherHistoryPanel');
    var showMap = !(w && w.style.display !== 'none');
    var m = document.getElementById('map');
    if (m && showMap) m.style.display = 'block';
    if (map && showMap) setTimeout(function() { map.invalidateSize(); }, 60);
}

$(document).on('click', '#leftPanel .card-header, #leftPanel button, #leftPanel .btn', function() {
    if ($(this).attr('data-keep-panel') === '1') return;
    var p = document.getElementById('geozonePanel');
    if (p && p.style.display !== 'none') closeGeozonePanel();
});

function gpShowOnMap() {
    var id = currentZoneId;
    closeGeozonePanel();
    if (id) focusGeozone(id);
}

function gpDelete() {
    var id = currentZoneId;
    if (!id) return;
    closeGeozonePanel();
    deleteGeozone(id);
}

// -------- Мини-карта поля в панели --------

var _gpMiniMap = null;
var _gpMiniPolygon = null;

function ensureMiniMap() {
    if (_gpMiniMap) return;
    var el = document.getElementById('geozoneMiniMap');
    if (!el) return;
    _gpMiniMap = L.map(el, {zoomControl: false, attributionControl: false, scrollWheelZoom: false, doubleClickZoom: false, dragging: false});
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {attribution: ''}).addTo(_gpMiniMap);
}

function drawMiniMap(zone) {
    ensureMiniMap();
    if (!_gpMiniMap || !zone) return;
    _gpMiniMap.invalidateSize();
    if (_gpMiniPolygon) { _gpMiniMap.removeLayer(_gpMiniPolygon); _gpMiniPolygon = null; }
    var pts = zone.points;
    if (!pts || !pts.length) return;
    _gpMiniPolygon = L.polygon(pts, {color: zone.color || '#3388ff', weight: 2, fillColor: zone.color || '#3388ff', fillOpacity: 0.15}).addTo(_gpMiniMap);
    _gpMiniMap.fitBounds(L.latLngBounds(pts).pad(0.1));
}

// -------- Детекция движения тракторов (список для оператора) --------

function toggleAlertsPanel(hdr) {
    var body = document.getElementById('alertsBody');
    var hidden = !body || body.style.display === 'none';
    if (body) body.style.display = hidden ? '' : 'none';
    if (hdr) {
        var ic = hdr.querySelector('.collapse-icon');
        if (ic) ic.classList.toggle('collapsed');
    }
    if (hidden) scanAlerts();
}

function scanAlerts() {
    var btn = document.getElementById('scanAlertsBtn');
    if (btn) { btn.disabled = true; btn.textContent = 'Проверка...'; }
    fetch('/api/alerts/scan')
        .then(function(r) { return r.json(); })
        .then(function(data) { renderAlerts(data); })
        .catch(function() { renderAlerts(null); })
        .then(function() {
            if (btn) { btn.disabled = false; btn.textContent = 'Проверить движение'; }
        });
}

function _fmtTime(t) {
    if (!t) return '—';
    var d = new Date(t * 1000);
    return pad2(d.getHours()) + ':' + pad2(d.getMinutes());
}

function renderAlerts(data) {
    var badge = document.getElementById('alertsBadge');
    var list = document.getElementById('alertsList');
    var pending = (data && data.pending) || [];
    var processed = (data && data.processed) || [];
    if (badge) {
        if (pending.length) {
            badge.textContent = pending.length;
            badge.style.display = 'inline-block';
        } else {
            badge.style.display = 'none';
        }
    }
    if (!list) return;
    var html = '';
    if (!pending.length) {
        html = '<span class="text-muted">Список пуст</span>';
    }
    pending.forEach(function(a) {
        html += '<div class="alert-item" style="border:1px solid #f5c6cb;background:#f8d7da;border-radius:4px;padding:4px 6px;margin-bottom:4px;">';
        html += '<div><b>' + escapeHtml(a.zone_name || a.zone_id) + '</b> · ' + escapeHtml(a.tractor_ip) + '</div>';
        html += '<div style="color:#666;font-size:0.8em;">' + escapeHtml(a.alert_date) + ' ' + _fmtTime(a.first_seen) + '–' + _fmtTime(a.last_seen) + ' · ' + a.points + ' точек' + (a.distance_km ? ' · ' + a.distance_km + ' км' : '') + '</div>';
        html += '<div style="margin-top:3px;">';
        html += '<button class="btn btn-xs btn-outline-info" onclick="showAlertOnMap(\'' + a.zone_id + '\',\'' + a.tractor_ip + '\',' + a.first_seen + ',' + a.last_seen + ')" style="font-size:0.75em;padding:0 6px;">Показать</button> ';
        html += '<button class="btn btn-xs btn-success" data-keep-panel="1" onclick="openAlertWork(' + a.id + ',\'' + a.zone_id + '\',' + a.first_seen + ',' + a.last_seen + ',\'' + a.tractor_ip + '\')" style="font-size:0.75em;padding:0 6px;">Обработать</button>';
        html += '</div></div>';
    });
    list.innerHTML = html;
}

function processAlert(alertId) {
    fetch('/api/alerts/' + alertId + '/process', {method: 'POST'})
        .then(function(r) { return r.json(); })
        .then(function(res) {
            if (res.ok) scanAlerts();
        })
        .catch(function(e) { alert('Не удалось обработать: ' + e.message); });
}

var _pendingAlertId = null;
var _pendingAlertIp = null;

function openAlertWork(alertId, zoneId, firstSeen, lastSeen, ip) {
    _pendingAlertId = alertId;
    _pendingAlertIp = ip || null;
    fetch('/api/alerts/' + alertId + '/process', {method: 'POST'})
        .then(function(r) { return r.json(); })
        .then(function(res) { if (res.ok) scanAlerts(); })
        .catch(function() {});
    if (!zoneId || !geozoneLayers[zoneId]) {
        alert('Поле не найдено на карте');
        return;
    }
    editGeozone(zoneId);
    setTimeout(function() {
        var d = new Date((lastSeen || firstSeen || Date.now() / 1000) * 1000);
        var dateEl = document.getElementById('opDate');
        if (dateEl) dateEl.value = d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate());
        if (ip) {
            var machEl = document.getElementById('opMachinery');
            if (machEl) machEl.value = ip;
        }
        var f = document.getElementById('addOpForm');
        if (f && f.style.display !== 'block') f.style.display = 'block';
        var ops = document.getElementById('gpOpsBody');
        if (ops) ops.scrollIntoView({behavior: 'smooth', block: 'start'});
    }, 120);
}

function showAlertOnMap(zoneId, ip, fromTs, toTs) {
    var m = document.getElementById('map');
    var w = document.getElementById('weatherHistoryPanel');
    var p = document.getElementById('geozonePanel');
    if (m) m.style.display = 'block';
    if (w) w.style.display = 'none';
    if (p) p.style.display = 'none';
    if (currentZoneId) hideNdviOverlay(currentZoneId);
    currentZoneId = null;
    if (map) setTimeout(function() { map.invalidateSize(); }, 60);
    if (zoneId && geozoneLayers[zoneId]) focusGeozone(zoneId);
    if (ip) loadAlertSessionTrack(ip, fromTs, toTs);
}

function loadAlertSessionTrack(ip, fromTs, toTs) {
    var url = '/api/tractor_track/' + encodeURIComponent(ip);
    if (fromTs || toTs) {
        url += '?' + (fromTs ? 'from=' + fromTs : '') + (fromTs && toTs ? '&' : '') + (toTs ? 'to=' + toTs : '');
    }
    fetch(url)
        .then(function(r) {
            if (!r.ok) throw new Error('HTTP ' + r.status);
            return r.json();
        })
        .then(function(points) {
            if (!points || points.length < 2) {
                alert('Нет трека за эту сессию');
                return;
            }
            if (tractorTracks[ip]) {
                map.removeLayer(tractorTracks[ip]);
                delete tractorTracks[ip];
            }
            var latlngs = points.map(function(p) { return [p.lat, p.lon]; });
            var polyline = L.polyline(latlngs, {
                color: '#3498db',
                weight: 3,
                opacity: 0.8
            }).addTo(map);
            polyline.bindTooltip(ip + ' · ' + _fmtTime(fromTs) + '–' + _fmtTime(toTs), {sticky: true});
            tractorTracks[ip] = polyline;
            polyline._hide = false;
            map.fitBounds(polyline.getBounds().pad(0.1));
        })
        .catch(function(e) { alert('Не удалось загрузить трек: ' + e.message); });
}

// -------- Урожайность (сводка) --------

function loadYieldSummary(zoneId) {
    var el = document.getElementById('yieldSummary');
    if (!el) return;
    el.textContent = 'Загрузка...';
    fetch('/api/geozones/' + zoneId + '/yield')
        .then(function(r) { return r.json(); })
        .then(function(s) {
            if (!s || s.error) throw new Error('no data');
            if (!s.count) {
                el.textContent = 'Нет данных об урожайности';
                return;
            }
            el.innerHTML = 'Записей: <b>' + s.count + '</b><br>' +
                'Средняя: <b>' + s.avg.toFixed(1).replace('.', ',') + '</b> ц/га' +
                ' (мин ' + s.min.toFixed(1).replace('.', ',') + ', макс ' + s.max.toFixed(1).replace('.', ',') + ')<br>' +
                'Площадь съёмки: <b>' + s.total_area_ha.toFixed(1).replace('.', ',') + '</b> га';
        })
        .catch(function(e) {
            el.textContent = 'Нет данных об урожайности';
        });
}

// -------- Работы на поле (журнал операций) --------

function loadFieldOps(zoneId) {
    var el = document.getElementById('fieldOpsList');
    if (!el) return;
    el.innerHTML = '<span class="text-muted">Загрузка...</span>';
    fetch('/api/geozones/' + zoneId + '/ops')
        .then(function(r) { return r.json(); })
        .then(function(ops) {
            if (!ops || !ops.length) {
                el.innerHTML = '<span class="text-muted">Работ не зафиксировано</span>';
                return;
            }
            var html = '';
            ops.forEach(function(o) {
                html += '<div class="op-item" style="padding:4px 0;border-bottom:1px solid #eee;font-size:0.88em;">';
                html += '<div style="display:flex;justify-content:space-between;">';
                html += '<span><b>' + escapeHtml(o.op_type || '') + '</b> <span style="color:#666;">' + escapeHtml(o.op_date || '') + '</span></span>';
                html += '<span style="color:#dc3545;cursor:pointer;font-weight:bold;padding-left:6px;" title="Удалить" onclick="deleteFieldOp(' + o.id + ')">&times;</span>';
                html += '</div>';
                var extra = [];
                if (o.crop) extra.push('культура: ' + escapeHtml(o.crop));
                if (o.area_ha) extra.push('площадь: ' + o.area_ha + ' га');
                if (o.machinery) extra.push('агрегат: ' + escapeHtml(o.machinery));
                if (o.operator) extra.push('механизатор: ' + escapeHtml(o.operator));
                if (o.material) extra.push('материал: ' + escapeHtml(o.material) + (o.dose ? ' (' + escapeHtml(o.dose) + ')' : ''));
                if (o.fuel_l) extra.push('топливо: ' + o.fuel_l + ' л');
                if (o.cost) extra.push('затраты: ' + o.cost + ' руб');
                if (o.notes) extra.push('примечание: ' + escapeHtml(o.notes));
                if (extra.length) {
                    html += '<div style="color:#666;font-size:0.85em;">' + extra.join(' &middot; ') + '</div>';
                }
                html += '</div>';
            });
            el.innerHTML = html;
        })
        .catch(function() {
            el.innerHTML = '<span class="text-muted">Ошибка загрузки работ</span>';
        });
}

function toggleAddOpForm() {
    var f = document.getElementById('addOpForm');
    if (!f) return;
    var hidden = f.style.display === 'none' || !f.style.display;
    f.style.display = hidden ? 'block' : 'none';
    if (hidden && !document.getElementById('opDate').value) {
        var now = new Date();
        document.getElementById('opDate').value = now.getFullYear() + '-' + pad2(now.getMonth() + 1) + '-' + pad2(now.getDate());
    }
}

function saveFieldOp() {
    var zoneId = currentZoneId;
    if (!zoneId) return;
    var opType = document.getElementById('opType').value;
    if (!opType) { alert('Выберите тип работы'); return; }
    var body = {
        op_date: document.getElementById('opDate').value,
        op_type: opType,
        crop: document.getElementById('editZoneCrop').value,
        machinery: document.getElementById('opMachinery').value,
        operator: document.getElementById('opOperator').value,
        area_ha: parseFloat(document.getElementById('opArea').value) || null,
        material: document.getElementById('opMaterial').value,
        dose: document.getElementById('opDose').value,
        fuel_l: parseFloat(document.getElementById('opFuel').value) || null,
        cost: parseFloat(document.getElementById('opCost').value) || null,
        notes: document.getElementById('opNotes').value
    };
    fetch('/api/geozones/' + zoneId + '/ops', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body)
    })
    .then(function(r) { return r.json(); })
    .then(function(res) {
        if (res.error) { alert('Ошибка: ' + res.error); return; }
        ['opMachinery', 'opOperator', 'opArea', 'opMaterial', 'opDose', 'opFuel', 'opCost', 'opNotes'].forEach(function(id) {
            var el = document.getElementById(id);
            if (el) el.value = '';
        });
        document.getElementById('opType').value = '';
        toggleAddOpForm();
        loadFieldOps(zoneId);
        if (_pendingAlertId) {
            var pid = _pendingAlertId;
            _pendingAlertId = null;
            _pendingAlertIp = null;
            fetch('/api/alerts/' + pid + '/process', {method: 'POST'})
                .then(function() { scanAlerts(); })
                .catch(function() {});
        }
    })
    .catch(function(e) { alert('Не удалось сохранить: ' + e.message); });
}

function deleteFieldOp(opId) {
    var zoneId = currentZoneId;
    if (!zoneId) return;
    if (!confirm('Удалить запись о работе?')) return;
    fetch('/api/geozones/' + zoneId + '/ops/' + opId, {method: 'DELETE'})
        .then(function() { loadFieldOps(zoneId); })
        .catch(function(e) { alert('Не удалось удалить: ' + e.message); });
}

function startEditPoints() {
    var id = currentZoneId;
    if (!id || !geozoneLayers[id]) return;
    editingZoneId = id;
    var layer = geozoneLayers[id];
    savedOriginalPoints = JSON.parse(JSON.stringify(layer.data.points));

    // Hide existing polygon/label
    map.removeLayer(layer.polygon);
    map.removeLayer(layer.label);

    // Initialize draw points from existing points
    drawPoints = savedOriginalPoints.map(function(p) { return [p[0], p[1]]; });

    // Create markers for each point
    drawPoints.forEach(function(latlng, idx) { createEditMarker(latlng, idx); });

    // Draw polyline
    redrawDrawPolyline();

    // Enable map click to add points
    map.on('click', onDrawClick);
    map.doubleClickZoom.disable();
    map.getContainer().style.cursor = 'crosshair';

    // Hide panel, show map for drawing
    var p = document.getElementById('geozonePanel');
    if (p) p.style.display = 'none';
    var m = document.getElementById('map');
    if (m) m.style.display = 'block';
    if (map) setTimeout(function() { map.invalidateSize(); }, 60);
    if (currentZoneId) hideNdviOverlay(currentZoneId);
    $('#savePointsBtn, #cancelPointsBtn').show();
    $('#drawInfo').text('Click on map to add points. Click a marker to remove last point. Drag to move.').show();
}

function createEditMarker(latlng, idx) {
    var icon = L.divIcon({
        className: '',
        html: '<div style="width:12px;height:12px;border-radius:50%;border:2px solid #e67e22;background:#fff;margin:-6px 0 0 -6px;cursor:pointer;"></div>',
        iconSize: [12, 12],
        iconAnchor: [6, 6]
    });
    var marker = L.marker(latlng, {icon: icon, draggable: true}).addTo(map);
    marker._editIdx = idx;
    marker.on('drag', function() {
        var pos = marker.getLatLng();
        drawPoints[marker._editIdx] = [pos.lat, pos.lng];
        redrawDrawPolyline();
    });
    marker.on('click', function(e) {
        e.originalEvent.stopPropagation();
        var i = marker._editIdx;
        if (drawPoints.length <= 3) return;
        map.removeLayer(marker);
        drawPoints.splice(i, 1);
        drawMarkers.splice(drawMarkers.indexOf(marker), 1);
        // Re-index remaining markers
        drawMarkers.forEach(function(m, j) { m._editIdx = j; });
        redrawDrawPolyline();
    });
    drawMarkers.push(marker);
}

function saveEditedPoints() {
    if (!editingZoneId || drawPoints.length < 3) return;
    fetch('/api/geozones/' + editingZoneId, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({points: drawPoints})
    })
    .then(function(r) { return r.json(); })
    .then(function(zone) {
        cancelEditPoints();
        // Reload the zone display
        if (geozoneLayers[editingZoneId]) {
            var old = geozoneLayers[editingZoneId];
            map.removeLayer(old.polygon);
            map.removeLayer(old.label);
            delete geozoneLayers[editingZoneId];
        }
        addGeozoneToMap(zone);
        renderGeozoneList();
        editingZoneId = null;
    });
}

function cancelEditPoints() {
    if (editingZoneId && savedOriginalPoints && geozoneLayers[editingZoneId]) {
        var layer = geozoneLayers[editingZoneId];
        // Restore original polygon/label
        if (layer.polygon) map.addLayer(layer.polygon);
        if (layer.label) map.addLayer(layer.label);
    }
    drawPoints = [];
    if (drawPolyline) { map.removeLayer(drawPolyline); drawPolyline = null; }
    drawMarkers.forEach(function(m) { map.removeLayer(m); });
    drawMarkers = [];
    map.off('click', onDrawClick);
    map.doubleClickZoom.enable();
    map.getContainer().style.cursor = '';
    $('#savePointsBtn, #cancelPointsBtn').hide();
    $('#drawInfo').hide();
    editingZoneId = null;
    savedOriginalPoints = null;
}

function saveEditZone() {
    var id = currentZoneId;
    if (!id) return;
    var data = {
        name: $('#editZoneName').val(),
        crop: $('#editZoneCrop').val(),
        planted_date: $('#editZonePlanted').val(),
        last_chemical: $('#editZoneChemDate').val(),
        chemical_name: $('#editZoneChemName').val()
    };
    fetch('/api/geozones/' + id, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(data)
    })
    .then(function(r) { return r.json(); })
    .then(function(zone) {
        geozoneLayers[id].data = zone;
        renderGeozoneList();
        // update label on map
        var z = geozoneLayers[id];
        map.removeLayer(z.label);
        var center = z.polygon.getBounds().getCenter();
        z.label = L.marker(center, {
            icon: L.divIcon({
                html: '<div style="background:' + zone.color + ';color:#fff;padding:2px 8px;border-radius:3px;font-size:0.85em;white-space:nowrap;text-shadow:0 0 2px #000,0 0 2px #000;">' + escapeHtml(zone.name) + '</div>',
                className: '',
                iconSize: [0, 0],
                iconAnchor: [0, 0]
            }),
            interactive: false
        }).addTo(map);
        // update panel header
        $('#gpColorDot').css('background', zone.color);
        $('#gpName').text(zone.name || '');
        var crop = zone.crop || '';
        if (crop) {
            $('#gpCropBadge').text(crop).css('background', zone.color).css('color', '#fff').show();
        } else {
            $('#gpCropBadge').hide();
        }
        $('#gpSaveMsg').text('Сохранено').fadeOut(1500);
    });
}

function importKml(kmlText) {
    var parser = new DOMParser();
    var xml = parser.parseFromString(kmlText, 'text/xml');
    var placemarks = xml.querySelectorAll('Placemark');
    var candidates = [];
    placemarks.forEach(function(pm) {
        var coordsEl = pm.querySelector('outerBoundaryIs LinearRing coordinates');
        if (!coordsEl) return;
        var raw = coordsEl.textContent.trim();
        var parts = raw.split(/[\s,]+/);
        var latlngs = [];
        for (var i = 0; i + 2 < parts.length; i += 3) {
            var lon = parseFloat(parts[i]);
            var lat = parseFloat(parts[i + 1]);
            if (!isNaN(lat) && !isNaN(lon)) latlngs.push([lat, lon]);
        }
        if (latlngs.length < 3) return;
        candidates.push({points: latlngs, count: latlngs.length});
    });
    if (candidates.length === 0) { alert('No valid polygons found in KML file'); return; }
    // Pick the largest polygon (field boundary) — skip implement sections
    var best = candidates.reduce(function(a, b) { return a.count > b.count ? a : b; });
    var name = xml.querySelector('Placemark name');
    var nameText = name ? name.textContent.trim() : 'Imported';

    fetch('/api/geozones', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name: nameText, points: best.points})
    })
    .then(function(r) { return r.json(); })
    .then(function(zone) {
        addGeozoneToMap(zone);
        renderGeozoneList();
    });
}

function escapeHtml(text) {
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(text));
    return div.innerHTML;
}

// -------- Area & Perimeter --------

function toRad(deg) { return deg * Math.PI / 180; }

function haversineDist(a, b) {
    var R = 6371000;
    var dLat = toRad(b[0] - a[0]);
    var dLon = toRad(b[1] - a[1]);
    var sinLat = Math.sin(dLat / 2);
    var sinLon = Math.sin(dLon / 2);
    var x = sinLat * sinLat + Math.cos(toRad(a[0])) * Math.cos(toRad(b[0])) * sinLon * sinLon;
    return R * 2 * Math.atan2(Math.sqrt(x), Math.sqrt(1 - x));
}

function calculateArea(latlngs) {
    var originLat = latlngs[0][0], originLon = latlngs[0][1];
    var cosLat = Math.cos(toRad(originLat));
    var xs = [], ys = [];
    for (var i = 0; i < latlngs.length; i++) {
        xs.push((latlngs[i][1] - originLon) * 111320 * cosLat);
        ys.push((latlngs[i][0] - originLat) * 111320);
    }
    var area = 0;
    var n = latlngs.length;
    for (var i = 0; i < n; i++) {
        var j = (i + 1) % n;
        area += xs[i] * ys[j] - xs[j] * ys[i];
    }
    return Math.abs(area) / 20000;
}

function calculatePerimeter(latlngs) {
    var perim = 0;
    for (var i = 0; i < latlngs.length; i++) {
        var j = (i + 1) % latlngs.length;
        perim += haversineDist(latlngs[i], latlngs[j]);
    }
    return perim;
}

// -------- Point-in-Polygon --------

function pointInPolygon(pLat, pLon, points) {
    var inside = false;
    var n = points.length;
    for (var i = 0, j = n - 1; i < n; j = i++) {
        var lat1 = points[i][0], lon1 = points[i][1];
        var lat2 = points[j][0], lon2 = points[j][1];
        if ((lat1 > pLat) !== (lat2 > pLat)) {
            var xInt = lon1 + (pLat - lat1) * (lon2 - lon1) / (lat2 - lat1);
            if (pLon < xInt) inside = !inside;
        }
    }
    return inside;
}

// -------- Tractor Tracking --------

var knownTractorIps = [];
var _fetchedKnownIps = false;
var tractorSessionsCache = {};

function fetchKnownTractors() {
    if (_fetchedKnownIps) return;
    _fetchedKnownIps = true;
    fetch('/api/tractor_ips').then(function(r){return r.json()}).then(function(ips){
        knownTractorIps = ips || [];
        updateTractors(_lastTractorsData || {});
    }).catch(function(e){console.error('fetchKnownTractors failed', e);});
}

function updateTractors(tractors) {
    _lastTractorsData = tractors;
    // Save expanded session state
    var expandedPrev = {};
    for (var u in expandedSessions) {
        if (expandedSessions[u]) {
            var eid = 't_sess_' + u.replace(/[^a-zA-Z0-9]/g, '_');
            var el = document.getElementById(eid);
            if (el) expandedPrev[u] = el.innerHTML;
        }
    }
    // Fetch known tractors once
    
    // Merge known IPs with current tractors
    if (!_fetchedKnownIps) fetchKnownTractors();
    var ipRe = /^\d+\.\d+\.\d+\.\d+$/;
    var allUsernames = {};
    for (var u in tractors) { if (!ipRe.test(u)) allUsernames[u] = true; }
    for (var i = 0; i < knownTractorIps.length; i++) { if (!ipRe.test(knownTractorIps[i])) allUsernames[knownTractorIps[i]] = true; }
    
    // Deduplicate by coordinates: keep one entry per ~100m radius
    var coordKeys = {};
    for (var u in allUsernames) {
        var t = tractors[u];
        if (t && t.lat) {
            var ck = Math.round(parseFloat(t.lat) * 1000) + ',' + Math.round(parseFloat(t.lon) * 1000);
            if (coordKeys[ck]) {
                var existing = coordKeys[ck];
                if ((t.last_seen || 0) > (tractors[existing].last_seen || 0)) {
                    delete allUsernames[existing];
                    coordKeys[ck] = u;
                } else {
                    delete allUsernames[u];
                }
            } else {
                coordKeys[ck] = u;
            }
        }
    }
    
    var listHtml = '';
    var now = Date.now() / 1000;
    var sorted = Object.keys(allUsernames).sort();
    
    for (var ui = 0; ui < sorted.length; ui++) {
        var username = sorted[ui];
        var t = tractors[username];
        var lat, lon, isOnline, age, speedKmph, zoneLabel;
        var hasPos = false;
        
        if (t && t.lat) {
            lat = parseFloat(t.lat);
            lon = parseFloat(t.lon);
            var lastSeen = t.last_seen || 0;
            age = Math.round(now - lastSeen);
            isOnline = age < 30;
            hasPos = true;
        } else {
            isOnline = false;
            age = 0;
            lat = 0;
            lon = 0;
        }

        if (hasPos) {
            if (!tractorMarkers[username]) {
                tractorMarkers[username] = createTractorMarker(username);
                loadTrack(username);
                trackLastReload[username] = now;
                tractorPrevPos[username] = null;
            } else if (isOnline && now - (trackLastReload[username] || 0) > 10) {
                loadTrack(username);
                trackLastReload[username] = now;
            }

            var speedKmph = 0;
            if (tractorPrevPos[username]) {
                var prev = tractorPrevPos[username];
                var dt = now - prev.t;
                if (dt > 0) {
                    var d = haversineDist([prev.lat, prev.lon], [lat, lon]);
                    speedKmph = (d / dt) * 3.6;
                }
            }
            tractorPrevPos[username] = {lat: lat, lon: lon, t: now};
            tractorMarkers[username]._speed = speedKmph;
            tractorMarkers[username].setLatLng([lat, lon]);
            tractorMarkers[username]._hide = false;
        } else if (tractorMarkers[username]) {
            // Offline but known: keep marker but hide it
            tractorMarkers[username]._hide = true;
            tractorMarkers[username].setLatLng([0, 0]); // move off map
        }

        var zoneLabel = '';
        if (hasPos) {
            for (var zid in geozoneLayers) {
                if (geozoneLayers[zid]._hide) continue;
                if (pointInPolygon(lat, lon, geozoneLayers[zid].data.points)) {
                    zoneLabel = ' <span class="badge badge-info" style="font-size:0.75em;background:' + geozoneLayers[zid].data.color + ';color:#fff;">' + escapeHtml(geozoneLayers[zid].data.name) + '</span>';
                    break;
                }
            }
        }

        var expandId = 't_sess_' + username.replace(/[^a-zA-Z0-9]/g, '_');
        listHtml += '<div class="tractor-item ' + (isOnline ? '' : 'offline') + '">' +
            '<div class="tractor-header" onclick="focusTractor(\'' + username + '\')">' +
            '<span class="expand-icon" onclick="event.stopPropagation();toggleTractorSessions(\'' + username + '\')">&#9654;</span> ' +
            '<strong>' + escapeHtml(username) + '</strong> ' +
            zoneLabel +
            '<span class="' + (isOnline ? 'badge-online' : 'badge-offline') + '">' +
            (isOnline ? 'Online' : (hasPos ? age + 's' : 'offline')) + '</span>' +
            (hasPos ? '<br><small>' + lat.toFixed(6) + ', ' + lon.toFixed(6) + '</small>' : '<br><small class="text-muted">no position</small>') +
            ' <a href="#" onclick="event.stopPropagation();toggleTrack(\'' + username + '\');return false;">[track]</a>' +
            ' <a href="#" onclick="event.stopPropagation();deleteTractor(\'' + username + '\');return false;" style="color:#c00;text-decoration:none;" title="Delete tractor">&times;</a></div>' +
            '<div class="tractor-sessions" id="' + expandId + '" style="display:none;padding-left:12px;font-size:0.8em;"></div>' +
            '</div>';
    }
    $('#tractorList').html(listHtml || '<div class="text-muted" style="padding:8px;">No tractors</div>');
    // Restore expanded sessions
    for (var u in expandedPrev) {
        var eid = 't_sess_' + u.replace(/[^a-zA-Z0-9]/g, '_');
        var el = document.getElementById(eid);
        if (el && expandedSessions[u]) {
            el.style.display = 'block';
            el.innerHTML = expandedPrev[u];
            var icon = el.closest('.tractor-item').querySelector('.expand-icon');
            if (icon) icon.innerHTML = '&#9660;';
        }
    }
}

function toggleTractorSessions(username) {
    var expandId = 't_sess_' + username.replace(/[^a-zA-Z0-9]/g, '_');
    var container = document.getElementById(expandId);
    if (!container) return;
    
    if (container.style.display !== 'none') {
        container.style.display = 'none';
        expandedSessions[username] = false;
        var header = container.closest('.tractor-item').querySelector('.expand-icon');
        if (header) header.innerHTML = '&#9654;';
        return;
    }
    expandedSessions[username] = true;
    // Save current HTML for updateTractors restore
    expandedSessionCache[username] = container.innerHTML;
    
    // Show loading
    container.style.display = 'block';
    container.innerHTML = '<div class="text-muted">Loading sessions...</div>';
    expandedSessionCache[username] = container.innerHTML;
    var header = container.closest('.tractor-item').querySelector('.expand-icon');
    if (header) header.innerHTML = '&#9660;';
    
    fetch('/api/tractor_sessions/' + encodeURIComponent(username))
        .then(function(r) { return r.json(); })
        .then(function(sessions) {
            if (!sessions || sessions.length === 0) {
                container.innerHTML = '<div class="text-muted">No track sessions</div>';
                return;
            }
            var html = '';
            sessions.forEach(function(s) {
                var distText = s.distance_m >= 1000 ? (s.distance_m / 1000).toFixed(2) + ' km' : s.distance_m.toFixed(0) + ' m';
                var sesKey = username + '_' + s.first_t;
                var isShown = typeof sessionTrackLayers[sesKey] !== 'undefined';
                var btnText = isShown ? 'Hide' : 'Show';
                var btnClass = isShown ? 'btn-outline-danger' : 'btn-outline-primary';
                html += '<div style="border-bottom:1px solid #eee;padding:2px 0;">' +
                    '<span>' + s.date + ' ' + s.start_time + '→' + s.end_time + '</span> ' +
                    '<span class="text-muted">' + s.count + 'pts ' + distText + '</span> ' +
                    '<a class="btn btn-sm btn-outline-secondary" href="/api/download_session_csv/' + username + '/' + s.first_t + '" download style="padding:0 4px;font-size:0.75em;">CSV</a> ' +
                    '<button class="btn btn-sm ' + btnClass + '" onclick="showTrackSession(\'' + username + '\', ' + s.first_t + ', ' + s.last_t + ', this)" style="padding:0 4px;font-size:0.75em;">' + btnText + '</button></div>';
            });
            container.innerHTML = html;
            expandedSessionCache[username] = html;
        })
        .catch(function(e) {
            container.innerHTML = '<div class="text-muted">Error: ' + e.message + '</div>';
            expandedSessionCache[username] = container.innerHTML;
        });
}


function deleteTractor(username) {
    if (!confirm('Delete all track data for "' + username + '"?')) return;
    fetch('/api/tractor_track/' + encodeURIComponent(username), {method: 'DELETE'})
        .then(function(r) {
            if (r.ok) {
                // Remove from known list
                var idx = knownTractorIps.indexOf(username);
                if (idx >= 0) knownTractorIps.splice(idx, 1);
                // Remove marker
                if (tractorMarkers[username]) {
                    map.removeLayer(tractorMarkers[username]);
                    delete tractorMarkers[username];
                }
                // Remove track
                if (tractorTracks[username]) {
                    map.removeLayer(tractorTracks[username]);
                    delete tractorTracks[username];
                }
                delete trackHidden[username];
                delete trackLoadSeq[username];
                // Remove session layers
                for (var key in sessionTrackLayers) {
                    if (key.startsWith(username + '_')) {
                        map.removeLayer(sessionTrackLayers[key]);
                        delete sessionTrackLayers[key];
                    }
                }
            } else {
                alert('Failed to delete: ' + r.status);
            }
        })
        .catch(function(e) { alert('Error: ' + e.message); });
}

function calcTrackDistance(latlngs) {
    var d = 0;
    for (var i = 1; i < latlngs.length; i++) d += haversineDist(latlngs[i - 1], latlngs[i]);
    return d;
}

function trackTooltip(d) {
    if (d < 1000) return 'Track: ' + d.toFixed(0) + ' m';
    return 'Track: ' + (d / 1000).toFixed(2) + ' km';
}

function loadTrack(username) {
    // Stale-response protection
    if (!trackLoadSeq[username]) trackLoadSeq[username] = 0;
    trackLoadSeq[username]++;
    var seq = trackLoadSeq[username];

    // Remove old track to avoid layer leaks
    if (tractorTracks[username]) {
        map.removeLayer(tractorTracks[username]);
        delete tractorTracks[username];
    }
    fetch('/api/tractor_track/' + username + '/last_session')
        .then(function(r) { return r.json(); })
        .then(function(points) {
            if (trackLoadSeq[username] !== seq) return; // stale
            if (!points || points.length < 2) return;
            var latlngs = points.map(function(p) { return [p.lat, p.lon]; });
            var polyline = L.polyline(latlngs, {
                color: '#e74c3c',
                weight: 2,
                opacity: 0.6
            });
            var d = calcTrackDistance(latlngs);
            polyline.bindTooltip(trackTooltip(d), {sticky: true});
            tractorTracks[username] = polyline;
            polyline._hide = !!trackHidden[username];
            if (!polyline._hide) {
                polyline.addTo(map);
            }
        });
}

function loadAndShowTrack(ip) {
    console.log('loadAndShowTrack:', ip);
    fetch('/api/tractor_track/' + ip)
        .then(function(r) {
            if (!r.ok) { console.error('Track fetch failed:', ip, r.status); return null; }
            return r.json();
        })
        .then(function(points) {
            if (!points || points.length < 2) { console.log('Track no data:', ip); return; }
            var latlngs = points.map(function(p) { return [p.lat, p.lon]; });
            var polyline = L.polyline(latlngs, {
                color: '#e74c3c',
                weight: 2,
                opacity: 0.6
            }).addTo(map);
            var d = calcTrackDistance(latlngs);
            polyline.bindTooltip(trackTooltip(d), {sticky: true});
            tractorTracks[ip] = polyline;
            polyline._hide = false;
            map.fitBounds(polyline.getBounds().pad(0.1));
            console.log('Track loaded:', ip, latlngs.length, 'points', d.toFixed(0) + 'm');
        })
        .catch(function(e) { console.error('Track error:', ip, e); });
}

function toggleTrack(username) {
    var poly = tractorTracks[username];
    if (!poly) {
        loadTrack(username);
        return;
    }
    poly._hide = !poly._hide;
    trackHidden[username] = poly._hide;
    if (poly._hide) {
        map.removeLayer(poly);
    } else {
        map.addLayer(poly);
    }
}

function createTractorMarker(username) {
    var svgIcon = L.divIcon({
        html: '<svg width="24" height="24" viewBox="0 0 24 24" fill="none">' +
              '<circle cx="12" cy="12" r="10" fill="#e74c3c" stroke="#fff" stroke-width="2"/>' +
              '<path d="M7 14h10l-2-6H9l-2 6z" fill="#fff"/>' +
              '<rect x="8" y="14" width="2" height="3" rx="1" fill="#333"/>' +
              '<rect x="14" y="14" width="2" height="3" rx="1" fill="#333"/></svg>',
        className: '',
        iconSize: [24, 24],
        iconAnchor: [12, 12]
    });
    var marker = L.marker([0, 0], {icon: svgIcon}).addTo(map);
    marker.bindTooltip(escapeHtml(username), {offset: L.point(20, 0)});
    marker.on('click', function(e) {
        L.DomEvent.stopPropagation(e);
        marker.unbindPopup();
        marker.bindPopup('<i>Loading...</i>').openPopup();
        fetch('/api/tractor_track/' + encodeURIComponent(username) + '/last')
            .then(function(r) { return r.json(); })
            .then(function(pt) {
                if (!pt) {
                    marker.setPopupContent('<i>No track data</i>');
                    return;
                }
                var qualLabels = {0: 'Invalid', 1: 'SPS', 2: 'DGPS', 4: 'RTK Fix', 5: 'RTK Float'};
                var html = '<b>' + escapeHtml(username) + '</b><br>' +
                    'Fix: ' + (qualLabels[pt.quality] || pt.quality) + '<br>' +
                    'Satellites: ' + pt.satellites + '<br>' +
                    'HDOP: ' + (pt.hdop || 0).toFixed(1) + '<br>' +
                    'Altitude: ' + (pt.altitude || 0).toFixed(0) + ' m';
                marker.setPopupContent(html);
            })
            .catch(function() {
                marker.setPopupContent('<i>Error</i>');
            });
    });
    return marker;
}


var ndviAutoShown = false;
var ndviAllZoneIds = [];
var ndviLegend = null;
var ndviDateLabels = {};

function showAllNdviOverlays() {
    if (ndviAutoShown) return;
    // Wait for geozone polygons to load before creating date labels
    if (Object.keys(geozoneLayers).length === 0) {
        setTimeout(showAllNdviOverlays, 300);
        return;
    }
    if (!ndviLegend) {
        ndviLegend = L.control({position: "bottomright"});
        ndviLegend.onAdd = function(map) {
            var div = L.DomUtil.create("div");
            div.style.background = "#fff";
            div.style.padding = "6px 10px";
            div.style.borderRadius = "4px";
            div.style.boxShadow = "0 1px 5px rgba(0,0,0,0.4)";
            div.style.fontSize = "12px";
            div.style.lineHeight = "1.4";
            div.innerHTML = "<b>NDVI</b><br>" +
                "<div style='width:18px;height:100px;display:inline-block;vertical-align:middle;border:1px solid #ccc;background:linear-gradient(to top,#b8360a,#f58b2d,#ffe822,#d5f721,#81e828,#3dca29,#267d1b,#195312,#10310d);'></div>" +
                "<div style='display:inline-block;vertical-align:middle;padding-left:4px;'>" +
                "1.0<br>0.8<br>0.6<br>0.5<br>0.4<br>0.3<br>0.2<br>0.0</div>";
            return div;
        };
    }
    ndviLegend.addTo(map); $("#ndviLegend").show();
    fetch("/api/ndvi/layers")
        .then(function(r) { return r.json(); })
        .then(function(layers) {
            ndviAllZoneIds = layers.map(function(l) { return l.zone_id; });
            ndviAllZoneIds.forEach(function(zid) {
                if (!ndviOverlays[zid]) showNdviOverlay(zid);
                fetch("/api/ndvi/data/" + zid)
                    .then(function(r) { return r.json(); })
                    .then(function(data) {
                        if (data && data.scene_date && geozoneLayers[zid]) {
                            var center = geozoneLayers[zid].polygon.getBounds().getCenter();
                            var label = L.marker(center, {
                                icon: L.divIcon({
                                    html: "<div style='background:" + geozoneLayers[zid].data.color + ";color:#fff;padding:2px 8px;border-radius:3px;font-size:0.85em;text-align:center;white-space:nowrap;text-shadow:0 0 2px #000,0 0 2px #000;line-height:1.4;'>" +
                                        escapeHtml(geozoneLayers[zid].data.name) + "<br>" + data.scene_date + " NDVI: " + parseFloat(data.mean_ndvi).toFixed(2) + "</div>",
                                    className: "",
                                    iconSize: [0, 0],
                                    iconAnchor: [0, 0]
                                }),
                                interactive: false
                            }).addTo(map);
                            ndviDateLabels[zid] = label;
                        }
                    });
            });
            ndviAutoShown = true;
        })
        .catch(function(e) { console.log("NDVI auto-show failed:", e); });
}

function hideAllNdviOverlays() {
    for (var zid in ndviOverlays) {
        map.removeLayer(ndviOverlays[zid]);
        delete ndviOverlays[zid];
    }
    for (var zid in ndviDateLabels) {
        map.removeLayer(ndviDateLabels[zid]);
        delete ndviDateLabels[zid];
    }
    if (ndviLegend) {
        map.removeControl(ndviLegend);
    }
    $("#ndviLegend").hide();
    ndviAutoShown = false;
}

// -------- NDVI --------

var ndviOverlays = {};
var ndviSelectedDate = null;
var ndviAvailableDates = [];

function loadNdviDates(zoneId) {
    fetch("/api/ndvi/scenes/" + zoneId)
        .then(function(r) { return r.json(); })
        .then(function(dates) {
            ndviAvailableDates = dates || [];
            var container = document.getElementById("ndviDatesContainer");
            var picker = document.getElementById("ndviDatePicker");
            if (!container || !picker) return;
            if (!ndviAvailableDates.length) {
                picker.style.display = "none";
                return;
            }
            picker.style.display = "block";
            container.innerHTML = "";
            ndviAvailableDates.forEach(function(d) {
                var btn = document.createElement("button");
                var dateStr = d.scene_date || d;
                btn.textContent = dateStr;
                btn.className = "btn btn-xs " + (dateStr === ndviSelectedDate ? "btn-primary" : "btn-outline-secondary");
                btn.style.fontSize = "0.75em";
                btn.style.padding = "1px 5px";
                btn.style.border = "1px solid #aaa";
                btn.style.borderRadius = "3px";
                btn.style.cursor = "pointer";
                btn.onclick = function() {
                    ndviSelectedDate = dateStr;
                    loadNdviDates(zoneId);
                    loadNdviStatus(zoneId);
                    showNdviOverlay(zoneId, dateStr);
                };
                container.appendChild(btn);
            });
        })
        .catch(function(e) { console.log("NDVI dates error:", e); });
}

function loadNdviStatus(zoneId) {
    fetch("/api/ndvi/data/" + zoneId)
        .then(function(r) {
            if (r.redirected || !r.ok) {
                $("#ndviStatus").html("No NDVI data");
                $("#calcNdviBtn").show();
                $("#showNdviBtn, #hideNdviBtn").hide();
                return null;
            }
            return r.json();
        })
        .then(function(data) {
            if (!data || data.error) {
                $("#ndviStatus").html("No NDVI data");
                $("#calcNdviBtn").show();
                $("#showNdviBtn, #hideNdviBtn").hide();
                return;
            }
            var ndvi = data.mean_ndvi;
            var html = "Mean NDVI: <b>" + parseFloat(ndvi).toFixed(3) + "</b>" +
                " (min: " + parseFloat(data.min_ndvi).toFixed(3) +
                ", max: " + parseFloat(data.max_ndvi).toFixed(3) + ")<br>" +
                "<small>Scene: " + (data.scene_date || "unknown") + "</small>";
            $("#ndviStatus").html(html);
            $("#calcNdviBtn").text("Recalculate NDVI").show();
            $("#showNdviBtn").show();
            loadNdviDates(zoneId);
        })
        .catch(function(e) {
            console.log("NDVI status error:", e);
            $("#ndviStatus").html("No NDVI data");
            $("#calcNdviBtn").show();
            $("#showNdviBtn, #hideNdviBtn").hide();
        });
}

function showNdviOverlay(zoneId, sceneDate) {
    var dateParam = sceneDate ? "?date=" + sceneDate : "";
    var overlayUrl = "/api/ndvi/overlay/" + zoneId + ".png" + dateParam;
    fetch(overlayUrl)
        .then(function(r) {
            if (!r.ok) throw new Error("NDVI overlay not found");
            var bbox = JSON.parse(r.headers.get("X-Bbox") || "[]");
            return r.blob().then(function(blob) { return {bbox: bbox, blob: blob}; });
        })
        .then(function(data) {
            if (data.bbox.length !== 4) throw new Error("Invalid bbox");
            var bounds = [[data.bbox[1], data.bbox[0]], [data.bbox[3], data.bbox[2]]];
            var imageUrl = URL.createObjectURL(data.blob);
            var overlay = L.imageOverlay(imageUrl, bounds, {opacity: 0.7}).addTo(map);
            if (ndviOverlays[zoneId]) {
                map.removeLayer(ndviOverlays[zoneId]);
            }
            ndviOverlays[zoneId] = overlay;
            $("#showNdviBtn").hide();
            $("#hideNdviBtn").show();
        })
        .catch(function(e) {
            console.log("NDVI overlay failed:", e.message);
        });
}

function hideNdviOverlay(zoneId) {
    $("#ndviLegend").hide();
    if (ndviOverlays[zoneId]) {
        map.removeLayer(ndviOverlays[zoneId]);
        delete ndviOverlays[zoneId];
    }
    $("#showNdviBtn").show();
    $("#hideNdviBtn").hide();
}

// Wire up NDVI buttons
$("#calcNdviBtn").click(function() {
    var zoneId = currentZoneId;
    if (!zoneId) {
        $("#ndviStatus").html('<span style="color:red">Error: no zone selected</span>');
        return;
    }
    $("#calcNdviBtn").prop("disabled", true).text("Calculating... (60-90s)");
    $("#ndviStatus").html("Calculating NDVI...");
    fetch("/api/ndvi/calculate/" + zoneId, {method: "POST"})
        .then(function(r) {
            if (r.redirected) {
                $("#ndviStatus").html('<span style="color:red">Session expired, please refresh and login</span>');
                $("#calcNdviBtn").prop("disabled", false).text("Calculate NDVI Now");
                return null;
            }
            return r.json();
        })
        .then(function(result) {
            if (!result) return;
            if (result.error) {
                $("#ndviStatus").html('<span style="color:red">Error: ' + result.error + "</span>");
                $("#calcNdviBtn").prop("disabled", false).text("Calculate NDVI Now");
                return;
            }
            loadNdviStatus(zoneId);
            $("#calcNdviBtn").prop("disabled", false);
        })
        .catch(function(e) {
            $("#ndviStatus").html('<span style="color:red">Request failed: ' + e.message + "</span>");
            $("#calcNdviBtn").prop("disabled", false).text("Calculate NDVI Now");
        });
});

$("#showNdviBtn").click(function() {
    var zoneId = currentZoneId;
    if (zoneId) showNdviOverlay(zoneId);
});

$("#hideNdviBtn").click(function() {
    var zoneId = currentZoneId;
    if (zoneId) hideNdviOverlay(zoneId);
});

// -------- NDVI Calendar (all zones) --------

var ndviCalYear, ndviCalMonth;

function pad2(n) { return n < 10 ? "0" + n : "" + n; }

function buildCalendar(year, month, dateMap) {
    var monthNames = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
    var dayLabels = ["Mo","Tu","We","Th","Fr","Sa","Su"];
    var firstDay = new Date(year, month, 1);
    var lastDay = new Date(year, month + 1, 0);
    var startCol = firstDay.getDay();
    var startOffset = startCol === 0 ? 6 : startCol - 1;
    var daysInMonth = lastDay.getDate();
    var now = new Date();
    var todayStr = now.getFullYear() + "-" + pad2(now.getMonth()+1) + "-" + pad2(now.getDate());
    var h = "";

    // Month header
    h += "<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;'>";
    h += "<button class='btn btn-sm btn-outline-secondary' data-cal-nav='prev' style='padding:0 8px;font-size:0.8em;line-height:1.4;'>&#9664;</button>";
    h += "<span style='font-weight:bold;font-size:0.9em;'>" + monthNames[month] + " " + year + "</span>";
    h += "<button class='btn btn-sm btn-outline-secondary' data-cal-nav='next' style='padding:0 8px;font-size:0.8em;line-height:1.4;'>&#9654;</button>";
    h += "</div>";

    // Day-of-week header
    h += "<div style='display:grid;grid-template-columns:repeat(7,1fr);text-align:center;font-size:0.7em;color:#888;margin-bottom:2px;'>";
    for (var i = 0; i < 7; i++) h += "<div>" + dayLabels[i] + "</div>";
    h += "</div>";

    // Date grid
    h += "<div style='display:grid;grid-template-columns:repeat(7,1fr);gap:1px;text-align:center;font-size:0.8em;'>";
    for (var i = 0; i < startOffset; i++) h += "<div></div>";

    for (var day = 1; day <= daysInMonth; day++) {
        var dateStr = year + "-" + pad2(month + 1) + "-" + pad2(day);
        var hasData = !!dateMap[dateStr];
        var isSelected = dateStr === ndviSelectedDate;
        var isToday = dateStr === todayStr;
        var cellClass = "ndvi-cal-day" + (hasData ? " ndvi-has-data" : "") + (isSelected ? " ndvi-selected" : "");
        var style = "padding:2px 0;border-radius:3px;cursor:" + (hasData ? "pointer" : "default") + ";";
        if (isSelected) { style += "background:#007bff;color:#fff;font-weight:bold;"; }
        else if (hasData) { style += "background:#d4edda;color:#155724;font-weight:bold;"; }
        if (isToday && !isSelected && !hasData) { style += "font-weight:bold;"; }
        h += "<div style='" + style + "' data-cal-date='" + dateStr + "' data-has-data='" + hasData + "'>" + day + "</div>";
    }
    h += "</div>";


    return h;
}

function loadNdviCalendar() {
    fetch("/api/ndvi/scenes")
        .then(function(r) { return r.json(); })
        .then(function(scenes) {
            var container = document.getElementById("ndviCalendarDates");
            if (!container) return;
            var dateMap = {};
            scenes.forEach(function(s) {
                var d = s.scene_date;
                if (d) dateMap[d] = (dateMap[d] || 0) + 1;
            });
            var sortedDates = Object.keys(dateMap).sort();
            if (sortedDates.length === 0) {
                container.innerHTML = '<span class="text-muted" style="padding:4px;font-size:0.85em;">No NDVI data</span>';
                return;
            }

            // Init month to most recent date
            if (ndviCalYear === undefined) {
                var last = new Date(sortedDates[sortedDates.length - 1]);
                ndviCalYear = last.getFullYear();
                ndviCalMonth = last.getMonth();
            }

            container.innerHTML = buildCalendar(ndviCalYear, ndviCalMonth, dateMap);

            // Delegate clicks
            container.onclick = function(e) {
                var t = e.target;
                if (t.getAttribute("data-cal-nav") === "prev") {
                    ndviCalMonth--;
                    if (ndviCalMonth < 0) { ndviCalMonth = 11; ndviCalYear--; }
                    loadNdviCalendar();
                    return;
                }
                if (t.getAttribute("data-cal-nav") === "next") {
                    ndviCalMonth++;
                    if (ndviCalMonth > 11) { ndviCalMonth = 0; ndviCalYear++; }
                    loadNdviCalendar();
                    return;
                }
                var dateStr = t.getAttribute("data-cal-date");
                if (dateStr && t.getAttribute("data-has-data") === "true") {
                    if (dateStr === ndviSelectedDate) {
                        ndviSelectedDate = null;
                        hideAllNdviOverlays();
                        $("#ndviShowCalendarBtn").hide();
                        $("#ndviHideCalendarBtn").hide();
                    } else {
                        ndviSelectedDate = dateStr;
                        showAllNdviForDate(dateStr);
                        $("#ndviShowCalendarBtn").hide();
                        $("#ndviHideCalendarBtn").show();
                    }
                    loadNdviCalendar();
                }
            };
        })
        .catch(function(e) { console.log("NDVI calendar error:", e); });
}

function showAllNdviForDate(date) {
    hideAllNdviOverlays();
    for (var zid in geozoneLayers) {
        (function(zoneId) {
            var overlayUrl = "/api/ndvi/overlay/" + zoneId + ".png?date=" + date;
            fetch(overlayUrl)
                .then(function(r) {
                    if (!r.ok) return null;
                    var bbox = JSON.parse(r.headers.get("X-Bbox") || "[]");
                    return r.blob().then(function(blob) { return {bbox: bbox, blob: blob}; });
                })
                .then(function(data) {
                    if (!data || data.bbox.length !== 4) return;
                    var bounds = [[data.bbox[1], data.bbox[0]], [data.bbox[3], data.bbox[2]]];
                    var imageUrl = URL.createObjectURL(data.blob);
                    var overlay = L.imageOverlay(imageUrl, bounds, {opacity: 0.7}).addTo(map);
                    if (ndviOverlays[zoneId]) {
                        map.removeLayer(ndviOverlays[zoneId]);
                    }
                    ndviOverlays[zoneId] = overlay;
                    fetch("/api/ndvi/data/" + zoneId + "?date=" + date)
                        .then(function(r2) { return r2.ok ? r2.json() : null; })
                        .then(function(data2) {
                            if (data2 && !data2.error && geozoneLayers[zoneId]) {
                                var center = geozoneLayers[zoneId].polygon.getBounds().getCenter();
                                var label = L.marker(center, {
                                    icon: L.divIcon({
                                        html: "<div style='background:" + geozoneLayers[zoneId].data.color + ";color:#fff;padding:2px 8px;border-radius:3px;font-size:0.85em;text-align:center;white-space:nowrap;text-shadow:0 0 2px #000,0 0 2px #000;line-height:1.4;'>" +
                                            escapeHtml(geozoneLayers[zoneId].data.name) + "<br>" + data2.scene_date + " NDVI: " + parseFloat(data2.mean_ndvi).toFixed(2) + "</div>",
                                        className: "",
                                        iconSize: [0, 0],
                                        iconAnchor: [0, 0]
                                    }),
                                    interactive: false
                                }).addTo(map);
                                ndviDateLabels[zoneId] = label;
                            }
                        });
                })
                .catch(function(e) {});
        })(zid);
    }
    if (!ndviLegend) {
        ndviLegend = L.control({position: "bottomright"});
        ndviLegend.onAdd = function(map) {
            var div = L.DomUtil.create("div");
            div.style.background = "#fff";
            div.style.padding = "6px 10px";
            div.style.borderRadius = "4px";
            div.style.boxShadow = "0 1px 5px rgba(0,0,0,0.4)";
            div.style.fontSize = "12px";
            div.style.lineHeight = "1.4";
            div.innerHTML = "<b>NDVI</b><br>" +
                "<div style='width:18px;height:100px;display:inline-block;vertical-align:middle;border:1px solid #ccc;background:linear-gradient(to top,#b8360a,#f58b2d,#ffe822,#d5f721,#81e828,#3dca29,#267d1b,#195312,#10310d);'></div>" +
                "<div style='display:inline-block;vertical-align:middle;padding-left:4px;'>1.0<br>0.8<br>0.6<br>0.5<br>0.4<br>0.3<br>0.2<br>0.0</div>";
            return div;
        };
    }
    ndviLegend.addTo(map); $("#ndviLegend").show();
    $("#ndviShowCalendarBtn").hide();
    $("#ndviHideCalendarBtn").show();
}

$("#ndviShowCalendarBtn").click(function() {
    if (ndviSelectedDate) {
        showAllNdviForDate(ndviSelectedDate);
        $("#ndviShowCalendarBtn").hide();
        $("#ndviHideCalendarBtn").show();
    } else {
        loadNdviCalendar();
    }
});

$("#ndviHideCalendarBtn").click(function() {
    hideAllNdviOverlays();
    ndviSelectedDate = null;
    loadNdviCalendar();
    $("#ndviShowCalendarBtn").show();
    $("#ndviHideCalendarBtn").hide();
});

// Load NDVI calendar on page ready
loadNdviCalendar();

// === Task Planner (sidebar) ===
var taskPlannerActive = false;
var plannerPathLayer = null;
var prevBaseLayer = null;

function openTaskPlanner(zoneId) {
    if (!zoneId) return;
    var z = geozoneLayers[zoneId];
    if (!z) return;
    
    taskPlannerActive = true;
    $("#plannerZoneId").val(zoneId);
    $("#taskPlannerSection").show();
    
    // Center map on geozone
    var bounds = z.polygon.getBounds();
    map.fitBounds(bounds.pad(0.2));
    
    // Switch to Satellite layer
    if (!map.hasLayer(sat)) {
        map.eachLayer(function(layer) {
            if (layer._url && layer._url.indexOf("openstreetmap") !== -1) {
                prevBaseLayer = layer;
                map.removeLayer(layer);
            }
        });
        map.addLayer(sat);
    }
    
    // Hide geozone panel, show map
    var _p = document.getElementById('geozonePanel');
    if (_p) _p.style.display = 'none';
    var _m = document.getElementById('map');
    if (_m) _m.style.display = 'block';
    if (map) setTimeout(function() { map.invalidateSize(); }, 60);
    if (currentZoneId) hideNdviOverlay(currentZoneId);
    currentZoneId = null;
    
    // Load saved tasks
    loadPlannerTasks(zoneId);
    
    // Reset UI
    $("#plannerInfo").hide();
    $("#plannerSaveBtn").hide();
    clearPlannerPreview();
}

function closeTaskPlanner() {
    taskPlannerActive = false;
    $("#taskPlannerSection").hide();
    
    // Restore previous base layer
    if (prevBaseLayer) {
        map.removeLayer(sat);
        map.addLayer(prevBaseLayer);
        prevBaseLayer = null;
    }
    
    clearPlannerPreview();
}

function clearPlannerPreview() {
    if (plannerPathLayer) {
        map.removeLayer(plannerPathLayer);
        plannerPathLayer = null;
    }
}

$("#plannerCloseBtn").click(function() {
    closeTaskPlanner();
});

$("#plannerGenerateBtn").click(function() {
    var zoneId = $("#plannerZoneId").val();
    var swathWidth = parseFloat($("#plannerSwathWidth").val()) || 10;
    var turningRadius = parseFloat($("#plannerTurningRadius").val());
    if (!turningRadius || turningRadius <= 0) turningRadius = swathWidth / 2;
    var angle = parseFloat($("#plannerAngle").val()) || 0;
    var boundaryOffset = parseFloat($("#plannerBoundaryOffset").val()) || 0;
    var boundaryPass = $("#plannerBoundaryPass").is(":checked");
    
    if (!zoneId) return;
    $("#plannerGenerateBtn").prop("disabled", true).text("Generating...");
    
    fetch("/api/geozones/" + zoneId + "/generate_path", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({swath_width: swathWidth, angle: angle, turning_radius: turningRadius, offset: boundaryOffset, boundary_pass: boundaryPass})
    })
    .then(function(r) {
        if (r.redirected) return null;
        return r.json();
    })
    .then(function(result) {
        $("#plannerGenerateBtn").prop("disabled", false).text("Generate");
        if (!result) return;
        if (result.error) {
            alert("Error: " + result.error);
            return;
        }
        showPlannerPreview(result);
    })
    .catch(function(e) {
        $("#plannerGenerateBtn").prop("disabled", false).text("Generate");
        alert("Request failed: " + e.message);
    });
});

// Auto-update turning radius default when swath width changes
$("#plannerSwathWidth").on("input change", function() {
    var tr = $("#plannerTurningRadius").val();
    if (!tr || parseFloat(tr) <= 0) {
        var sw = parseFloat($(this).val()) || 10;
        $("#plannerTurningRadius").val((sw / 2).toFixed(1));
    }
});

function showPlannerPreview(result) {
    clearPlannerPreview();
    
    var feature = result.features[0];
    var props = feature.properties;
    var coords = feature.geometry.coordinates;
    
    // Show path on main map
    plannerPathLayer = L.polyline(coords.map(function(c) { return [c[1], c[0]]; }), {
        color: "#e74c3c",
        weight: 3,
        opacity: 0.8
    }).addTo(map);
    
    map.fitBounds(plannerPathLayer.getBounds().pad(0.1));
    
    // Show info
    var km = (props.total_length_m / 1000).toFixed(1);
    var bpLabel = $("#plannerBoundaryPass").is(":checked") ? " + boundary pass" : "";
    $("#plannerInfo").html(
        '<strong>' + props.num_swaths + '</strong> swaths, ' +
        '<strong>' + props.swath_width + '</strong>m width, ' +
        '<strong>' + km + '</strong> km'
    ).show();
    $("#plannerSaveBtn").show().data("result", result);
}

$("#plannerSaveBtn").click(function() {
    var zoneId = $("#plannerZoneId").val();
    var name = $("#plannerTaskName").val() || "Coverage Task";
    var swathWidth = parseFloat($("#plannerSwathWidth").val()) || 10;
    var turningRadius = parseFloat($("#plannerTurningRadius").val());
    if (!turningRadius || turningRadius <= 0) turningRadius = swathWidth / 2;
    var angle = parseFloat($("#plannerAngle").val()) || 0;
    var result = $(this).data("result");
    
    if (!result) return;
    var props = result.features[0].properties;
    
    $("#plannerSaveBtn").prop("disabled", true).text("Saving...");
    
    fetch("/api/geozones/" + zoneId + "/tasks", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
            name: name,
            swath_width: swathWidth,
            angle: angle,
            path_geojson: JSON.stringify(result),
            total_length_m: props.total_length_m,
            num_swaths: props.num_swaths
        })
    })
    .then(function(r) { return r.json(); })
    .then(function(res) {
        $("#plannerSaveBtn").prop("disabled", false).text("Save Task");
        if (res.error) {
            alert("Error: " + res.error);
            return;
        }
        loadPlannerTasks(zoneId);
        $("#plannerInfo").html('<span style="color:green;">Task saved!</span>');
        // Keep the path visible
    })
    .catch(function(e) {
        $("#plannerSaveBtn").prop("disabled", false).text("Save Task");
        alert("Save failed: " + e.message);
    });
});

function loadPlannerTasks(zoneId) {
    if (!zoneId) return;
    fetch("/api/geozones/" + zoneId + "/tasks")
        .then(function(r) { return r.json(); })
        .then(function(tasks) {
            var html = "";
            if (tasks.length === 0) {
                html = '<div class="text-muted">No saved tasks</div>';
            } else {
                html = '<div class="font-weight-bold small mt-1">Saved Tasks:</div>';
                tasks.forEach(function(t) {
                    var d = new Date(t.created * 1000);
                    html += '<div class="task-item" style="padding:3px 0;border-bottom:1px solid #eee;cursor:pointer;" onclick="showTaskOnMap(\'' + zoneId + '\',' + t.id + ')">';
                    html += escapeHtml(t.name);
                    html += '<span style="float:right;color:#dc3545;cursor:pointer;font-weight:bold;" onclick="event.stopPropagation();deletePlannerTask(\'' + zoneId + '\',' + t.id + ')">&times;</span>';
                    html += '<br><small class="text-muted">' + t.swath_width + 'm, ' + t.angle + 'deg, ' + t.total_length_m + 'm</small>';
                    html += '</div>';
                });
            }
            $("#plannerSavedTasks").html(html);
        });
}

function showTaskOnMap(zoneId, taskId) {
    var m = document.getElementById('map');
    var p = document.getElementById('geozonePanel');
    if (m) m.style.display = 'block';
    if (p) p.style.display = 'none';
    if (currentZoneId) hideNdviOverlay(currentZoneId);
    currentZoneId = null;
    if (map) setTimeout(function() { map.invalidateSize(); }, 60);
    fetch("/api/geozones/" + zoneId + "/tasks/" + taskId + "/path")
        .then(function(r) { return r.json(); })
        .then(function(geojson) {
            if (!geojson || geojson.error) return;
            showPlannerPreview(geojson);
        });
}

function deletePlannerTask(zoneId, taskId) {
    if (!confirm("Delete this task?")) return;
    fetch("/api/tasks/" + taskId, {method: "DELETE"})
        .then(function() {
            loadPlannerTasks(zoneId);
            if ($("#plannerSavedTasks").children().length <= 1) {
                clearPlannerPreview();
            }
        });
}

// === Pick 2 Points Mode ===
var plannerPickMarkers = [];
var plannerPickLine = null;
var plannerPickActive = false;
var plannerPickStep = 0; // 0=idle, 1=waiting first, 2=waiting second

function exitPickMode() {
    plannerPickActive = false;
    plannerPickStep = 0;
    $("#plannerPickInfo").hide();
    $("#plannerPickBtn").text("Pick 2 Points on Map").removeClass("btn-danger").addClass("btn-outline-info");
    // Remove markers and line
    plannerPickMarkers.forEach(function(m) { map.removeLayer(m); });
    plannerPickMarkers = [];
    if (plannerPickLine) { map.removeLayer(plannerPickLine); plannerPickLine = null; }
    map.off("click", onPlannerMapClick);
    map.getContainer().style.cursor = "";
}

function onPlannerMapClick(e) {
    if (!plannerPickActive) return;
    var zoneId = $("#plannerZoneId").val();
    if (!zoneId) return;
    
    var latlng = e.latlng;
    
    // Snap to boundary
    fetch("/api/geozones/" + zoneId + "/snap_point", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({lat: latlng.lat, lon: latlng.lng})
    })
    .then(function(r) { return r.json(); })
    .then(function(res) {
        if (!res || res.error) {
            addPickPoint(latlng);
            return;
        }
        var pt = res.snapped ? L.latLng(res.lat, res.lon) : latlng;
        if (res.snapped) {
            addPickPoint(pt);
        } else {
            addPickPoint(pt);
        }
    });
}

function addPickPoint(latlng) {
    if (!plannerPickActive) return;
    plannerPickStep++;
    
    var marker = L.circleMarker(latlng, {
        radius: 6,
        color: "#e74c3c",
        fillColor: "#fff",
        fillOpacity: 1,
        weight: 2
    }).addTo(map);
    plannerPickMarkers.push(marker);
    
    // Draw line between points if we have 2
    if (plannerPickStep === 2) {
        var p1 = plannerPickMarkers[0].getLatLng();
        var p2 = plannerPickMarkers[1].getLatLng();
        
        plannerPickLine = L.polyline([p1, p2], {
            color: "#e67e22",
            weight: 3,
            dashArray: "5,5",
            opacity: 0.8
        }).addTo(map);
        
        // Calculate angle
        var angle = calculateAngle(p1, p2);
        $("#plannerAngle").val(Math.round(angle));
        
        // Auto-generate
        $("#plannerPickInfo").html("Angle: " + Math.round(angle) + " deg. Generating path...");
        exitPickMode();
        $("#plannerGenerateBtn").click();
    } else {
        $("#plannerPickInfo").html("Point " + plannerPickStep + " set. Click second point on map.");
    }
}

function calculateAngle(p1, p2) {
    // Returns angle in degrees (0=north, 90=east) from p1 to p2
    var dx = p2.lng - p1.lng;
    var dy = p2.lat - p1.lat;
    // Convert to meters (approximate)
    var rlat = (p1.lat + p2.lat) / 2 * Math.PI / 180;
    var mx = dx * 111320 * Math.cos(rlat);
    var my = dy * 111320;
    // Angle from north, clockwise
    var angle = Math.atan2(mx, my) * 180 / Math.PI;
    if (angle < 0) angle += 360;
    if (angle >= 180) angle -= 180;
    return angle;
}

$("#plannerPickBtn").click(function() {
    if (plannerPickActive) {
        exitPickMode();
        return;
    }
    var zoneId = $("#plannerZoneId").val();
    if (!zoneId) return;
    
    // Clear previous preview
    clearPlannerPreview();
    $("#plannerInfo").hide();
    $("#plannerSaveBtn").hide();
    
    plannerPickActive = true;
    plannerPickStep = 0;
    plannerPickMarkers = [];
    if (plannerPickLine) { map.removeLayer(plannerPickLine); plannerPickLine = null; }
    
    $(this).text("Cancel Pick").removeClass("btn-outline-info").addClass("btn-danger");
    $("#plannerPickInfo").html("Click first point on map (near geozone boundary for snap).").show();
    
    map.on("click", onPlannerMapClick);
    map.getContainer().style.cursor = "crosshair";
});

// Clean up pick mode when closing planner
var origCloseTaskPlanner = closeTaskPlanner;
closeTaskPlanner = function() {
    if (plannerPickActive) exitPickMode();
    origCloseTaskPlanner();
};

// -------- Tractor Sessions --------
var sessionTrackLayers = {};



function focusTractor(username) {
    var marker = tractorMarkers[username];
    if (marker) {
        map.setView(marker.getLatLng(), map.getZoom(), {animate: true});
        marker.openTooltip();
    }
}

function showTractorSessions(username) {
    document.getElementById('sessionsTractorName').textContent = username;
    var tbody = document.getElementById('sessionsTableBody');
    tbody.innerHTML = '<tr><td colspan="5" class="text-muted">Loading...</td></tr>';
    $('#tractorSessionsModal').modal('show');
    
    fetch('/api/tractor_sessions/' + encodeURIComponent(username))
        .then(function(r) { return r.json(); })
        .then(function(sessions) {
            if (!sessions || sessions.length === 0) {
                tbody.innerHTML = '<tr><td colspan="5" class="text-muted">No sessions found</td></tr>';
                return;
            }
            tbody.innerHTML = '';
            sessions.forEach(function(s, i) {
                var distText = s.distance_m >= 1000 ? (s.distance_m / 1000).toFixed(2) + ' km' : s.distance_m.toFixed(0) + ' m';
                var tr = document.createElement('tr');
                tr.innerHTML = '<td>' + s.date + '</td><td>' + s.start_time + '→' + s.end_time + '</td>' +
                    '<td>' + s.count + '</td>' +
                    '<td>' + distText + '</td>' +
                    '<td style="white-space:nowrap;"><a class="btn btn-sm btn-outline-secondary" href="/api/download_session_csv/' + username + '/' + s.first_t + '" download>CSV</a> <button class="btn btn-sm btn-outline-primary" onclick="showTrackSession(\'' + username + '\', ' + s.first_t + ', ' + s.last_t + ', this)">Show</button></td>';
                tbody.appendChild(tr);
            });
            // Fix button states for already-visible sessions
            var allBtns = tbody.querySelectorAll('button');
            for (var bi = 0; bi < allBtns.length; bi++) {
                var b = allBtns[bi];
                if (b.textContent === 'Show' || b.textContent === 'Hide') {
                    // Extract firstT from onclick attribute
                    var match = b.getAttribute('onclick').match(/showTrackSession\([^,]+,\s*(\d+)/);
                    if (match) {
                        var key = username + '_' + match[1];
                        if (typeof sessionTrackLayers[key] !== 'undefined') {
                            b.textContent = 'Hide';
                            b.className = 'btn btn-sm btn-outline-danger';
                        }
                    }
                }
            }
        })
        .catch(function(e) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-muted">Error: ' + e.message + '</td></tr>';
        });
}

function showTrackSession(username, firstT, lastT, btn) {
    // Toggle: if already showing this session, hide it
    var key = username + '_' + firstT;
    if (sessionTrackLayers[key]) {
        map.removeLayer(sessionTrackLayers[key]);
        delete sessionTrackLayers[key];
        btn.textContent = 'Show';
        btn.className = 'btn btn-sm btn-outline-primary';
        return;
    }
    
    btn.textContent = 'Loading...';
    btn.disabled = true;
    
    fetch('/api/tractor_track/' + encodeURIComponent(username))
        .then(function(r) { return r.json(); })
        .then(function(points) {
            btn.textContent = 'Show';
            btn.disabled = false;
            if (!points || points.length < 2) return;
            // Filter points within the session time range
            var filtered = points.filter(function(p) { return p.t >= firstT && p.t <= lastT; });
            if (filtered.length < 2) return;
            
            var latlngs = filtered.map(function(p) { return [p.lat, p.lon]; });
            var polyline = L.polyline(latlngs, {
                color: '#2980b9',
                weight: 3,
                opacity: 0.8
            }).addTo(map);
            var d = 0;
            for (var i = 1; i < latlngs.length; i++) d += haversineDist(latlngs[i-1], latlngs[i]);
            var distText = d >= 1000 ? (d / 1000).toFixed(2) + ' km' : d.toFixed(0) + ' m';
            polyline.bindTooltip(username + ' ' + distText, {sticky: true});
            
            sessionTrackLayers[key] = polyline;
            map.fitBounds(polyline.getBounds().pad(0.1));
            
            btn.textContent = 'Hide';
            btn.className = 'btn btn-sm btn-outline-danger';
        })
        .catch(function(e) {
            btn.textContent = 'Show';
            btn.disabled = false;
            console.error('Session track error:', e);
        });
}

// Clean up session tracks when modal closes
// Session tracks now managed inline, no cleanup on modal hide



// -------- Weather --------
var weatherInterval = null;
var _weatherCurrent = null;
var _weatherForecast = null;
var _weatherPeriodIdx = -1;

function weatherIcon(desc) {
    var d = (desc || '').toLowerCase();
    if (d.indexOf('sunny') >= 0 || d.indexOf('clear') >= 0 || d.indexOf('солнечн') >= 0 || d.indexOf('ясн') >= 0) return '\u2600\ufe0f';
    if (d.indexOf('cloud') >= 0 && d.indexOf('partly') >= 0 || d.indexOf('переменная облач') >= 0 || d.indexOf('переменная обл') >= 0) return '\u26c5';
    if ((d.indexOf('cloud') >= 0 || d.indexOf('облачн') >= 0 || d.indexOf('обл') >= 0) && d.indexOf('overcast') < 0) return '\u2601\ufe0f';
    if (d.indexOf('overcast') >= 0 || d.indexOf('пасмурн') >= 0) return '\u2601\ufe0f';
    if (d.indexOf('rain') >= 0 || d.indexOf('дожд') >= 0 || d.indexOf('ливень') >= 0 || d.indexOf('слабая') >= 0 || d.indexOf('patchy') >= 0 || d.indexOf('near') >= 0 || d.indexOf('shower') >= 0) return '\ud83c\udf27\ufe0f';
    if (d.indexOf('drizzle') >= 0 || d.indexOf('морос') >= 0) return '\ud83c\udf26\ufe0f';
    if (d.indexOf('thunder') >= 0 || d.indexOf('гроз') >= 0) return '\u26c8\ufe0f';
    if (d.indexOf('snow') >= 0 || d.indexOf('sleet') >= 0 || d.indexOf('blizzard') >= 0 || d.indexOf('снег') >= 0) return '\u2744\ufe0f';
    if (d.indexOf('fog') >= 0 || d.indexOf('mist') >= 0 || d.indexOf('haze') >= 0 || d.indexOf('туман') >= 0) return '\ud83c\udf2b\ufe0f';
    return '\u2600\ufe0f';
}

function renderTop(data, label) {
    var icon = weatherIcon(data.desc || '');
    var h = '<div style="padding:2px 0;">';
    if (label) h += '<div style="font-size:0.7em;color:#999;cursor:pointer;" id="weatherBackBtn" onclick="showWeatherNow()" title="Back to current">&larr; ' + label + '</div>';
    h += '<div style="display:flex;align-items:center;gap:10px;">' +
        '<span style="font-size:2.5em;line-height:1;">' + icon + '</span>' +
        '<div>' +
        '<div style="font-size:2em;font-weight:700;line-height:1.1;">' + (data.temp || '--') + '\u00b0C</div>' +
        '<div style="font-size:0.8em;color:#888;">' + (data.desc || '') + '</div>' +
        '</div>' +
        '</div>' +
        '<div style="display:flex;gap:10px;margin-top:6px;font-size:0.78em;color:#555;">' +
        (data.humidity ? '<span title="Humidity">\ud83d\udca7 ' + data.humidity + '%</span>' : '') +
        '<span title="Wind">\ud83d\udca8 ' + (data.wind_speed || '--') + ' km/h' + (data.wind_dir ? ' ' + data.wind_dir : '') + '</span>' +
        (data.pressure ? '<span title="Pressure">\ud83d\udd30 ' + data.pressure + ' hPa</span>' : '') +
        (data.precip ? '<span title="Precip">\ud83d\udca6 ' + data.precip + ' mm</span>' : '') +
        '</div></div>';
    return h;
}

var _weatherPeriods = ['morning', 'day', 'evening', 'night'];
var _weatherPLabels = ['\ud83c\udf04', '\u2600\ufe0f', '\ud83c\udf07', '\ud83c\udf19'];
var _weatherPLabelsEn = {morning:'Morning', day:'Day', evening:'Evening', night:'Night'};

function getWeatherPeriodsForDisplay(forecast) {
    if (!forecast || forecast.length === 0) return [];
    var h = new Date().getHours();
    var cur;
    if (h >= 6 && h < 12) cur = 0;
    else if (h >= 12 && h < 17) cur = 1;
    else if (h >= 17 && h < 20) cur = 2;
    else cur = 3;
    var result = [];
    for (var offset = 1; offset <= 4; offset++) {
        var gi = cur + offset;
        var dayIdx = Math.floor(gi / 4);
        var periodIdx = gi % 4;
        if (dayIdx >= forecast.length) break;
        var day = forecast[dayIdx];
        var p = day[_weatherPeriods[periodIdx]];
        if (p && p.temp) {
            p._globalIdx = gi;
            p._dayIdx = dayIdx;
            p._periodIdx = periodIdx;
            p._label = dayIdx === 0 ? _weatherPLabels[periodIdx] : _weatherPLabels[periodIdx];
            result.push(p);
        }
    }
    return result;
}

function showWeatherNow() {
    if (!_weatherCurrent) return;
    _weatherPeriodIdx = -1;
    var c = _weatherCurrent;
    document.getElementById('weatherTop').innerHTML = renderTop(c);
}

function showWeatherPeriod(globalIdx) {
    if (!_weatherForecast) return;
    _weatherPeriodIdx = globalIdx;
    var dayIdx = Math.floor(globalIdx / 4);
    var periodIdx = globalIdx % 4;
    var day = _weatherForecast[dayIdx];
    if (!day) return;
    var p = day[_weatherPeriods[periodIdx]];
    if (!p) return;
    var label = _weatherPLabelsEn[_weatherPeriods[periodIdx]] + (dayIdx > 0 ? ' (' + day.date + ')' : '');
    document.getElementById('weatherTop').innerHTML = renderTop(p, label);
}

function fetchWeather() {
    fetch('/api/weather')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (data.error) throw new Error(data.error);
            _weatherCurrent = data.current;
            _weatherForecast = data.forecast;

            var c = data.current;
            var html = '<div id="weatherTop" style="padding:4px 0;">' + renderTop(c) + '</div>';

            var displayPeriods = getWeatherPeriodsForDisplay(data.forecast);
            if (displayPeriods.length > 0) {
                html += '<div style="margin-top:4px;border-top:1px solid #ddd;padding-top:4px;">' +
                    '<div style="display:flex;justify-content:space-around;text-align:center;gap:2px;">';
                for (var pi = 0; pi < displayPeriods.length; pi++) {
                    var p = displayPeriods[pi];
                    var picon = weatherIcon(p.desc);
                    html += '<div style="flex:1;min-width:0;padding:2px;cursor:pointer;border-radius:4px;' +
                        (_weatherPeriodIdx === p._globalIdx ? 'background:#e8f4fd;' : '') +
                        '" onclick="showWeatherPeriod(' + p._globalIdx + ')" title="' + p.desc + '">' +
                        '<div style="font-size:0.7em;color:#888;">' + p._label + '</div>' +
                        '<div style="font-size:1.2em;">' + picon + '</div>' +
                        '<div style="font-size:0.85em;font-weight:600;">' + p.temp + '\u00b0</div>' +
                        '</div>';
                }
                html += '</div></div>';
            }

            html += '</div>';
            document.getElementById('weatherContent').innerHTML = html;
            loadDiseaseRisk();
        })
        .catch(function(e) {
            document.getElementById('weatherContent').innerHTML = '<span class="text-muted">Weather unavailable</span>';
        });
}

function riskColor(val, thresh) {
    if (val >= thresh) return '#c0392b';
    if (val >= thresh - 0.5) return '#e67e22';
    return '#27ae60';
}

function riskLabel(val, thresh) {
    if (val >= thresh) return '\u0432\u044b\u0441\u043e\u043a\u0438\u0439';
    if (val >= thresh - 0.5) return '\u0443\u043c\u0435\u0440\u0435\u043d\u043d\u044b\u0439';
    return '\u043d\u0438\u0437\u043a\u0438\u0439';
}

function loadDiseaseRisk() {
    var stage = localStorage.getItem('growthStage') || 'mid';
    document.getElementById('growthStage').value = stage;
    fetch('/api/disease_risk?stage=' + stage)
        .then(function(r) { return r.json(); })
        .then(function(data) {
            var phyto = data.phytophthora;
            var alt = data.alternaria;
            var thresh = data.threshold;
            document.getElementById('diseaseRisk').style.display = 'block';

            var phytoHtml = '<span style="color:#888;">\u0424\u0438\u0442\u043e\u0444\u0442\u043e\u0440\u043e\u0437:</span> ' +
                '<span style="color:' + riskColor(phyto.total, thresh) + ';font-weight:600;">' + phyto.total + ' (' + riskLabel(phyto.total, thresh) + ')</span>';
            document.getElementById('phytoRisk').innerHTML = phytoHtml;

            var altHtml = '<span style="color:#888;">\u0410\u043b\u044c\u0442\u0435\u0440\u043d\u0430\u0440\u0438\u043e\u0437:</span> ' +
                '<span style="color:' + riskColor(alt.total, thresh) + ';font-weight:600;">' + alt.total + ' (' + riskLabel(alt.total, thresh) + ')</span>';
            document.getElementById('altRisk').innerHTML = altHtml;

            document.getElementById('riskRec').innerHTML = data.recommendation || '';
        })
        .catch(function(e) {
            // Keep diseaseRisk hidden if no data
        });
}

// Init weather on page load
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function() { fetchWeather(); });
} else {
    fetchWeather();
}
weatherInterval = setInterval(fetchWeather, 300000);

// -------- Weather history panel (Open-Meteo) --------
var _weatherHistory = null;
var _weatherHistoryLoading = false;
var _weatherHistoryMonth = 0;
var _whMonthsFull = {1:'Январь',2:'Февраль',3:'Март',4:'Апрель',5:'Май',6:'Июнь',7:'Июль',8:'Август',9:'Сентябрь',10:'Октябрь',11:'Ноябрь',12:'Декабрь'};

function toggleWeatherPanel(hdr) {
    var body = document.getElementById('weatherBody');
    var w = document.getElementById('weatherHistoryPanel');
    var m = document.getElementById('map');
    var hidden = !body || body.style.display === 'none';
    if (hidden) {
        if (body) body.style.display = '';
        if (m) m.style.display = 'none';
        if (w) w.style.display = 'block';
        fetchWeatherHistory();
    } else {
        if (body) body.style.display = 'none';
        if (w) w.style.display = 'none';
        if (m) m.style.display = 'block';
        if (map) setTimeout(function() { map.invalidateSize(); }, 60);
    }
    if (hdr) {
        var ic = hdr.querySelector('.collapse-icon');
        if (ic) ic.classList.toggle('collapsed');
    }
}

function fetchWeatherHistory() {
    if (_weatherHistoryLoading) return;
    _weatherHistoryLoading = true;
    fetch('/api/weather/history')
        .then(function(r) {
            if (!r.ok) throw new Error('HTTP ' + r.status);
            return r.json();
        })
        .then(function(data) {
            _weatherHistory = data;
            _weatherHistoryLoading = false;
            renderWeatherHistory();
        })
        .catch(function() {
            _weatherHistoryLoading = false;
            var el = document.getElementById('weatherHistoryContent');
            if (el) el.innerHTML = '<span class="text-muted">История погоды недоступна</span>';
        });
}

function _whNum(v) {
    if (v === null || v === undefined || isNaN(v)) return '\u2014';
    var s = Math.round(v * 10) / 10;
    return s.toString().replace('.', ',');
}

function _whTemp(v) {
    if (v === null || v === undefined || isNaN(v)) return '\u2014';
    var s = Math.round(v * 10) / 10;
    return (s > 0 ? '+' : '') + s.toString().replace('.', ',');
}

function renderWeatherHistory() {
    var el = document.getElementById('weatherHistoryContent');
    if (!el) return;
    var sel = document.getElementById('whMonthFilter');
    if (sel) _weatherHistoryMonth = parseInt(sel.value, 10) || 0;
    var d = _weatherHistory;
    if (!d || !d.summary) {
        el.innerHTML = '<span class="text-muted">Нет данных об истории погоды</span>';
        return;
    }
    var s = d.summary;
    var html = '';
    html += '<div class="wh-summary">';
    html += '<div class="wh-card"><div class="wh-label">Осадки с 1 января</div><div class="wh-value">' + _whNum(s.precip_ytd) + ' мм</div><div class="wh-sub">за ' + d.year + ' год</div></div>';
    html += '<div class="wh-card"><div class="wh-label">Осадки за ' + s.precip_month_label + '</div><div class="wh-value">' + _whNum(s.precip_month) + ' мм</div><div class="wh-sub">текущий месяц</div></div>';
    html += '<div class="wh-card"><div class="wh-label">Ср. t° за год</div><div class="wh-value">' + _whTemp(s.temp_mean_ytd) + ' °C</div><div class="wh-sub">' + d.year + '</div></div>';
    html += '<div class="wh-card"><div class="wh-label">Ср. t° за ' + s.temp_mean_month_label + '</div><div class="wh-value">' + _whTemp(s.temp_mean_month) + ' °C</div><div class="wh-sub">текущий месяц</div></div>';
    html += '</div>';

    var months = d.monthly || [];
    var nowMonth = new Date().getMonth() + 1;
    var maxP = 1;
    for (var i = 0; i < months.length; i++) {
        if (months[i].precip_sum > maxP) maxP = months[i].precip_sum;
    }
    html += '<div style="font-weight:600;margin:8px 0 2px;">Осадки по месяцам, мм</div>';
    html += '<div class="wh-barchart">';
    for (var mi = 0; mi < months.length; mi++) {
        var mo = months[mi];
        if (!mo.month || mo.month > nowMonth) break;
        var h = Math.max(2, Math.round((mo.precip_sum || 0) / maxP * 110));
        html += '<div class="wh-bar-wrap" title="' + mo.month_ru + ': ' + _whNum(mo.precip_sum) + ' мм, ср. ' + _whTemp(mo.temp_mean) + ' °C">';
        html += '<div class="wh-bar-val">' + (mo.precip_sum ? _whNum(mo.precip_sum) : '') + '</div>';
        html += '<div class="wh-bar" style="height:' + h + 'px;"></div>';
        html += '<div class="wh-bar-temp">' + (mo.temp_mean !== null && mo.temp_mean !== undefined ? _whTemp(mo.temp_mean) : '') + '</div>';
        html += '<div class="wh-bar-month">' + mo.month_ru + '</div>';
        html += '</div>';
    }
    html += '</div>';

    var daily = d.daily || [];
    html += '<div style="display:flex;justify-content:space-between;align-items:center;margin:10px 0 4px;">';
    html += '<span style="font-weight:600;">По дням</span>';
    html += '<select id="whMonthFilter" style="font-size:0.85em;" onchange="renderWeatherHistory()">';
    html += '<option value="0">Весь год</option>';
    for (var mm = 1; mm <= nowMonth; mm++) {
        html += '<option value="' + mm + '"' + (mm === _weatherHistoryMonth ? ' selected' : '') + '>' + _whMonthsFull[mm] + '</option>';
    }
    html += '</select></div>';
    html += '<div style="font-weight:600;font-size:0.9em;margin:4px 0 2px;">Осадки за сутки, мм</div>';
    html += '<div id="whPrecipChart"></div>';
    html += '<div style="font-weight:600;font-size:0.9em;margin:10px 0 2px;">Температура за сутки, °C</div>';
    html += '<div style="font-size:0.75em;color:#888;margin:0 0 2px;"><span style="color:#e74c3c;">— макс</span> &middot; <span style="color:#2980b9;">— мин</span> &middot; <span style="color:#27ae60;">— средняя</span></div>';
    html += '<div id="whTempChart"></div>';

    el.innerHTML = html;
    renderDailyCharts();
}

function _whFilteredDaily() {
    var sel = document.getElementById('whMonthFilter');
    var month = sel ? (parseInt(sel.value, 10) || 0) : 0;
    var daily = _weatherHistory ? (_weatherHistory.daily || []) : [];
    var rows = [];
    for (var i = 0; i < daily.length; i++) {
        var r = daily[i];
        if (month === 0 || parseInt(r.date.slice(5, 7), 10) === month) rows.push(r);
    }
    return rows;
}

function renderDailyCharts() {
    drawPrecipChart(_whFilteredDaily());
    drawTempChart(_whFilteredDaily());
}

function drawPrecipChart(rows) {
    var el = document.getElementById('whPrecipChart');
    if (!el) return;
    if (!rows.length) {
        el.innerHTML = '<span class="text-muted">Нет данных</span>';
        return;
    }
    var w = Math.max(el.clientWidth, 400);
    var h = 160, padL = 36, padB = 46, padT = 8;
    var maxP = 1;
    for (var i = 0; i < rows.length; i++) {
        if (rows[i].precip_mm > maxP) maxP = rows[i].precip_mm;
    }
    var innerW = w - padL - 6, innerH = h - padT - padB;
    var n = rows.length;
    var slot = innerW / n;
    var bw = Math.max(1, slot - (n > 100 ? 0 : 0.6));
    var gap = slot - bw;
    var svg = '<svg class="wh-svg" width="' + w + '" height="' + h + '" xmlns="http://www.w3.org/2000/svg" style="display:block;background:#fff;border:1px solid #e9ecef;border-radius:4px;cursor:crosshair;" onmousemove="whChartMove(event,this,\'precip\')" onmouseleave="whChartLeave(this)" onclick="whChartClick(event,this,\'precip\')">';
    for (var gy = 0; gy <= 4; gy++) {
        var yv = maxP * gy / 4;
        var yy = h - padB - innerH * gy / 4;
        svg += '<line x1="' + padL + '" y1="' + yy + '" x2="' + (w - 4) + '" y2="' + yy + '" stroke="#eee" stroke-width="1"/>';
        svg += '<text x="' + (padL - 4) + '" y="' + (yy + 4) + '" text-anchor="end" font-size="9" fill="#888">' + (Math.round(yv * 10) / 10) + '</text>';
    }
    for (var b = 0; b < n; b++) {
        var pv = rows[b].precip_mm || 0;
        var bh = pv / maxP * innerH;
        var bx = padL + b * (bw + gap);
        if (pv > 0) {
            svg += '<rect x="' + bx + '" y="' + (h - padB - bh) + '" width="' + bw + '" height="' + bh + '" fill="#2980b9" opacity="0.85"/>';
        }
    }
    svg += '<line x1="' + padL + '" y1="' + (h - padB) + '" x2="' + (w - 4) + '" y2="' + (h - padB) + '" stroke="#999" stroke-width="1"/>';
    svg += '<text x="' + (padL - 4) + '" y="' + (h - padB + 8) + '" text-anchor="end" font-size="9" fill="#666">мм</text>';
    var ls = Math.max(1, Math.ceil(n / 12));
    for (var li = 0; li < n; li += ls) {
        var lx = padL + li * (bw + gap) + bw / 2;
        var ltxt = rows[li].date.slice(8, 10) + '.' + rows[li].date.slice(5, 7);
        svg += '<text transform="rotate(-45 ' + lx + ' ' + (h - padB + 8) + ')" x="' + lx + '" y="' + (h - padB + 8) + '" text-anchor="end" font-size="8" fill="#888">' + ltxt + '</text>';
    }
    svg += '</svg>';
    el.innerHTML = svg;
    var svgEl = el.querySelector('svg');
    svgEl._whC = {rows: rows, padL: padL, innerW: innerW, n: n, bw: bw, gap: gap, type: 'precip'};
    svgEl._whBars = {};
    var rects = svgEl.querySelectorAll('rect');
    for (var ri = 0; ri < rects.length; ri++) {
        var bi = Math.round((parseFloat(rects[ri].getAttribute('x')) - padL) / (bw + gap));
        svgEl._whBars[bi] = rects[ri];
    }
}

function drawTempChart(rows) {
    var el = document.getElementById('whTempChart');
    if (!el) return;
    if (!rows.length) {
        el.innerHTML = '<span class="text-muted">Нет данных</span>';
        return;
    }
    var w = Math.max(el.clientWidth, 400);
    var h = 190, padL = 36, padB = 46, padT = 8;
    var tmin = 99, tmax = -99;
    for (var i = 0; i < rows.length; i++) {
        if (rows[i].temp_min !== null && rows[i].temp_min !== undefined && rows[i].temp_min < tmin) tmin = rows[i].temp_min;
        if (rows[i].temp_max !== null && rows[i].temp_max !== undefined && rows[i].temp_max > tmax) tmax = rows[i].temp_max;
    }
    if (tmin > 50) tmin = -20;
    if (tmax < -50) tmax = 30;
    var tspan = (tmax - tmin) || 1;
    tmin -= tspan * 0.05;
    tmax += tspan * 0.05;
    var innerW = w - padL - 6, innerH = h - padT - padB;
    var n = rows.length;
    var X = function(i) { return n <= 1 ? padL + innerW / 2 : padL + (innerW * i) / (n - 1); };
    var Y = function(v) { return h - padB - ((v - tmin) / (tmax - tmin)) * innerH; };
    var pts = function(key) {
        var out = [];
        for (var i = 0; i < n; i++) {
            var v = rows[i][key];
            if (v === null || v === undefined) { out.push(null); continue; }
            out.push(X(i).toFixed(1) + ',' + Y(v).toFixed(1));
        }
        return out;
    };
    var svg = '<svg class="wh-svg" width="' + w + '" height="' + h + '" xmlns="http://www.w3.org/2000/svg" style="display:block;background:#fff;border:1px solid #e9ecef;border-radius:4px;cursor:crosshair;" onmousemove="whChartMove(event,this,\'temp\')" onmouseleave="whChartLeave(this)" onclick="whChartClick(event,this,\'temp\')">';
    for (var gy = 0; gy <= 4; gy++) {
        var tv = tmin + (tmax - tmin) * gy / 4;
        var yy = Y(tv);
        svg += '<line x1="' + padL + '" y1="' + yy + '" x2="' + (w - 4) + '" y2="' + yy + '" stroke="#eee" stroke-width="1"/>';
        svg += '<text x="' + (padL - 4) + '" y="' + (yy + 4) + '" text-anchor="end" font-size="9" fill="#888">' + (Math.round(tv * 10) / 10) + '</text>';
    }
    var maxPts = pts('temp_max'), minPts = pts('temp_min');
    var area = '';
    for (var i = 0; i < n; i++) {
        if (maxPts[i] && minPts[i]) area += (i === 0 ? 'M' : ' L') + maxPts[i];
    }
    for (var j = n - 1; j >= 0; j--) {
        if (minPts[j]) area += ' L' + minPts[j];
    }
    if (area) svg += '<path d="' + area + ' Z" fill="#2980b9" opacity="0.18"/>';
    var linePath = function(ptsArr, color, width) {
        var d = '';
        for (var i = 0; i < ptsArr.length; i++) {
            if (!ptsArr[i]) continue;
            d += (d === '' ? 'M' : ' L') + ptsArr[i];
        }
        return d ? '<path d="' + d + '" fill="none" stroke="' + color + '" stroke-width="' + width + '"/>' : '';
    };
    svg += linePath(maxPts, '#e74c3c', 1.4);
    svg += linePath(minPts, '#2980b9', 1.4);
    svg += linePath(pts('temp_mean'), '#27ae60', 1.6);
    svg += '<line x1="' + padL + '" y1="' + (h - padB) + '" x2="' + (w - 4) + '" y2="' + (h - padB) + '" stroke="#999" stroke-width="1"/>';
    svg += '<line class="wh-cross" x1="0" y1="0" x2="0" y2="0" stroke="#999" stroke-width="1" stroke-dasharray="3,2" display="none"/>';
    svg += '<circle class="wh-dot" cx="0" cy="0" r="3.5" fill="#e67e22" stroke="#fff" stroke-width="1" display="none"/>';
    svg += '<text x="' + (padL - 4) + '" y="' + (h - padB + 8) + '" text-anchor="end" font-size="9" fill="#666">°C</text>';
    var ls = Math.max(1, Math.ceil(n / 12));
    for (var li = 0; li < n; li += ls) {
        var lx = X(li);
        var ltxt = rows[li].date.slice(8, 10) + '.' + rows[li].date.slice(5, 7);
        svg += '<text transform="rotate(-45 ' + lx + ' ' + (h - padB + 8) + ')" x="' + lx + '" y="' + (h - padB + 8) + '" text-anchor="end" font-size="8" fill="#888">' + ltxt + '</text>';
    }
    svg += '</svg>';
    el.innerHTML = svg;
    var svgEl = el.querySelector('svg');
    svgEl._whC = {rows: rows, padL: padL, innerW: innerW, n: n, h: h, padB: padB, X: X, Y: Y, type: 'temp'};
    svgEl._whCross = svgEl.querySelector('.wh-cross');
    svgEl._whDot = svgEl.querySelector('.wh-dot');
}

var _whPinned = null;

function _whTooltipShow(html, ev) {
    var tt = document.getElementById('whTooltip');
    if (!tt) return;
    tt.innerHTML = html;
    tt.style.display = 'block';
    var left = ev.clientX + 14, top = ev.clientY + 14;
    var pw = tt.offsetWidth, ph = tt.offsetHeight;
    if (left + pw > window.innerWidth - 8) left = ev.clientX - pw - 10;
    if (top + ph > window.innerHeight - 8) top = ev.clientY - ph - 10;
    tt.style.left = left + 'px';
    tt.style.top = top + 'px';
}

function _whTooltipHide() {
    var tt = document.getElementById('whTooltip');
    if (tt) tt.style.display = 'none';
}

function _whTooltipHtml(svg, type, idx) {
    var c = svg._whC;
    var r = c.rows[idx];
    var h = '<b>' + r.date + '</b>';
    if (type === 'precip') h += '<br>Осадки: ' + _whNum(r.precip_mm) + ' мм';
    else h += '<br>Макс: ' + _whTemp(r.temp_max) + '&deg; &middot; Мин: ' + _whTemp(r.temp_min) + '&deg; &middot; Ср: ' + _whTemp(r.temp_mean) + '&deg;';
    return h;
}

function _whIndexFromEvent(svg, ev) {
    var c = svg._whC;
    if (!c) return -1;
    var rect = svg.getBoundingClientRect();
    var x = ev.clientX - rect.left;
    var i = Math.round((x - c.padL) / c.innerW * (c.n - 1));
    if (i < 0) i = 0;
    if (i > c.n - 1) i = c.n - 1;
    return i;
}

function _whHighlight(svg, type, idx) {
    var c = svg._whC;
    if (type === 'precip') {
        if (svg._whCur !== undefined && svg._whBars[svg._whCur]) {
            svg._whBars[svg._whCur].setAttribute('fill', '#2980b9');
            svg._whBars[svg._whCur].setAttribute('opacity', '0.85');
        }
        svg._whCur = idx;
        if (svg._whBars[idx]) {
            svg._whBars[idx].setAttribute('fill', '#e67e22');
            svg._whBars[idx].setAttribute('opacity', '1');
        }
    } else {
        var x = c.X(idx);
        var y = c.Y(c.rows[idx].temp_mean);
        if (svg._whCross) {
            svg._whCross.setAttribute('x1', x);
            svg._whCross.setAttribute('x2', x);
            svg._whCross.setAttribute('y1', 6);
            svg._whCross.setAttribute('y2', c.h - c.padB);
            svg._whCross.setAttribute('display', '');
        }
        if (svg._whDot) {
            svg._whDot.setAttribute('cx', x);
            svg._whDot.setAttribute('cy', y);
            svg._whDot.setAttribute('display', '');
        }
    }
}

function _whUnhighlight(svg) {
    if (svg._whCur !== undefined && svg._whBars && svg._whBars[svg._whCur]) {
        svg._whBars[svg._whCur].setAttribute('fill', '#2980b9');
        svg._whBars[svg._whCur].setAttribute('opacity', '0.85');
    }
    svg._whCur = undefined;
    if (svg._whCross) svg._whCross.setAttribute('display', 'none');
    if (svg._whDot) svg._whDot.setAttribute('display', 'none');
}

function whChartMove(ev, svg, type) {
    var c = svg._whC;
    if (!c) return;
    var i = _whIndexFromEvent(svg, ev);
    _whHighlight(svg, type, i);
    if (_whPinned && _whPinned.svg === svg) return;
    _whTooltipShow(_whTooltipHtml(svg, type, i), ev);
}

function whChartLeave(svg) {
    if (_whPinned) return;
    _whTooltipHide();
    _whUnhighlight(svg);
}

function whChartClick(ev, svg, type) {
    var c = svg._whC;
    if (!c) return;
    var i = _whIndexFromEvent(svg, ev);
    if (_whPinned && _whPinned.svg === svg) {
        _whPinned = null;
        _whTooltipHide();
        _whUnhighlight(svg);
        return;
    }
    if (_whPinned && _whPinned.svg !== svg) {
        _whUnhighlight(_whPinned.svg);
    }
    _whPinned = {svg: svg, type: type, idx: i};
    _whHighlight(svg, type, i);
    _whTooltipShow(_whTooltipHtml(svg, type, i), ev);
}

document.addEventListener('click', function(ev) {
    if (!_whPinned) return;
    var t = ev.target;
    var inside = t && t.closest && t.closest('.wh-svg');
    if (!inside) {
        var s = _whPinned.svg;
        _whPinned = null;
        _whTooltipHide();
        if (s) _whUnhighlight(s);
    }
});

setInterval(function() {
    fetchWeather();
    var w = document.getElementById('weatherHistoryPanel');
    if (w && w.style.display === 'block') fetchWeatherHistory();
}, 300000);

// Growth stage selector
document.addEventListener('change', function(e) {
    if (e.target && e.target.id === 'growthStage') {
        localStorage.setItem('growthStage', e.target.value);
        loadDiseaseRisk();
    }
});

// -------- Field Files --------
var _fieldFiles = [];
var _fieldFileActive = null;
var _fieldFileMenuTarget = null;

function loadFieldFiles() {
    fetch('/api/fields/list')
        .then(function(r) { return r.json(); })
        .then(function(files) {
            _fieldFiles = files;
            renderFieldFileList();
        })
        .catch(function() {
            document.getElementById('fieldFileList').innerHTML = '<span class="text-muted" style="padding:4px;font-size:0.85em;">Ошибка загрузки</span>';
        });
}

function renderFieldFileList() {
    var el = document.getElementById('fieldFileList');
    if (!el) return;
    if (_fieldFiles.length === 0) {
        el.innerHTML = '<div class="text-muted" style="padding:8px;font-size:0.85em;">Нет файлов полей</div>';
        return;
    }
    var html = '';
    for (var i = 0; i < _fieldFiles.length; i++) {
        var f = _fieldFiles[i];
        var d = new Date(f.updated * 1000);
        var dateStr = d.toLocaleDateString('ru-RU');
        var isActive = fieldPreview && fieldPreview.name === f.name;
        var itemStyle = isActive ? 'background:#e8f4fd;' : '';
        html += '<div class="field-file-item" style="padding:5px 8px;border-bottom:1px solid #eee;font-size:0.9em;cursor:pointer;' + itemStyle + '"';
        html += ' onclick="onFieldFileClick(\'' + escapeJs(f.name) + '\', this)"';
        html += ' ondblclick="event.stopPropagation();onFieldFileDblClick(\'' + escapeJs(f.name) + '\')"';
        html += ' oncontextmenu="event.preventDefault();showFieldFileMenu(\'' + escapeJs(f.name) + '\', this);return false;">';
        html += '<div style="font-weight:500;">' + escapeHtml(f.name) + '</div>';
        html += '<div style="font-size:0.75em;color:#888;">' + dateStr + '</div>';
        html += '</div>';
        if (isActive) {
            html += '<div style="padding:2px 8px 6px 24px;font-size:0.8em;">' + fieldPreviewControlsHtml() + '</div>';
        }
    }
    el.innerHTML = html;
}

var _fieldPreviewDetailLabels = {'tracks': 'Треки', 'headland': 'Гон', 'sections': 'Секции', 'abLine': 'AB линии', 'yield': 'Урожайность'};

function fieldPreviewControlsHtml() {
    var types = ['tracks', 'headland', 'sections', 'abLine'];
    var html = '';
    for (var i = 0; i < types.length; i++) {
        var t = types[i];
        var layer = fieldPreview ? fieldPreview.layers[t] : null;
        var on = layer && map.hasLayer(layer);
        var cb = on ? ' checked' : '';
        var label = _fieldPreviewDetailLabels[t] || t;
        html += '<label style="display:inline-block;margin-right:8px;cursor:pointer;font-weight:400;margin-bottom:2px;">' +
            '<input type="checkbox"' + cb + ' onchange="toggleFieldPreviewDetail(\'' + t + '\')" style="vertical-align:middle;margin-right:2px;"> ' + label + '</label>';
    }
    if (fieldPreview && fieldPreview.layers.yield) {
        var yOn = map.hasLayer(fieldPreview.layers.yield);
        html += '<label style="display:inline-block;margin-right:8px;cursor:pointer;font-weight:400;margin-bottom:2px;">' +
            '<input type="checkbox"' + (yOn ? ' checked' : '') + ' onchange="toggleFieldPreviewDetail(\'yield\')" style="vertical-align:middle;margin-right:2px;"> Урожайность</label>';
        html += '<span style="margin-left:4px;font-size:0.85em;">';
        html += '<label style="font-weight:400;margin-right:4px;cursor:pointer;"><input type="radio" name="yieldColorMode" value="aog"' + (yieldColorMode === 'aog' ? ' checked' : '') + ' onchange="setYieldColorMode(\'aog\')"> AOG</label>';
        html += '<label style="font-weight:400;cursor:pointer;"><input type="radio" name="yieldColorMode" value="gradient"' + (yieldColorMode === 'gradient' ? ' checked' : '') + ' onchange="setYieldColorMode(\'gradient\')"> Градиент</label>';
        html += '</span>';
    }
    return html;
}

function onFieldFileClick(name, btn) {
    if (_fieldFileClickTimer) { clearTimeout(_fieldFileClickTimer); _fieldFileClickTimer = null; }
    _fieldFileClickTimer = setTimeout(function() {
        _fieldFileClickTimer = null;
        showFieldFileMenu(name, btn);
    }, 250);
}

function onFieldFileDblClick(name) {
    if (_fieldFileClickTimer) { clearTimeout(_fieldFileClickTimer); _fieldFileClickTimer = null; }
    showFieldOnMap(name);
}

// -------- Field preview on map (no geozone) --------

function hideAllGeozoneLayers() {
    for (var id in geozoneLayers) {
        map.removeLayer(geozoneLayers[id].polygon);
        map.removeLayer(geozoneLayers[id].label);
        var dl = fieldDetailLayers[id];
        if (dl) {
            for (var k in dl) {
                if (dl[k] && map.hasLayer(dl[k])) {
                    _savedDetailVisibility[id + '_' + k] = true;
                    map.removeLayer(dl[k]);
                }
            }
        }
    }
}

function showAllGeozoneLayers() {
    for (var id in geozoneLayers) {
        if (geozoneLayers[id]._hide) continue;
        map.addLayer(geozoneLayers[id].polygon);
        map.addLayer(geozoneLayers[id].label);
        var dl = fieldDetailLayers[id];
        if (dl) {
            for (var k in dl) {
                if (dl[k] && _savedDetailVisibility[id + '_' + k]) {
                    map.addLayer(dl[k]);
                }
            }
        }
    }
    _savedDetailVisibility = {};
}

function showFieldOnMap(name) {
    var seq = ++_fieldPreviewSeq;
    if (previewABActive) exitPreviewAB();
    fetch('/api/fields/' + encodeURIComponent(name) + '/details')
        .then(function(r) {
            if (!r.ok) throw new Error('HTTP ' + r.status);
            return r.json();
        })
        .then(function(data) {
            if (_fieldPreviewSeq !== seq) return;
            hideAllGeozoneLayers();
            closeFieldPreviewLayers();

            var group = L.layerGroup().addTo(map);
            fieldPreview = {name: data.name, group: group, layers: {}};

            // boundary
            if (data.boundary && data.boundary.length >= 3) {
                var closed = data.boundary.concat([data.boundary[0]]);
                L.polyline(closed, {color: '#e74c3c', weight: 3, opacity: 0.85}).addTo(group);
                try {
                    var bBounds = L.polygon(data.boundary).getBounds();
                    var bCenter = bBounds.getCenter();
                    L.marker(bCenter, {
                        icon: L.divIcon({
                            html: '<div style="background:#e74c3c;color:#fff;padding:2px 8px;border-radius:3px;font-size:0.85em;white-space:nowrap;text-shadow:0 0 2px #000;">' + escapeHtml(data.name) + '</div>',
                            className: '',
                            iconSize: [0, 0],
                            iconAnchor: [0, 0]
                        }),
                        interactive: false
                    }).addTo(group);
                    map.fitBounds(bBounds.pad(0.15));
                } catch(e) {}
            }

            // fast details (tracks / headland / abLine)
            data.details.forEach(function(d) {
                var geo = d.geometry;
                if (!geo) return;
                var style = d.style || {};
                var opts = {
                    color: style.color || '#3498db',
                    weight: style.weight || 2,
                    opacity: style.opacity || 0.8,
                    fillOpacity: style.fillOpacity || 0,
                    dashArray: style.dashArray || null
                };
                var layer = L.geoJSON(geo, {style: function() { return opts; }}).addTo(group);
                fieldPreview.layers[d.type] = layer;
            });

            showFieldPreviewBar(data.name);
            renderFieldFileList();
            loadFieldPreviewSections(name, seq);
            loadFieldPreviewYield(name, seq);
        })
        .catch(function(e) {
            console.error('Field preview error:', e);
            alert('Ошибка загрузки поля: ' + e.message);
        });
}

function closeFieldPreview() {
    _fieldPreviewSeq++;
    if (previewABActive) exitPreviewAB();
    closeFieldPreviewLayers();
    _updateYieldLegend();
    showAllGeozoneLayers();
    hideFieldPreviewBar();
    renderFieldFileList();
}

function closeFieldPreviewLayers() {
    if (fieldPreview) {
        try { map.removeLayer(fieldPreview.group); } catch(e) {}
        fieldPreview = null;
    }
}

// -------- AB line drawing in field preview --------

function onPreviewLineTypeChange() {
    var els = document.getElementsByName('previewLineType');
    for (var i = 0; i < els.length; i++) {
        if (els[i].checked) { previewLineType = els[i].value; }
    }
    resetPreviewABDraft();
    updatePreviewABHint();
}

function updatePreviewABHint() {
    var hint = document.getElementById('previewABHint');
    if (!hint) return;
    if (!previewABActive || !fieldPreview) {
        hint.style.display = 'none';
        hint.textContent = '';
        return;
    }
    hint.style.display = 'inline';
    if (previewABPoints.length === 0) {
        hint.textContent = 'Клик 1: точка A (' + (previewLineType === 'curve' ? 'кривая' : 'прямая') + ')';
    } else if (previewABPoints.length === 1) {
        hint.textContent = 'Клик 2: точка B';
    } else {
        hint.textContent = previewABName ? 'Линия "' + previewABName + '"' : 'Линия готова';
    }
}

function startPreviewAB() {
    if (!fieldPreview) return;
    if (drawMode) toggleDrawMode();
    previewABActive = true;
    resetPreviewABDraft();
    previewABGroup = L.layerGroup().addTo(map);
    map.getContainer().style.cursor = 'crosshair';
    map.on('click', onPreviewABClick);
    document.addEventListener('keydown', onPreviewABKeydown);
    map.doubleClickZoom.disable();
    updatePreviewABHint();
}

function exitPreviewAB() {
    previewABActive = false;
    resetPreviewABDraft();
    map.off('click', onPreviewABClick);
    document.removeEventListener('keydown', onPreviewABKeydown);
    map.doubleClickZoom.enable();
    map.getContainer().style.cursor = '';
}

function resetPreviewABDraft() {
    previewABPoints = [];
    previewABName = '';
    if (previewABGroup) {
        try { map.removeLayer(previewABGroup); } catch(e) {}
        previewABGroup = null;
    }
    var saveBtn = document.getElementById('previewABSaveBtn');
    var cancelBtn = document.getElementById('previewABCancelBtn');
    var btn = document.getElementById('previewABBtn');
    if (saveBtn) saveBtn.style.display = 'none';
    if (cancelBtn) cancelBtn.style.display = 'none';
    if (btn) btn.disabled = false;
}

function onPreviewABKeydown(e) {
    if (e.key === 'Escape' && previewABActive) cancelPreviewAB();
}

function onPreviewABClick(e) {
    if (!previewABActive || !fieldPreview) return;
    if (previewABPoints.length >= 2) return;
    var latlng = e.latlng;
    previewABPoints.push([latlng.lat, latlng.lng]);
    var idx = previewABPoints.length - 1;
    var icon = L.divIcon({
        className: '',
        html: '<div style="width:14px;height:14px;border-radius:50%;border:2px solid #27ae60;background:#fff;text-align:center;line-height:14px;font-size:10px;font-weight:bold;color:#27ae60;">' + (idx === 0 ? 'A' : 'B') + '</div>',
        iconSize: [14, 14],
        iconAnchor: [7, 7]
    });
    L.marker(latlng, {icon: icon, interactive: false}).addTo(previewABGroup);
    if (previewABPoints.length === 2) {
        document.getElementById('previewABSaveBtn').style.display = '';
        document.getElementById('previewABCancelBtn').style.display = '';
        document.getElementById('previewABBtn').disabled = true;
        requestPreviewABLine();
    }
    updatePreviewABHint();
}

function requestPreviewABLine() {
    var ptA = previewABPoints[0];
    var ptB = previewABPoints[1];
    fetch('/api/fields/' + encodeURIComponent(fieldPreview.name) + '/abline', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({type: previewLineType, ptA: ptA, ptB: ptB})
    })
    .then(function(r) { return r.json(); })
    .then(function(res) {
        if (!previewABActive || !previewABGroup) return;
        if (res && res.ok && res.geometry) {
            previewABName = res.name || '';
            L.geoJSON(res.geometry, {style: {color: '#27ae60', weight: 3, opacity: 0.9}}).addTo(previewABGroup);
            updatePreviewABHint();
        } else {
            alert((res && res.error) ? res.error : 'Ошибка построения линии');
            resetPreviewABDraft();
            updatePreviewABHint();
        }
    })
    .catch(function(e) { console.error('AB preview error:', e); });
}

function savePreviewAB() {
    if (!fieldPreview || previewABPoints.length < 2) return;
    var ptA = previewABPoints[0];
    var ptB = previewABPoints[1];
    var name = prompt('Имя линии:', previewABName || (previewLineType === 'curve' ? 'Cu' : 'AB'));
    if (name === null || name === '') return;
    var seq = _fieldPreviewSeq;
    fetch('/api/fields/' + encodeURIComponent(fieldPreview.name) + '/abline', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({type: previewLineType, ptA: ptA, ptB: ptB, name: name})
    })
    .then(function(r) { return r.json(); })
    .then(function(res) {
        if (!res || !res.ok) {
            alert((res && res.error) ? res.error : 'Ошибка сохранения линии');
            return;
        }
        exitPreviewAB();
        refreshFieldPreviewAbLine(seq);
    })
    .catch(function(e) { console.error('AB save error:', e); });
}

function cancelPreviewAB() {
    exitPreviewAB();
    updatePreviewABHint();
}

function refreshFieldPreviewAbLine(seq) {
    if (!fieldPreview) return;
    fetch('/api/fields/' + encodeURIComponent(fieldPreview.name) + '/details')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (_fieldPreviewSeq !== seq || !fieldPreview) return;
            var old = fieldPreview.layers.abLine;
            if (old && map.hasLayer(old)) map.removeLayer(old);
            delete fieldPreview.layers.abLine;
            var d = null;
            for (var i = 0; i < data.details.length; i++) {
                if (data.details[i].type === 'abLine') { d = data.details[i]; break; }
            }
            if (!d || !d.geometry) return;
            var style = d.style || {};
            var opts = {
                color: style.color || '#e74c3c',
                weight: style.weight || 2,
                opacity: style.opacity || 0.8,
                dashArray: style.dashArray || null
            };
            fieldPreview.layers.abLine = L.geoJSON(d.geometry, {style: function() { return opts; }}).addTo(fieldPreview.group);
        })
        .catch(function(e) { console.error('AB refresh error:', e); });
}

function toggleFieldPreviewDetail(type) {
    if (!fieldPreview) return;
    var layer = fieldPreview.layers[type];
    if (!layer) return;
    if (map.hasLayer(layer)) {
        map.removeLayer(layer);
    } else {
        map.addLayer(layer);
    }
    if (type === 'yield') _updateYieldLegend();
    renderFieldFileList();
}

function showFieldPreviewBar(name) {
    var bar = document.getElementById('fieldPreviewBar');
    if (!bar) return;
    document.getElementById('fieldPreviewName').textContent = name;
    document.getElementById('fieldPreviewSectionsStatus').textContent = '';
    var yieldEl = document.getElementById('fieldPreviewYieldStatus');
    if (yieldEl) { yieldEl.textContent = ''; yieldEl.style.color = '#888'; yieldEl.style.display = 'none'; }
    document.getElementById('previewABControls').style.display = '';
    document.getElementById('previewABHint').style.display = 'none';
    document.getElementById('previewABBtn').disabled = false;
    _yieldPolyCache = [];
    bar.style.display = 'block';
}

function hideFieldPreviewBar() {
    var bar = document.getElementById('fieldPreviewBar');
    if (bar) {
        var controls = document.getElementById('previewABControls');
        var hint = document.getElementById('previewABHint');
        if (controls) controls.style.display = 'none';
        if (hint) hint.style.display = 'none';
        bar.style.display = 'none';
    }
}

function showSectionsLoading(show) {
    var el = document.getElementById('fieldPreviewSectionsStatus');
    if (el) el.style.display = show ? 'inline' : 'none';
}

function showSectionsError() {
    var el = document.getElementById('fieldPreviewSectionsStatus');
    if (el) {
        el.textContent = 'Ошибка загрузки секций';
        el.style.color = '#dc3545';
        el.style.display = 'inline';
    }
}

function loadFieldPreviewSections(name, seq) {
    fieldPreviewSectionLoading = true;
    showSectionsLoading(true);
    var statusEl = document.getElementById('fieldPreviewSectionsStatus');
    if (statusEl) {
        statusEl.textContent = 'Загрузка секций...';
        statusEl.style.color = '#888';
    }

    function checkStatus() {
        if (_fieldPreviewSeq !== seq) return;
        fetch('/api/fields/' + encodeURIComponent(name) + '/sections/status')
            .then(function(r) { return r.json(); })
            .then(function(s) {
                if (_fieldPreviewSeq !== seq) return;
                if (s.state === 'ready') {
                    fetchSectionsStream(name, seq);
                } else if (s.state === 'processing') {
                    setTimeout(checkStatus, 1500);
                } else {
                    throw new Error('sections status: ' + (s.error || s.state));
                }
            })
            .catch(function(e) {
                console.error('sections status error:', e);
                if (_fieldPreviewSeq !== seq) return;
                fieldPreviewSectionLoading = false;
                showSectionsLoading(false);
                showSectionsError();
            });
    }
    checkStatus();
}

function fetchSectionsStream(name, seq) {
    fetch('/api/fields/' + encodeURIComponent(name) + '/sections')
        .then(function(res) {
            if (!res.ok) throw new Error('HTTP ' + res.status);
            var reader = res.body.getReader();
            var decoder = new TextDecoder();
            var buf = '';
            var batch = [];
            var first = true;

            function ensureContainer() {
                if (!fieldPreview || fieldPreview.name !== name || _fieldPreviewSeq !== seq) return null;
                if (!fieldPreview.layers.sections) {
                    var grp = L.layerGroup();
                    grp.addTo(fieldPreview.group);
                    fieldPreview.layers.sections = grp;
                }
                return fieldPreview.layers.sections;
            }

            function flush() {
                if (batch.length === 0) return;
                var container = ensureContainer();
                if (container) {
                    for (var i = 0; i < batch.length; i++) {
                        var item = batch[i];
                        var ring = item.ring[0];
                        var ll = [];
                        for (var k = 0; k < ring.length; k++) {
                            ll.push([ring[k][1], ring[k][0]]);
                        }
                        var c = item.color || '#27ae60';
                        var opts = {color: c, weight: 0, fillOpacity: 0.3, fillColor: c};
                        L.polygon([ll], opts).addTo(container);
                    }
                }
                batch = [];
            }

            function finish() {
                fieldPreviewSectionLoading = false;
                showSectionsLoading(false);
                renderFieldFileList();
            }

            function pump() {
                return reader.read().then(function(res2) {
                    if (res2.done) {
                        if (buf.trim()) {
                            try { batch.push(JSON.parse(buf)); } catch(e) {}
                        }
                        flush();
                        finish();
                        return;
                    }
                    buf += decoder.decode(res2.value, {stream: true});
                    var lines = buf.split('\n');
                    buf = lines.pop();
                    for (var i = 0; i < lines.length; i++) {
                        var line = lines[i].trim();
                        if (!line) continue;
                        try {
                            var obj = JSON.parse(line);
                            if (first) {
                                first = false;
                                continue;
                            }
                            batch.push(obj);
                        } catch(e) {}
                    }
                    if (batch.length >= 200) flush();
                    return pump();
                });
            }

            return pump();
        })
        .catch(function(e) {
            console.error('sections stream error:', e);
            if (_fieldPreviewSeq !== seq) return;
            fieldPreviewSectionLoading = false;
            showSectionsLoading(false);
            showSectionsError();
        });
}

// -------- Yield data preview --------

var _yieldPolyCache = [];

function showYieldLoading(show) {
    var el = document.getElementById('fieldPreviewYieldStatus');
    if (el) el.style.display = show ? 'inline' : 'none';
}

function showYieldError() {
    var el = document.getElementById('fieldPreviewYieldStatus');
    if (el) { el.textContent = 'Ошибка загрузки урожайности'; el.style.color = '#dc3545'; el.style.display = 'inline'; }
}

function setYieldColorMode(mode) {
    yieldColorMode = mode;
    _renderYieldCache();
    _updateYieldLegend();
    renderFieldFileList();
}

function _updateYieldLegend() {
    var el = document.getElementById('yieldLegend');
    if (!el) return;
    var visible = fieldPreview && fieldPreview.layers.yield && map.hasLayer(fieldPreview.layers.yield);
    el.style.display = visible ? 'block' : 'none';
}

function _renderYieldCache() {
    if (!fieldPreview || !fieldPreview.layers.yield) return;
    fieldPreview.layers.yield.clearLayers();
    for (var i = 0; i < _yieldPolyCache.length; i++) {
        var item = _yieldPolyCache[i];
        var ring = item.ring[0];
        var ll = [];
        for (var k = 0; k < ring.length; k++) {
            ll.push([ring[k][1], ring[k][0]]);
        }
        var c = yieldColorMode === 'gradient' ? item.color_gradient : item.color_aog;
        c = c || '#27ae60';
        var opts = {color: c, weight: 0, fillOpacity: 0.4, fillColor: c};
        L.polygon([ll], opts).addTo(fieldPreview.layers.yield);
    }
}

function loadFieldPreviewYield(name, seq) {
    fieldPreviewYieldLoading = true;
    showYieldLoading(true);
    var statusEl = document.getElementById('fieldPreviewYieldStatus');
    if (statusEl) {
        statusEl.textContent = 'Загрузка урожайности...';
        statusEl.style.color = '#888';
    }

    function checkStatus() {
        if (_fieldPreviewSeq !== seq) return;
        fetch('/api/fields/' + encodeURIComponent(name) + '/yield/status')
            .then(function(r) { return r.json(); })
            .then(function(s) {
                if (_fieldPreviewSeq !== seq) return;
                if (s.state === 'ready') {
                    fetchYieldStream(name, seq);
                } else if (s.state === 'processing') {
                    setTimeout(checkStatus, 1500);
                } else if (s.state === 'empty') {
                    fieldPreviewYieldLoading = false;
                    showYieldLoading(false);
                    var el = document.getElementById('fieldPreviewYieldStatus');
                    if (el) { el.style.display = 'none'; }
                } else {
                    throw new Error('yield status: ' + (s.error || s.state));
                }
            })
            .catch(function(e) {
                console.error('yield status error:', e);
                if (_fieldPreviewSeq !== seq) return;
                fieldPreviewYieldLoading = false;
                showYieldLoading(false);
                showYieldError();
            });
    }
    checkStatus();
}

function fetchYieldStream(name, seq) {
    _yieldPolyCache = [];
    fetch('/api/fields/' + encodeURIComponent(name) + '/yield')
        .then(function(res) {
            if (!res.ok) throw new Error('HTTP ' + res.status);
            var reader = res.body.getReader();
            var decoder = new TextDecoder();
            var buf = '';
            var first = true;

            function ensureContainer() {
                if (!fieldPreview || fieldPreview.name !== name || _fieldPreviewSeq !== seq) return null;
                if (!fieldPreview.layers.yield) {
                    var grp = L.layerGroup();
                    grp.addTo(fieldPreview.group);
                    fieldPreview.layers.yield = grp;
                }
                return fieldPreview.layers.yield;
            }

            function flush() {
                if (_yieldPolyCache.length === 0) return;
                var container = ensureContainer();
                if (container) {
                    _renderYieldCache();
                }
            }

            function finish() {
                fieldPreviewYieldLoading = false;
                showYieldLoading(false);
                _updateYieldLegend();
                renderFieldFileList();
            }

            function pump() {
                return reader.read().then(function(res2) {
                    if (res2.done) {
                        if (buf.trim()) {
                            try { _yieldPolyCache.push(JSON.parse(buf)); } catch(e) {}
                        }
                        flush();
                        finish();
                        return;
                    }
                    buf += decoder.decode(res2.value, {stream: true});
                    var lines = buf.split('\n');
                    buf = lines.pop();
                    for (var i = 0; i < lines.length; i++) {
                        var line = lines[i].trim();
                        if (!line) continue;
                        try {
                            var obj = JSON.parse(line);
                            if (first) {
                                first = false;
                                continue;
                            }
                            _yieldPolyCache.push(obj);
                        } catch(e) {}
                    }
                    if (_yieldPolyCache.length % 200 === 0 && _yieldPolyCache.length > 0) {
                        flush();
                    }
                    return pump();
                });
            }

            return pump();
        })
        .catch(function(e) {
            console.error('yield stream error:', e);
            if (_fieldPreviewSeq !== seq) return;
            fieldPreviewYieldLoading = false;
            showYieldLoading(false);
            showYieldError();
        });
}

function escapeJs(s) {
    return s.replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/\n/g, '\\n');
}

var _fieldFileMenuVisible = false;

function showFieldFileMenu(name, btn) {
    _fieldFileMenuTarget = name;
    var menu = document.getElementById('fieldFileMenu');
    if (!menu) return;

    var rect = btn.getBoundingClientRect();
    menu.style.position = 'fixed';
    menu.style.left = Math.min(rect.left, window.innerWidth - 220) + 'px';
    menu.style.top = rect.bottom + 'px';
    $(menu).show();

    _fieldFileMenuVisible = true;
    var closer = function(e) {
        if (_fieldFileMenuVisible) {
            _fieldFileMenuVisible = false;
            menu.style.display = 'none';
            document.removeEventListener('click', closer);
        }
    };
    setTimeout(function() { document.addEventListener('click', closer); }, 10);
}

function initFieldFileUI() {
    loadFieldFiles();

    document.getElementById('menuCopyFile').addEventListener('click', function(e) {
        e.preventDefault();
        fieldFilePrompt('Копировать файл', 'Новое имя:', _fieldFileMenuTarget + ' (копия)', function(val) {
            fetch('/api/fields/' + encodeURIComponent(_fieldFileMenuTarget) + '/duplicate', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({new_name: val})
            }).then(function(r) {
                if (r.ok) loadFieldFiles();
            });
        });
    });

    document.getElementById('menuRenameFile').addEventListener('click', function(e) {
        e.preventDefault();
        fieldFilePrompt('Переименовать файл', 'Новое имя:', _fieldFileMenuTarget, function(val) {
            fetch('/api/fields/' + encodeURIComponent(_fieldFileMenuTarget) + '/rename', {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({new_name: val})
            }).then(function(r) {
                if (r.ok) loadFieldFiles();
            });
        });
    });

    document.getElementById('menuShowField').addEventListener('click', function(e) {
        e.preventDefault();
        showFieldOnMap(_fieldFileMenuTarget);
    });

    document.getElementById('menuConvertField').addEventListener('click', function(e) {
        e.preventDefault();
        var name = _fieldFileMenuTarget;
        fieldFileConfirm('Конвертировать в зону', 'Создать геозону из «' + escapeHtml(name) + '»?', function() {
            fetch('/api/fields/' + encodeURIComponent(name) + '/convert', {
                method: 'POST'
            }).then(function(r) {
                if (r.ok) return r.json();
                return r.json().then(function(err) { throw new Error(err.error || 'conversion failed'); });
            }).then(function(zone) {
                console.log('CONVERT success zone:', JSON.stringify({id:zone.id, name:zone.name, ptsCount:zone.points ? zone.points.length : 0, pts0:zone.points ? zone.points[0] : null}));
                closeFieldPreview();
                addGeozoneToMap(zone);
                renderGeozoneList();
                loadGeozoneDetails(zone.id);
                loadFieldFiles();
            }).catch(function(err) {
                alert('Ошибка конвертации: ' + err.message);
            });
        });
    });

    document.getElementById('menuDeleteFile').addEventListener('click', function(e) {
        e.preventDefault();
        fieldFileConfirm('Удалить файл', 'Удалить «' + _fieldFileMenuTarget + '»?', function() {
            fetch('/api/fields/' + encodeURIComponent(_fieldFileMenuTarget), {
                method: 'DELETE'
            }).then(function(r) {
                if (r.ok) loadFieldFiles();
            });
        });
    });

    document.getElementById('menuExportField').addEventListener('click', function(e) {
        e.preventDefault();
        var url = '/api/fields/' + encodeURIComponent(_fieldFileMenuTarget) + '/export';
        window.open(url, '_blank');
    });

    document.getElementById('menuCopyElement').addEventListener('click', function(e) {
        e.preventDefault();
        showElementMenu('copy');
    });

    document.getElementById('menuRenameElement').addEventListener('click', function(e) {
        e.preventDefault();
        showElementMenu('rename');
    });

    document.getElementById('menuDeleteElement').addEventListener('click', function(e) {
        e.preventDefault();
        showElementMenu('delete');
    });
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initFieldFileUI);
} else {
    initFieldFileUI();
}

function fieldFilePrompt(title, label, defaultValue, callback) {
    document.getElementById('fieldFileModalTitle').textContent = title;
    var body = document.getElementById('fieldFileModalBody');
    body.innerHTML = '<div class="form-group"><label>' + label + '</label><input type="text" class="form-control" id="fieldFilePromptInput" value="' + escapeHtml(defaultValue) + '"></div>';
    var ok = document.getElementById('fieldFileModalOk');
    var newOk = ok.cloneNode(true);
    ok.parentNode.replaceChild(newOk, ok);

    var modal = $('#fieldFileModal');
    newOk.addEventListener('click', function() {
        var val = document.getElementById('fieldFilePromptInput').value.trim();
        if (val) {
            modal.modal('hide');
            callback(val);
        }
    });
    modal.modal('show');
    setTimeout(function() {
        var inp = document.getElementById('fieldFilePromptInput');
        if (inp) { inp.focus(); inp.select(); }
    }, 300);
}

function fieldFileConfirm(title, message, callback) {
    document.getElementById('fieldFileModalTitle').textContent = title;
    document.getElementById('fieldFileModalBody').innerHTML = '<p>' + message + '</p>';
    var ok = document.getElementById('fieldFileModalOk');
    var newOk = ok.cloneNode(true);
    ok.parentNode.replaceChild(newOk, ok);

    var modal = $('#fieldFileModal');
    newOk.addEventListener('click', function() {
        modal.modal('hide');
        callback();
    });
    modal.modal('show');
}

function showElementMenu(action) {
    var name = _fieldFileMenuTarget;
    fetch('/api/fields/' + encodeURIComponent(name) + '/export')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            var keys = Object.keys(data);
            var body = document.getElementById('fieldFileModalBody');
            var title = document.getElementById('fieldFileModalTitle');

            if (action === 'delete') {
                title.textContent = 'Удалить элемент из «' + name + '»';
                var html = '<div style="max-height:250px;overflow-y:auto;">';
                for (var i = 0; i < keys.length; i++) {
                    var val = data[keys[i]];
                    var type = Array.isArray(val) ? '[' + val.length + ']' : typeof val === 'object' ? '{...}' : typeof val;
                    html += '<div class="field-element-item" style="padding:4px 6px;cursor:pointer;border-bottom:1px solid #eee;font-size:0.85em;"';
                    html += ' onclick="confirmDeleteElement(\'' + escapeJs(name) + '\',\'' + escapeJs(keys[i]) + '\')">';
                    html += '<span style="color:#dc3545;margin-right:6px;">&times;</span>';
                    html += '<strong>' + escapeHtml(keys[i]) + '</strong> <span style="color:#888;">' + type + '</span>';
                    html += '</div>';
                }
                html += '</div>';
                body.innerHTML = html;
                $('#fieldFileModal').modal('show');
            } else if (action === 'copy') {
                title.textContent = 'Копировать элемент из «' + name + '»';
                var html = '<div style="max-height:200px;overflow-y:auto;margin-bottom:8px;">';
                for (var i = 0; i < keys.length; i++) {
                    html += '<div class="field-element-item" style="padding:4px 6px;cursor:pointer;border-bottom:1px solid #eee;font-size:0.85em;"';
                    html += ' onclick="selectElementForCopy(\'' + escapeJs(name) + '\',\'' + escapeJs(keys[i]) + '\')">';
                    html += '<strong>' + escapeHtml(keys[i]) + '</strong></div>';
                }
                html += '</div>';
                body.innerHTML = html;
                $('#fieldFileModal').modal('show');
            } else if (action === 'rename') {
                title.textContent = 'Переименовать элемент в «' + name + '»';
                var html = '<div style="max-height:200px;overflow-y:auto;margin-bottom:8px;">';
                for (var i = 0; i < keys.length; i++) {
                    html += '<div class="field-element-item" style="padding:4px 6px;cursor:pointer;border-bottom:1px solid #eee;font-size:0.85em;"';
                    html += ' onclick="promptRenameElement(\'' + escapeJs(name) + '\',\'' + escapeJs(keys[i]) + '\')">';
                    html += '<strong>' + escapeHtml(keys[i]) + '</strong></div>';
                }
                html += '</div>';
                body.innerHTML = html;
                $('#fieldFileModal').modal('show');
            }
        });
}

function confirmDeleteElement(name, key) {
    $('#fieldFileModal').modal('hide');
    fieldFileConfirm('Удалить элемент', 'Удалить «' + key + '» из «' + name + '»?', function() {
        fetch('/api/fields/' + encodeURIComponent(name) + '/element/' + encodeURIComponent(key), {
            method: 'DELETE'
        }).then(function(r) {
            if (r.ok) loadFieldFiles();
        });
    });
}

var _elementCopySource = null;

function selectElementForCopy(name, key) {
    _elementCopySource = {field: name, key: key};
    $('#fieldFileModal').modal('hide');

    // Show field list to choose target
    var body = document.getElementById('fieldFileModalBody');
    document.getElementById('fieldFileModalTitle').textContent = 'Куда копировать?';
    var html = '<div style="margin-bottom:6px;">Элемент: <strong>' + escapeHtml(key) + '</strong> из <strong>' + escapeHtml(name) + '</strong></div>';
    html += '<div class="form-group"><label>Новое имя элемента:</label><input type="text" class="form-control" id="elementNewKeyInput" value="' + escapeHtml(key) + '"></div>';
    html += '<label>Выберите поле:</label><div style="max-height:200px;overflow-y:auto;">';
    for (var i = 0; i < _fieldFiles.length; i++) {
        var f = _fieldFiles[i];
        var selected = f.name === name ? ' style="background:#e8f4fd;"' : '';
        html += '<div class="field-file-target" data-name="' + escapeHtml(f.name) + '"' + selected;
        html += ' style="padding:4px 6px;cursor:pointer;border-bottom:1px solid #eee;font-size:0.85em;"';
        html += ' onclick="executeElementCopy(\'' + escapeJs(f.name) + '\')">';
        html += escapeHtml(f.name) + '</div>';
    }
    html += '</div>';
    body.innerHTML = html;
    $('#fieldFileModal').modal('show');
}

function executeElementCopy(targetField) {
    var newKey = document.getElementById('elementNewKeyInput').value.trim();
    if (!newKey) return;
    $('#fieldFileModal').modal('hide');
    fetch('/api/fields/' + encodeURIComponent(_elementCopySource.field) + '/element/' + encodeURIComponent(_elementCopySource.key) + '/copy', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({target: targetField, new_key: newKey})
    }).then(function(r) {
        if (r.ok) loadFieldFiles();
    });
}

function promptRenameElement(name, key) {
    $('#fieldFileModal').modal('hide');
    fieldFilePrompt('Переименовать элемент', 'Новое имя для «' + key + '»:', key, function(newKey) {
        if (newKey === key) return;
        // Rename via copy-delete
        fetch('/api/fields/' + encodeURIComponent(name) + '/element/' + encodeURIComponent(key) + '/copy', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({target: name, new_key: newKey})
        }).then(function(r) {
            if (r.ok) {
                fetch('/api/fields/' + encodeURIComponent(name) + '/element/' + encodeURIComponent(key), {
                    method: 'DELETE'
                }).then(function(r2) {
                    if (r2.ok) loadFieldFiles();
                });
            }
        });
    });
}

// Init field files (handled in initFieldFileUI above)



// === Measurement Tool (ruler) ===
var measureMode = false;
var measurePoints = [];
var measureMarkers = [];
var measureLines = [];
var measureLabels = [];
var measureTotalLabel = null;

var MeasureControl = L.Control.extend({
    options: { position: 'topright' },
    onAdd: function(map) {
        var btn = L.DomUtil.create('button', 'leaflet-bar leaflet-control');
        btn.innerHTML = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 21h18M3 21v-4M7 21v-3M11 21v-5M15 21v-3M19 21v-4"/></svg>';
        btn.title = 'Измерить расстояние/площадь';
        btn.style.cssText = 'width:34px;height:34px;font-size:18px;line-height:34px;text-align:center;cursor:pointer;background:#fff;border:2px solid rgba(0,0,0,.2);border-radius:4px;';
        L.DomEvent.on(btn, 'click', function(e) {
            L.DomEvent.stopPropagation(e);
            toggleMeasureMode();
        });
        return btn;
    }
});

function toggleMeasureMode() {
    measureMode = !measureMode;
    if (measureMode) {
        map.getContainer().style.cursor = 'crosshair';
        map.on('click', onMeasureClick);
        map.on('dblclick', onMeasureDblClick);
    } else {
        map.getContainer().style.cursor = '';
        map.off('click', onMeasureClick);
        map.off('dblclick', onMeasureDblClick);
        clearMeasure();
    }
}

function clearMeasure() {
    measurePoints = [];
    measureMarkers.forEach(function(m) { map.removeLayer(m); });
    measureMarkers = [];
    measureLines.forEach(function(l) { map.removeLayer(l); });
    measureLines = [];
    measureLabels.forEach(function(l) { map.removeLayer(l); });
    measureLabels = [];
    if (measureTotalLabel) { map.removeLayer(measureTotalLabel); measureTotalLabel = null; }
}

function formatDist(m) {
    if (m >= 1000) return (m / 1000).toFixed(2) + ' км';
    return m.toFixed(1) + ' м';
}

function formatArea(sqm) {
    if (sqm >= 10000) return (sqm / 10000).toFixed(2) + ' га';
    return sqm.toFixed(1) + ' м²';
}

function addMeasurePoint(latlng) {
    var idx = measurePoints.length;
    measurePoints.push(latlng);

    var marker = L.circleMarker(latlng, {
        radius: 5, color: '#e74c3c', fillColor: '#e74c3c', fillOpacity: 1, weight: 2
    }).addTo(map);
    measureMarkers.push(marker);

    if (idx > 0) {
        var prev = measurePoints[idx - 1];
        var segDist = prev.distanceTo(latlng);
        var totalDist = 0;
        for (var i = 1; i <= idx; i++) {
            totalDist += measurePoints[i - 1].distanceTo(measurePoints[i]);
        }
        var line = L.polyline([prev, latlng], {
            color: '#e74c3c', weight: 2, dashArray: '5,5'
        }).addTo(map);
        measureLines.push(line);

        var midLat = (prev.lat + latlng.lat) / 2;
        var midLng = (prev.lng + latlng.lng) / 2;
        var label = L.tooltip({
            permanent: true, direction: 'auto', className: 'measure-label',
            offset: [0, -8]
        }).setLatLng([midLat, midLng]).setContent(formatDist(segDist));
        label.addTo(map);
        measureLabels.push(label);
    }

    if (idx >= 2) {
        updateMeasureSummary();
    }
}

function updateMeasureSummary() {
    if (measureTotalLabel) { map.removeLayer(measureTotalLabel); measureTotalLabel = null; }
    var totalDist = 0;
    for (var i = 1; i < measurePoints.length; i++) {
        totalDist += measurePoints[i - 1].distanceTo(measurePoints[i]);
    }
    var html = '<b>Итого:</b> ' + formatDist(totalDist);
    if (measurePoints.length >= 3) {
        var area = computePolygonArea(measurePoints);
        html += '<br><b>Площадь:</b> ' + formatArea(area);
    }
    var last = measurePoints[measurePoints.length - 1];
    measureTotalLabel = L.tooltip({
        permanent: true, direction: 'top', className: 'measure-total',
        offset: [0, -10]
    }).setLatLng(last).setContent(html);
    measureTotalLabel.addTo(map);
}

function computePolygonArea(latlngs) {
    if (latlngs.length < 3) return 0;
    var d2r = Math.PI / 180;
    var R = 6378137;
    var area = 0;
    for (var i = 0; i < latlngs.length; i++) {
        var p1 = latlngs[i];
        var p2 = latlngs[(i + 1) % latlngs.length];
        area += (p2.lng - p1.lng) * d2r * (2 + Math.sin(p1.lat * d2r) + Math.sin(p2.lat * d2r));
    }
    return Math.abs(area * R * R / 2);
}

function onMeasureClick(e) {
    addMeasurePoint(e.latlng);
}

function onMeasureDblClick(e) {
    toggleMeasureMode();
}

$(document).ready(function() { new MeasureControl().addTo(map); });
