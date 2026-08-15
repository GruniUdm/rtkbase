import sys

with open('/home/basegnss/rtkbase/web_app/ndvi_helper.py', 'r') as f:
    content = f.read()

# Full rewrite of calc_ndvi_for_zone with lazy candidate verification
# First, find the section to replace - from "candidates = _find_best_tile_and_date" 
# through to "base_name, b04_crop, b08_crop, cloud_mask, scene_date = selected"

old = """    candidates = _find_best_tile_and_date(bbox_wgs84, prefer_date)
    if not candidates:
        return {'error': 'No suitable Sentinel-2 scene found for this area'}

    zone_safe = re.sub(r'[^a-zA-Z0-9_-]', '_', zone_name)

    def crop_band(url, out_path):
        r = subprocess.run(['gdal_translate', '-projwin',
            str(bbox_utm[0]), str(bbox_utm[1]),
            str(bbox_utm[2]), str(bbox_utm[3]),
            '-projwin_srs', f'EPSG:326{utm_zone}',
            '-of', 'GTiff', url, out_path],
            capture_output=True, text=True, timeout=180, env=GDAL_ENV)
        return r.returncode == 0 and os.path.exists(out_path)

    def _compute_cloud_pct(cloud_clipped):
        info_r = subprocess.run(['gdalinfo', '-json', '-stats', cloud_clipped],
            capture_output=True, text=True, timeout=30, env=GDAL_ENV)
        if info_r.returncode == 0:
            info = json.loads(info_r.stdout)
            bands = info.get('bands', [])
            if bands:
                mean_val = bands[0].get('mean', 0)
                return mean_val * 100
        return None

    selected = None
    for attempt_idx, (b04_url, b08_url, scl_url_stac, scene_date) in enumerate(candidates):
        timestamp = f'{time.strftime("%Y%m%d_%H%M%S")}_{attempt_idx}'
        base_name = f'ndvi_{zone_safe}_{timestamp}'

        b04_crop = os.path.join(NDVI_DIR, f'{base_name}_B04.tif')
        b08_crop = os.path.join(NDVI_DIR, f'{base_name}_B08.tif')

        if not crop_band(b04_url, b04_crop) or not crop_band(b08_url, b08_crop):
            for f in [b04_crop, b08_crop]:
                if os.path.exists(f): os.remove(f)
            print(f'  {scene_date}: band download failed, trying next')
            continue

        # Check cloud cover within zone using SCL
        too_cloudy = False
        cloud_mask = None
        scl_url = scl_url_stac or ''
        r_check = subprocess.run(['curl', '-so', '/dev/null', '-w', '%{http_code}',
            '--connect-timeout', '5', '-m', '15', scl_url],
            capture_output=True, text=True, timeout=20)
        if r_check.stdout.strip() == '200':
            scl_crop = os.path.join(NDVI_DIR, f'{base_name}_SCL.tif')
            if crop_band(scl_url, scl_crop):
                scl_10m = os.path.join(NDVI_DIR, f'{base_name}_SCL_10m.tif')
                r_resample = subprocess.run(['gdalwarp', '-tr', '10', '10', '-r', 'near',
                    scl_crop, scl_10m],
                    capture_output=True, text=True, timeout=60, env=GDAL_ENV)
                if r_resample.returncode == 0 and os.path.exists(scl_10m):
                    cloud_mask_raw = os.path.join(NDVI_DIR, f'{base_name}_cloud.tif')
                    r_mask = subprocess.run(['gdal_calc.py', '-A', scl_10m,
                        '--outfile', cloud_mask_raw, '--calc',
                        '((A==8)+(A==9)+(A==10))>0',
                        '--NoDataValue', '0', '--type', 'Byte', '--overwrite'],
                        capture_output=True, text=True, timeout=60, env=GDAL_ENV)
                    if r_mask.returncode == 0 and os.path.exists(cloud_mask_raw):
                        # Clip cloud mask to zone polygon
                        valid_cutline = os.path.join(NDVI_DIR, f'{base_name}_cutline.gpkg')
                        subprocess.run(['ogr2ogr', '-f', 'GPKG', '-makevalid', '-nln', 'cutline',
                            valid_cutline, GPKG_PATH, 'geozones', '-where', f"zone_id='{zone_id}'"],
                            capture_output=True, text=True, timeout=30)

                        cloud_clipped = os.path.join(NDVI_DIR, f'{base_name}_cloud_clip.tif')
                        r_cc = subprocess.run(['gdalwarp', '-cutline', valid_cutline, '-crop_to_cutline',
                            cloud_mask_raw, cloud_clipped],
                            capture_output=True, text=True, timeout=60, env=GDAL_ENV)

                        if r_cc.returncode == 0 and os.path.exists(cloud_clipped):
                            cloud_pct = _compute_cloud_pct(cloud_clipped)
                            if cloud_pct is not None and cloud_pct > 30:
                                print(f'  {scene_date}: {cloud_pct:.1f}% clouds in zone > 30%, skipping')
                                too_cloudy = True
                            else:
                                cloud_mask = cloud_clipped
                                print(f'  {scene_date}: {cloud_pct:.1f}% clouds in zone OK')
                        else:
                            if os.path.exists(cloud_clipped): os.remove(cloud_clipped)

                        os.remove(valid_cutline)
                    else:
                        if os.path.exists(cloud_mask_raw): os.remove(cloud_mask_raw)
                    os.remove(scl_10m)
                os.remove(scl_crop)

            if too_cloudy:
                for f in [b04_crop, b08_crop]:
                    if os.path.exists(f): os.remove(f)
                continue

        # Cloud check passed (or SCL unavailable)
        selected = (base_name, b04_crop, b08_crop, cloud_mask, scene_date)
        print(f'  Selected scene: {scene_date}')
        break

    if not selected:
        return {'error': 'All candidates had > 30% cloud cover within the zone'}

    base_name, b04_crop, b08_crop, cloud_mask, scene_date = selected"""

new = """    # Step 1: Get scene candidates from STAC, sorted by UTM match + date
    raw_candidates = _stac_search(bbox_wgs84)
    if not raw_candidates:
        return {'error': 'No suitable Sentinel-2 scene found for this area'}

    lon_center = (bbox_wgs84[0] + bbox_wgs84[2]) / 2
    target_utm = int((lon_center + 180) / 6) + 1
    raw_candidates.sort(key=lambda r: r['datetime'] or '', reverse=True)
    raw_candidates.sort(key=lambda r: 0 if r['tile'][:2].lstrip('0') == str(target_utm) else 1)
    if prefer_date:
        date_results = [r for r in raw_candidates if r.get('datetime', '').startswith(prefer_date)]
        if date_results:
            raw_candidates = date_results + [r for r in raw_candidates if not r.get('datetime', '').startswith(prefer_date)]
    raw_candidates = raw_candidates[:10]

    zone_safe = re.sub(r'[^a-zA-Z0-9_-]', '_', zone_name)

    def crop_band(url, out_path):
        r = subprocess.run(['gdal_translate', '-projwin',
            str(bbox_utm[0]), str(bbox_utm[1]),
            str(bbox_utm[2]), str(bbox_utm[3]),
            '-projwin_srs', f'EPSG:326{utm_zone}',
            '-of', 'GTiff', url, out_path],
            capture_output=True, text=True, timeout=180, env=GDAL_ENV)
        return r.returncode == 0 and os.path.exists(out_path)

    def _compute_cloud_pct(cloud_clipped):
        info_r = subprocess.run(['gdalinfo', '-json', '-stats', cloud_clipped],
            capture_output=True, text=True, timeout=30, env=GDAL_ENV)
        if info_r.returncode == 0:
            info = json.loads(info_r.stdout)
            bands = info.get('bands', [])
            if bands:
                mean_val = bands[0].get('mean', 0)
                return mean_val * 100
        return None

    def _url_exists(url):
        r = subprocess.run(['curl', '-so', '/dev/null', '-w', '%{http_code}', '--connect-timeout', '3', '-m', '5', url],
            capture_output=True, text=True, timeout=10)
        return r.stdout.strip() == '200'

    # Build candidate URLs lazily
    base_aws = 'https://sentinel-s2-l2a.s3.amazonaws.com'
    token = _get_sas_token()
    token_suffix = f'?{token}' if token else ''

    def _build_candidates(results):
        cands = []
        for result in results:
            sd = result.get('datetime', '')[:10]
            parts = sd.split('-')
            tile_id = result.get('tile', '')
            if len(parts) == 3 and tile_id and len(tile_id) == 5:
                aws_prefix = _tile_to_aws_path(tile_id, parts[0], parts[1], parts[2])
                if aws_prefix:
                    cands.append({
                        'b04': f'{base_aws}/{aws_prefix}/B04.jp2',
                        'b08': f'{base_aws}/{aws_prefix}/B08.jp2',
                        'scl': f'{base_aws}/{aws_prefix.replace("R10m", "R20m")}/SCL.jp2',
                        'date': sd,
                    })
            b04_pc = result.get('b04_url', '')
            b08_pc = result.get('b08_url', '')
            scl_pc = result.get('scl_url', '')
            if b04_pc and b08_pc:
                cands.append({
                    'b04': b04_pc + token_suffix,
                    'b08': b08_pc + token_suffix,
                    'scl': scl_pc + token_suffix if scl_pc else '',
                    'date': sd,
                })
        return cands

    all_candidates = _build_candidates(raw_candidates)

    selected = None
    for attempt_idx, cand in enumerate(all_candidates):
        scene_date = cand['date']
        timestamp = f'{time.strftime("%Y%m%d_%H%M%S")}_{attempt_idx}'
        base_name = f'ndvi_{zone_safe}_{timestamp}'

        print(f'  Trying {scene_date}...')

        # 1. Check SCL cloud cover FIRST (fast, 20m) before downloading B04/B08
        cloud_mask = None
        too_cloudy = False
        scl_url = cand.get('scl', '')
        if scl_url and _url_exists(scl_url):
            scl_crop = os.path.join(NDVI_DIR, f'{base_name}_SCL.tif')
            if crop_band(scl_url, scl_crop):
                # Use SCL at native 20m for cloud check (no resample needed)
                # Create binary cloud mask from SCL
                cloud_mask_raw = os.path.join(NDVI_DIR, f'{base_name}_cloud.tif')
                r_mask = subprocess.run(['gdal_calc.py', '-A', scl_crop,
                    '--outfile', cloud_mask_raw, '--calc',
                    '((A==8)+(A==9)+(A==10))>0',
                    '--NoDataValue', '0', '--type', 'Byte', '--overwrite'],
                    capture_output=True, text=True, timeout=60, env=GDAL_ENV)
                if r_mask.returncode == 0 and os.path.exists(cloud_mask_raw):
                    # Clip to zone polygon
                    valid_cutline = os.path.join(NDVI_DIR, f'{base_name}_cutline.gpkg')
                    subprocess.run(['ogr2ogr', '-f', 'GPKG', '-makevalid', '-nln', 'cutline',
                        valid_cutline, GPKG_PATH, 'geozones', '-where', f"zone_id='{zone_id}'"],
                        capture_output=True, text=True, timeout=30)

                    cloud_clipped = os.path.join(NDVI_DIR, f'{base_name}_cloud_clip.tif')
                    r_cc = subprocess.run(['gdalwarp', '-cutline', valid_cutline, '-crop_to_cutline',
                        cloud_mask_raw, cloud_clipped],
                        capture_output=True, text=True, timeout=60, env=GDAL_ENV)

                    if r_cc.returncode == 0 and os.path.exists(cloud_clipped):
                        cloud_pct = _compute_cloud_pct(cloud_clipped)
                        if cloud_pct is not None and cloud_pct > 30:
                            print(f'  {scene_date}: {cloud_pct:.1f}% clouds in zone > 30%, skipping')
                            too_cloudy = True
                            os.remove(cloud_clipped)
                        else:
                            cloud_mask = cloud_clipped
                            print(f'  {scene_date}: {cloud_pct:.1f}% clouds in zone OK')
                    if os.path.exists(valid_cutline): os.remove(valid_cutline)
                if os.path.exists(cloud_mask_raw) and (too_cloudy or cloud_mask != cloud_mask_raw):
                    os.remove(cloud_mask_raw)
                os.remove(scl_crop)

            if too_cloudy:
                continue

        # 2. Cloud check passed (or SCL unavailable) — verify and download B04/B08
        if not _url_exists(cand['b04']) or not _url_exists(cand['b08']):
            print(f'  {scene_date}: band URLs not accessible, trying next')
            continue

        b04_crop = os.path.join(NDVI_DIR, f'{base_name}_B04.tif')
        b08_crop = os.path.join(NDVI_DIR, f'{base_name}_B08.tif')

        if not crop_band(cand['b04'], b04_crop) or not crop_band(cand['b08'], b08_crop):
            for f in [b04_crop, b08_crop]:
                if os.path.exists(f): os.remove(f)
            print(f'  {scene_date}: band download failed, trying next')
            continue

        selected = (base_name, b04_crop, b08_crop, cloud_mask, scene_date)
        print(f'  Selected scene: {scene_date}')
        break

    if not selected:
        return {'error': 'All candidates had > 30% cloud cover within the zone, or bands unavailable'}

    base_name, b04_crop, b08_crop, cloud_mask, scene_date = selected
    
    # Resample cloud mask to 10m if we have one (for later overlay with NDVI)
    if cloud_mask and os.path.exists(cloud_mask):
        cloud_10m = os.path.join(NDVI_DIR, f'{base_name}_cloud_10m.tif')
        r_resample = subprocess.run(['gdalwarp', '-tr', '10', '10', '-r', 'near',
            cloud_mask, cloud_10m],
            capture_output=True, text=True, timeout=60, env=GDAL_ENV)
        if r_resample.returncode == 0 and os.path.exists(cloud_10m):
            os.remove(cloud_mask)
            cloud_mask = cloud_10m"""

assert old in content, 'Replacement text not found'
content = content.replace(old, new)
print('calc_ndvi_for_zone rewritten with lazy candidate verification')

with open('/home/basegnss/rtkbase/web_app/ndvi_helper.py', 'w') as f:
    f.write(content)
print('File written')
