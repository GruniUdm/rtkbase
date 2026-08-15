with open('/home/basegnss/rtkbase/web_app/ndvi_helper.py', 'r') as f:
    c = f.read()

# Fix 1: cloud check section
old1 = """                    r_mask = subprocess.run(['gdal_calc.py', '-A', scl_crop,
                        '--outfile', cloud_mask_raw, '--calc',
                        '((A==8)+(A==9)+(A==10))>0',
                        '--NoDataValue', '0', '--type', 'Byte', '--overwrite'],"""
new1 = """                    r_mask = subprocess.run(['gdal_calc.py', '-A', scl_crop,
                        '--outfile', cloud_mask_raw, '--calc',
                        '((A==8)|(A==9)|(A==10))*1',
                        '--type', 'Byte', '--overwrite'],"""

assert old1 in c, 'Fix 1 not found'
c = c.replace(old1, new1)
print('Fix 1 OK')

# Fix 2: NDVI overlay section (might already be fixed)
old2 = """                        '--outfile', cloud_mask, '--calc',
                        '((A==8)+(A==9)+(A==10))>0',
                        '--NoDataValue', '0', '--type', 'Byte', '--overwrite'],"""
if old2 in c:
    new2 = """                        '--outfile', cloud_mask, '--calc',
                        '((A==8)|(A==9)|(A==10))*1',
                        '--type', 'Byte', '--overwrite'],"""
    c = c.replace(old2, new2)
    print('Fix 2 OK')
else:
    print('Fix 2 not needed')

with open('/home/basegnss/rtkbase/web_app/ndvi_helper.py', 'w') as f:
    f.write(c)
print('Done')
