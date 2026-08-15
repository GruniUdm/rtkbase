import sys, os, json, subprocess
sys.path.insert(0, '/home/basegnss/rtkbase/web_app')
import ndvi_helper

base_aws = 'https://sentinel-s2-l2a.s3.amazonaws.com'
scl_url = f'{base_aws}/tiles/39/V/WC/2026/6/11/0/R20m/SCL.jp2'
b04_url = f'{base_aws}/tiles/39/V/WC/2026/6/11/0/R10m/B04.jp2'

print('=== URL checks ===')
for name, url in [('B04', b04_url), ('SCL', scl_url)]:
    r = subprocess.run(['curl', '-so', '/dev/null', '-w', '%{http_code}', '--connect-timeout', '5', '-m', '10', url],
        capture_output=True, text=True, timeout=15)
    print(f'{name}: HTTP {r.stdout.strip()}')
    if r.stdout.strip() == '200':
        r2 = subprocess.run(['curl', '-sI', '--connect-timeout', '5', '-m', '10', url],
            capture_output=True, text=True, timeout=15)
        for line in r2.stdout.split('\n'):
            if 'content-length' in line.lower():
                print(f'  Size: {line.strip()}')

print('\n=== gdalinfo SCL ===')
r = subprocess.run(['gdalinfo', '-json', f'/vsicurl/{scl_url}'],
    capture_output=True, text=True, timeout=30, env=ndvi_helper.GDAL_ENV)
if r.returncode == 0:
    info = json.loads(r.stdout)
    bands = info.get('bands', [])
    print(f'Bands: {len(bands)}')
    for i, b in enumerate(bands):
        t = b.get('type', '?')
        c = b.get('colorInterpretation', '?')
        s = b.get('size', '?')
        print(f'  Band {i}: type={t} color={c} size={s}')
        if b.get('computedStatistics'):
            cs = b['computedStatistics']
            print(f'    min={cs.get("minimum")} max={cs.get("maximum")} mean={cs.get("mean")}')
else:
    print(f'Failed: {r.stderr[:300]}')

print('\n=== gdalinfo B04 ===')
r = subprocess.run(['gdalinfo', '-json', f'/vsicurl/{b04_url}'],
    capture_output=True, text=True, timeout=30, env=ndvi_helper.GDAL_ENV)
if r.returncode == 0:
    info = json.loads(r.stdout)
    bands = info.get('bands', [])
    print(f'Bands: {len(bands)}')
    for i, b in enumerate(bands):
        t = b.get('type', '?')
        print(f'  Band {i}: type={t}')
else:
    print(f'Failed: {r.stderr[:300]}')
