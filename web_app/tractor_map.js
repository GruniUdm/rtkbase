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
var drawMode = false;
var drawPoints = [];
var drawMarkers = [];
var drawPolyline = null;
var editingZoneId = null;
var savedOriginalPoints = null;

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

    map.on("baselayerchange", function(e) {
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
    $('#saveEditZoneBtn').on('click', saveEditZone);
    $('#editPointsBtn').on('click', startEditPoints);
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
});

// -------- Geozone Drawing --------

function toggleDrawMode() {
    if (editingZoneId) { cancelEditPoints(); }
    drawMode = !drawMode;
    var btn = $('#drawBtn');
    var info = $('#drawInfo');
    var saveBtn = $('#saveGeozoneBtn');
    if (drawMode) {
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
    var detailLabels = {'tracks': 'Треки', 'headland': 'Гон', 'sections': 'Секции'};
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
    var layer = geozoneLayers[id];
    if (!layer) return;
    var z = layer.data;
    $('#editZoneId').val(id);
    $('#editZoneName').val(z.name || '');
    $('#editZoneCrop').val(z.crop || '');
    $('#editZonePlanted').val(z.planted_date || '');
    $('#editZoneChemDate').val(z.last_chemical || '');
    $('#editZoneChemName').val(z.chemical_name || '');
    $('#editGeozoneModal').data('zone-id', id);
    $('#editGeozoneModal').modal('show');
}

function startEditPoints() {
    var id = $('#editGeozoneModal').data('zone-id');
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

    $('#editGeozoneModal').modal('hide');
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
    var id = $('#editZoneId').val();
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
        $('#editGeozoneModal').modal('hide');
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
var tractorSessionsCache = {};

function fetchKnownTractors() {
    fetch('/api/tractor_ips').then(function(r){return r.json()}).then(function(ips){
        knownTractorIps = ips || [];
        updateTractors(_lastTractorsData || {});
    }).catch(function(){});
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
    if (knownTractorIps.length === 0) fetchKnownTractors();
    var allUsernames = {};
    for (var u in tractors) allUsernames[u] = true;
    for (var i = 0; i < knownTractorIps.length; i++) allUsernames[knownTractorIps[i]] = true;
    
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
    fetch('/api/tractor_track/' + username)
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
    marker.on('dblclick', function(e) {
        L.DomEvent.stopPropagation(e);
        marker.unbindPopup();
        marker.bindPopup('<i>Loading...</i>').openPopup();
        fetch('/api/tractor_track/' + encodeURIComponent(username) + '/last')
            .then(function(r) { return r.json(); })
            .then(function(pt) {
                if (!pt) {
                    marker.setPopupContent('<i>No track data</i>');
                    setTimeout(function() { marker.closePopup(); }, 3000);
                    return;
                }
                var qualLabels = {0: 'Invalid', 1: 'SPS', 2: 'DGPS', 4: 'RTK Fix', 5: 'RTK Float'};
                var html = '<b>' + escapeHtml(username) + '</b><br>' +
                    'Fix: ' + (qualLabels[pt.quality] || pt.quality) + '<br>' +
                    'Satellites: ' + pt.satellites + '<br>' +
                    'HDOP: ' + (pt.hdop || 0).toFixed(1) + '<br>' +
                    'Altitude: ' + (pt.altitude || 0).toFixed(0) + ' m';
                marker.setPopupContent(html);
                setTimeout(function() { marker.closePopup(); }, 5000);
            })
            .catch(function() {
                marker.setPopupContent('<i>Error</i>');
                setTimeout(function() { marker.closePopup(); }, 3000);
            });
    });
    // Also bind click to test if ANY marker event fires
    marker.on('click', function() {
        marker.unbindPopup();
        marker.bindPopup('<b>' + escapeHtml(username) + '</b><br>click works').openPopup();
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
                "<div style='width:18px;height:100px;display:inline-block;vertical-align:middle;border:1px solid #ccc;background:linear-gradient(to top,#b8360a,#d7611b,#f58b2d,#feb92b,#ffe822,#d5f721,#81e828,#10310d);'></div>" +
                "<div style='display:inline-block;vertical-align:middle;padding-left:4px;'>" +
                "1.0<br>0.8<br>0.6<br>0.5<br>0.4<br>0.3<br>0.2<br>0.0</div>";
            return div;
        };
    }
    ndviLegend.addTo(map);
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
    if (ndviOverlays[zoneId]) {
        map.removeLayer(ndviOverlays[zoneId]);
        delete ndviOverlays[zoneId];
    }
    $("#showNdviBtn").show();
    $("#hideNdviBtn").hide();
}

// Wire up NDVI buttons
$("#editGeozoneModal").on("show.bs.modal", function() {
    var zoneId = $(this).data("zone-id");
    if (zoneId) loadNdviStatus(zoneId);
});

$("#calcNdviBtn").click(function() {
    var zoneId = $("#editZoneId").val() || $("#editGeozoneModal").data("zone-id");
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
    var zoneId = $("#editGeozoneModal").data("zone-id");
    if (zoneId) showNdviOverlay(zoneId);
});

$("#hideNdviBtn").click(function() {
    var zoneId = $("#editGeozoneModal").data("zone-id");
    if (zoneId) hideNdviOverlay(zoneId);
});

// Clean up NDVI overlay when modal is hidden
$("#editGeozoneModal").on("hidden.bs.modal", function() {
    var zoneId = $(this).data("zone-id");
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
        var cellClass = "ndvi-cal-day" + (hasData ? " ndvi-has-data" : "") + (isSelected ? " ndvi-selected" : "");
        var style = "padding:2px 0;border-radius:3px;cursor:" + (hasData ? "pointer" : "default") + ";";
        if (isSelected) { style += "background:#007bff;color:#fff;font-weight:bold;"; }
        else if (hasData) { style += "background:#d4edda;color:#155724;font-weight:bold;"; }
        h += "<div style='" + style + "' data-cal-date='" + dateStr + "' data-has-data='" + hasData + "'>" + day + "</div>";
    }
    h += "</div>";

    // Available dates row (compact)
    var avDates = Object.keys(dateMap).sort().reverse();
    h += "<div style='margin-top:6px;font-size:0.7em;display:flex;flex-wrap:wrap;gap:2px;'>";
    for (var i = 0; i < avDates.length; i++) {
        var d = avDates[i];
        var sel = d === ndviSelectedDate;
        h += "<span style='cursor:pointer;padding:1px 5px;border-radius:2px;" +
            (sel ? "background:#007bff;color:#fff;" : "color:#155724;font-weight:bold;") +
            "' data-cal-date='" + d + "' data-has-data='true'>" + d + "</span>";
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
                "<div style='width:18px;height:100px;display:inline-block;vertical-align:middle;border:1px solid #ccc;background:linear-gradient(to top,#b8360a,#d7611b,#f58b2d,#feb92b,#ffe822,#d5f721,#81e828,#10310d);'></div>" +
                "<div style='display:inline-block;vertical-align:middle;padding-left:4px;'>1.0<br>0.8<br>0.6<br>0.5<br>0.4<br>0.3<br>0.2<br>0.0</div>";
            return div;
        };
    }
    ndviLegend.addTo(map);
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
    
    // Hide edit modal
    $("#editGeozoneModal").modal("hide");
    
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
                    html += '<div class="task-item" style="padding:3px 0;border-bottom:1px solid #eee;cursor:pointer;" onclick="showTaskOnMap(' + t.id + ')">';
                    html += escapeHtml(t.name);
                    html += '<span style="float:right;color:#dc3545;cursor:pointer;font-weight:bold;" onclick="event.stopPropagation();deletePlannerTask(' + t.id + ')">&times;</span>';
                    html += '<br><small class="text-muted">' + t.swath_width + 'm, ' + t.angle + 'deg, ' + t.total_length_m + 'm</small>';
                    html += '</div>';
                });
            }
            $("#plannerSavedTasks").html(html);
        });
}

function showTaskOnMap(taskId) {
    var zoneId = $("#plannerZoneId").val();
    fetch("/api/geozones/" + zoneId + "/tasks/" + taskId + "/path")
        .then(function(r) { return r.json(); })
        .then(function(geojson) {
            if (!geojson || geojson.error) return;
            showPlannerPreview(geojson);
        });
}

function deletePlannerTask(taskId) {
    if (!confirm("Delete this task?")) return;
    fetch("/api/tasks/" + taskId, {method: "DELETE"})
        .then(function() {
            loadPlannerTasks($("#plannerZoneId").val());
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

// "Create Task" button opens sidebar planner
$("#createTaskBtn").click(function() {
    var zoneId = $("#editGeozoneModal").data("zone-id");
    if (!zoneId) return;
    openTaskPlanner(zoneId);
});

// Clean up planner on Edit Geozone close
$("#editGeozoneModal").on("hidden.bs.modal", function() {
    if (!taskPlannerActive) return;
    // Don't close planner when modal hides, it was hidden by openTaskPlanner
});


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
        })
        .catch(function(e) {
            document.getElementById('weatherContent').innerHTML = '<span class="text-muted">Weather unavailable</span>';
        });
}

// Init weather on page load
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function() { fetchWeather(); });
} else {
    fetchWeather();
}
weatherInterval = setInterval(fetchWeather, 300000);

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
        html += '<div class="field-file-item" style="padding:5px 8px;border-bottom:1px solid #eee;font-size:0.9em;cursor:pointer;"';
        html += ' onclick="showFieldFileMenu(\'' + escapeJs(f.name) + '\', this)"';
        html += ' oncontextmenu="event.preventDefault();showFieldFileMenu(\'' + escapeJs(f.name) + '\', this);return false;">';
        html += '<div style="font-weight:500;">' + escapeHtml(f.name) + '</div>';
        html += '<div style="font-size:0.75em;color:#888;">' + dateStr + '</div>';
        html += '</div>';
    }
    el.innerHTML = html;
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

