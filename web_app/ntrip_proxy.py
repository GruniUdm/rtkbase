#!/usr/bin/env python3
"""NTRIP Proxy - captures GGA from tractors, forwards to str2str
   Accepts any username with configured password, rewrites auth for str2str.
   Writes session CSV logs + GPKG tracks + keeps tractors online."""

import socket, threading, base64, re, sys, os, json, time, csv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tractor_tracker import tractor_tracker
import gpkg_helper

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(BASE_DIR, 'data', 'session_logs')

def _load_settings():
    s = {}
    try:
        with open(os.path.join(BASE_DIR, 'settings.conf')) as f:
            for line in f:
                line = line.strip()
                if '=' in line and not line.startswith('[') and not line.startswith('#'):
                    k, v = line.split('=', 1)
                    s[k.strip()] = v.strip().strip("'\"")
    except:
        pass
    return s

_SETTINGS = _load_settings()
NTRIPC_USER = _SETTINGS.get('local_ntripc_user', 'basegnss')
NTRIPC_PWD = _SETTINGS.get('local_ntripc_pwd', '12345678')
CASTER_PORT = int(_SETTINGS.get('local_ntripc_port', 2102))
CASTER_HOST = '127.0.0.1'
PROXY_PORT = 2101

_GPKG_PATH = os.path.join(BASE_DIR, 'data', 'tracks.gpkg')
try:
    _db = gpkg_helper.connect(_GPKG_PATH)
except:
    _db = None

os.makedirs(LOG_DIR, exist_ok=True)

def log(msg):
    with open('/tmp/ntrip_proxy.log', 'a') as f:
        f.write(f"{msg}\n")
        f.flush()

def parse_gga_full(text):
    m = re.search(
        r'\$[A-Z]{2}GGA,(\d+\.?\d*),(\d+\.\d+),([NS]),(\d+\.\d+),([EW]),'
        r'(\d),(\d+),([\d.]+),([\d.]+),M',
        text
    )
    if not m:
        return None
    time_utc, lat_raw, ns, lon_raw, ew, qual, sats, hdop, alt = m.groups()
    lat = float(lat_raw[:2]) + float(lat_raw[2:]) / 60.0
    if ns == 'S': lat = -lat
    lon = float(lon_raw[:3]) + float(lon_raw[3:]) / 60.0
    if ew == 'W': lon = -lon
    return {
        "lat": round(lat, 7), "lon": round(lon, 7),
        "utc": time_utc, "quality": int(qual),
        "satellites": int(sats), "hdop": float(hdop), "altitude": float(alt)
    }

def parse_gga(text):
    pattern = r'\$[A-Z]{2}GGA,\d+\.?\d*,(\d+\.\d+),([NS]),(\d+\.\d+),([EW])'
    match = re.search(pattern, text)
    if not match: return None
    lat_raw, ns, lon_raw, ew = match.groups()
    lat = float(lat_raw[:2]) + float(lat_raw[2:]) / 60.0
    if ns == 'S': lat = -lat
    lon = float(lon_raw[:3]) + float(lon_raw[3:]) / 60.0
    if ew == 'W': lon = -lon
    return {"lat": round(lat, 7), "lon": round(lon, 7)}

def write_track(username, gga):
    if not _db:
        return
    try:
        gpkg_helper.add_track_point(
            _db, username, int(time.time()),
            gga['lat'], gga['lon'],
            gga.get('quality', 0), gga.get('satellites', 0),
            gga.get('hdop', 0), gga.get('altitude', 0)
        )
    except Exception as e:
        log(f"[{username}] GPKG write error: {e}")

def extract_auth(http_request):
    match = re.search(r'Authorization:\s*Basic\s+(\S+)', http_request, re.IGNORECASE)
    if match:
        try:
            decoded = base64.b64decode(match.group(1)).decode()
            parts = decoded.split(':', 1)
            return parts[0], parts[1] if len(parts) > 1 else ''
        except:
            pass
    m = re.search(r'GET\s+/(\S+)', http_request)
    return (m.group(1), '') if m else ('unknown', '')

def rewrite_auth(data, new_user, new_pass):
    new_b64 = base64.b64encode(f"{new_user}:{new_pass}".encode()).decode()
    request = data.decode('utf-8', errors='ignore')
    request = re.sub(
        r'Authorization:\s*Basic\s+\S+',
        f'Authorization: Basic {new_b64}',
        request, flags=re.IGNORECASE
    )
    return request.encode('utf-8')

def send_401(sock):
    resp = b'HTTP/1.1 401 Unauthorized\r\nWWW-Authenticate: Basic realm="NTRIP"\r\nConnection: close\r\n\r\n'
    try:
        sock.sendall(resp)
    except:
        pass

def recv_caster_response(sock, timeout=10):
    sock.settimeout(timeout)
    data = b''
    try:
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
            crlf = data.find(b'\r\n')
            if crlf >= 0:
                rest = data[crlf+2:]
                if len(rest) >= 4 or b'\r\n\r\n' in data:
                    break
                if len(data) > 20 and len(rest) == 0:
                    try:
                        more = sock.recv(1024)
                        if more:
                            data += more
                    except:
                        pass
                    break
    except socket.timeout:
        pass
    except:
        pass
    return data

def make_session_file(username):
    now = time.localtime()
    fname = f"{username}_{now.tm_mday:02d}.{now.tm_mon:02d}.{now.tm_year}_{now.tm_hour:02d}.{now.tm_min:02d}.csv"
    path = os.path.join(LOG_DIR, fname)
    f = open(path, 'w', newline='')
    w = csv.writer(f)
    w.writerow(['unix_time', 'utc', 'lat', 'lon', 'quality', 'satellites', 'hdop', 'altitude'])
    f.flush()
    log(f"[{username}] Session log: {fname}")
    return f

def handle_gga(username, line_text, session_file):
    gga = parse_gga_full(line_text)
    if not gga:
        gga = parse_gga(line_text)
    if gga:
        tractor_tracker.update_position(username, gga['lat'], gga['lon'])
        write_track(username, gga)
        if session_file:
            w = csv.writer(session_file)
            w.writerow([
                int(time.time()), gga.get('utc', ''),
                gga['lat'], gga['lon'],
                gga.get('quality', 0), gga.get('satellites', 0),
                gga.get('hdop', 0), gga.get('altitude', 0)
            ])
            session_file.flush()

def proxy_client(client_sock, addr):
    username = 'unknown'
    session_file = None
    try:
        data = b''
        while b'\r\n\r\n' not in data:
            chunk = client_sock.recv(4096)
            if not chunk:
                break
            data += chunk
            if len(data) > 65536:
                break
        if not data:
            client_sock.close()
            return

        request = data.decode('utf-8', errors='ignore')
        username, password = extract_auth(request)

        if password != NTRIPC_PWD:
            log(f"[{username}] REJECTED from {addr[0]}:{addr[1]} (wrong password)")
            send_401(client_sock)
            client_sock.close()
            return

        log(f"[{username}] Connect from {addr[0]}:{addr[1]}")
        tractor_tracker.touch(username)
        session_file = make_session_file(username)

        data = rewrite_auth(data, NTRIPC_USER, NTRIPC_PWD)

        h_end = data.find(b'\r\n\r\n') + 4
        body = data[h_end:].strip()
        if body:
            body_text = body.decode('utf-8', errors='ignore')
            if 'GGA' in body_text:
                handle_gga(username, body_text, session_file)

        caster = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        caster.settimeout(15)
        caster.connect((CASTER_HOST, CASTER_PORT))

        if body:
            caster.sendall(data[:h_end])
        else:
            caster.sendall(data)

        resp = recv_caster_response(caster)
        client_sock.sendall(resp)
        log(f"[{username}] Caster resp: {len(resp)}b")

        def forward(src, dst, name, direction):
            buf = b''
            last_touch = 0
            while True:
                try:
                    chunk = src.recv(4096)
                    if not chunk:
                        break
                    dst.sendall(chunk)
                    if direction == 'client->caster':
                        now = time.time()
                        if now - last_touch >= 30:
                            tractor_tracker.touch(name)
                            last_touch = now
                        buf += chunk
                        while b'\n' in buf:
                            line, buf = buf.split(b'\n', 1)
                            line_text = line.decode('utf-8', errors='ignore')
                            if 'GPGGA' in line_text or 'GNGGA' in line_text:
                                handle_gga(name, line_text, session_file)
                except:
                    break

        t1 = threading.Thread(target=forward, args=(client_sock, caster, username, 'client->caster'), daemon=True)
        t2 = threading.Thread(target=forward, args=(caster, client_sock, username, 'caster->client'), daemon=True)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        log(f"[{username}] Disconnected")
    except Exception as e:
        import traceback
        log(f"[{username}] ERROR: {e}")
        log(f"[{username}] Traceback: {traceback.format_exc()}")
    finally:
        if session_file:
            try:
                session_file.close()
            except:
                pass
        try:
            client_sock.close()
        except:
            pass

def start():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(('0.0.0.0', PROXY_PORT))
    srv.listen(50)
    log(f"NTRIP Proxy listening on {PROXY_PORT} -> {CASTER_HOST}:{CASTER_PORT} (user={NTRIPC_USER})")
    while True:
        client, addr = srv.accept()
        threading.Thread(target=proxy_client, args=(client, addr), daemon=True).start()

if __name__ == '__main__':
    start()
