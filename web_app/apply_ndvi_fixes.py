import sys

with open('/home/basegnss/rtkbase/web_app/ndvi_helper.py', 'r') as f:
    content = f.read()

# Change 1: Relax STAC cloud filter
old1 = """        'query': {'eo:cloud_cover': {'lt': 30}},"""
new1 = """        'query': {'eo:cloud_cover': {'lt': 90}},"""
assert old1 in content, 'Change 1 not found'
content = content.replace(old1, new1)
print('Change 1 OK')

# Change 2: _find_best_tile_and_date returns list (was tuple)
old2 = """    results = results[:5]
    token = _get_sas_token()
    token_suffix = f'?{token}' if token else ''
    base_aws = 'https://sentinel-s2-l2a.s3.amazonaws.com'
    # Build candidate list: PC COG + AWS JP2 fallback
    candidates = []
    for result in results:
        sd = result.get('datetime', '')[:10]
        parts = sd.split('-')
        # AWS JP2 first (more reliable coverage, no SAS needed)
        tile_id = result.get('tile', '')
        if len(parts) == 3 and tile_id and len(tile_id) == 5:
            aws_prefix = _tile_to_aws_path(tile_id, parts[0], parts[1], parts[2])
            if aws_prefix:
                candidates.append((
                    f'{base_aws}/{aws_prefix}/B04.jp2',
                    f'{base_aws}/{aws_prefix}/B08.jp2',
                    f'{base_aws}/{aws_prefix.replace("R10m", "R20m")}/SCL.jp2',
                    sd
                ))
        # PC COG URLs
        b04_pc = result.get('b04_url', '')
        b08_pc = result.get('b08_url', '')
        scl_pc = result.get('scl_url', '')
        if b04_pc and b08_pc:
            candidates.append((b04_pc + token_suffix, b08_pc + token_suffix, scl_pc + token_suffix if scl_pc else '', sd))
    for b04, b08, scl, sd in candidates:
        ok = True
        for url in [b04, b08]:
            r = subprocess.run(['curl', '-so', '/dev/null', '-w', '%{http_code}', '--connect-timeout', '3', '-m', '5', url],
                capture_output=True, text=True, timeout=10)
            if r.stdout.strip() != '200':
                ok = False
                break
        if ok:
            return b04, b08, scl, sd
    return None, None, None, None"""

new2 = """    results = results[:10]
    token = _get_sas_token()
    token_suffix = f'?{token}' if token else ''
    base_aws = 'https://sentinel-s2-l2a.s3.amazonaws.com'
    candidates = []
    for result in results:
        sd = result.get('datetime', '')[:10]
        parts = sd.split('-')
        tile_id = result.get('tile', '')
        if len(parts) == 3 and tile_id and len(tile_id) == 5:
            aws_prefix = _tile_to_aws_path(tile_id, parts[0], parts[1], parts[2])
            if aws_prefix:
                candidates.append((
                    f'{base_aws}/{aws_prefix}/B04.jp2',
                    f'{base_aws}/{aws_prefix}/B08.jp2',
                    f'{base_aws}/{aws_prefix.replace("R10m", "R20m")}/SCL.jp2',
                    sd
                ))
        b04_pc = result.get('b04_url', '')
        b08_pc = result.get('b08_url', '')
        scl_pc = result.get('scl_url', '')
        if b04_pc and b08_pc:
            candidates.append((b04_pc + token_suffix, b08_pc + token_suffix, scl_pc + token_suffix if scl_pc else '', sd))
    valid = []
    for b04, b08, scl, sd in candidates:
        ok = True
        for url in [b04, b08]:
            r = subprocess.run(['curl', '-so', '/dev/null', '-w', '%{http_code}', '--connect-timeout', '3', '-m', '5', url],
                capture_output=True, text=True, timeout=10)
            if r.stdout.strip() != '200':
                ok = False
                break
        if ok:
            valid.append((b04, b08, scl, sd))
    return valid"""

assert old2 in content, 'Change 2 not found'
content = content.replace(old2, new2)
print('Change 2 OK')

# Change 3: calc_ndvi_for_zone loops with cloud check
old3 = """    b04_url, b08_url, scl_url_stac, scene_date = _find_best_tile_and_date(bbox_wgs84, prefer_date)
    if not b04_url:
        return {'error': 'No suitable Sentinel-2 scene found for this area'}

    zone_safe = re.sub(r'[^a-zA-Z0-9_-]', '_', zone_name)
    timestamp = time.strftime('%Y%m%d_%H%M%S')
    base_name = f'ndvi_{zone_safe}_{timestamp}'

    # 1. Crop B04 and B08 to bbox
    b04_crop = os.path.join(NDVI_DIR, f'{base_name}_B04.tif')
    b08_crop = os.path.join(NDVI_DIR, f'{base_name}_B08.tif')

    def crop_band(url, out_path):
        r = subprocess.run(['gdal_translate', '-projwin',
            str(bbox_utm[0]), str(bbox_utm[1]),
            str(bbox_utm[2]), str(bbox_utm[3]),
            '-projwin_srs', f'EPSG:326{utm_zone}',
            '-of', 'GTiff', url, out_path],
            capture_output=True, text=True, timeout=180, env=GDAL_ENV)
        return r.returncode == 0 and os.path.exists(out_path)

    if not crop_band(b04_url, b04_crop) or not crop_band(b08_url, b08_crop):
        for f in [b04_crop, b08_crop]:
            if os.path.exists(f): os.remove(f)
        return {'error': 'Failed to download bands'}

    # 1b. Download SCL (Scene Classification) for cloud masking
    scl_crop = os.path.join(NDVI_DIR, f'{base_name}_SCL.tif')
    scl_url = scl_url_stac or ''
    scl_ok = False
    # Quick check if SCL exists
    r_check = subprocess.run(['curl', '-so', '/dev/null', '-w', '%{http_code}',
        '--connect-timeout', '5', '-m', '15', scl_url],
        capture_output=True, text=True, timeout=20)
    scl_exists = r_check.stdout.strip() == '200'
    cloud_mask = None
    if scl_exists:
        if crop_band(scl_url, scl_crop):
            # Resample SCL from 20m to 10m to match NDVI
            scl_10m = os.path.join(NDVI_DIR, f'{base_name}_SCL_10m.tif')
            r_resample = subprocess.run(['gdalwarp', '-tr', '10', '10', '-r', 'near',
                scl_crop, scl_10m],
                capture_output=True, text=True, timeout=60, env=GDAL_ENV)
            if r_resample.returncode == 0 and os.path.exists(scl_10m):
                os.remove(scl_crop)
                # Create binary cloud mask: SCL 8,9,10 → 1, rest → 0
                cloud_mask = os.path.join(NDVI_DIR, f'{base_name}_cloud.tif')
                r_mask = subprocess.run(['gdal_calc.py', '-A', scl_10m,
                    '--outfile', cloud_mask, '--calc',
                    '((A==8)+(A==9)+(A==10))>0',
                    '--NoDataValue', '0', '--type', 'Byte', '--overwrite'],
                    capture_output=True, text=True, timeout=60, env=GDAL_ENV)
                if r_mask.returncode == 0 and os.path.exists(cloud_mask):
                    scl_ok = True
                else:
                    if os.path.exists(cloud_mask): os.remove(cloud_mask)
                    cloud_mask = None
                os.remove(scl_10m)
        if not scl_ok:
            if os.path.exists(scl_crop): os.remove(scl_crop)"""

new3 = """    candidates = _find_best_tile_and_date(bbox_wgs84, prefer_date)
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

assert old3 in content, 'Change 3 not found'
content = content.replace(old3, new3)
print('Change 3 OK')

with open('/home/basegnss/rtkbase/web_app/ndvi_helper.py', 'w') as f:
    f.write(content)
print('All changes applied and written')
