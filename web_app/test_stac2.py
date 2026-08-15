import subprocess, json
body = json.dumps({
    "collections": ["sentinel-2-l2a"],
    "bbox": [52.49, 56.50, 52.52, 56.51],
    "datetime": "2026-05-01T00:00:00Z/2026-06-10T23:59:59Z",
    "limit": 10,
    "query": {"eo:cloud_cover": {"lt": 30}},
    "fields": {"include": ["id", "properties.datetime", "properties.eo:cloud_cover"]}
})
r = subprocess.run(["curl", "-s", "--connect-timeout", "15", "-m", "120", "-X", "POST",
    "https://earth-search.aws.element84.com/v1/search",
    "-H", "Content-Type: application/json", "-d", body],
    capture_output=True, text=True, timeout=150)
print(f"rc={r.returncode}, stdout_len={len(r.stdout)}")
if r.returncode == 0:
    data = json.loads(r.stdout)
    print(f'{len(data["features"])} features')
    for f in data["features"]:
        print(f"  {f['id']}")
else:
    print(f"err: {r.stderr[:200]}")
