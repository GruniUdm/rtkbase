import sqlite3, json
conn = sqlite3.connect('/home/armsom/rtkbase/data/tracks.gpkg')
rows = conn.execute('SELECT data FROM field_data').fetchall()
conn.close()
for r in rows:
    d = json.loads(r[0])
    n = d.get('name', '')
    yd = d.get('yieldData')
    if not yd:
        continue
    recs = yd.get('records', [])
    if not recs:
        continue
    empty_cmds = sum(1 for rec in recs if not rec.get('cmds'))
    colors = set()
    for rec in recs:
        cmds = rec.get('cmds', [])
        if cmds and len(cmds[0]) >= 11:
            colors.add(cmds[0][10])
    print('FIELD:', n)
    print('  total records:', len(recs))
    print('  empty cmds:', empty_cmds)
    print('  unique colors:', colors)
    # first 20 non-empty cmds
    shown = 0
    for i, rec in enumerate(recs):
        cmds = rec.get('cmds', [])
        if cmds and len(cmds[0]) >= 11:
            print('  first non-empty rec[%d] cmd color: %d (0x%08X)' % (i, cmds[0][10], cmds[0][10]))
            break
