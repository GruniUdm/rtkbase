import subprocess, json
body = json.dumps({
    "collections": ["sentinel-2-l2a"],
    "bbox": [30.7, 52.85, 30.8, 52.92],
    "limit": 3,
    "query": {"eo:cloud_cover": {"lt": 30}},
    "fields": {"include": ["id", "properties.datetime", "properties.eo:cloud_cover", "bbox", "geometry"]},
    "sortby": [{"field": "properties.datetime", "direction": "desc"}]
})
r = subprocess.run(["curl", "-s", "--connect-timeout", "10", "-m", "30", "-X", "POST",
    "https://earth-search.aws.element84.com/v1/search",
    "-H", "Content-Type: application/json", "-d", body],
    capture_output=True, text=True)
print(f"returncode={r.returncode}")
print(f"stdout len={len(r.stdout)}")
print(f"stderr={r.stderr}")
if r.stdout.strip():
    try:
        d = json.loads(r.stdout)
        print(f"features={len(d.get('features',[]))}")
        for f in d.get("features",[]):
            p = f["properties"]
            print(f"  cloud={p.get('eo:cloud_cover','?')}% date={p['datetime'][:10] if p.get('datetime') else '?'} id={f['id']}")
    except Exception as e:
        print(f"bad json: {e}")
        print(r.stdout[:500])
