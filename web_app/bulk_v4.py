import sys, time
sys.path.insert(0, "/home/basegnss/rtkbase/web_app")
from ndvi_helper import recalc_all_ndvi

print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Bulk NDVI v4 (June) started")
start = time.time()
results = recalc_all_ndvi()
elapsed = time.time() - start
print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Done in {elapsed:.0f}s")
ok = sum(1 for v in results.values() if v)
fail = sum(1 for v in results.values() if not v)
print(f"OK={ok} FAIL={fail}")
for zid, r in results.items():
    print(f"  {zid}: {'OK' if r else 'FAIL'}")
