import subprocess, json

# CORRECT order: [lon_min, lat_min, lon_max, lat_max]
correct = json.dumps({
    "collections": ["sentinel-2-l2a"],
    "bbox": [30.7, 52.85, 30.8, 52.92],
    "limit": 3,
    "query": {"eo:cloud_cover": {"lt": 30}},
    "fields": {"exclude": ["assets"], "include": ["id", "properties.datetime", "properties.eo:cloud_cover"]},
    "sortby": [{"field": "properties.datetime", "direction": "desc"}]
})
# WRONG order: [lat_min, lon_min, lat_max, lon_max]  
wrong = json.dumps({
    "collections": ["sentinel-2-l2a"],
    "bbox": [52.85, 30.7, 52.92, 30.8],
    "limit": 3,
    "query": {"eo:cloud_cover": {"lt": 30}},
    "fields": {"exclude": ["assets"], "include": ["id", "properties.datetime", "properties.eo:cloud_cover"]},
    "sortby": [{"field": "properties.datetime", "direction": "desc"}]
})

def search(body):
    r = subprocess.run(["curl", "-s", "--connect-timeout", "10", "-m", "30", "-X", "POST",
        "https://earth-search.aws.element84.com/v1/search",
        "-H", "Content-Type: application/json", "-d", body],
        capture_output=True, text=True)
    d = json.loads(r.stdout)
    return d.get("features", [])

print("=== CORRECT bbox [30.7, 52.85, 30.8, 52.92] ===")
for f in search(correct)[:3]:
    p = f["properties"]
    print(f"  {f['id']}: cloud={p.get('eo:cloud_cover','?')}%")

print("=== WRONG bbox [52.85, 30.7, 52.92, 30.8] (as used by code) ===")
for f in search(wrong)[:3]:
    p = f["properties"]
    print(f"  {f['id']}: cloud={p.get('eo:cloud_cover','?')}%")
