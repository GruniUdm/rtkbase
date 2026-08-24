#!/usr/bin/env python3
"""Passive GGA sniffer - captures GGA from port 2101, writes to GPKG and updates tractor tracker"""
import socket, struct, re, json, os, time, sys
from configparser import ConfigParser

_rtkbase = os.path.join(os.path.dirname(os.path.abspath(__file__)))
_home = os.path.dirname(_rtkbase)
sys.path.insert(0, os.path.join(_rtkbase, 'web_app'))
from tractor_tracker import tractor_tracker
import gpkg_helper

# Read config from settings.conf
_config = ConfigParser(interpolation=None)
_config.read(os.path.join(_home, 'rtkbase', 'settings.conf'))
_TRACK_DIR = _config.get('tracks', 'trackdir', fallback=os.path.join(_home, 'rtkbase', 'data', 'tracks')).strip("'")
os.makedirs(_TRACK_DIR, exist_ok=True)

GPKG_PATH = os.path.join(_TRACK_DIR, '..', 'tracks.gpkg')
_db = gpkg_helper.connect(GPKG_PATH)

def parse_gga(text):
    """Parse full GGA: lat, lon, quality, sats, hdop, altitude"""
    m = re.search(
        r'\$G[NP]GGA,(\d+\.?\d*),(\d+\.\d+),([NS]),(\d+\.\d+),([EW]),'
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
        "lat": round(lat, 7),
        "lon": round(lon, 7),
        "utc": time_utc,
        "quality": int(qual),
        "satellites": int(sats),
        "hdop": float(hdop),
        "altitude": float(alt)
    }

def log(msg):
    with open('/tmp/gga_sniffer.log', 'a') as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
        f.flush()

def get_local_ip():
    """Detect local IP used for NTRIP caster"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return '127.0.0.1'

LOCAL_IP = get_local_ip()
log(f"Local IP: {LOCAL_IP}")

def get_src_ip(packet):
    ip_header = packet[14:34]
    return socket.inet_ntoa(ip_header[12:16])

def get_tcp_payload(packet):
    ip_header = packet[14:34]
    ip_ihl = (ip_header[0] & 0x0F) * 4
    tcp_header = packet[14 + ip_ihl:14 + ip_ihl + 20]
    tcp_data_offset = (tcp_header[12] >> 4) * 4
    payload_start = 14 + ip_ihl + tcp_data_offset
    return packet[payload_start:]

def write_track(ip, gga):
    """Append one GGA record to GPKG"""
    gpkg_helper.add_track_point(
        _db, ip, int(time.time()),
        gga['lat'], gga['lon'],
        gga['quality'], gga['satellites'], gga['hdop'], gga['altitude']
    )

def start():
    srv = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(0x0800))
    log("GGA Sniffer started on port 2101 (with CSV logging)")
    while True:
        packet, _ = srv.recvfrom(65535)
        try:
            src_ip = get_src_ip(packet)
            if src_ip == LOCAL_IP or src_ip == '127.0.0.1' or src_ip.startswith('127.'):
                continue
            ip_header = packet[14:34]
            if ip_header[9] != 6:  # not TCP
                continue
            ip_ihl = (ip_header[0] & 0x0F) * 4
            tcp_header = packet[14 + ip_ihl:14 + ip_ihl + 14]
            src_port = (tcp_header[0] << 8) | tcp_header[1]
            dst_port = (tcp_header[2] << 8) | tcp_header[3]
            if dst_port != 2101:
                continue
            payload = get_tcp_payload(packet)
            if not payload or len(payload) < 10:
                continue
            text = payload.decode('utf-8', errors='ignore')
            if '$GPGGA' in text or '$GNGGA' in text:
                gga = parse_gga(text)
                if gga:
                    log(f"GGA from {src_ip}:{src_port} qual={gga['quality']} sats={gga['satellites']} "
                        f"lat={gga['lat']} lon={gga['lon']}")
                    tractor_tracker.update_position(src_ip, gga['lat'], gga['lon'])
                    # Use username if this IP is mapped to one (via ntrip_proxy)
                    track_key = src_ip
                    try:
                        raw = tractor_tracker._read()
                        for k, v in raw.items():
                            if k == src_ip:
                                continue
                            if v.get('lat') and abs(v['lat'] - gga['lat']) < 0.001 and abs(v['lon'] - gga['lon']) < 0.001:
                                track_key = k
                                break
                    except:
                        pass
                    write_track(track_key, gga)
        except Exception as e:
            log(f"Error: {e}")

if __name__ == '__main__':
    start()
