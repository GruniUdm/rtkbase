import sys
sys.path.insert(0, "/home/basegnss/rtkbase/web_app")
from ndvi_helper import recalc_all_ndvi
import time, json

print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Starting bulk NDVI recalc v3...")
start = time.time()
results = recalc_all_ndvi()
elapsed = time.time() - start
print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Done in {elapsed:.0f}s")
success = sum(1 for v in results.values() if v)
fail = sum(1 for v in results.values() if not v)
print(f"Success: {success}, Failed: {fail}")
for zid, ok in results.items():
    status = "OK" if ok else "FAIL"
    print(f"  {zid}: {status}")
