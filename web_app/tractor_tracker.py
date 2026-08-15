#!/usr/bin/env python3
"""Shared TractorTracker with file-based IPC for cross-process access.
   Uses fcntl file locking for safe concurrent writes."""
import json
import os
import time
import re
import fcntl
import grp

TRACKER_FILE = '/tmp/tractors.json'

class TractorTracker:
    def __init__(self, data_file=TRACKER_FILE):
        self.data_file = data_file
        if not os.path.exists(self.data_file):
            with open(self.data_file, 'w') as f:
                f.write('{}')
        try:
            os.chmod(self.data_file, 0o666)
            st = os.stat(self.data_file)
            if st.st_uid != 0:
                gid = grp.getgrnam('basegnss').gr_gid
                os.chown(self.data_file, 0, gid)
        except (OSError, KeyError):
            pass

    def _read(self):
        try:
            with open(self.data_file, 'r') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                data = json.load(f)
            return data
        except:
            return {}

    def _write(self, data):
        # Write with exclusive flock. Use 'r+' mode + truncate(0) under lock
        # to prevent race where two processes both truncate on open.
        try:
            with open(self.data_file, 'r+') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                f.truncate(0)
                json.dump(data, f)
                f.flush()
        except PermissionError:
            import logging
            import traceback
            logging.getLogger(__name__).warning("PermissionError writing %s\n%s", self.data_file, traceback.format_exc())
    def update_position(self, username, lat, lon, mount=None, seq=None):
        data = self._read()
        data[username] = {
            "lat": lat, "lon": lon,
            "mount": mount, "seq": seq,
            "last_seen": time.time()
        }
        self._write(data)

    def touch(self, username):
        """Update last_seen without changing position data. Throttled: only writes if >30s since last update."""
        data = self._read()
        now = time.time()
        entry = data.get(username)
        if entry and now - entry.get("last_seen", 0) < 30:
            return
        if not entry:
            data[username] = {"last_seen": now}
        else:
            entry["last_seen"] = now
        self._write(data)

    def get_all_tractors(self):
        data = self._read()
        now = time.time()
        stale = [k for k, v in data.items() if now - v.get("last_seen", 0) > 60]
        for k in stale:
            del data[k]
        if stale:
            try:
                self._write(data)
            except OSError:
                import logging
                import traceback
                logging.getLogger(__name__).warning("OSError cleaning stale tractors\n%s", traceback.format_exc())

        # Deduplicate by coordinates: same rounded coords = same tractor
        seen = {}
        for key in list(data.keys()):
            entry = data[key]
            lat = entry.get('lat')
            lon = entry.get('lon')
            if lat is not None and lon is not None:
                ckey = (round(lat, 3), round(lon, 3))
                if ckey in seen:
                    kept = seen[ckey]
                    # Prefer non-IP keys over IP keys
                    is_ip_key = bool(re.match(r'^\d+\.\d+\.\d+\.\d+$', key))
                    is_ip_kept = bool(re.match(r'^\d+\.\d+\.\d+\.\d+$', kept))
                    if is_ip_key and not is_ip_kept:
                        del data[key]
                        continue
                    elif not is_ip_key and is_ip_kept:
                        seen[ckey] = key
                        del data[kept]
                    else:
                        if entry.get('last_seen', 0) > data[kept].get('last_seen', 0):
                            seen[ckey] = key
                            data[kept] = dict(data[key])
                        else:
                            data[key] = dict(data[kept])
                else:
                    seen[ckey] = key
        return data

    @staticmethod
    def parse_gga(gga_string):
        pattern = r'\$[A-Z]{2}GGA,\d+\.?\d*,(\d+\.\d+),([NS]),(\d+\.\d+),([EW])'
        match = re.search(pattern, gga_string)
        if not match:
            return None
        lat_raw, ns, lon_raw, ew = match.groups()
        lat = float(lat_raw[:2]) + float(lat_raw[2:]) / 60.0
        if ns == 'S': lat = -lat
        lon = float(lon_raw[:3]) + float(lon_raw[3:]) / 60.0
        if ew == 'W': lon = -lon
        return {"lat": lat, "lon": lon}


# Global singleton
tractor_tracker = TractorTracker()
