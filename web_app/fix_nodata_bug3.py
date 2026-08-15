with open('/home/basegnss/rtkbase/web_app/ndvi_helper.py', 'r') as f:
    lines = f.readlines()

# Find and fix the NoDataValue line
for i, line in enumerate(lines):
    if '--NoDataValue' in line and 'gdal_calc' in lines[i-2] if i >= 2 else False:
        print(f'Found at line {i+1}: {line.rstrip()}')
        # Fix the current line
        lines[i] = line.replace("'--NoDataValue', '0', ", "")
        # Also fix the calc expression in the previous line
        if i >= 1 and "((A==8)+(A==9)+(A==10))>0" in lines[i-1]:
            lines[i-1] = lines[i-1].replace("((A==8)+(A==9)+(A==10))>0", "((A==8)|(A==9)|(A==10))*1")
        print(f'Fixed line {i+1}')

with open('/home/basegnss/rtkbase/web_app/ndvi_helper.py', 'w') as f:
    f.writelines(lines)
print('Done')
