import sys
sys.path.insert(0, "/home/basegnss/rtkbase/web_app")
from ndvi_helper import _stac_search
result = _stac_search([52.49, 56.50, 52.52, 56.51])
if result:
    print(f"{len(result)} scenes:")
    for r in result:
        print(f"  {r['id']}: tile={r['tile']}, cloud={r['cloud']}%, date={r['datetime'][:10]}")
else:
    print("No scenes found")
