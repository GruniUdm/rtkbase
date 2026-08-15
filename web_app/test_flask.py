import sys
sys.path.insert(0, '/home/basegnss/rtkbase/web_app')
from server import app

with app.test_client() as c:
    resp = c.post('/login', data={'password': '196411014Selfon!', 'remember_me': False},
                  follow_redirects=False)
    print('Login:', resp.status_code)
    if resp.status_code in (302,):
        print('  redirect to:', resp.headers.get('Location'))
    resp2 = c.get('/api/tractor_track/zetor/last')
    print('Last:', resp2.status_code)
    print('Data:', resp2.data[:300].decode())
