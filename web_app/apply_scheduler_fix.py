import re

with open('/home/basegnss/rtkbase/web_app/server.py', 'r') as f:
    c = f.read()

old = '''        def ndvi_scheduler():
            import time as _time
            import datetime as _dt
            import sqlite3 as _sqlite3
            GPKG_PATH = '/home/basegnss/rtkbase/data/tracks.gpkg'
            for _ in range(3):
                try:
                    from ndvi_helper import calc_ndvi_for_zone
                    zones = gpkg_helper.list_geozones(_db)
                    if not zones:
                        _time.sleep(61)
                        continue
                    today_str = _dt.datetime.now().strftime('%Y-%m-%d')
                    conn = _sqlite3.connect(GPKG_PATH)
                    done_today = set()
                    try:
                        for r in conn.execute('SELECT DISTINCT zone_id FROM ndvi_scenes_v2 WHERE scene_date=?', (today_str,)):
                            done_today.add(r[0])
                    except:
                        pass
                    conn.close()
                    for z in zones:
                        zid = z['id']
                        if zid in done_today:
                            continue
                        try:
                            calc_ndvi_for_zone(zid)
                        except Exception as e:
                            print(f"NDVI calc for zone {zid}: {e}")
                except Exception as e:
                    print(f"NDVI scheduler error: {e}")
                _time.sleep(61)
            _time.sleep(30)
        ndvi_thread = Thread(target=ndvi_scheduler, daemon=True)
        ndvi_thread.start()'''

new = '''        def ndvi_scheduler():
            import time as _time
            import datetime as _dt
            import sqlite3 as _sqlite3
            GPKG_PATH = '/home/basegnss/rtkbase/data/tracks.gpkg'

            def _run_all():
                from ndvi_helper import calc_ndvi_for_zone
                zones = gpkg_helper.list_geozones(_db)
                if not zones:
                    return
                today_str = _dt.datetime.now().strftime('%Y-%m-%d')
                conn = _sqlite3.connect(GPKG_PATH)
                done_today = set()
                try:
                    for r in conn.execute('SELECT DISTINCT zone_id FROM ndvi_scenes_v2 WHERE scene_date=?', (today_str,)):
                        done_today.add(r[0])
                except:
                    pass
                conn.close()
                for z in zones:
                    zid = z['id']
                    if zid in done_today:
                        continue
                    try:
                        calc_ndvi_for_zone(zid)
                    except Exception as e:
                        print(f"NDVI calc for zone {zid}: {e}")

            # First pass: run immediately to catch up
            try:
                _run_all()
            except Exception as e:
                print(f"NDVI scheduler first pass error: {e}")

            # Then run daily at 3:00 AM
            while True:
                now = _dt.datetime.now()
                next_run = now.replace(hour=3, minute=0, second=0, microsecond=0)
                if next_run <= now:
                    next_run += _dt.timedelta(days=1)
                _time.sleep((next_run - now).total_seconds())
                try:
                    _run_all()
                except Exception as e:
                    print(f"NDVI scheduler error: {e}")

        ndvi_thread = Thread(target=ndvi_scheduler, daemon=True)
        ndvi_thread.start()'''

if old in c:
    c = c.replace(old, new)
    with open('/home/basegnss/rtkbase/web_app/server.py', 'w') as f:
        f.write(c)
    print('Scheduler updated successfully')
else:
    print('ERROR: Old text not found in server.py')
    # Debug: find where ndvi_scheduler is defined
    idx = c.find('def ndvi_scheduler')
    if idx >= 0:
        print('Found at index', idx)
        print(c[idx:idx+500])
