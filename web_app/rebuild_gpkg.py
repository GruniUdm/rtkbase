#!/usr/bin/env python3
"""Recreate GPKG using GDAL ogr2ogr for full compatibility."""
import subprocess, json, sqlite3, os, struct, sys
sys.path.insert(0, '/home/basegnss/rtkbase/web_app')
from gpkg_helper import _skip_gpkg_header

DB = '/home/basegnss/rtkbase/data/tracks.gpkg'
TMP = '/tmp/gpkg_rebuild'

os.makedirs(TMP, exist_ok=True)

c = sqlite3.connect(DB)

# ---- Export tracks to GeoJSON ----
# Determine fid column name
tracks_cols = [r[1] for r in c.execute('PRAGMA table_info(tracks)').fetchall()]
fid_col_tracks = 'fid' if 'fid' in tracks_cols else 'id'
print(f'Tracks columns: {tracks_cols}, using fid_col={fid_col_tracks}')

tracks_feats = []
for row in c.execute(f'SELECT {fid_col_tracks},ip,time,quality,satellites,hdop,altitude,geom FROM tracks'):
    # Convert GP-format geometry to GeoJSON coordinates
    blob = row[7]
    wkb_off = _skip_gpkg_header(blob)
    bo = blob[wkb_off]
    endian = '<' if bo == 1 else '>'
    x, y = struct.unpack(endian + 'dd', blob[wkb_off+5:wkb_off+21])  # x=lon, y=lat
    tracks_feats.append({
        'type': 'Feature',
        'geometry': {'type': 'Point', 'coordinates': [x, y]},
        'properties': {
            'id': row[0], 'ip': row[1], 'time': row[2],
            'quality': row[3], 'satellites': row[4],
            'hdop': row[5], 'altitude': row[6]
        }
    })

with open(os.path.join(TMP, 'tracks.json'), 'w') as f:
    json.dump({'type': 'FeatureCollection', 'features': tracks_feats}, f)
print(f'Tracks: {len(tracks_feats)} features')

# ---- Export geozones to GeoJSON ----
geo_cols = [r[1] for r in c.execute('PRAGMA table_info(geozones)').fetchall()]
fid_col_geo = 'fid' if 'fid' in geo_cols else 'id'
print(f'Geozones columns: {geo_cols}, using fid_col={fid_col_geo}')

geo_feats = []
for row in c.execute(f'SELECT {fid_col_geo},zone_id,name,color,crop,planted_date,last_chemical,chemical_name,created,geom FROM geozones'):
    blob = row[9]
    if not blob:
        continue
    wkb_off = _skip_gpkg_header(blob)
    bo = blob[wkb_off]; endian = '<' if bo == 1 else '>'
    num_rings = struct.unpack(endian + 'I', blob[wkb_off+5:wkb_off+9])[0]
    rings = []
    pos = wkb_off + 9
    for r in range(num_rings):
        num_pts = struct.unpack(endian + 'I', blob[pos:pos+4])[0]
        pos += 4
        pts = []
        for i in range(num_pts):
            x, y = struct.unpack(endian + 'dd', blob[pos:pos+16])
            pos += 16
            pts.append([x, y])  # GeoJSON uses [lon, lat]
        rings.append(pts)
    geo_feats.append({
        'type': 'Feature',
        'geometry': {'type': 'Polygon', 'coordinates': rings},
        'properties': {
            'id': row[0], 'zone_id': row[1], 'name': row[2] or '',
            'color': row[3] or '', 'crop': row[4] or '',
            'planted_date': row[5] or '', 'last_chemical': row[6] or '',
            'chemical_name': row[7] or '', 'created': row[8] or 0
        }
    })

with open(os.path.join(TMP, 'geozones.json'), 'w') as f:
    json.dump({'type': 'FeatureCollection', 'features': geo_feats}, f)
print(f'Geozones: {len(geo_feats)} features')

c.close()

# ---- Use ogr2ogr to create proper GPKG ----
NEW_DB = os.path.join(TMP, 'tracks_new.gpkg')
subprocess.run(['rm', '-f', NEW_DB])

# Create tracks layer
r = subprocess.run([
    'ogr2ogr', '-f', 'GPKG', NEW_DB, os.path.join(TMP, 'tracks.json'),
    '-nln', 'tracks', '-nlt', 'POINT',
    '-lco', 'GEOMETRY_NAME=geom', '-lco', 'SPATIAL_INDEX=NO',
    '-s_srs', 'EPSG:4326', '-t_srs', 'EPSG:4326',
    '-preserve_fid'
], capture_output=True, text=True)
if r.returncode != 0:
    print('ogr2ogr tracks ERROR:', r.stderr)
    sys.exit(1)
print('tracks layer created')

# Append geozones
r = subprocess.run([
    'ogr2ogr', '-f', 'GPKG', NEW_DB, os.path.join(TMP, 'geozones.json'),
    '-nln', 'geozones', '-nlt', 'POLYGON',
    '-lco', 'GEOMETRY_NAME=geom', '-lco', 'SPATIAL_INDEX=NO',
    '-s_srs', 'EPSG:4326', '-t_srs', 'EPSG:4326',
    '-preserve_fid', '-append'
], capture_output=True, text=True)
if r.returncode != 0:
    print('ogr2ogr geozones ERROR:', r.stderr)
    sys.exit(1)
print('geozones layer appended')

# ---- Replace old DB ----
subprocess.run(['cp', NEW_DB, DB])
print('Done! New GPKG at', DB)
