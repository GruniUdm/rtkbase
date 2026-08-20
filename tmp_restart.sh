sudo kill $(ps aux | grep 'server.py' | grep -v grep | head -1 | awk '{print $2}')
sleep 2
cd /home/armsom/rtkbase/web_app
sudo /home/armsom/rtkbase/venv/bin/python server.py > /tmp/server.log 2>&1 &
sleep 6
curl -s -o /dev/null -w '%{http_code}' http://localhost/tractor_map
echo
tail -3 /tmp/server.log
