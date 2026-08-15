import sys, sqlite3
sys.path.insert(0, '/home/basegnss/rtkbase/web_app')
import gpkg_helper
conn = sqlite3.connect('/home/basegnss/rtkbase/data/tracks.gpkg')
pt = gpkg_helper.get_last_track_point(conn, 'zetor')
print('zetor:', pt)
pt2 = gpkg_helper.get_last_track_point(conn, '1523')
print('1523:', pt2)
pt3 = gpkg_helper.get_last_track_point(conn, 'kirovec')
print('kirovec:', pt3)
conn.close()
