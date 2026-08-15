with open('/home/basegnss/rtkbase/web_app/ndvi_helper.py', 'r') as f:
    c = f.read()

# Replace the specific section: cloud check with SCL
old = """                cloud_mask_raw = os.path.join(NDVI_DIR, f'{base_name}_cloud.tif')
                r_mask = subprocess.run(['gdal_calc.py', '-A', scl_crop,
                    '--outfile', cloud_mask_raw, '--calc',
                    '((A==8)+(A==9)+(A==10))>0',
                    '--NoDataValue', '0', '--type', 'Byte', '--overwrite'],
                    capture_output=True, text=True, timeout=60, env=GDAL_ENV)"""

new = """                cloud_mask_raw = os.path.join(NDVI_DIR, f'{base_name}_cloud.tif')
                r_mask = subprocess.run(['gdal_calc.py', '-A', scl_crop,
                    '--outfile', cloud_mask_raw, '--calc',
                    '((A==8)|(A==9)|(A==10))*1',
                    '--type', 'Byte', '--overwrite'],
                    capture_output=True, text=True, timeout=60, env=GDAL_ENV)"""

if old in c:
    c = c.replace(old, new)
    print('Fix 1: OK')
else:
    print('Fix 1: NOT FOUND - dumping context')
    import re
    matches = list(re.finditer(r'gdal_calc.py.*cloud_mask_raw.*SCL', c, re.DOTALL))
    for m in matches:
        print(repr(c[m.start():m.end()]))

# Also fix the overlay section (different context)
old2 = """                        '--outfile', cloud_mask, '--calc',
                        '((A==8)+(A==9)+(A==10))>0',
                        '--NoDataValue', '0', '--type', 'Byte', '--overwrite'],"""

new2 = """                        '--outfile', cloud_mask, '--calc',
                        '((A==8)|(A==9)|(A==10))*1',
                        '--type', 'Byte', '--overwrite'],"""

if old2 in c:
    c = c.replace(old2, new2)
    print('Fix 2: OK')
else:
    print('Fix 2: NOT FOUND (may already be fixed)')

with open('/home/basegnss/rtkbase/web_app/ndvi_helper.py', 'w') as f:
    f.write(c)
print('Done')
