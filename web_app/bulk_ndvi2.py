import sys, os, logging
sys.path.insert(0, '/home/basegnss/rtkbase/web_app')
os.chdir('/home/basegnss/rtkbase/web_app')

logging.basicConfig(
    filename='/home/basegnss/rtkbase/web_app/bulk_ndvi2.log',
    level=logging.INFO, format='%(asctime)s %(message)s', filemode='w'
)
logging.info("Starting bulk NDVI recalc v2 (with cloud filter)")

import ndvi_helper
import sqlite3

conn = sqlite3.connect(ndvi_helper.GPKG_PATH)
zones = [r[0] for r in conn.execute('SELECT zone_id FROM geozones').fetchall()]
conn.close()
logging.info(f"Found {len(zones)} zones: {zones}")

for i, zid in enumerate(zones):
    logging.info(f"[{i+1}/{len(zones)}] Starting {zid}...")
    try:
        result = ndvi_helper.calc_ndvi_for_zone(zid)
        if result and result.get("zone_id"):
            logging.info(f"[{i+1}/{len(zones)}] {zid} OK: date={result.get('scene_date')} mean={result.get('mean_ndvi')}")
        else:
            logging.warning(f"[{i+1}/{len(zones)}] {zid} returned: {result}")
    except Exception as e:
        logging.error(f"[{i+1}/{len(zones)}] {zid} FAILED: {e}", exc_info=True)

logging.info("Bulk NDVI recalc v2 DONE")
