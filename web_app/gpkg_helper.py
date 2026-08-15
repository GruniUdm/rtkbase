"""Minimal GeoPackage helper for RTKBase tracks and geozones."""
import sqlite3, struct, os, json

WGS84_DEF = 'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563,AUTHORITY["EPSG","7030"]],AUTHORITY["EPSG","6326"]],PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],AUTHORITY["EPSG","4326"]]'
SRS_DDL = 'CREATE TABLE IF NOT EXISTS gpkg_spatial_ref_sys (srs_name TEXT NOT NULL, srs_id INTEGER NOT NULL PRIMARY KEY, organization TEXT NOT NULL, organization_coordsys_id INTEGER NOT NULL, definition TEXT NOT NULL, description TEXT)'

_wal_set = set()

def connect(path):
    new = not os.path.exists(path)
    conn = sqlite3.connect(path, check_same_thread=False)
    if new:
        conn.execute('PRAGMA application_id = 1196444487')
        conn.execute('PRAGMA user_version = 10000')
        conn.execute('PRAGMA journal_mode = WAL').fetchone()
        _init_metadata(conn)
        conn.commit()
    else:
        _ensure_metadata(conn)
        if path not in _wal_set:
            try:
                conn.execute('PRAGMA journal_mode = WAL').fetchone()
            except sqlite3.OperationalError:
                pass
            _wal_set.add(path)
    return conn

def _ensure_metadata(conn, retries=20):
    import time as _t
    for i in range(retries):
        try:
            conn.execute(SRS_DDL)
            cols = [r[1] for r in conn.execute('PRAGMA table_info(gpkg_spatial_ref_sys)').fetchall()]
            if 'srs_name' not in cols:
                conn.execute("ALTER TABLE gpkg_spatial_ref_sys ADD COLUMN srs_name TEXT")
            if 'org_coordsys_id' not in cols and 'organization_coordsys_id' in cols:
                conn.execute("ALTER TABLE gpkg_spatial_ref_sys ADD COLUMN org_coordsys_id INTEGER")
                conn.execute("UPDATE gpkg_spatial_ref_sys SET org_coordsys_id = organization_coordsys_id")
            if 'organization_coordsys_id' not in cols and 'org_coordsys_id' in cols:
                conn.execute("ALTER TABLE gpkg_spatial_ref_sys ADD COLUMN organization_coordsys_id INTEGER")
                conn.execute("UPDATE gpkg_spatial_ref_sys SET organization_coordsys_id = org_coordsys_id")
            conn.execute("INSERT OR REPLACE INTO gpkg_spatial_ref_sys (srs_name,srs_id,organization,organization_coordsys_id,definition,description) VALUES (?,4326,'EPSG',4326,?,?)", ('WGS 84 geodetic', WGS84_DEF, 'WGS 84'))
            conn.execute("INSERT OR IGNORE INTO gpkg_spatial_ref_sys (srs_name,srs_id,organization,organization_coordsys_id,definition,description) VALUES ('Undefined geographic SRS',0,'NONE',0,'undefined','undefined')")
            conn.execute("INSERT OR IGNORE INTO gpkg_spatial_ref_sys (srs_name,srs_id,organization,organization_coordsys_id,definition,description) VALUES ('Undefined cartesian SRS',-1,'NONE',-1,'undefined','undefined')")
            if 'organization_coordsys_id' in cols:
                conn.execute("UPDATE gpkg_spatial_ref_sys SET organization_coordsys_id = org_coordsys_id WHERE organization_coordsys_id IS NULL")
            if 'org_coordsys_id' in cols:
                conn.execute("UPDATE gpkg_spatial_ref_sys SET org_coordsys_id = organization_coordsys_id WHERE org_coordsys_id IS NULL")
            conn.execute('''CREATE TABLE IF NOT EXISTS path_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                zone_id TEXT NOT NULL,
                name TEXT,
                swath_width REAL,
                angle REAL,
                path_geojson TEXT,
                total_length_m REAL,
                num_swaths INTEGER,
                created INTEGER)''')
            conn.execute("INSERT OR IGNORE INTO gpkg_contents VALUES ('path_tasks','attributes','path_tasks','','2024-01-01',NULL,NULL,NULL,NULL,NULL)")
            conn.commit()
            return
        except sqlite3.OperationalError as e:
            if 'locked' in str(e) and i < retries - 1:
                _t.sleep(0.3)
            else:
                raise

def wal_checkpoint(conn):
    # Retry loop: PASSIVE then TRUNCATE, fallback to PASSIVE
    for attempt in range(3):
        r = conn.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()
        if r[0] == 0:
            return r
        conn.execute('PRAGMA wal_checkpoint(PASSIVE)').fetchone()
    return r

def _init_metadata(conn):
    c = conn.cursor()
    c.execute(SRS_DDL)
    c.execute("INSERT OR IGNORE INTO gpkg_spatial_ref_sys (srs_name,srs_id,organization,organization_coordsys_id,definition,description) VALUES ('WGS 84 geodetic',4326,'EPSG',4326,?,'WGS 84')", (WGS84_DEF,))
    c.execute("INSERT OR IGNORE INTO gpkg_spatial_ref_sys (srs_name,srs_id,organization,organization_coordsys_id,definition,description) VALUES ('Undefined geographic SRS',0,'NONE',0,'undefined','undefined')")
    c.execute("INSERT OR IGNORE INTO gpkg_spatial_ref_sys (srs_name,srs_id,organization,organization_coordsys_id,definition,description) VALUES ('Undefined cartesian SRS',-1,'NONE',-1,'undefined','undefined')")
    c.execute('CREATE TABLE IF NOT EXISTS gpkg_contents (table_name TEXT PRIMARY KEY, data_type TEXT, identifier TEXT, description TEXT, last_change TEXT, min_x REAL, min_y REAL, max_x REAL, max_y REAL, srs_id INTEGER)')
    c.execute('CREATE TABLE IF NOT EXISTS gpkg_geometry_columns (table_name TEXT, column_name TEXT, geometry_type_name TEXT, srs_id INTEGER, z TEXT, m TEXT, PRIMARY KEY(table_name, column_name))')
    c.execute('''CREATE TABLE IF NOT EXISTS tracks (
        fid INTEGER PRIMARY KEY AUTOINCREMENT, ip TEXT NOT NULL,
        time INTEGER NOT NULL, quality INTEGER DEFAULT 0,
        satellites INTEGER DEFAULT 0, hdop REAL DEFAULT 0.0,
        altitude REAL DEFAULT 0.0, geom BLOB)''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_tracks_ip ON tracks(ip)')
    c.execute("INSERT OR IGNORE INTO gpkg_contents VALUES ('tracks','features','tracks','','2024-01-01',-180,-90,180,90,4326)")
    c.execute("INSERT OR IGNORE INTO gpkg_geometry_columns VALUES ('tracks','geom','POINT',4326,'','')")
    c.execute('''CREATE TABLE IF NOT EXISTS geozones (
        fid INTEGER PRIMARY KEY AUTOINCREMENT, zone_id TEXT UNIQUE NOT NULL,
        name TEXT, color TEXT, crop TEXT, planted_date TEXT,
        last_chemical TEXT, chemical_name TEXT, created INTEGER,
        geom BLOB)''')
    c.execute("INSERT OR IGNORE INTO gpkg_contents VALUES ('geozones','features','geozones','','2024-01-01',-180,-90,180,90,4326)")
    c.execute("INSERT OR IGNORE INTO gpkg_geometry_columns VALUES ('geozones','geom','POLYGON',4326,'','')")
    c.execute('''CREATE TABLE IF NOT EXISTS path_tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        zone_id TEXT NOT NULL,
        name TEXT,
        swath_width REAL,
        angle REAL,
        path_geojson TEXT,
        total_length_m REAL,
        num_swaths INTEGER,
        created INTEGER)''')
    c.execute("INSERT OR IGNORE INTO gpkg_contents VALUES ('path_tasks','attributes','path_tasks','','2024-01-01',NULL,NULL,NULL,NULL,NULL)")
    conn.commit()

SRS_ID = 4326

def _gdal_geom_prefix(geom_type):
    """GDAL 3.2.2 GP format: GP + flags(0) + geom_type + SRID(LE) = 8 bytes."""
    return b'GP' + struct.pack('BB', 0, geom_type) + struct.pack('<I', SRS_ID)

def gpkg_point(lon, lat):
    return _gdal_geom_prefix(1) + wkb_point(lon, lat)

def gpkg_polygon(points):
    hdr = _gdal_geom_prefix(3)
    min_lon = min(p[1] for p in points)
    min_lat = min(p[0] for p in points)
    max_lon = max(p[1] for p in points)
    max_lat = max(p[0] for p in points)
    env = struct.pack('<dddd', min_lon, min_lat, max_lon, max_lat)
    return hdr + env + wkb_polygon(points)

def _skip_gpkg_header(blob):
    """Return WKB offset. Handles GDAL GP (8B), GPKG std (7B), GDAL-envelope (40B), and GPB0."""
    if blob[:2] != b'GP':
        return 0
    if len(blob) >= 4 and blob[2:4] == b'B0':
        flags = blob[4]
        env_type = (flags >> 1) & 0x07
        env_sizes = [0, 32, 48, 48, 64]
        return 5 + (env_sizes[env_type] if env_type <= 4 else 0)

    flags = blob[2]
    if flags & 1:
        return 40

    def valid_wkb(off):
        if off + 5 > len(blob):
            return False
        if blob[off] not in (0, 1):
            return False
        endian = '<' if blob[off] == 1 else '>'
        wkb_t = struct.unpack(endian + 'I', blob[off+1:off+5])[0]
        return (wkb_t & 0x7FFFFFFF) in (1, 2, 3, 4, 5, 6, 7)

    if valid_wkb(40):
        return 40
    if valid_wkb(7):
        return 7
    if valid_wkb(8):
        return 8
    if valid_wkb(5):
        return 5
    if valid_wkb(4):
        return 4
    return 0

def wkb_point(lon, lat):
    return struct.pack('<BI', 1, 1) + struct.pack('<dd', lon, lat)

def parse_wkb_point(blob):
    off = _skip_gpkg_header(blob)
    bo = struct.unpack('B', blob[off:off+1])[0]
    gtype = struct.unpack('<I', blob[off+1:off+5])[0]
    endian = '<' if bo == 1 else '>'
    x, y = struct.unpack(endian + 'dd', blob[off+5:off+21])
    return [y, x]

def wkb_polygon(points):
    n = len(points)
    buf = struct.pack('<BI', 1, 3)
    buf += struct.pack('<I', 1)
    buf += struct.pack('<I', n + 1)
    for p in points:
        buf += struct.pack('<dd', p[1], p[0])
    buf += struct.pack('<dd', points[0][1], points[0][0])
    return buf

def parse_wkb_polygon(blob):
    off = _skip_gpkg_header(blob)
    endian = '<' if struct.unpack('B', blob[off:off+1])[0] == 1 else '>'
    gtype = struct.unpack('I', blob[off+1:off+5])[0]
    pos = off + 5
    num_rings = struct.unpack(endian + 'I', blob[pos:pos+4])[0]
    pos += 4
    pts = []
    for r in range(num_rings):
        num_pts = struct.unpack(endian + 'I', blob[pos:pos+4])[0]
        pos += 4
        for i in range(num_pts):
            x, y = struct.unpack(endian + 'dd', blob[pos:pos+16])
            pos += 16
            if r == 0 and i < num_pts - 1:
                pts.append([y, x])
    return pts

def add_track_point(conn, ip, t, lat, lon, quality=0, sats=0, hdop=0.0, alt=0.0):
    conn.execute('INSERT INTO tracks (ip,time,quality,satellites,hdop,altitude,geom) VALUES (?,?,?,?,?,?,?)',
                 (ip, t, quality, sats, hdop, alt, gpkg_point(lon, lat)))
    conn.commit()

def add_track_points_batch(conn, ip, rows):
    cur = conn.cursor()
    cur.execute('BEGIN')
    try:
        for row in rows:
            t, lat, lon, quality, sats, hdop, alt = row
            cur.execute('INSERT INTO tracks (ip,time,quality,satellites,hdop,altitude,geom) VALUES (?,?,?,?,?,?,?)',
                        (ip, t, quality, sats, hdop, alt, gpkg_point(lon, lat)))
        conn.commit()
    except Exception:
        conn.rollback()
        raise

def get_track(conn, ip):
    cur = conn.execute('SELECT time,quality,satellites,hdop,altitude,geom FROM tracks WHERE ip=? ORDER BY time', (ip,))
    rows = []
    for row in cur:
        pt = parse_wkb_point(row[5])
        rows.append({'t': row[0], 'lat': pt[0], 'lon': pt[1],
                     'quality': row[1], 'satellites': row[2],
                     'hdop': row[3], 'altitude': row[4]})
    return rows

def get_track_ips(conn):
    cur = conn.execute('SELECT DISTINCT ip FROM tracks ORDER BY ip')
    return [row[0] for row in cur]

def delete_track(conn, ip):
    cur = conn.execute('DELETE FROM tracks WHERE ip=?', (ip,))
    conn.commit()
    return cur.rowcount

def get_last_track_point(conn, ip):
    cur = conn.execute('SELECT time,quality,satellites,hdop,altitude,geom FROM tracks WHERE ip=? ORDER BY time DESC LIMIT 1', (ip,))
    for row in cur:
        pt = parse_wkb_point(row[5])
        return {'t': row[0], 'lat': pt[0], 'lon': pt[1],
                'quality': row[1], 'satellites': row[2],
                'hdop': row[3], 'altitude': row[4]}
    return None

def list_geozones(conn):
    cur = conn.execute('SELECT zone_id,name,color,crop,planted_date,last_chemical,chemical_name,created,geom FROM geozones ORDER BY name')
    zones = []
    for row in cur:
        pts = parse_wkb_polygon(row[8]) if row[8] else []
        zones.append({'id': row[0], 'name': row[1] or '', 'color': row[2] or '#e67e22',
                      'crop': row[3] or '', 'planted_date': row[4] or '',
                      'last_chemical': row[5] or '', 'chemical_name': row[6] or '',
                      'created': row[7] or 0, 'points': pts})
    return zones

def create_geozone(conn, zone_id, name, points, color, now):
    geom = gpkg_polygon(points)
    conn.execute('INSERT INTO geozones (zone_id,name,color,created,geom) VALUES (?,?,?,?,?)',
                 (zone_id, name, color, now, geom))
    conn.commit()

def update_geozone(conn, zone_id, data):
    fields = []
    vals = []
    for key in ('name','color','crop','planted_date','last_chemical','chemical_name'):
        if key in data:
            fields.append(key + '=?')
            vals.append(data[key])
    if 'points' in data:
        fields.append('geom=?')
        vals.append(gpkg_polygon(data['points']))
    if fields:
        vals.append(zone_id)
        conn.execute('UPDATE geozones SET ' + ','.join(fields) + ' WHERE zone_id=?', vals)
        conn.commit()

def delete_geozone(conn, zone_id):
    conn.execute('DELETE FROM geozones WHERE zone_id=?', (zone_id,))
    conn.commit()

def get_geozone_by_id(conn, zone_id):
    cur = conn.execute('SELECT zone_id,name,color,crop,planted_date,last_chemical,chemical_name,created,geom FROM geozones WHERE zone_id=?', (zone_id,))
    row = cur.fetchone()
    if not row:
        return None
    pts = parse_wkb_polygon(row[8]) if row[8] else []
    return {'id': row[0], 'name': row[1] or '', 'color': row[2] or '#e67e22',
            'crop': row[3] or '', 'planted_date': row[4] or '',
            'last_chemical': row[5] or '', 'chemical_name': row[6] or '',
            'created': row[7] or 0, 'points': pts}

### Path tasks ###

def create_path_task(conn, zone_id, name, swath_width, angle, path_geojson, total_length_m, num_swaths):
    now = int(__import__('time').time())
    conn.execute(
        'INSERT INTO path_tasks (zone_id,name,swath_width,angle,path_geojson,total_length_m,num_swaths,created) VALUES (?,?,?,?,?,?,?,?)',
        (zone_id, name, swath_width, angle, path_geojson, total_length_m, num_swaths, now))
    conn.commit()
    return conn.execute('SELECT last_insert_rowid()').fetchone()[0]

def list_path_tasks(conn, zone_id=None):
    if zone_id:
        cur = conn.execute('SELECT id,zone_id,name,swath_width,angle,total_length_m,num_swaths,created FROM path_tasks WHERE zone_id=? ORDER BY created DESC', (zone_id,))
    else:
        cur = conn.execute('SELECT id,zone_id,name,swath_width,angle,total_length_m,num_swaths,created FROM path_tasks ORDER BY created DESC')
    rows = []
    for row in cur:
        rows.append({
            'id': row[0], 'zone_id': row[1], 'name': row[2] or '',
            'swath_width': row[3], 'angle': row[4],
            'total_length_m': row[5], 'num_swaths': row[6], 'created': row[7]
        })
    return rows

def get_path_task(conn, task_id):
    cur = conn.execute('SELECT id,zone_id,name,swath_width,angle,path_geojson,total_length_m,num_swaths,created FROM path_tasks WHERE id=?', (task_id,))
    row = cur.fetchone()
    if not row:
        return None
    return {
        'id': row[0], 'zone_id': row[1], 'name': row[2] or '',
        'swath_width': row[3], 'angle': row[4],
        'path_geojson': row[5], 'total_length_m': row[6],
        'num_swaths': row[7], 'created': row[8]
    }

def delete_path_task(conn, task_id):
    conn.execute('DELETE FROM path_tasks WHERE id=?', (task_id,))
    conn.commit()




### AB Lines ###

def _ensure_field_tracks_table(conn):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS field_tracks ("
        "id TEXT PRIMARY KEY,"
        "field_name TEXT NOT NULL,"
        "name TEXT NOT NULL,"
        "heading REAL DEFAULT 0.0,"
        "point_a_lat REAL NOT NULL,"
        "point_a_lon REAL NOT NULL,"
        "point_b_lat REAL NOT NULL,"
        "point_b_lon REAL NOT NULL,"
        "nudge_distance REAL DEFAULT 0.0,"
        "mode INTEGER DEFAULT 2,"
        "is_visible INTEGER DEFAULT 1,"
        "curve_pts TEXT DEFAULT '[]',"
        "zone_id TEXT DEFAULT '',"
        "created INTEGER DEFAULT (strftime('%s','now'))"
        ")"
    )
    conn.execute("INSERT OR IGNORE INTO gpkg_contents VALUES ('field_tracks','attributes','field_tracks','','2024-01-01',NULL,NULL,NULL,NULL,NULL)")
    conn.commit()

def create_field_track(conn, field_name, name, point_a_lat, point_a_lon, point_b_lat, point_b_lon, heading=0.0, mode=2, nudge_distance=0.0, is_visible=1, curve_pts=None, zone_id=''):
    _ensure_field_tracks_table(conn)
    import uuid, json as _json
    track_id = uuid.uuid4().hex
    if curve_pts is None:
        curve_pts = []
    conn.execute(
        'INSERT INTO field_tracks (id,field_name,name,heading,point_a_lat,point_a_lon,point_b_lat,point_b_lon,nudge_distance,mode,is_visible,curve_pts,zone_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
        (track_id, field_name, name, heading, point_a_lat, point_a_lon, point_b_lat, point_b_lon, nudge_distance, mode, is_visible, _json.dumps(curve_pts), zone_id))
    conn.commit()
    return track_id

def list_field_tracks(conn, field_name=None):
    _ensure_field_tracks_table(conn)
    if field_name:
        cur = conn.execute('SELECT id,field_name,name,heading,point_a_lat,point_a_lon,point_b_lat,point_b_lon,nudge_distance,mode,is_visible,curve_pts,zone_id,created FROM field_tracks WHERE field_name=? ORDER BY created ASC', (field_name,))
    else:
        cur = conn.execute('SELECT id,field_name,name,heading,point_a_lat,point_a_lon,point_b_lat,point_b_lon,nudge_distance,mode,is_visible,curve_pts,zone_id,created FROM field_tracks ORDER BY created ASC')
    import json as _json
    rows = []
    for r in cur:
        try:
            cpts = _json.loads(r[11]) if r[11] else []
        except Exception:
            cpts = []
        rows.append({
            'id': r[0], 'field_name': r[1], 'name': r[2],
            'heading': r[3],
            'point_a': [r[4], r[5]], 'point_b': [r[6], r[7]],
            'nudge_distance': r[8], 'mode': r[9], 'is_visible': bool(r[10]),
            'curve_pts': cpts, 'zone_id': r[12] or '', 'created': r[13]
        })
    return rows

def list_field_tracks_by_zone(conn, zone_id):
    _ensure_field_tracks_table(conn)
    cur = conn.execute('SELECT id,field_name,name,heading,point_a_lat,point_a_lon,point_b_lat,point_b_lon,nudge_distance,mode,is_visible,curve_pts,zone_id,created FROM field_tracks WHERE zone_id=? ORDER BY created ASC', (zone_id,))
    import json as _json
    rows = []
    for r in cur:
        try:
            cpts = _json.loads(r[11]) if r[11] else []
        except Exception:
            cpts = []
        rows.append({
            'id': r[0], 'field_name': r[1], 'name': r[2],
            'heading': r[3],
            'point_a': [r[4], r[5]], 'point_b': [r[6], r[7]],
            'nudge_distance': r[8], 'mode': r[9], 'is_visible': bool(r[10]),
            'curve_pts': cpts, 'zone_id': r[12] or '', 'created': r[13]
        })
    return rows

def get_field_track(conn, track_id):
    _ensure_field_tracks_table(conn)
    cur = conn.execute('SELECT id,field_name,name,heading,point_a_lat,point_a_lon,point_b_lat,point_b_lon,nudge_distance,mode,is_visible,curve_pts,zone_id,created FROM field_tracks WHERE id=?', (track_id,))
    r = cur.fetchone()
    if not r:
        return None
    import json as _json
    try:
        cpts = _json.loads(r[11]) if r[11] else []
    except Exception:
        cpts = []
    return {
        'id': r[0], 'field_name': r[1], 'name': r[2],
        'heading': r[3],
        'point_a': [r[4], r[5]], 'point_b': [r[6], r[7]],
        'nudge_distance': r[8], 'mode': r[9], 'is_visible': bool(r[10]),
        'curve_pts': cpts, 'zone_id': r[12] or '', 'created': r[13]
    }

def update_field_track(conn, track_id, data):
    _ensure_field_tracks_table(conn)
    fields = []
    vals = []
    for key in ('name','heading','nudge_distance','mode','is_visible','field_name','zone_id'):
        if key in data:
            fields.append(key + '=?')
            vals.append(data[key])
    if 'point_a' in data:
        fields.append('point_a_lat=?')
        fields.append('point_a_lon=?')
        vals.extend([data['point_a'][0], data['point_a'][1]])
    if 'point_b' in data:
        fields.append('point_b_lat=?')
        fields.append('point_b_lon=?')
        vals.extend([data['point_b'][0], data['point_b'][1]])
    if 'curve_pts' in data:
        fields.append('curve_pts=?')
        import json as _json
        vals.append(_json.dumps(data['curve_pts']))
    if fields:
        vals.append(track_id)
        conn.execute('UPDATE field_tracks SET ' + ','.join(fields) + ' WHERE id=?', vals)
        conn.commit()

def delete_field_track(conn, track_id):
    _ensure_field_tracks_table(conn)
    conn.execute('DELETE FROM field_tracks WHERE id=?', (track_id,))
    conn.commit()

def delete_field_tracks_by_zone(conn, zone_id):
    _ensure_field_tracks_table(conn)
    conn.execute('DELETE FROM field_tracks WHERE zone_id=?', (zone_id,))
    conn.commit()

### Field Details (converted field files) ###

def _wkb_linestring(coords):
    buf = struct.pack('<BI', 1, 2)
    buf += struct.pack('<I', len(coords))
    for p in coords:
        buf += struct.pack('<dd', p[0], p[1])
    return buf

def _wkb_multilinestring(coords):
    buf = struct.pack('<BI', 1, 5)
    buf += struct.pack('<I', len(coords))
    for ln in coords:
        buf += _wkb_linestring(ln)
    return buf

def _wkb_multipolygon(coords):
    buf = struct.pack('<BI', 1, 6)
    buf += struct.pack('<I', len(coords))
    for poly in coords:
        buf += struct.pack('<BI', 1, 3)
        buf += struct.pack('<I', len(poly))
        for ring in poly:
            buf += struct.pack('<I', len(ring))
            for p in ring:
                buf += struct.pack('<dd', p[0], p[1])
    return buf

def _geojson_to_gpkg(geojson):
    typ = geojson.get('type')
    coords = geojson.get('coordinates', [])
    if typ == 'MultiLineString':
        geom_type = 5
        wkb = _wkb_multilinestring(coords)
    elif typ == 'MultiPolygon':
        geom_type = 6
        wkb = _wkb_multipolygon(coords)
    elif typ == 'LineString':
        geom_type = 2
        wkb = _wkb_linestring(coords)
    else:
        return None
    lons, lats = [], []
    _extract_lonlat(coords, lons, lats)
    if not lons:
        return None
    hdr = b'GP' + struct.pack('BB', 1, geom_type) + struct.pack('<I', SRS_ID)
    env = struct.pack('<dddd', min(lons), max(lons), min(lats), max(lats))
    return hdr + env + wkb

def _extract_lonlat(coords, lons, lats):
    if not coords:
        return
    if isinstance(coords[0], (int, float)):
        if len(coords) >= 2:
            lons.append(coords[0])
            lats.append(coords[1])
    else:
        for c in coords:
            _extract_lonlat(c, lons, lats)

def _ensure_field_details_table(conn):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS field_details ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "zone_id TEXT NOT NULL,"
        "type TEXT NOT NULL,"
        "geometry_geojson TEXT NOT NULL,"
        "style TEXT DEFAULT '{}',"
        "geom BLOB"
        ")"
    )
    cur = conn.execute("PRAGMA table_info(field_details)")
    cols = [r[1] for r in cur.fetchall()]
    if 'geom' not in cols:
        conn.execute("ALTER TABLE field_details ADD COLUMN geom BLOB")
    conn.execute("INSERT OR REPLACE INTO gpkg_contents (table_name,data_type,identifier,description,last_change,srs_id) VALUES ('field_details','features','field_details','','2024-01-01',4326)")
    conn.execute("INSERT OR REPLACE INTO gpkg_geometry_columns (table_name,column_name,geometry_type_name,srs_id,z,m) VALUES ('field_details','geom','GEOMETRY',4326,'','')")
    # Create views for each detail type so QGIS shows them as separate layers
    for vname, vtype, gtype in [('detail_tracks','tracks','MULTILINESTRING'),('detail_headland','headland','MULTILINESTRING'),('detail_sections','sections','MULTIPOLYGON')]:
        conn.execute(f"CREATE VIEW IF NOT EXISTS {vname} AS SELECT id,zone_id,geom FROM field_details WHERE type='{vtype}'")
        conn.execute(f"INSERT OR IGNORE INTO gpkg_contents (table_name,data_type,identifier,last_change,srs_id) VALUES ('{vname}','features','{vname}','2024-01-01',4326)")
        conn.execute(f"INSERT OR IGNORE INTO gpkg_geometry_columns (table_name,column_name,geometry_type_name,srs_id,z,m) VALUES ('{vname}','geom','{gtype}',4326,'','')")
    conn.commit()

def _update_field_details_extent(conn):
    blobs = conn.execute("SELECT type, geom FROM field_details WHERE geom IS NOT NULL").fetchall()
    if not blobs:
        return
    mnx = mny = float('inf')
    mxx = mxy = float('-inf')
    type_extents = {}
    for (typ, b) in blobs:
        if len(b) < 40 or b[:2] != b'GP':
            continue
        if b[2] & 1:
            ex = struct.unpack('<dddd', b[8:40])
            # envelope order: min_x, max_x, min_y, max_y
            mnx = min(mnx, ex[0]); mxx = max(mxx, ex[1])
            mny = min(mny, ex[2]); mxy = max(mxy, ex[3])
            te = type_extents.setdefault(typ, [float('inf'), float('inf'), float('-inf'), float('-inf')])
            te[0] = min(te[0], ex[0]); te[1] = min(te[1], ex[2])
            te[2] = max(te[2], ex[1]); te[3] = max(te[3], ex[3])
    ts = __import__('time').strftime('%Y-%m-%dT%H:%M:%SZ', __import__('time').gmtime())
    if mnx != float('inf'):
        conn.execute(
            "UPDATE gpkg_contents SET min_x=?,min_y=?,max_x=?,max_y=?,last_change=? WHERE table_name='field_details'",
            (mnx, mny, mxx, mxy, ts))
    view_map = {'tracks': 'detail_tracks', 'headland': 'detail_headland', 'sections': 'detail_sections'}
    for typ, te in type_extents.items():
        vname = view_map.get(typ)
        if vname:
            conn.execute(
                "UPDATE gpkg_contents SET min_x=?,min_y=?,max_x=?,max_y=?,last_change=? WHERE table_name=?",
                (te[0], te[1], te[2], te[3], ts, vname))

def create_field_detail(conn, zone_id, type_name, geometry, style=None):
    _ensure_field_details_table(conn)
    if style is None:
        style = {}
    blob = _geojson_to_gpkg(geometry) if isinstance(geometry, dict) else None
    conn.execute(
        'INSERT INTO field_details (zone_id,type,geometry_geojson,style,geom) VALUES (?,?,?,?,?)',
        (zone_id, type_name,
         json.dumps(geometry) if isinstance(geometry, dict) else geometry,
         json.dumps(style) if isinstance(style, dict) else style,
         blob)
    )
    _update_field_details_extent(conn)
    conn.commit()

def get_field_details(conn, zone_id):
    _ensure_field_details_table(conn)
    cur = conn.execute('SELECT id,type,geometry_geojson,style FROM field_details WHERE zone_id=? ORDER BY id', (zone_id,))
    rows = []
    for r in cur:
        rows.append({
            'id': r[0], 'type': r[1],
            'geometry_geojson': json.loads(r[2]) if r[2] else None,
            'style': json.loads(r[3]) if r[3] else {}
        })
    return rows

def delete_field_details_by_zone(conn, zone_id):
    _ensure_field_details_table(conn)
    conn.execute('DELETE FROM field_details WHERE zone_id=?', (zone_id,))
    conn.commit()
