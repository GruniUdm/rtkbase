#!/usr/bin/env python3
"""2G GPS tracker bridge for RTKBase.

Listens for SinoTrack ST-907 (protocol H02) on TCP 5013, parses GPS
fixes, and forwards them as NTRIP client to the local ntrip_proxy
(127.0.0.1:2101) pretending to be a tractor named by the tracker IMEI.
The proxy records tracks/session logs and keeps the tractor online.

H02 packet: *HQ,IMEI,V6,HHMMSS,A|V,lat,N/S,lon,E/W,speed,course,DDMMYY,status#
"""

import asyncio
import base64
import os
import re
import sys
import time

BRIDGE_PORT = 5013
PROXY_HOST = '127.0.0.1'
PROXY_PORT = 2101
GGA_INTERVAL = 30
MAX_BUFFER = 65536


def load_settings():
    s = {}
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        with open(os.path.join(base, 'settings.conf')) as f:
            for line in f:
                line = line.strip()
                if '=' in line and not line.startswith('[') and not line.startswith('#'):
                    k, v = line.split('=', 1)
                    s[k.strip()] = v.strip().strip("'\"")
    except Exception:
        pass
    return s


_SETTINGS = load_settings()
MNT_NAME = _SETTINGS.get('local_ntripc_mnt_name', 'biya')
NTRIPC_PWD = _SETTINGS.get('local_ntripc_pwd', '12345678')


def log(msg):
    print(msg, flush=True)


def parse_h02(line):
    """Parse an H02 packet.

    Returns a dict with 'kind' in {'fix','invalid','heartbeat'} or None
    if the line is not H02. A 'fix' has valid coordinates, an 'invalid'
    is a position without GPS fix (V flag / zero coords), a 'heartbeat'
    is a status packet (e.g. NBR, battery/LBS report).
    """
    line = line.strip()
    if not line.startswith('*HQ,'):
        return None
    body = line[1:].rstrip('#').strip()
    parts = body.split(',')
    if len(parts) < 5 or parts[0] != 'HQ':
        return None
    imei = parts[1].strip()
    typ = parts[2].strip().upper()
    utc = parts[3].strip() if len(parts) > 3 else ''
    if typ in ('NBR', 'GEO', 'D0'):
        return {'kind': 'heartbeat', 'imei': imei, 'utc': utc,
                'lat': None, 'lon': None, 'valid': False}
    if not typ.startswith('V'):
        return {'kind': 'heartbeat', 'imei': imei, 'utc': utc,
                'lat': None, 'lon': None, 'valid': False}
    valid = parts[4].strip().upper() == 'A' if len(parts) > 4 else False
    lat_raw = parts[5].strip() if len(parts) > 5 else ''
    ns = parts[6].strip().upper() if len(parts) > 6 else ''
    lon_raw = parts[7].strip() if len(parts) > 7 else ''
    ew = parts[8].strip().upper() if len(parts) > 8 else ''
    try:
        if len(lat_raw) < 5 or len(lon_raw) < 6:
            return {'kind': 'heartbeat', 'imei': imei, 'utc': utc,
                    'lat': None, 'lon': None, 'valid': False}
        lat_deg = float(lat_raw[:2])
        lat_min = float(lat_raw[2:])
        lon_deg = float(lon_raw[:3])
        lon_min = float(lon_raw[3:])
    except ValueError:
        return None
    if lat_deg == 0 and lat_min == 0:
        return {'kind': 'invalid', 'imei': imei, 'utc': utc,
                'lat': 0.0, 'lon': 0.0, 'valid': False}
    if lon_deg == 0 and lon_min == 0:
        return {'kind': 'invalid', 'imei': imei, 'utc': utc,
                'lat': 0.0, 'lon': 0.0, 'valid': False}
    lat = lat_deg + lat_min / 60.0
    lon = lon_deg + lon_min / 60.0
    if ns == 'S':
        lat = -lat
    if ew == 'W':
        lon = -lon
    if not valid:
        return {'kind': 'invalid', 'imei': imei, 'utc': utc,
                'lat': round(lat, 7), 'lon': round(lon, 7), 'valid': False}
    return {'kind': 'fix', 'imei': imei, 'utc': utc,
            'lat': round(lat, 7), 'lon': round(lon, 7), 'valid': True}


def build_gga(fix):
    """Build a $GPGGA sentence matching what ntrip_proxy.parse_gga_full expects."""
    lat_abs = abs(fix['lat'])
    lon_abs = abs(fix['lon'])
    lat_deg = int(lat_abs)
    lat_min = (lat_abs - lat_deg) * 60.0
    lon_deg = int(lon_abs)
    lon_min = (lon_abs - lon_deg) * 60.0
    ns = 'N' if fix['lat'] >= 0 else 'S'
    ew = 'E' if fix['lon'] >= 0 else 'W'
    utc = fix.get('utc') or '000000'
    if not re.fullmatch(r'\d{6}(?:\.\d+)?', utc):
        utc = '000000'
    body = ','.join([
        'GPGGA',
        utc,
        '%02d%07.4f' % (lat_deg, lat_min),
        ns,
        '%03d%07.4f' % (lon_deg, lon_min),
        ew,
        '1' if fix['valid'] else '0',
        '0',
        '0.0',
        '0.0',
        'M',
        '0.0',
        '0000',
    ])
    cksum = 0
    for ch in body:
        cksum ^= ord(ch)
    return '$' + body + '*' + '%02X' % cksum + '\r\n'


class TrackerSession:
    def __init__(self, reader, writer, addr):
        self.reader = reader
        self.writer = writer
        self.addr = addr
        self.imei = None
        self.proxy_reader = None
        self.proxy_writer = None
        self.proxy_task = None
        self.last_gga = 0
        self.bytes_received = 0
        self.connected_at = time.time()

    async def connect_proxy(self):
        try:
            r, w = await asyncio.wait_for(
                asyncio.open_connection(PROXY_HOST, PROXY_PORT), timeout=10)
            auth = base64.b64encode(
                ('%s:%s' % (self.imei, NTRIPC_PWD)).encode()).decode()
            req = ('GET /%s HTTP/1.1\r\n'
                   'Host: %s:%d\r\n'
                   'User-Agent: NTRIP RTKBase_TrackerBridge/1.0\r\n'
                   'Authorization: Basic %s\r\n'
                   '\r\n' % (MNT_NAME, PROXY_HOST, PROXY_PORT, auth))
            w.write(req.encode())
            await w.drain()
            # Consume proxy response headers.
            buf = b''
            while b'\r\n\r\n' not in buf:
                chunk = await asyncio.wait_for(r.read(4096), timeout=10)
                if not chunk:
                    break
                buf += chunk
                if len(buf) > MAX_BUFFER:
                    break
            self.proxy_reader = r
            self.proxy_writer = w
            log('[%s] NTRIP proxy connected (%db headers received)' % (self.imei, len(buf)))
        except Exception as e:
            log('[%s] NTRIP proxy connect failed: %s' % (self.imei, e))
            self.proxy_reader = None
            self.proxy_writer = None

    async def proxy_loop(self):
        """Drain proxy (RTCM) bytes so the socket does not fill up."""
        while self.proxy_reader:
            try:
                chunk = await self.proxy_reader.read(4096)
                if not chunk:
                    break
            except Exception:
                break
        await self.close_proxy()

    async def close_proxy(self):
        if self.proxy_task:
            try:
                self.proxy_task.cancel()
            except Exception:
                pass
            self.proxy_task = None
        if self.proxy_writer:
            try:
                self.proxy_writer.close()
            except Exception:
                pass
        self.proxy_writer = None
        self.proxy_reader = None

    async def send_gga_if_due(self, fix):
        now = time.time()
        if now - self.last_gga < GGA_INTERVAL:
            return
        self.last_gga = now
        if not self.proxy_writer:
            await self.connect_proxy()
            if self.proxy_writer:
                self.proxy_task = asyncio.ensure_future(self.proxy_loop())
        if self.proxy_writer:
            try:
                self.proxy_writer.write(build_gga(fix).encode())
                await self.proxy_writer.drain()
                log('[%s] GGA sent lat=%.7f lon=%.7f' % (self.imei, fix['lat'], fix['lon']))
            except Exception as e:
                log('[%s] GGA send failed: %s' % (self.imei, e))
                await self.close_proxy()

    async def run(self):
        buf = b''
        self._last_fix_log = 0
        self._hb_logged = False
        try:
            while True:
                chunk = await self.reader.read(4096)
                if not chunk:
                    break
                self.bytes_received += len(chunk)
                buf += chunk
                if len(buf) > MAX_BUFFER:
                    buf = buf[-4096:]
                while b'#' in buf:
                    idx = buf.index(b'#')
                    raw = buf[:idx + 1]
                    buf = buf[idx + 1:]
                    line = raw.decode('utf-8', errors='ignore')
                    if not line.startswith('*HQ,'):
                        hq = line.find('*HQ,')
                        if hq >= 0:
                            line = line[hq:]
                        else:
                            log('[detect] non-H02 binary packet: %s' % repr(raw[:40]))
                            continue
                    pkt = parse_h02(line)
                    if not pkt:
                        if raw[:1] == b'(':
                            log('[detect] possible SinoTrack OEM (non-H02), expected on port 8090')
                        continue
                    self.imei = pkt['imei']
                    if pkt['kind'] == 'heartbeat':
                        if not self._hb_logged:
                            self._hb_logged = True
                            log('[%s] heartbeat/status packet (no position)' % self.imei)
                        continue
                    if pkt['kind'] == 'invalid':
                        now = time.time()
                        if now - self._last_fix_log > 60:
                            self._last_fix_log = now
                            log('[%s] position invalid (no GPS fix): lat=%s lon=%s'
                                % (self.imei, pkt['lat'], pkt['lon']))
                        continue
                    if self.imei and not self._first_fix_logged:
                        self._first_fix_logged = True
                        log('[%s] first GPS fix from %s: lat=%.7f lon=%.7f'
                            % (self.imei, self.addr, pkt['lat'], pkt['lon']))
                    if not self.proxy_writer and not self._proxy_conn:
                        self._proxy_conn = True
                        log('[%s] connecting to NTRIP proxy %s:%d (mount %s)'
                            % (self.imei, PROXY_HOST, PROXY_PORT, MNT_NAME))
                        await self.connect_proxy()
                        if self.proxy_writer:
                            self.proxy_task = asyncio.ensure_future(self.proxy_loop())
                    await self.send_gga_if_due(pkt)
        except Exception as e:
            log('[%s] connection error: %s' % (self.imei or '?', e))
        finally:
            log('[%s] client %s disconnected (%d bytes)' %
                (self.imei or '?', self.addr, self.bytes_received))
            await self.close_proxy()
            try:
                self.writer.close()
            except Exception:
                pass


async def start_server():
    server = await asyncio.start_server(
        lambda r, w: TrackerSession(r, w, w.get_extra_info('peername')).run(),
        '0.0.0.0', BRIDGE_PORT)
    log('Tracker bridge listening on 0.0.0.0:%d -> %s:%d (%s:%s)'
        % (BRIDGE_PORT, PROXY_HOST, PROXY_PORT, 'IMEI', NTRIPC_PWD))
    async with server:
        await server.serve_forever()


if __name__ == '__main__':
    try:
        asyncio.run(start_server())
    except KeyboardInterrupt:
        sys.exit(0)