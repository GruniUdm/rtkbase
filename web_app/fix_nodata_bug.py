import sys

with open('/home/basegnss/rtkbase/web_app/ndvi_helper.py', 'r') as f:
    content = f.read()

# Fix 1: In cloud check part, remove --NoDataValue 0 from gdal_calc 
# The raw cloud mask for percentage check must not have NoData masking non-cloud pixels
old = """                    cloud_mask_raw = os.path.join(NDVI_DIR, f'{base_name}_cloud.tif')
                    r_mask = subprocess.run(['gdal_calc.py', '-A', scl_crop,
                        '--outfile', cloud_mask_raw, '--calc',
                        '((A==8)+(A==9)+(A==10))>0',
                        '--NoDataValue', '0', '--type', 'Byte', '--overwrite'],"""

new = """                    cloud_mask_raw = os.path.join(NDVI_DIR, f'{base_name}_cloud.tif')
                    r_mask = subprocess.run(['gdal_calc.py', '-A', scl_crop,
                        '--outfile', cloud_mask_raw, '--calc',
                        '((A==8)|(A==9)|(A==10))*1',
                        '--type', 'Byte', '--overwrite'],"""

assert old in content, 'Fix 1 not found'
content = content.replace(old, new)
print('Fix 1 applied: removed NoData from cloud check mask, used OR instead of addition')

# Fix 2: Do the same for the existing NDVI processing part (the old SCL code path)
# that runs after scene selection - the cloud_mask used for overlay
old2 = """                    r_mask = subprocess.run(['gdal_calc.py', '-A', scl_10m,
                        '--outfile', cloud_mask, '--calc',
                        '((A==8)+(A==9)+(A==10))>0',
                        '--NoDataValue', '0', '--type', 'Byte', '--overwrite'],"""

new2 = """                    r_mask = subprocess.run(['gdal_calc.py', '-A', scl_10m,
                        '--outfile', cloud_mask, '--calc',
                        '((A==8)|(A==9)|(A==10))*1',
                        '--type', 'Byte', '--overwrite'],"""

assert old2 in content, 'Fix 2 not found'
content = content.replace(old2, new2)
print('Fix 2 applied: same fix in NDVI processing section')

with open('/home/basegnss/rtkbase/web_app/ndvi_helper.py', 'w') as f:
    f.write(content)
print('File written')
