#!/usr/bin/python

# This Flask app is a heavily modified version of Reachview
# modified to be used as a front end for GNSS base
# author: St??phane P??neau
# source: https://github.com/Stefal/rtkbase

# ReachView code is placed under the GPL license.
# Written by Egor Fedorov (egor.fedorov@emlid.com)
# Copyright (c) 2015, Emlid Limited
# All rights reserved.

# If you are interested in using ReachView code as a part of a
# closed source project, please contact Emlid Limited (info@emlid.com).

# This file is part of ReachView.

# ReachView is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# ReachView is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with ReachView.  If not, see <http://www.gnu.org/licenses/>.

#from gevent import monkey
#monkey.patch_all()
import eventlet
eventlet.monkey_patch()

import time
import json
import os
import shutil
import signal
import sys
import requests
import math
import re
from threading import Lock


# Weather cache for forecast data
_weather_cache = {'data': None, 'ts': 0}
_weather_lock = Lock()
WEATHER_CACHE_TTL = 1800  # 30 min

_WEATHER_RU = {
    'Sunny': 'Солнечно',
    'Clear': 'Ясно',
    'Partly Cloudy': 'Переменная облачность',
    'Cloudy': 'Облачно',
    'Overcast': 'Пасмурно',
    'Mist': 'Туман',
    'Fog': 'Туман',
    'Light Fog': 'Лёгкий туман',
    'Freezing Fog': 'Ледяной туман',
    'Light rain shower': 'Небольшой дождь',
    'Patchy rain nearby': 'Небольшой дождь',
    'Patchy rain possible': 'Возможен небольшой дождь',
    'Patchy light drizzle': 'Небольшая морось',
    'Light drizzle': 'Лёгкая морось',
    'Drizzle': 'Морось',
    'Light rain': 'Небольшой дождь',
    'Moderate rain': 'Умеренный дождь',
    'Heavy rain': 'Сильный дождь',
    'Moderate rain at times': 'Временами умеренный дождь',
    'Heavy rain at times': 'Временами сильный дождь',
    'Torrential rain shower': 'Проливной дождь',
    'Light snow': 'Небольшой снег',
    'Snow': 'Снег',
    'Heavy snow': 'Сильный снег',
    'Light snow showers': 'Небольшой снег',
    'Moderate or heavy snow showers': 'Умеренный или сильный снег',
    'Blowing snow': 'Метель',
    'Blizzard': 'Метель',
    'Thunder': 'Гроза',
    'Thunderstorm': 'Гроза',
    'Thunderstorms': 'Гроза',
    'Thunderstorms in vicinity': 'Гроза рядом',
    'Haze': 'Дымка',
    'Smoke': 'Дым',
    'Dust': 'Пыль',
    'Squalls': 'Шквал',
    'Tornado': 'Торнадо',
    'Hurricane': 'Ураган',
    'Windy': 'Ветрено',
    'Ice pellets': 'Ледяной дождь',
    'Sleet': 'Мокрый снег',
    'Showers in vicinity': 'Дождь рядом',
    'Light sleet': 'Небольшой мокрый снег',
    'Moderate or heavy sleet': 'Умеренный или сильный мокрый снег',
    'Light freezing rain': 'Небольшой ледяной дождь',
    'Moderate or heavy freezing rain': 'Умеренный или сильный ледяной дождь',
    'Moderate or heavy rain shower': 'Умеренный или сильный дождь',
    'Light rain with thunderstorm': 'Небольшой дождь с грозой',
}

def _is_cyrillic(text):
    return any(ord(c) > 0x0400 and ord(c) < 0x0500 for c in text)

def _wd(entry):
    ru = entry.get('lang_ru', [{}])
    if ru and ru[0].get('value') and _is_cyrillic(ru[0]['value']):
        return ru[0]['value']
    wd = entry.get('weatherDesc', [{}])
    en = wd[0].get('value', '').strip() if wd else ''
    return _WEATHER_RU.get(en, en)

def _fetch_weather():
    import subprocess, json
    try:
        r = subprocess.run(
            ['curl', '-s', '-k', '--max-time', '15',
             'http://wttr.in/56.5026,52.4776?format=j1&lang=ru'],
            capture_output=True, text=True, timeout=20)

        if r.returncode != 0:
            print(f'Weather fetch failed: rc={r.returncode}')
            return

        data = json.loads(r.stdout)
        cc = data.get('current_condition', [{}])[0]
        weather = data.get('weather', [])

        current = dict(
            desc=_wd(cc),
            temp=cc.get('temp_C', ''),
            feels_like=cc.get('FeelsLikeC', ''),
            humidity=cc.get('humidity', ''),
            precip=cc.get('precipMM', '0'),
            pressure=cc.get('pressure', ''),
            uv=cc.get('uvIndex', ''),
            wind_speed=cc.get('windspeedKmph', ''),
            wind_dir=cc.get('winddir16Point', '')
        )

        time_map = {'morning': '900', 'day': '1500', 'evening': '1800', 'night': '2100'}
        periods = ['morning', 'day', 'evening', 'night']

        forecast = []
        for day in weather:
            day_fc = {'date': day.get('date', '')}
            hourly = {h.get('time', ''): h for h in day.get('hourly', [])}
            for pname in periods:
                h = hourly.get(time_map[pname], {})
                day_fc[pname] = dict(
                    desc=_wd(h) if h else '',
                    temp=h.get('tempC', '') if h else '',
                    feels_like=h.get('FeelsLikeC', '') if h else '',
                    humidity=h.get('humidity', '') if h else '',
                    precip=h.get('precipMM', '0') if h else '0',
                    pressure=h.get('pressure', '') if h else '',
                    wind_speed=h.get('windspeedKmph', '') if h else '',
                    wind_dir=h.get('winddir16Point', '') if h else ''
                )
            # Store raw hourly data for disease risk calculation
            day_fc['hourly'] = []
            for h in day.get('hourly', []):
                day_fc['hourly'].append({
                    'time': h.get('time', ''),
                    'tempC': h.get('tempC', ''),
                    'precipMM': h.get('precipMM', '0'),
                    'humidity': h.get('humidity', '')
                })
            forecast.append(day_fc)

        result = {'current': current, 'forecast': forecast}
        with _weather_lock:
            _weather_cache['data'] = result
            _weather_cache['ts'] = time.time()
        print(f'Weather updated (desc={_wd(cc)}, temp={cc.get("temp_C","")}, forecast days={len(forecast)})')
    except Exception as e:
        print(f'Weather fetch error: {e}')

def _estimate_wetness_hours(hourly):
    rain_blocks = 0
    dew_blocks = 0
    consec_rain = 0
    max_consec_rain = 0
    for h in hourly:
        try:
            precip = float(h.get("precipMM", 0))
            humidity = float(h.get("humidity", 0))
        except (ValueError, TypeError):
            continue
        if precip > 0:
            rain_blocks += 1
            consec_rain += 1
            max_consec_rain = max(max_consec_rain, consec_rain)
        else:
            consec_rain = 0
            if humidity > 85:
                dew_blocks += 1
    return rain_blocks, dew_blocks, max_consec_rain
def _t_coef_phytophthora(t):
    if t < 12 or t > 25:
        return 0.0
    if t <= 14:
        return 0.5
    if t <= 20:
        return 1.0
    return 0.8  # 21-24

def _t_coef_alternaria(t):
    if t < 15 or t > 30:
        return 0.3
    if t <= 20:
        return 1.0
    if t <= 28:
        return 0.8
    return 0.5  # 29-30

def _w_coef_phyto(rain_blocks, dew_blocks, max_consec_rain):
    rain_h = rain_blocks * 3
    dew_h = dew_blocks * 3
    total_wet = rain_h + dew_h
    max_rain_h = max_consec_rain * 3
    # Level 1.0: continuous rain >=4h OR total wet >=8h
    if max_rain_h >= 4 or total_wet >= 8:
        return 1.0
    # Level 0.7: dew 4-7h OR any rain (1-3h)
    if (4 <= dew_h <= 7) or rain_blocks >= 1:
        return 0.7
    # Level 0.4: dew 2-3h
    if 2 <= dew_h <= 3:
        return 0.4
    return 0.0

def _w_coef_alt(rain_blocks, dew_blocks, max_consec_rain):
    rain_h = rain_blocks * 3
    dew_h = dew_blocks * 3
    total_wet = rain_h + dew_h
    max_rain_h = max_consec_rain * 3
    # Level 1.0: continuous rain >=4h OR total wet >=8h
    if max_rain_h >= 4 or total_wet >= 8:
        return 1.0
    # Level 0.7: dew 3-6h OR any rain (1-3h)
    if (3 <= dew_h <= 6) or rain_blocks >= 1:
        return 0.7
    # Level 0.4: dew 1-2h
    if 1 <= dew_h <= 2:
        return 0.4
    return 0.0

def _calc_disease_risk(forecast, stage='mid'):
    """Calculate phytophthora and alternaria risk for forecast days."""
    stage_thresholds = {
        'early': 2.2,  # before canopy closure
        'mid': 1.8,    # canopy closure - budding
        'late': 1.5    # flowering - tuber growth
    }
    threshold = stage_thresholds.get(stage, 1.8)

    days = []
    for day in forecast:
        hourly = day.get('hourly', [])
        if not hourly:
            continue
        # Average temperature from hourly data
        temps = []
        for h in hourly:
            try:
                temps.append(float(h.get('tempC', 0)))
            except (ValueError, TypeError):
                pass
        if not temps:
            continue
        avg_temp = sum(temps) / len(temps)

        rain_blocks, dew_blocks, max_consec_rain = _estimate_wetness_hours(hourly)
        tc_p = _t_coef_phytophthora(avg_temp)
        tc_a = _t_coef_alternaria(avg_temp)
        wc_p = _w_coef_phyto(rain_blocks, dew_blocks, max_consec_rain)
        wc_a = _w_coef_alt(rain_blocks, dew_blocks, max_consec_rain)

        days.append({
            'date': day.get('date', ''),
            'avg_temp': round(avg_temp, 1),
            'rain_blocks': rain_blocks,
            'dew_blocks': dew_blocks,
            'r_phytophthora': round(tc_p * wc_p, 2),
            'r_alternaria': round(tc_a * wc_a, 2)
        })

    # Sum over all days
    r_phyto = sum(d['r_phytophthora'] for d in days)
    r_alt = sum(d['r_alternaria'] for d in days)

    def risk_level(val, thresh):
        if val >= thresh:
            return 'high'
        if val >= thresh - 0.5:
            return 'moderate'
        return 'low'

    def recommendation(phyto, alt, thresh):
        if phyto >= thresh or alt >= thresh:
            return 'Plan protective treatment within 1-2 days'
        if phyto >= thresh - 0.5 or alt >= thresh - 0.5:
            return 'Monitor closely, prepare treatment'
        return 'No urgent action needed'

    return {
        'phytophthora': {
            'total': round(r_phyto, 2),
            'risk': risk_level(r_phyto, threshold),
            'per_day': days
        },
        'alternaria': {
            'total': round(r_alt, 2),
            'risk': risk_level(r_alt, threshold),
            'per_day': days
        },
        'threshold': threshold,
        'recommendation': recommendation(r_phyto, r_alt, threshold)
    }

def _get_weather():
    now = time.time()
    with _weather_lock:
        if _weather_cache['data'] and now - _weather_cache['ts'] < WEATHER_CACHE_TTL:
            return _weather_cache['data']
    return None


# -------- Weather history (Open-Meteo archive, free, no key) --------
_weather_pos_cache = {}


def _weather_position():
    """Weather location from the settings.conf base position (no hardcoded coordinates)."""
    if 'pos' not in _weather_pos_cache:
        try:
            pos = rtkbaseconfig.get("main", "position").replace("'", "").split()
            _weather_pos_cache['pos'] = (float(pos[0]), float(pos[1]))
        except Exception:
            _weather_pos_cache['pos'] = (0.0, 0.0)
    return _weather_pos_cache['pos']


WEATHER_HISTORY_TZ = 'Europe/Moscow'
WEATHER_HISTORY_SOURCE = 'openmeteo'
_weather_history_lock = Lock()


def _ensure_weather_table():
    _db.execute(
        "CREATE TABLE IF NOT EXISTS weather_history ("
        "date TEXT PRIMARY KEY,"
        "precip_mm REAL,"
        "temp_max REAL,"
        "temp_min REAL,"
        "temp_mean REAL,"
        "source TEXT,"
        "updated INTEGER"
        ")"
    )
    _db.commit()


def _weather_upsert(days):
    _ensure_weather_table()
    rows = []
    now = int(time.time())
    times = days.get('time', [])
    if not times:
        return 0
    for i, d in enumerate(times):
        rows.append((
            d,
            days.get('precipitation_sum', [None] * len(times))[i],
            days.get('temperature_2m_max', [None] * len(times))[i],
            days.get('temperature_2m_min', [None] * len(times))[i],
            days.get('temperature_2m_mean', [None] * len(times))[i],
            WEATHER_HISTORY_SOURCE,
            now,
        ))
    _db.executemany(
        "INSERT OR REPLACE INTO weather_history "
        "(date, precip_mm, temp_max, temp_min, temp_mean, source, updated) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
    _db.commit()
    return len(rows)


def _fetch_openmeteo_history(start_date, end_date):
    """Fetch daily aggregates for [start_date, end_date] from the archive API."""
    lat, lon = _weather_position()
    url = (
        'https://archive-api.open-meteo.com/v1/archive'
        '?latitude=%s&longitude=%s&start_date=%s&end_date=%s'
        '&daily=precipitation_sum,temperature_2m_max,temperature_2m_min,temperature_2m_mean'
        '&timezone=%s' % (lat, lon, start_date, end_date, WEATHER_HISTORY_TZ)
    )
    r = requests.get(url, timeout=25)
    r.raise_for_status()
    return _weather_upsert(r.json().get('daily', {}))


def _fetch_recent_days():
    """Fill the last few days (archive lags) from the forecast API."""
    lat, lon = _weather_position()
    url = (
        'https://api.open-meteo.com/v1/forecast'
        '?latitude=%s&longitude=%s&past_days=6&forecast_days=1'
        '&daily=precipitation_sum,temperature_2m_max,temperature_2m_min,temperature_2m_mean'
        '&timezone=%s' % (lat, lon, WEATHER_HISTORY_TZ)
    )
    r = requests.get(url, timeout=25)
    r.raise_for_status()
    return _weather_upsert(r.json().get('daily', {}))


def _ensure_weather_history(year=None):
    """Backfill weather_history from Jan 1 of the year to today."""
    import datetime as _dt
    _ensure_weather_table()
    if year is None:
        year = _dt.date.today().year
    start = _dt.date(year, 1, 1)
    today = _dt.date.today()
    if start > today:
        return 0
    have = set(r[0] for r in _db.execute(
        'SELECT date FROM weather_history WHERE date >= ? AND date <= ?',
        (start.isoformat(), today.isoformat())).fetchall())
    missing_start = None
    missing_end = None
    cur = start
    while cur <= today:
        ds = cur.isoformat()
        if ds not in have:
            if missing_start is None:
                missing_start = ds
            missing_end = ds
        cur += _dt.timedelta(days=1)
    if missing_start is None:
        return 0
    with _weather_history_lock:
        n = _fetch_openmeteo_history(missing_start, missing_end)
        try:
            n += _fetch_recent_days()
        except Exception as e:
            print(f'Weather history recent-days fetch error: {e}')
    return n


def _build_history_summary(year=None):
    import datetime as _dt
    if year is None:
        year = _dt.date.today().year
    _ensure_weather_table()
    rows = _db.execute(
        'SELECT date, precip_mm, temp_max, temp_min, temp_mean FROM weather_history '
        'WHERE date >= ? AND date <= ? ORDER BY date',
        ('%04d-01-01' % year, '%04d-12-31' % year)).fetchall()
    months_ru = ['', 'янв', 'фев', 'мар', 'апр', 'май', 'июн',
                 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']
    monthly = []
    for m in range(1, 13):
        monthly.append({'month': m, 'month_ru': months_ru[m],
                        'precip_sum': 0.0, 'temp_sum': 0.0, 'temp_cnt': 0})
    daily = []
    precip_ytd = 0.0
    temp_ytd_sum = 0.0
    temp_ytd_cnt = 0
    for d, prec, tmax, tmin, tmean in rows:
        try:
            prec = float(prec) if prec is not None else 0.0
        except (TypeError, ValueError):
            prec = 0.0
        vals = []
        for v in (tmax, tmin, tmean):
            try:
                vals.append(float(v) if v is not None else None)
            except (TypeError, ValueError):
                vals.append(None)
        tmax, tmin, tmean = vals
        daily.append({'date': d, 'precip_mm': round(prec, 1),
                      'temp_max': tmax, 'temp_min': tmin, 'temp_mean': tmean})
        m = int(d[5:7])
        mi = m - 1
        monthly[mi]['precip_sum'] += prec
        if tmean is not None:
            monthly[mi]['temp_sum'] += tmean
            monthly[mi]['temp_cnt'] += 1
            temp_ytd_sum += tmean
            temp_ytd_cnt += 1
        precip_ytd += prec
    monthly_out = []
    for mm in monthly:
        monthly_out.append({
            'month': mm['month'],
            'month_ru': mm['month_ru'],
            'precip_sum': round(mm['precip_sum'], 1),
            'temp_mean': round(mm['temp_sum'] / mm['temp_cnt'], 1) if mm['temp_cnt'] else None,
        })
    cur_month = _dt.date.today().month
    summary = {
        'precip_ytd': round(precip_ytd, 1),
        'precip_month': round(monthly_out[cur_month - 1]['precip_sum'], 1),
        'precip_month_label': months_ru[cur_month],
        'temp_mean_ytd': round(temp_ytd_sum / temp_ytd_cnt, 1) if temp_ytd_cnt else None,
        'temp_mean_month': monthly_out[cur_month - 1]['temp_mean'],
        'temp_mean_month_label': months_ru[cur_month],
    }
    lat, lon = _weather_position()
    return {
        'year': year,
        'location': {'lat': lat, 'lon': lon, 'name': ''},
        'daily': daily,
        'monthly': monthly_out,
        'summary': summary,
    }


from threading import Thread
from RTKLIB import RTKLIB
from port import changeBaudrateTo115200
from reach_tools import reach_tools, provisioner
from ServiceController import ServiceController
from RTKBaseConfigManager import RTKBaseConfigManager

#print("Installing all required packages")
#provisioner.provision_reach()

#import reach_bluetooth.bluetoothctl
#import reach_bluetooth.tcp_bridge

from threading import Thread
from flask_bootstrap import Bootstrap4
from flask import Flask, render_template, session, request, flash, url_for, jsonify
from flask import send_file, send_from_directory, redirect, abort
from flask import Response, stream_with_context
from flask import g
from flask_wtf import FlaskForm
from wtforms import PasswordField, BooleanField, SubmitField
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from wtforms.validators import ValidationError, DataRequired, EqualTo
from flask_socketio import SocketIO, emit, disconnect
import urllib
import subprocess
import psutil
import distro

from werkzeug.security import generate_password_hash
from werkzeug.security import check_password_hash
import urllib





from tractor_tracker import tractor_tracker
import gpkg_helper

app = Flask(__name__)
app.debug = False
app.config["SECRET_KEY"] = "secret!"
#app.config["UPLOAD_FOLDER"] = os.path.join(os.path.dirname(__file__), "../logs")
app.config["DOWNLOAD_FOLDER"] = os.path.join(os.path.dirname(__file__), "../data")
app.config["LOGIN_DISABLED"] = False
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 128
app.config['UPLOAD_EXTENSIONS'] = ['.conf', '.txt', 'ini']

rtkbase_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../"))
path_to_rtklib = "/usr/local/bin" #TODO find path with which or another tool
GPKG_PATH = os.path.join(rtkbase_path, 'data', 'tracks.gpkg')
GEOZONE_COLORS = ['#e67e22', '#2980b9', '#27ae60', '#8e44ad', '#d35400', '#1abc9c', '#f39c12', '#2c3e50']

_db = gpkg_helper.connect(GPKG_PATH)

TRACK_DIR = os.path.join(rtkbase_path, 'data', 'tracks')

def migrate_csv_to_gpkg():
    track_dir = TRACK_DIR
    if not os.path.exists(track_dir):
        return
    ips = gpkg_helper.get_track_ips(_db)
    for fname in os.listdir(track_dir):
        if not fname.endswith('.csv'): continue
        ip = fname.split('_')[0]
        if ip in ips: continue
        path = os.path.join(track_dir, fname)
        rows = []
        with open(path) as f:
            r = csv.DictReader(f)
            for row in r:
                rows.append((
                    int(row['time']), float(row['lat']), float(row['lon']),
                    int(row.get('quality', 0)), int(row.get('satellites', 0)),
                    float(row.get('hdop', 0)), float(row.get('altitude', 0))
                ))
        if rows:
            gpkg_helper.add_track_points_batch(_db, ip, rows)
        ips.append(ip)

def migrate_geojson_to_gpkg():
    path = os.path.join(rtkbase_path, 'data', 'geozones.json')
    if not os.path.exists(path):
        return
    with open(path) as f:
        zones = json.load(f)
    for z in zones:
        existing = gpkg_helper.get_geozone_by_id(_db, z['id'])
        if existing: continue
        gpkg_helper.create_geozone(
            _db, z['id'], z.get('name', 'Unnamed'),
            z['points'], z.get('color', '#e67e22'), z.get('created', int(time.time()))
        )
    os.rename(path, path + '.bak')

_migrated = False
def ensure_migrated():
    global _migrated
    if _migrated:
        return
    _migrated = True
    try:
        migrate_csv_to_gpkg()
    except Exception as e:
        print('CSV migration error:', e)
    try:
        migrate_geojson_to_gpkg()
    except Exception as e:
        print('GeoJSON migration error:', e)


login=LoginManager(app)
login.login_view = 'login_page'
socketio = SocketIO(app)
bootstrap = Bootstrap4(app)

#Get settings from settings.conf.default and settings.conf
rtkbaseconfig = RTKBaseConfigManager(os.path.join(rtkbase_path, "settings.conf.default"), os.path.join(rtkbase_path, "settings.conf"))

rtk = RTKLIB(socketio,
            rtklib_path=path_to_rtklib,
            log_path=app.config["DOWNLOAD_FOLDER"],
            )

services_list = [{"service_unit" : "str2str_tcp.service", "name" : "main"},
                 {"service_unit" : "str2str_ntrip_A.service", "name" : "ntrip_A"},
                 {"service_unit" : "str2str_ntrip_B.service", "name" : "ntrip_B"},
                 {"service_unit" : "str2str_local_ntrip_caster.service", "name" : "local_ntrip_caster"},
                 {"service_unit" : "str2str_rtcm_svr.service", "name" : "rtcm_svr"},
                 {'service_unit' : 'str2str_rtcm_serial.service', "name" : "rtcm_serial"},
                 {"service_unit" : "str2str_file.service", "name" : "file"},
                 {"service_unit" : "tracks_sniffer.service", "name" : "tracks"},
                 {'service_unit' : 'rtkbase_archive.timer', "name" : "archive_timer"}, 
                 {'service_unit' : 'rtkbase_archive.service', "name" : "archive_service"},
                 ]

#Delay before rtkrcv will stop if no user is on status.html page
rtkcv_standby_delay = 600
connected_clients = 0

class User(UserMixin):
    """ Class for user authentification """
    def __init__(self, username):
        self.id=username
        self.password_hash = rtkbaseconfig.get("general", "web_password_hash")

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class LoginForm(FlaskForm):
    """ Class for the loginform"""
    #username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Please enter the password:', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Sign In')

def update_password(config_object):
    """
        Check in settings.conf if web_password entry contains a value
        If yes, this function will generate a new hash for it and
        remove the web_password value
        :param config_object: a RTKBaseConfigManager instance
    """
    new_password = config_object.get("general", "new_web_password")
    if new_password != "":
        config_object.update_setting("general", "web_password_hash", generate_password_hash(new_password))
        config_object.update_setting("general", "new_web_password", "")
        
def manager():
    """ This manager runs inside a separate thread
        It checks how long rtkrcv is running since the last user leaves the
        status web page, and stop rtkrcv when sleep_count reaches rtkrcv_standby delay
        And it sends various system informations to the web interface
    """
    max_cpu_temp = 0
    cpu_temp_offset = int(rtkbaseconfig.get("general", "cpu_temp_offset"))
    services_status = getServicesStatus(emit_pingback=False)
    main_service = {}
    while True:
        # Make sure max_cpu_temp is always updated
        cpu_temp = get_cpu_temp() + cpu_temp_offset
        max_cpu_temp = max(cpu_temp, max_cpu_temp)

        if connected_clients > 0:
            # We only need to emit to the socket if there are clients able to receive it.
            updated_services_status = getServicesStatus(emit_pingback=False)
            main_service = updated_services_status[0]
            if  services_status != updated_services_status:
                services_status = updated_services_status
                socketio.emit("services status", json.dumps(services_status), namespace="/test")
                print("service status", services_status)

            volume_usage = get_volume_usage()
            sys_infos = {"cpu_temp" : cpu_temp,
                        "max_cpu_temp" : max_cpu_temp,
                        "uptime" : get_uptime(),
                        "volume_free" : round(volume_usage.free / 10E8, 2),
                        "volume_used" : round(volume_usage.used / 10E8, 2),
                        "volume_total" : round(volume_usage.total / 10E8, 2),
                        "volume_percent_used" : volume_usage.percent}
            socketio.emit("sys_informations", json.dumps(sys_infos), namespace="/test")

            tractors = tractor_tracker.get_all_tractors()
            socketio.emit("tractors update", json.dumps(tractors), namespace="/test")
        
        if rtk.sleep_count > rtkcv_standby_delay and rtk.state != "inactive" or \
                 main_service.get("active") == False and rtk.state != "inactive":
            print("DEBUG Stopping rtkrcv")
            if rtk.stopBase() == 1:
                rtk.sleep_count = 0
        elif rtk.sleep_count > rtkcv_standby_delay:
            print("I'd like to stop rtkrcv (sleep_count = {}), but rtk.state is: {}".format(rtk.sleep_count, rtk.state))
        time.sleep(1)

def repaint_services_button(services_list):
    """
       set service color on web app frontend depending on the service status:
       status = running => green button
        status = auto-restart => orange button (alert)
        result = exit-code => red button (danger)
    """ 
    for service in services_list:
        if service.get("status") == "running":
            service["btn_color"] = "success"
        #elif service.get("status") == "dead":
        #    service["btn_color"] = "danger"
        elif service.get("result") == "exit-code":
            service["btn_color"] = "warning"
        elif service.get("status") == "auto-restart":
            service["btn_color"] = "warning"

        if service.get("state_ok") == False:
            service["btn_off_color"] = "outline-danger"
        elif service.get("state_ok") == True:
            service["btn_off_color"] = "outline-secondary"
        
    return services_list

def old_get_cpu_temp():
    try:
        with open('/sys/class/thermal/thermal_zone0/temp', 'r') as ftemp:
            current_temp = int(ftemp.read()) / 1000
        print(current_temp)
    except:
        print("can't get cpu temp")
        current_temp = 75
    return current_temp

def get_cpu_temp():
    try:
        temps = psutil.sensors_temperatures()
        current_cpu_temp = round(temps.get('cpu_thermal')[0].current, 1)
    except:
        current_cpu_temp = 0
    return current_cpu_temp

def get_uptime():
    return round(time.time() - psutil.boot_time())

def get_volume_usage(volume = rtk.logm.log_path):
    try:
        volume_info = psutil.disk_usage(volume)
    except FileNotFoundError:
        volume_info = psutil.disk_usage("/")
    return volume_info

def get_sbc_model():
    """
        Try to detect the single board computer used
        :return the model name or unknown if not detected
    """
    answer = subprocess.run(["cat", "/proc/device-tree/model"], encoding="UTF-8", stderr=subprocess.PIPE, stdout=subprocess.PIPE)
    if answer.returncode == 0:
        sbc_model = answer.stdout.split("\n").pop().strip()
    else:
        sbc_model = "unknown"
    return sbc_model

@socketio.on("check update", namespace="/test")
def check_update(source_url = None, current_release = None, prerelease=rtkbaseconfig.getboolean("general", "prerelease"), emit = True):
    """
        Check if a RTKBase update exists
        :param source_url: the url where we will try to find an update. It uses the github api.
        :param current_release: The current RTKBase release
        :param prerelease: True/False Get prerelease or not
        :param emit: send the result to the web front end with socketio
        :return The new release version inside a dict (release version and url for this release)
    """
    ## test
    #new_release = {'url' : 'http://localhost', 'new_release' : "3.9", "comment" : "blabla"}
    #if emit:
    #    socketio.emit("new release", json.dumps(new_release), namespace="/test")
    #return new_release
    ## test

    new_release = {}
    source_url = source_url if source_url is not None else "https://api.github.com/repos/stefal/rtkbase/releases"
    current_release = current_release if current_release is not None else rtkbaseconfig.get("general", "version").strip("v")
    current_release = current_release.split("-beta", 1)[0].split("-alpha", 1)[0].split("-rc", 1)[0].split("b", 1)[0]
    
    try:    
        response = requests.get(source_url)
        response = response.json()
        for release in response:
            if release.get("prerelease") & prerelease or release.get("prerelease") == False:
                latest_release = release.get("tag_name").strip("v").replace("-beta", "").replace("-alpha", "").replace("-rc", "")
                if latest_release > current_release and latest_release <= rtkbaseconfig.get("general", "checkpoint_version"):
                    new_release = {"new_release" : release.get("tag_name"), "comment" : release.get("body")}
                    #find url for rtkbase.tar.gz
                    for i, asset in enumerate(release["assets"]):
                        if "rtkbase.tar.gz" in asset["name"]:
                            new_release["url"] = asset.get("browser_download_url")
                            break
                    break
             
    except Exception as e:
        print("Check update error: ", e)
        new_release = { "error" : repr(e)}
        
    if emit:
        socketio.emit("new release", json.dumps(new_release), namespace="/test")
    return new_release

@socketio.on("update rtkbase", namespace="/test")
def update_rtkbase(update_file=False):
    """
        Check if a RTKBase update exists, download it and update rtkbase
        if update_file is a link to a file, use it to update rtkbase (mainly used for dev purpose)
    """

    shutil.rmtree("/var/tmp/rtkbase", ignore_errors=True)
    import tarfile

    if not update_file:
        #Check if an update is available
        update_url = check_update(emit=False).get("url")
        if update_url is None:
            return
        #Download update
        update_archive = download_update(update_url)
    else:
        #update from file
        update_file.save("/var/tmp/rtkbase_update.tar.gz")
        update_archive = "/var/tmp/rtkbase_update.tar.gz"
        print("update stored in /var/tmp/")
    
    if update_archive is None:
        socketio.emit("downloading_update", json.dumps({"result": 'false'}), namespace="/test")
        return
    else:
        socketio.emit("downloading_update", json.dumps({"result": 'true'}), namespace="/test")

    #Get the "root" folder in the archive
    tar = tarfile.open(update_archive)
    for tarinfo in tar:
        if tarinfo.isdir():
            primary_folder = tarinfo.name
            break
    #Delete previous update directory
    try:
        os.rmdir("/var/tmp/rtkbase")
    except FileNotFoundError:
        print("/var/tmp/rtkbase directory doesn't exist")
        
    #Extract archive
    tar.extractall("/var/tmp")

    source_path = os.path.join("/var/tmp/", primary_folder)
    script_path = os.path.join(source_path, "rtkbase_update.sh")
    current_release = rtkbaseconfig.get("general", "version").strip("v")
    standard_user = rtkbaseconfig.get("general", "user")
    #launch update verifications
    answer = subprocess.run([script_path, source_path, rtkbase_path, app.config["DOWNLOAD_FOLDER"].split("/")[-1], current_release, standard_user, "--checking"], encoding="UTF-8", stderr=subprocess.PIPE, stdout=subprocess.PIPE)
    if answer.returncode != 0:
        socketio.emit("updating_rtkbase_stopped", json.dumps({"error" : answer.stderr.splitlines()}), namespace="/test")
    else : #if ok, launch update script
        print("Launch update")
        socketio.emit("updating_rtkbase", namespace="/test")
        rtk.shutdownBase()
        time.sleep(1)
        os.execl(script_path, "unused arg0", source_path, rtkbase_path, app.config["DOWNLOAD_FOLDER"].split("/")[-1], current_release, standard_user)

def download_update(update_path):
    update_archive = "/var/tmp/rtkbase_update.tar.gz"
    try:
        response = requests.get(update_path)
        with open(update_archive, "wb") as f:
            f.write(response.content)
    except Exception as e:
        print("Error: Can't download update - ", e)
        return None
    else:
        return update_archive

@app.before_request
def inject_release():
    """
        Insert the RTKBase release number as a global variable for Flask/Jinja
    """
    g.version = rtkbaseconfig.get("general", "version")
    g.sbc_model = get_sbc_model()

@login.user_loader
def load_user(id):
    return User(id)

@app.route('/')
@app.route('/index')
@app.route('/status')
@login_required
def status_page():
    """
        The status web page with the gnss satellites levels and a map
    """
    base_position = rtkbaseconfig.get("main", "position").replace("'", "").split()
    base_coordinates = {"lat" : base_position[0], "lon" : base_position[1]}
    return render_template("status.html", base_coordinates = base_coordinates, tms_key = {"maptiler_key" : rtkbaseconfig.get("general", "maptiler_key")})

@app.route('/settings')
@login_required
def settings_page():
    """
        The settings page where you can manage the various services, the parameters, update, power...
    """
    main_settings = rtkbaseconfig.get_main_settings()
    ntrip_A_settings = rtkbaseconfig.get_ntrip_A_settings()
    ntrip_B_settings = rtkbaseconfig.get_ntrip_B_settings()
    local_ntripc_settings = rtkbaseconfig.get_local_ntripc_settings()
    file_settings = rtkbaseconfig.get_file_settings()
    tracks_settings = rtkbaseconfig.get_tracks_settings()
    rtcm_svr_settings = rtkbaseconfig.get_rtcm_svr_settings()
    rtcm_serial_settings = rtkbaseconfig.get_rtcm_serial_settings()

    return render_template("settings.html", main_settings = main_settings,
                                            ntrip_A_settings = ntrip_A_settings,
                                            ntrip_B_settings = ntrip_B_settings,
                                            local_ntripc_settings = local_ntripc_settings,
                                            file_settings = file_settings,
                                            tracks_settings = tracks_settings,
                                            rtcm_svr_settings = rtcm_svr_settings,
                                            rtcm_serial_settings = rtcm_serial_settings,
                                            os_infos = distro.info(),)

@app.route('/logs')
@login_required
def logs_page():
    """
        The data web pages where you can download/delete the raw gnss data
    """
    return render_template("logs.html")

@app.route("/logs/download/<path:log_name>")
@login_required
def downloadLog(log_name):
    """ Route for downloading raw gnss data"""
    try:
        full_log_path = rtk.logm.log_path + "/" + log_name
        if log_name == 'tracks.gpkg' or log_name == 'tracks':
            gpkg_helper.wal_checkpoint(_db)
        return send_file(full_log_path, as_attachment = True)
    except FileNotFoundError:
        abort(404)

@app.route('/api/download/tracks')
def download_tracks():
    """Download tracks.gpkg with WAL checkpoint before serving."""
    r = gpkg_helper.wal_checkpoint(_db)
    if r is not None and r[0] != 0:
        print(f'WAL checkpoint busy ({r[0]}), retrying...')
        r = gpkg_helper.wal_checkpoint(_db)
    return send_file(GPKG_PATH, as_attachment=True, download_name='tracks.gpkg')

@app.route('/api/download_session_csv/<username>/<int:ts>')
@login_required
def download_session_csv(username, ts):
    import glob, datetime
    log_dir = app.config["DOWNLOAD_FOLDER"] + "/session_logs"
    if not os.path.isdir(log_dir):
        abort(404)
    dt = datetime.datetime.fromtimestamp(ts)
    prefix = username + "_" + dt.strftime("%d.%m.%Y") + "_"
    best = None
    for f in sorted(glob.glob(log_dir + "/" + prefix + "*.csv")):
        best = f
    if best and os.path.isfile(best):
        return send_file(best, as_attachment=True, mimetype="text/csv")
    abort(404)

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if current_user.is_authenticated:
        return redirect(url_for('status_page'))
    loginform = LoginForm()
    if loginform.validate_on_submit():
        user = User('admin')
        password = loginform.password.data
        if not user.check_password(password):
            return abort(401)
        
        login_user(user, remember=loginform.remember_me.data)
        next_page = request.args.get('next')
        if not next_page or urllib.parse.urlsplit(next_page).netloc != '':
            next_page = url_for('status_page')

        return redirect(next_page)
        
    return render_template('login.html', title='Sign In', form=loginform)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login_page'))

@app.route('/diagnostic')
@login_required
def diagnostic():
    """
    Get services journal and status
    """
    getServicesStatus()
    rtkbase_web_service = {'service_unit' : 'rtkbase_web.service', 'name' : 'RTKBase Web Server', 'active' : True}
    logs = []
    for service in services_list + [rtkbase_web_service]:
        sysctl_status = subprocess.run(['systemctl', 'status', service['service_unit']],
                                stdout=subprocess.PIPE,
                                universal_newlines=True)
        journalctl = subprocess.run(['journalctl', '--since', '7 days ago', '-u', service['service_unit']], 
                                 stdout=subprocess.PIPE, 
                                 universal_newlines=True)
        
        #Replace carrier return to <br> for html view
        sysctl_status = sysctl_status.stdout.replace('\n', '<br>') 
        journalctl = journalctl.stdout.replace('\n', '<br>')
        active_state = "Active" if service.get('active') == True else "Inactive"
        logs.append({'name' : service['service_unit'], 'active' : active_state, 'sysctl_status' : sysctl_status, 'journalctl' : journalctl})
        
    return render_template('diagnostic.html', logs = logs)
    
@app.route('/manual_update', methods=['GET', 'POST'])       
@login_required
def upload_file():
    if request.method == 'POST':
        uploaded_file = request.files['file']
        if uploaded_file.filename != '':
            update_rtkbase(uploaded_file)
        return "Updating....please refresh in a few minutes"
    return render_template('manual_update.html')

@app.route('/api/tractor_position', methods=['POST'])
@login_required
def receive_tractor_position():
    data = request.json
    tid = data.get('id', 'unknown')
    lat = data.get('lat')
    lon = data.get('lon')
    seq = data.get('seq')
    if lat is not None and lon is not None:
        tractor_tracker.update_position(tid, lat, lon, seq)
        return json.dumps({"ack": seq, "status": "ok"})
    return json.dumps({"error": "invalid data"})

@app.route('/api/tractor_ips')
@login_required
def tractor_ips():
    """Return list of all known tractor usernames from tracks + session_logs."""
    import glob
    ips = set()
    try:
        ips.update(gpkg_helper.get_track_ips(_db))
    except:
        pass
    log_dir = app.config["DOWNLOAD_FOLDER"] + "/session_logs"
    try:
        for f in glob.glob(log_dir + "/*.csv"):
            name = os.path.basename(f).split('_')[0]
            if name:
                ips.add(name)
    except:
        pass
    ips = {i for i in ips if not re.match(r'^\d+\.\d+\.\d+\.\d+$', i)}
    return json.dumps(sorted(ips))

@app.route('/api/tractor_track/<ip>')
@login_required
def tractor_track(ip):
    ensure_migrated()
    from_ts = request.args.get('from', type=int)
    to_ts = request.args.get('to', type=int)
    points = gpkg_helper.get_track(_db, ip)
    if not points or not isinstance(points, list):
        points = []
        files = [f for f in os.listdir(TRACK_DIR) if f.startswith(ip) and f.endswith('.csv')]
        if files:
            path = os.path.join(TRACK_DIR, sorted(files)[-1])
            with open(path) as f2:
                r = csv.DictReader(f2)
                for row in r:
                    points.append({
                        't': int(row['time']), 'lat': float(row['lat']), 'lon': float(row['lon']),
                        'q': int(row.get('quality', 0)), 's': int(row.get('satellites', 0)),
                        'h': float(row.get('hdop', 0)), 'alt': float(row.get('altitude', 0))
                    })
    if from_ts is not None or to_ts is not None:
        points = [p for p in points
                  if (from_ts is None or p.get('t', 0) >= from_ts) and
                     (to_ts is None or p.get('t', 0) <= to_ts)]
    return json.dumps(points)

@app.route('/api/tractor_track/<ip>/last_session')
@login_required
def tractor_track_last_session(ip):
    ensure_migrated()
    points = gpkg_helper.get_track(_db, ip)
    if not points:
        return json.dumps([])
    points.sort(key=lambda p: p['t'])
    GAP = 300
    sessions = []
    cur = []
    for p in points:
        if not cur:
            cur = [p]
        elif p['t'] - cur[-1]['t'] <= GAP:
            cur.append(p)
        else:
            sessions.append(cur)
            cur = [p]
    if cur:
        sessions.append(cur)
    if not sessions:
        return json.dumps([])
    last = sessions[-1]
    simplified = [{'t': p['t'], 'lat': p['lat'], 'lon': p['lon']} for p in last]
    return json.dumps(simplified)

@app.route('/api/tractor_track/<ip>/last')
@login_required
def tractor_track_last(ip):
    ensure_migrated()
    pt = gpkg_helper.get_last_track_point(_db, ip)
    if not pt:
        # Fallback: last point from CSV
        files = [f for f in os.listdir(TRACK_DIR) if f.startswith(ip) and f.endswith('.csv')]
        if files:
            path = os.path.join(TRACK_DIR, sorted(files)[-1])
            with open(path) as f2:
                rows = list(csv.DictReader(f2))
                if rows:
                    r = rows[-1]
                    pt = {'t': int(r['time']), 'lat': float(r['lat']), 'lon': float(r['lon']),
                          'quality': int(r.get('quality', 0)), 'satellites': int(r.get('satellites', 0)),
                          'hdop': float(r.get('hdop', 0)), 'altitude': float(r.get('altitude', 0))}
    return json.dumps(pt)

@app.route('/api/tractor_track/<ip>', methods=['DELETE'])
@login_required
def delete_tractor_track(ip):
    """Delete all track data for a tractor."""
    gpkg_helper.delete_tractor_tracks(_db, ip)
    return json.dumps({'ok': True})

@app.route('/tractor_map')
@login_required
def tractor_map_page():
    base_position = rtkbaseconfig.get("main", "position").replace("'", "").split()
    base_coordinates = {"lat": float(base_position[0]), "lon": float(base_position[1])}
    resp = app.make_response(render_template("tractor_map.html", base_coordinates=base_coordinates))
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp




@app.route('/api/geozones')
@login_required
def list_geozones():
    ensure_migrated()
    return json.dumps(gpkg_helper.list_geozones(_db))

@app.route('/api/geozones', methods=['POST'])
@login_required
def create_geozone():
    data = json.loads(request.data)
    zones = gpkg_helper.list_geozones(_db)
    zone_id = 'zone_' + str(int(time.time()))
    color = GEOZONE_COLORS[len(zones) % len(GEOZONE_COLORS)]
    now = int(time.time())
    gpkg_helper.create_geozone(_db, zone_id, data.get('name', 'Unnamed'), data['points'], color, now)
    return json.dumps(gpkg_helper.get_geozone_by_id(_db, zone_id))

@app.route('/api/geozones/<zone_id>', methods=['PUT'])
@login_required
def update_geozone(zone_id):
    data = json.loads(request.data)
    gpkg_helper.update_geozone(_db, zone_id, data)
    zone = gpkg_helper.get_geozone_by_id(_db, zone_id)
    if not zone:
        return (json.dumps({'error': 'not found'}), 404)
    return json.dumps(zone)

@app.route('/api/geozones/<zone_id>', methods=['DELETE'])
@login_required
def delete_geozone(zone_id):
    _delete_ndvi_for_zone(zone_id)
    gpkg_helper.delete_geozone(_db, zone_id)
    # Delete tracks linked to this zone
    gpkg_helper.delete_field_tracks_by_zone(_db, zone_id)
    # Delete field details linked to this zone
    gpkg_helper.delete_field_details_by_zone(_db, zone_id)
    # Delete field operations linked to this zone
    _ensure_field_ops_table()
    _db.execute('DELETE FROM field_ops WHERE zone_id=?', (zone_id,))
    _db.commit()
    # Delete movement alerts linked to this zone
    _ensure_field_alerts_table()
    _db.execute('DELETE FROM field_alerts WHERE zone_id=?', (zone_id,))
    _db.commit()
    return json.dumps({'ok': True})


def _delete_ndvi_for_zone(zone_id):
    """Remove cached NDVI rows and files for a geozone (called on delete)."""
    import glob as _glob
    import os as _os
    try:
        file_paths = set()
        for table in ('ndvi_scenes_v2', 'ndvi_scenes', 'ndvi_contrast_v2'):
            try:
                for (fp,) in _db.execute(f'SELECT file_path FROM {table} WHERE zone_id=?', (zone_id,)):
                    if fp:
                        file_paths.add(fp)
            except Exception:
                pass
        for fp in file_paths:
            base = fp.rsplit('.', 1)[0] if '.' in fp else fp
            for p in _glob.glob(base + '*'):
                try:
                    _os.remove(p)
                except OSError:
                    pass
        for table in ('ndvi_scenes_v2', 'ndvi_scenes', 'ndvi_contrast_v2'):
            try:
                _db.execute(f'DELETE FROM {table} WHERE zone_id=?', (zone_id,))
            except Exception:
                pass
        _db.commit()
    except Exception as e:
        print(f'NDVI cleanup for zone {zone_id} failed: {e}')


# -------- Field operations (учёт работ на поле) --------

def _ensure_field_ops_table():
    _db.execute(
        "CREATE TABLE IF NOT EXISTS field_ops ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "zone_id TEXT NOT NULL,"
        "op_date TEXT NOT NULL,"
        "op_type TEXT NOT NULL,"
        "crop TEXT,"
        "machinery TEXT,"
        "operator TEXT,"
        "area_ha REAL,"
        "material TEXT,"
        "dose TEXT,"
        "amount REAL,"
        "fuel_l REAL,"
        "cost REAL,"
        "notes TEXT,"
        "track_data TEXT,"
        "created INTEGER DEFAULT (strftime('%s','now')),"
        "updated INTEGER DEFAULT (strftime('%s','now'))"
        ")"
    )
    try:
        cols = [r[1] for r in _db.execute('PRAGMA table_info(field_ops)').fetchall()]
        if 'track_data' not in cols:
            _db.execute('ALTER TABLE field_ops ADD COLUMN track_data TEXT')
    except Exception:
        pass
    try:
        _db.execute("CREATE INDEX IF NOT EXISTS idx_field_ops_zone ON field_ops(zone_id)")
    except Exception:
        pass
    _db.commit()

_FIELD_OP_COLS = ['id', 'zone_id', 'op_date', 'op_type', 'crop', 'machinery', 'operator',
                  'area_ha', 'material', 'dose', 'amount', 'fuel_l', 'cost', 'notes',
                  'track_data', 'created', 'updated']


def _field_op_row(r):
    return dict(zip(_FIELD_OP_COLS, r))


@app.route('/api/geozones/<zone_id>/ops')
@login_required
def list_field_ops(zone_id):
    _ensure_field_ops_table()
    _sel = ', '.join(_FIELD_OP_COLS)
    rows = _db.execute(f'SELECT {_sel} FROM field_ops WHERE zone_id=? ORDER BY op_date DESC, id DESC', (zone_id,)).fetchall()
    return json.dumps([_field_op_row(r) for r in rows])


@app.route('/api/geozones/<zone_id>/ops', methods=['POST'])
@login_required
def create_field_op(zone_id):
    _ensure_field_ops_table()
    body = json.loads(request.data)
    op_type = (body.get('op_type') or '').strip()
    if not op_type:
        return json.dumps({'error': 'op_type required'}), 400
    now = int(time.time())
    op_date = body.get('op_date') or time.strftime('%Y-%m-%d')
    _db.execute(
        'INSERT INTO field_ops (zone_id, op_date, op_type, crop, machinery, operator, area_ha, material, dose, amount, fuel_l, cost, notes, track_data, created, updated) '
        'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
        (zone_id, op_date, op_type,
         body.get('crop'), body.get('machinery'), body.get('operator'),
         body.get('area_ha'), body.get('material'), body.get('dose'), body.get('amount'),
         body.get('fuel_l'), body.get('cost'), body.get('notes'), body.get('track_data'), now, now))
    _db.commit()
    _sel = ', '.join(_FIELD_OP_COLS)
    row = _db.execute(f'SELECT {_sel} FROM field_ops WHERE id=last_insert_rowid()').fetchone()
    return json.dumps(_field_op_row(row))


@app.route('/api/geozones/<zone_id>/ops/<int:op_id>', methods=['PUT'])
@login_required
def update_field_op(zone_id, op_id):
    _ensure_field_ops_table()
    body = json.loads(request.data)
    now = int(time.time())
    _db.execute(
        'UPDATE field_ops SET op_date=?, op_type=?, crop=?, machinery=?, operator=?, area_ha=?, material=?, dose=?, amount=?, fuel_l=?, cost=?, notes=?, track_data=?, updated=? '
        'WHERE id=? AND zone_id=?',
        (body.get('op_date'), body.get('op_type'),
         body.get('crop'), body.get('machinery'), body.get('operator'),
         body.get('area_ha'), body.get('material'), body.get('dose'), body.get('amount'),
         body.get('fuel_l'), body.get('cost'), body.get('notes'), body.get('track_data'), now, op_id, zone_id))
    _db.commit()
    _sel = ', '.join(_FIELD_OP_COLS)
    row = _db.execute(f'SELECT {_sel} FROM field_ops WHERE id=? AND zone_id=?', (op_id, zone_id)).fetchone()
    if not row:
        return json.dumps({'error': 'not found'}), 404
    return json.dumps(_field_op_row(row))


@app.route('/api/geozones/<zone_id>/ops/<int:op_id>', methods=['DELETE'])
@login_required
def delete_field_op(zone_id, op_id):
    _ensure_field_ops_table()
    _db.execute('DELETE FROM field_ops WHERE id=? AND zone_id=?', (op_id, zone_id))
    _db.commit()
    return json.dumps({'ok': True})


def _find_field_for_zone(zone_name):
    """Find field_data name matching a geozone name (exact, then normalized containment)."""
    try:
        _ensure_field_table()
        names = [r[0] for r in _db.execute('SELECT name FROM field_data').fetchall()]
    except Exception:
        return None
    if not names:
        return None
    zl = (zone_name or '').strip().lower()
    if not zl:
        return None
    for n in names:
        if n.strip().lower() == zl:
            return n
    import re as _re
    znorm = _re.sub(r'[^a-z0-9\u0430-\u044f\u0451]', '', zl)
    if not znorm:
        return None
    best = None
    for n in names:
        nn = _re.sub(r'[^a-z0-9\u0430-\u044f\u0451]', '', n.lower())
        if not nn:
            continue
        if znorm in nn or nn in znorm:
            if best is None or len(nn) < len(best):
                best = n
    return best


@app.route('/api/geozones/<zone_id>/yield')
@login_required
def get_geozone_yield_summary(zone_id):
    zone = gpkg_helper.get_geozone_by_id(_db, zone_id)
    if not zone:
        return json.dumps({'error': 'not found'}), 404
    summary = {'count': 0, 'min': None, 'max': None, 'avg': None, 'total_area_ha': 0}
    name = _find_field_for_zone(zone.get('name'))
    if name:
        try:
            row = _db.execute('SELECT data FROM field_data WHERE name=?', (name,)).fetchone()
        except Exception:
            row = None
    else:
        row = None
    if row:
        try:
            data = json.loads(row[0])
        except Exception:
            data = None
        if data and data.get('yieldData'):
            recs = (data['yieldData'].get('records') or [])
            vals = []
            area = 0.0
            for r in recs:
                try:
                    v = float(r.get('yieldCenHa'))
                except (TypeError, ValueError):
                    continue
                vals.append(v)
                try:
                    area += float(r.get('patchAreaM2') or 0)
                except (TypeError, ValueError):
                    pass
            if vals:
                summary['count'] = len(vals)
                summary['min'] = round(min(vals), 2)
                summary['max'] = round(max(vals), 2)
                summary['avg'] = round(sum(vals) / len(vals), 2)
                summary['total_area_ha'] = round(area / 10000.0, 2)
    return json.dumps(summary)


# -------- Детекция движения тракторов по геозонам (список для оператора) --------

def _ensure_field_alerts_table():
    _db.execute(
        "CREATE TABLE IF NOT EXISTS field_alerts ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "zone_id TEXT NOT NULL,"
        "zone_name TEXT,"
        "tractor_ip TEXT NOT NULL,"
        "alert_date TEXT NOT NULL,"
        "first_seen INTEGER,"
        "last_seen INTEGER,"
        "points INTEGER DEFAULT 0,"
        "distance_km REAL DEFAULT 0,"
        "status TEXT DEFAULT 'pending',"
        "created INTEGER DEFAULT (strftime('%s','now')),"
        "updated INTEGER DEFAULT (strftime('%s','now')),"
        "UNIQUE(zone_id, tractor_ip, alert_date)"
        ")"
    )
    try:
        _db.execute("CREATE INDEX IF NOT EXISTS idx_field_alerts_status ON field_alerts(status)")
    except Exception:
        pass
    _db.commit()


_BASE_STATION_IPS = {'basegnss', 'Base', 'BASE'}


def _point_in_poly(lat, lon, poly):
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        yi, xi = poly[i][0], poly[i][1]
        yj, xj = poly[j][0], poly[j][1]
        if ((yi > lat) != (yj > lat)) and (lon < (xj - xi) * (lat - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def _haversine_km(lat1, lon1, lat2, lon2):
    import math
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _scan_field_alerts(window_hours=48):
    """Find recent track points inside geozone polygons and upsert field_alerts.

    A visit is a run of points of one tractor inside one zone with gaps <= 30 min.
    Alerts with >= 2 points become pending (status resets to 'pending' on new movement).
    """
    _ensure_field_alerts_table()
    zones = gpkg_helper.list_geozones(_db)
    if not zones:
        return []
    since = int(time.time()) - window_hours * 3600
    rows = _db.execute('SELECT ip, time, geom FROM tracks WHERE time >= ?', (since,)).fetchall()

    events = []
    for ip, t, geom in rows:
        if ip in _BASE_STATION_IPS:
            continue
        try:
            lat, lon = gpkg_helper.parse_wkb_point(geom)
        except Exception:
            continue
        for z in zones:
            pts = z.get('points')
            if not pts:
                continue
            lats = [p[0] for p in pts]
            lons = [p[1] for p in pts]
            if not (min(lats) - 0.0001 <= lat <= max(lats) + 0.0001 and min(lons) - 0.0001 <= lon <= max(lons) + 0.0001):
                continue
            if _point_in_poly(lat, lon, pts):
                events.append((z['id'], z.get('name'), ip, t, lat, lon))
                break

    events.sort(key=lambda e: (e[0], e[2], e[3]))
    import datetime as _dt
    now = int(time.time())
    made = []
    i = 0
    while i < len(events):
        zid, zname, ip, t0, lat0, lon0 = events[i]
        j = i
        last = t0
        cnt = 1
        dist = 0.0
        prev_lat, prev_lon = lat0, lon0
        while j + 1 < len(events) and events[j + 1][0] == zid and events[j + 1][2] == ip and (events[j + 1][3] - last) <= 1800:
            j += 1
            nlat, nlon = events[j][4], events[j][5]
            dist += _haversine_km(prev_lat, prev_lon, nlat, nlon)
            prev_lat, prev_lon = nlat, nlon
            last = events[j][3]
            cnt += 1
        if cnt >= 2:
            d = _dt.datetime.fromtimestamp(last).strftime('%Y-%m-%d')
            _db.execute(
                'INSERT INTO field_alerts (zone_id, zone_name, tractor_ip, alert_date, first_seen, last_seen, points, distance_km, status, created, updated) '
                'VALUES (?,?,?,?,?,?,?,?,?,?,?) '
                'ON CONFLICT(zone_id, tractor_ip, alert_date) DO UPDATE SET '
                'last_seen=excluded.last_seen, first_seen=MIN(field_alerts.first_seen, excluded.first_seen), '
                'points=excluded.points, distance_km=excluded.distance_km, updated=excluded.updated',
                (zid, zname, ip, d, t0, last, cnt, round(dist, 2), 'pending', now, now))
            made.append((zid, zname, ip, d))
        i = j + 1
    _db.commit()
    return made


def _alerts_json():
    _ensure_field_alerts_table()
    cols = ['id', 'zone_id', 'zone_name', 'tractor_ip', 'alert_date', 'first_seen', 'last_seen', 'points', 'distance_km', 'status', 'created', 'updated']
    rows = _db.execute('SELECT id, zone_id, zone_name, tractor_ip, alert_date, first_seen, last_seen, points, distance_km, status, created, updated '
                       'FROM field_alerts ORDER BY status, last_seen DESC').fetchall()
    items = [dict(zip(cols, r)) for r in rows]
    return json.dumps({'pending': [i for i in items if i['status'] == 'pending'],
                       'processed': [i for i in items if i['status'] == 'processed']})


@app.route('/api/alerts/scan')
@login_required
def scan_field_alerts_endpoint():
    _scan_field_alerts(48)
    return _alerts_json()


@app.route('/api/alerts')
@login_required
def list_field_alerts():
    return _alerts_json()


@app.route('/api/alerts/<int:alert_id>/process', methods=['POST'])
@login_required
def process_field_alert(alert_id):
    _ensure_field_alerts_table()
    _db.execute('UPDATE field_alerts SET status=? WHERE id=?', ('processed', alert_id))
    _db.commit()
    return json.dumps({'ok': True})


@app.route('/api/alerts/<int:alert_id>', methods=['DELETE'])
@login_required
def delete_field_alert(alert_id):
    _ensure_field_alerts_table()
    _db.execute('UPDATE field_alerts SET status=? WHERE id=?', ('hidden', alert_id))
    _db.commit()
    return json.dumps({'ok': True})


@app.route('/api/geozones/<zone_id>/tracks')
@login_required
def list_geozone_tracks(zone_id):
    try:
        tracks = gpkg_helper.list_field_tracks_by_zone(_db, zone_id)
        return json.dumps(tracks)
    except Exception as e:
        return (json.dumps({'error': str(e)}), 500)



#### Path Planning Endpoint ####
try:
    import path_planner
except Exception:
    path_planner = None

@app.route("/api/geozones/<zone_id>/generate_path", methods=["POST"])
@login_required
def generate_path(zone_id):
    try:
        if path_planner is None:
            return (json.dumps({"error": "Path planner unavailable (GDAL not installed)"}), 500)
        data = json.loads(request.data)
        swath_width = float(data.get("swath_width", 10))
        angle = float(data.get("angle", 0))
        turning_radius = float(data.get("turning_radius", 0))
        offset = float(data.get("offset", 0))
        boundary_pass = data.get("boundary_pass", False)
        zone = gpkg_helper.get_geozone_by_id(_db, zone_id)
        if not zone:
            return (json.dumps({"error": "Zone not found"}), 404)
        points = zone.get("points", [])
        if len(points) < 3:
            return (json.dumps({"error": "Zone has < 3 points"}), 400)
        result = path_planner.generate_coverage_path(points, swath_width, angle, turning_radius, offset, boundary_pass)
        if result is None:
            return (json.dumps({"error": "Could not generate path"}), 500)
        return json.dumps(result)
    except Exception as e:
        return (json.dumps({"error": str(e)}), 500)

@app.route("/api/geozones/<zone_id>/snap_point", methods=["POST"])
@login_required
def snap_point(zone_id):
    try:
        if path_planner is None:
            return json.dumps({"error": "Path planner unavailable (GDAL not installed)"})
        data = json.loads(request.data)
        lat = float(data.get("lat", 0))
        lon = float(data.get("lon", 0))
        zone = gpkg_helper.get_geozone_by_id(_db, zone_id)
        if not zone:
            return (json.dumps({"error": "Zone not found"}), 404)
        points = zone.get("points", [])
        if len(points) < 3:
            return json.dumps({"lat": lat, "lon": lon, "snapped": False, "distance_m": 0})
        snapped_lat, snapped_lon, dist, snapped = path_planner.snap_to_polygon(points, lat, lon)
        return json.dumps({"lat": snapped_lat, "lon": snapped_lon, "distance_m": dist, "snapped": snapped})
    except Exception as e:
        return (json.dumps({"error": str(e)}), 500)

@app.route("/api/geozones/<zone_id>/tasks", methods=["GET"])
@login_required
def list_path_tasks(zone_id):
    return json.dumps(gpkg_helper.list_path_tasks(_db, zone_id))

@app.route("/api/geozones/<zone_id>/tasks", methods=["POST"])
@login_required
def create_path_task(zone_id):
    try:
        data = json.loads(request.data)
        task_id = gpkg_helper.create_path_task(
            _db, zone_id,
            data.get("name", "Unnamed Task"),
            float(data.get("swath_width", 10)),
            float(data.get("angle", 0)),
            data.get("path_geojson", "{}"),
            float(data.get("total_length_m", 0)),
            int(data.get("num_swaths", 0))
        )
        return json.dumps({"id": task_id, "ok": True})
    except Exception as e:
        return (json.dumps({"error": str(e)}), 500)

@app.route("/api/tasks/<int:task_id>", methods=["DELETE"])
@login_required
def delete_path_task(task_id):
    gpkg_helper.delete_path_task(_db, task_id)
    return json.dumps({"ok": True})

@app.route("/api/geozones/<zone_id>/tasks/<int:task_id>/path", methods=["GET"])
@login_required
def get_path_task_path(zone_id, task_id):
    task = gpkg_helper.get_path_task(_db, task_id)
    if not task:
        return (json.dumps({"error": "Task not found"}), 404)
    return task["path_geojson"]

#### NDVI Endpoints ####
import ndvi_helper

@app.route("/api/ndvi/layers")
@login_required
def list_ndvi_layers():
    return json.dumps(ndvi_helper.get_ndvi_layers())

@app.route("/api/ndvi/calculate/<zone_id>", methods=["POST"])
@login_required
def calculate_ndvi(zone_id):
    try:
        result = ndvi_helper.calc_ndvi_for_zone(zone_id)
        contrast_result = ndvi_helper.calc_contrast_ndvi_for_zone(zone_id)
        if "error" in result and "error" in contrast_result:
            return (json.dumps({"error": result["error"], "contrast_error": contrast_result["error"]}), 400)
        return json.dumps({"standard": result, "contrast": contrast_result}, default=str)
    except Exception as e:
        return (json.dumps({"error": str(e)}), 500)

@app.route("/api/ndvi/scenes")
@login_required
def get_ndvi_scenes():
    from flask import request
    zone_id = request.args.get("zone_id")
    return json.dumps(ndvi_helper.get_ndvi_dates(zone_id), default=str)

@app.route("/api/ndvi/scenes/<zone_id>")
@login_required
def get_ndvi_scenes_for_zone(zone_id):
    return json.dumps(ndvi_helper.get_ndvi_dates(zone_id), default=str)

@app.route("/api/ndvi/overlay/<zone_id>.png")
@login_required
def serve_ndvi_overlay(zone_id):
    from flask import request, make_response
    scene_date = request.args.get("date")
    png_bytes, bbox = ndvi_helper.get_ndvi_overlay(zone_id, scene_date)
    if png_bytes is None:
        return ("", 404)
    response = make_response(png_bytes)
    response.headers["Content-Type"] = "image/png"
    response.headers["X-Bbox"] = json.dumps(bbox)
    return response

@app.route("/api/ndvi/overlay/<zone_id>.tif")

@login_required

def serve_ndvi_geotiff(zone_id):

    """Download NDVI raster as GeoTIFF for QGIS."""

    from flask import request

    scene_date = request.args.get("date")

    tif_data, fname = ndvi_helper.get_ndvi_geotiff(zone_id, scene_date)

    if tif_data is None:

        return ("", 404)

    response = make_response(tif_data)

    response.headers["Content-Type"] = "image/tiff"

    response.headers["Content-Disposition"] = f'attachment; filename="{fname}"'

    return response

@app.route("/api/ndvi/data/<zone_id>")
@login_required
def get_ndvi_data(zone_id):
    from flask import request
    scene_date = request.args.get("date")
    layers = ndvi_helper.get_ndvi_layers()
    for layer in layers:
        if layer["zone_id"] == zone_id:
            if not scene_date or layer.get("scene_date") == scene_date:
                return json.dumps(layer, default=str)
    return (json.dumps({"error": "No NDVI data for this zone"}), 404)

#### Contrast NDVI Endpoints ####

@app.route("/api/ndvi/contrast/layers")
@login_required
def list_contrast_ndvi_layers():
    return json.dumps(ndvi_helper.get_contrast_ndvi_layers())

@app.route("/api/ndvi/contrast/scenes")
@login_required
def get_contrast_ndvi_scenes():
    from flask import request
    zone_id = request.args.get("zone_id")
    return json.dumps(ndvi_helper.get_contrast_ndvi_dates(zone_id), default=str)

@app.route("/api/ndvi/contrast/scenes/<zone_id>")
@login_required
def get_contrast_ndvi_scenes_for_zone(zone_id):
    return json.dumps(ndvi_helper.get_contrast_ndvi_dates(zone_id), default=str)

@app.route("/api/ndvi/contrast/overlay/<zone_id>.png")
@login_required
def serve_contrast_ndvi_overlay(zone_id):
    from flask import request, make_response
    scene_date = request.args.get("date")
    png_bytes, bbox = ndvi_helper.get_contrast_ndvi_overlay(zone_id, scene_date)
    if png_bytes is None:
        return ("", 404)
    response = make_response(png_bytes)
    response.headers["Content-Type"] = "image/png"
    response.headers["X-Bbox"] = json.dumps(bbox)
    return response

@app.route("/api/ndvi/contrast/data/<zone_id>")
@login_required
def get_contrast_ndvi_data(zone_id):
    from flask import request
    scene_date = request.args.get("date")
    layers = ndvi_helper.get_contrast_ndvi_layers()
    for layer in layers:
        if layer["zone_id"] == zone_id:
            if not scene_date or layer.get("scene_date") == scene_date:
                return json.dumps(layer, default=str)
    return (json.dumps({"error": "No contrast NDVI data for this zone"}), 404)

#### Handle connect/disconnect events ####

@socketio.on("connect", namespace="/test")
def testConnect():
    global connected_clients
    connected_clients += 1
    print("Browser client connected")
    rtk.sendState()

@socketio.on("disconnect", namespace="/test")
def testDisconnect():
    global connected_clients
    connected_clients -=1
    print("Browser client disconnected")

#### Log list handling ###

@socketio.on("get logs list", namespace="/test")
def getAvailableLogs():
    #print("DEBUG updating logs")
    rtk.logm.updateAvailableLogs()
    #print("Updated logs list is " + str(rtk.logm.available_logs))
    rtk.socketio.emit("available logs", rtk.logm.available_logs, namespace="/test")

#### str2str launch/shutdown handling ####

@socketio.on("launch base", namespace="/test")
def launchBase():
    rtk.launchBase()

@socketio.on("shutdown base", namespace="/test")
def shutdownBase():
    rtk.shutdownBase()

#### str2str start/stop handling ####

@socketio.on("start base", namespace="/test")
def startBase():
    saved_input_type = rtkbaseconfig.get("main", "receiver_format").strip("'")
    #check if the main service is running and the gnss format is correct. If not, don't try to start rtkrcv with startBase() 
    if services_list[0].get("active") is False or saved_input_type not in ["rtcm2","rtcm3","nov","oem3","ubx","ss2","hemis","stq","javad","nvs","binex","rt17","sbf"]:
        print("DEBUG: Can't start rtkrcv as main service isn't enabled or gnss format is wrong")
        result = {"result" : "failed"}
        socketio.emit("base starting", json.dumps(result), namespace="/test")
        return
    # We must start rtkcv before trying to modify an option
    rtk.startBase()
    saved_input_path = "localhost" + ":" + rtkbaseconfig.get("main", "tcp_port").strip("'")
    if rtk.get_rtkcv_option("inpstr1-path") != saved_input_path:
        rtk.set_rtkcv_option("inpstr1-path", saved_input_path)
        rtk.set_rtkcv_pending_refresh(True)
    if rtk.get_rtkcv_option("inpstr1-format") != saved_input_type:
        rtk.set_rtkcv_option("inpstr1-format", saved_input_type)
        rtk.set_rtkcv_pending_refresh(True)
    
    if rtk.get_rtkcv_pending_status():
        print("REFRESH NEEDED !!!!!!!!!!!!!!!!")
        rtk.startBase()
    
@socketio.on("stop base", namespace="/test")
def stopBase():
    rtk.stopBase()

@socketio.on("on graph", namespace="/test")
def continueBase():
    rtk.sleep_count = 0

#### Free space handler

@socketio.on("get available space", namespace="/test")
def getAvailableSpace():
    rtk.socketio.emit("available space", reach_tools.getFreeSpace(path_to_gnss_log), namespace="/test")

#### Delete log button handler ####

@socketio.on("delete log", namespace="/test")
def deleteLog(json_msg):
    rtk.logm.deleteLog(json_msg.get("name"))
    # Sending the the new available logs
    getAvailableLogs()

#### Detect GNSS receiver button handler ####

@socketio.on("detect_receiver", namespace="/test")
def detect_receiver(json_msg):
    print("Detecting gnss receiver")
    #print("DEBUG json_msg: ", json_msg)
    answer = subprocess.run([os.path.join(rtkbase_path, "tools", "install.sh"), "--user", rtkbaseconfig.get("general", "user"), "--detect-gnss", "--no-write-port"], encoding="UTF-8", stderr=subprocess.PIPE, stdout=subprocess.PIPE)
    if answer.returncode == 0 and "/dev/" in answer.stdout:
        #print("DEBUG ok stdout: ", answer.stdout)
        try:
            device_info = next(x for x in answer.stdout.splitlines() if x.startswith('/dev/')).split(' - ')
            port, gnss_type, speed = [x.strip() for x in device_info]
            result = {"result" : "success", "port" : port, "gnss_type" : gnss_type, "port_speed" : speed}
            result.update(json_msg)
        except Exception:
            result = {"result" : "failed"}
    else:
        #print("DEBUG Not ok stdout: ", answer.stdout)
        result = {"result" : "failed"}
    #result = {"result" : "failed"}
    #result = {"result" : "success", "port" : "bestport", "gnss_type" : "F12P"}
    #print('DEBUG result: ', result)
    socketio.emit("gnss_detection_result", json.dumps(result), namespace="/test")

@socketio.on("configure_receiver", namespace="/test")
def configure_receiver(brand="u-blox", model="F9P"):
    # only ZED-F9P could be configured automaticaly
    # After port detection, the main service will be restarted, and it will take some time. But we have to stop it to
    # configure the receiver. We wait 2 seconds before stopping it to remove conflicting calls.
    time.sleep(4)
    main_service = services_list[0]
    if main_service.get("active") is True:
        main_service["unit"].stop()
        restart_main = True
    else:
        restart_main = False

    print("configuring {} gnss receiver model {}".format(brand, model))
    answer = subprocess.run([os.path.join(rtkbase_path, "tools", "install.sh"), "--user", rtkbaseconfig.get("general", "user"), "--configure-gnss"], encoding="UTF-8", stderr=subprocess.PIPE, stdout=subprocess.PIPE)
    #print("DEBUG - stdout: ", answer.stdout)
    #print("DEBUG - returncode: ", answer.returncode)

    if answer.returncode == 0: # and "Done" in answer.stdout:
        result = {"result" : "success"}
        rtkbaseconfig.reload_settings()
    else:
        result = {"result" : "failed"}
    if restart_main is True:
        #print("DEBUG: Restarting main service after F9P configuration")
        main_service["unit"].start()
    #result = {"result" : "success"}
    socketio.emit("gnss_configuration_result", json.dumps(result), namespace="/test")

#### Settings Backup Restore Reset ####

@socketio.on("reset settings", namespace="/test")
def reset_settings():
    switchService({"name":"main", "active":False})
    rtkbaseconfig.merge_default_and_user(os.path.join(rtkbase_path, "settings.conf.default"), os.path.join(rtkbase_path, "settings.conf.default"))
    rtkbaseconfig.write_file()
    socketio.emit("settings_reset", namespace="/test")

@app.route("/logs/download/settings")
@login_required
def backup_settings():
    settings_file_name = str("RTKBase_{}_{}_{}.conf".format(rtkbaseconfig.get("general", "version"), rtkbaseconfig.get("ntrip_A", "mnt_name_a").strip("'"), time.strftime("%Y-%m-%d_%HH%M")))
    return send_file(os.path.join(rtkbase_path, "settings.conf"), as_attachment=True, download_name=settings_file_name)

@socketio.on("restore settings", namespace="/test")
def restore_settings_file(json_msg):
    #print("DEBUG: type: ", type(json_msg))
    #print("DEBUG: print msg: ", msg)
    #print("DEBUG: filename: ", json_msg["filename"])
    try:
        if not json_msg["filename"].lower().endswith(".conf"):
            raise TypeError("Wrong file type")
        if not "[general]" in json_msg["data"].decode():
            raise ValueError(("Not a valid RTKBase settings file"))
        tmp_file = tempfile.NamedTemporaryFile()
        with open(tmp_file.name, 'wb') as file:
            file.write(json_msg["data"])
        rtkbaseconfig.restore_settings(os.path.join(rtkbase_path, "settings.conf.default"), tmp_file.name)
    except TypeError as e:
        #print("DEBUG: ", e)
        result= {"result" : "failed", "msg" : "The file should be a .conf filetype"}
    except ValueError as e:
        #print("DEBUG: ", e)
        result= {"result" : "failed", "msg" : "The file is invalid"}
    except Exception as e:
        #print("DEBUG: Settings restoration error")
        #print("DEBUG: ", e)
        result= {"result" : "failed", "msg" : "Unknown error"}
    else:
        result= {"result" : "success", "msg" : "Successful restoration, You will be redirect to the login page in 5 seconds"}
        restartServices()
    finally:
        socketio.emit("restore_settings_result", json.dumps(result), namespace="/test")

#### Convert ubx file to rinex ####

@socketio.on("rinex conversion", namespace="/test")
def rinex_ign(json_msg):
    #print("DEBUG: json convbin: ", json_msg)
    rinex_type = {"rinex_ign" : "ign", "rinex_nrcan" : "nrcan", "rinex_30s_full" : "30s_full", "rinex_1s_full" : "1s_full"}.get(json_msg.get("rinex-preset"))
    convpath = os.path.abspath(os.path.join(rtkbase_path, "tools", "convbin.sh"))
    convbin_user = rtkbaseconfig.get("general", "user").strip("'")
    #print("DEBUG", convpath, json_msg.get("filename"), rtk.logm.log_path, rinex_type)
    answer = subprocess.run(["sudo", "-u", convbin_user, convpath, json_msg.get("filename"), rtk.logm.log_path, rinex_type], encoding="UTF-8", stderr=subprocess.PIPE, stdout=subprocess.PIPE)
    if answer.returncode == 0 and "rinex_file=" in answer.stdout:
        rinex_file = answer.stdout.split("\n").pop().strip("rinex_file=")
        result = {"result" : "success", "file" : rinex_file}
    else:
        result = {"result" : "failed", "msg" : answer.stderr}
    #print("DEBUG: ", result)
    socketio.emit("rinex ready", json.dumps(result), namespace="/test")

#### Download and convert log handlers ####

@socketio.on("process log", namespace="/test")
def processLog(json_msg):
    log_name = json_msg.get("name")

    print("Got signal to process a log, name = " + str(log_name))
    print("Path to log == " + rtk.logm.log_path + "/" + str(log_name))

    raw_log_path = rtk.logm.log_path + "/" + log_name
    rtk.processLogPackage(raw_log_path)

@socketio.on("cancel log conversion", namespace="/test")
def cancelLogConversion(json_msg):
    log_name = json_msg.get("name")
    raw_log_path = rtk.logm.log_path + "/" + log_name
    rtk.cancelLogConversion(raw_log_path)

#### RINEX versioning ####

@socketio.on("read RINEX version", namespace="/test")
def readRINEXVersion():
    rinex_version = rtk.logm.getRINEXVersion()
    rtk.socketio.emit("current RINEX version", {"version": rinex_version}, namespace="/test")

@socketio.on("write RINEX version", namespace="/test")
def writeRINEXVersion(json_msg):
    rinex_version = json_msg.get("version")
    rtk.logm.setRINEXVersion(rinex_version)

#### Device hardware functions ####

@socketio.on("reboot device", namespace="/test")
def rebootRtkbase():
    print("Rebooting...")
    rtk.shutdown()
    #socketio.stop() hang. I disabled it
    #socketio.stop()
    subprocess.check_output("reboot")

@socketio.on("shutdown device", namespace="/test")
def shutdownRtkbase():
    print("Shutdown...")
    rtk.shutdown()
    #socketio.stop() hang. I disabled it
    #socketio.stop()
    subprocess.check_output(["shutdown", "now"])

@socketio.on("turn off wi-fi", namespace="/test")
def turnOffWiFi():
    print("Turning off wi-fi")
#    subprocess.check_output("rfkill block wlan", shell = True)

#### Systemd Services functions ####

def load_units(services):
    """
        load unit service before getting status
        :param services: A list of systemd services (dict) containing a service_unit key:value
        :return The dict list updated with the pystemd ServiceController object

        example: 
            services = [{"service_unit" : "str2str_tcp.service"}]
            return will be [{"service_unit" : "str2str_tcp.service", "unit" : a pystemd object}]
        
    """
    for service in services:
        service["unit"] = ServiceController(service["service_unit"])
    return services

def update_std_user(services):
    """
        check which user run str2str_file service and update settings.conf
        :param services: A list of systemd services (dict) containing a service_unit key:value
    """
    service = next(x for x in services_list if x["name"] == "file")
    user = service["unit"].getUser()
    rtkbaseconfig.update_setting("general", "user", user)

def restartServices(restart_services_list=None):
    """
        Restart already running services
        This function will refresh all services status, then compare the global services_list and 
        the restart_services_list to find the services we need to restart.
        #TODO I don't really like this global services_list use.
    """
    if restart_services_list == None:
        restart_services_list = [unit["name"] for unit in services_list if unit["name"] not in ("archive_timer", "archive_service")]
    #Update services status
    for service in services_list:
        service["active"] = service["unit"].isActive()

    #Restart running services
    for restart_service in restart_services_list:
        for service in services_list:
            if service["name"] == restart_service and service["active"] is True:
                print("Restarting service: ", service["name"])
                if service["name"] == "main":
                    #the main service should be stopped during at least 1 second to let rtkrcv stop too.
                    #another solution would be to call rtk.stopbase()
                    service["unit"].stop()
                    time.sleep(1.5)
                    service["unit"].start()
                else:
                    service["unit"].restart()
    
    #refresh service status
    getServicesStatus()

@socketio.on("get services status", namespace="/test")
def getServicesStatus(emit_pingback=True):
    """
        Get the status of services listed in services_list
        (services_list is global)
        
        :param emit_pingback: whether or not the services status is sent to clients 
            (defaults to true as the socketio.on() should receive back the information)
        :return The gathered services status list
    """

    #print("Getting services status")
    try:
        for service in services_list:
            #print("unit qui d??conne : ", service["name"])
            service["active"] = service["unit"].isActive()
            service["status"] = service["unit"].status()
            service["result"] = service["unit"].get_result()
            if service.get("result") == "success" and service.get("status") == "running":
                service["state_ok"] = True
            elif service.get("result") == "exit-code":
                service["state_ok"] = False
            else:
                service["state_ok"] = None

    except Exception as e:
        #print("Error getting service info for: {} - {}".format(service['name'], e))
        #TODO manage better the error with rtkbase_archive.service. See https://github.com/Stefal/rtkbase/issues/162
        #and try to remove this "pass" without any notification (bad practive)
        pass

    services_status = []
    for service in services_list: 
        services_status.append({key:service[key] for key in service if key != 'unit'})
    
    services_status = repaint_services_button(services_status)
    #print(services_status)
    if emit_pingback:
        socketio.emit("services status", json.dumps(services_status), namespace="/test")
    return services_status

@socketio.on("services switch", namespace="/test")
def switchService(json_msg):
    """
        Start or stop some systemd services
        As a service could need some time to start or stop, there is a 5 seconds sleep
        before refreshing the status.
        param: json_msg: A json var from the web front end containing one or more service
        name with their new status.
    """
    #print("Received service to switch", json_msg)
    try:
        for service in services_list:
            if json_msg["name"] == service["name"] and json_msg["active"] == True:
                print("Trying to start service {}".format(service["name"]))
                service["unit"].start()
            elif json_msg["name"] == service["name"] and json_msg["active"] == False:
                print("Trying to stop service {}".format(service["name"]))
                service["unit"].stop()

    except Exception as e:
        print(e)
    # finally not needed anymore since the service status is refreshed continuously
    # with the manager
    #finally:
    #    time.sleep(5)
    #    getServicesStatus()

@socketio.on("form data", namespace="/test")
def update_settings(json_msg):
    """
        Get the form data from the web front end, and save theses values to settings.conf
        Then restart the services which have a dependency with these parameters.
        param json_msg: A json variable containing the source form and the new paramaters
    """
    #print("received settings form", json_msg)
    source_section = json_msg.pop().get("source_form")
    #print("section: ", source_section)
    if source_section == "change_password":
        if json_msg[0].get("value") == json_msg[1].get("value"):
            rtkbaseconfig.update_setting("general", "new_web_password", json_msg[0].get("value"))
            update_password(rtkbaseconfig)
            socketio.emit("password updated", namespace="/test")

        else:
            print("ERROR, WRONG PASSWORD!")
    else:
        for form_input in json_msg:
            #print("name: ", form_input.get("name"))
            #print("value: ", form_input.get("value"))
            rtkbaseconfig.update_setting(source_section, form_input.get("name"), form_input.get("value"), write_file=False)
        rtkbaseconfig.write_file()

        #Restart service if needed
        if source_section == "main":
            restartServices(("main", "ntrip_A", "ntrip_B", "local_ntrip_caster", "rtcm_svr", "file", "rtcm_serial", "tracks"))  
        elif source_section == "ntrip_A":
            restartServices(("ntrip_A",))
        elif source_section == "ntrip_B":
            restartServices(("ntrip_B",))
        elif source_section == "local_ntrip_caster":
            restartServices(("local_ntrip_caster",))
        elif source_section == "rtcm_svr":
            restartServices(("rtcm_svr",))
        elif source_section == "rtcm_serial":
            restartServices(("rtcm_serial",))
        elif source_section == "local_storage":
            restartServices(("file",))
        elif source_section == "tracks":
            restartServices(("tracks",))

_sessions_cache = {}

@app.route('/api/tractor_sessions/<username>')
@login_required
def tractor_sessions(username):
    import datetime, time
    now = time.time()
    cached = _sessions_cache.get(username)
    if cached and now - cached[0] < 30:
        return cached[1]
    points = gpkg_helper.get_track(_db, username)
    if not points:
        return json.dumps([])
    points.sort(key=lambda p: p['t'])
    GAP = 300
    sessions = []
    cur = []
    for p in points:
        if not cur:
            cur = [p]
        elif p['t'] - cur[-1]['t'] <= GAP:
            cur.append(p)
        else:
            sessions.append(cur)
            cur = [p]
    if cur:
        sessions.append(cur)
    result = []
    for seg in sessions:
        d = 0
        for i in range(1, len(seg)):
            d += haversine(seg[i-1]['lat'], seg[i-1]['lon'], seg[i]['lat'], seg[i]['lon'])
        result.append({
            'date': datetime.datetime.fromtimestamp(seg[0]['t']).strftime('%d.%m.%Y'),
            'start_time': datetime.datetime.fromtimestamp(seg[0]['t']).strftime('%H:%M:%S'),
            'end_time': datetime.datetime.fromtimestamp(seg[-1]['t']).strftime('%H:%M:%S'),
            'count': len(seg),
            'distance_m': round(d, 1),
            'first_t': seg[0]['t'],
            'last_t': seg[-1]['t']
        })
    result_json = json.dumps(result)
    _sessions_cache[username] = (now, result_json)
    return result_json

def haversine(lat1, lon1, lat2, lon2):
    from math import radians, sin, cos, sqrt, asin
    R = 6371000
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    return 2 * R * asin(sqrt(a))


@app.route('/api/weather')
@login_required
def api_weather():
    data = _get_weather()
    if not data:
        return jsonify({'error': 'no weather data'}), 502
    return jsonify(data)


@app.route('/api/disease_risk')
@login_required
def api_disease_risk():
    data = _get_weather()
    if not data or not data.get('forecast'):
        return jsonify({'phytophthora': {'total': 0, 'risk': 'unknown', 'per_day': []}, 'alternaria': {'total': 0, 'risk': 'unknown', 'per_day': []}, 'recommendation': 'No forecast data'})
    stage = request.args.get('stage', 'mid')
    result = _calc_disease_risk(data['forecast'], stage)
    return jsonify(result)


@app.route('/api/weather/history')
@login_required
def api_weather_history():
    import datetime as _dt
    try:
        year = int(request.args.get('year', 0) or 0)
    except ValueError:
        year = 0
    if not year:
        year = _dt.date.today().year
    _ensure_weather_table()
    try:
        n = _ensure_weather_history(year)
        if n:
            print(f'Weather history backfilled {n} rows for {year}')
    except Exception as e:
        print(f'Weather history fetch error: {e}')
    result = _build_history_summary(year)
    if not result['daily']:
        return jsonify({'error': 'no history data for year %d' % year}), 404
    return jsonify(result)


# -------- AB Lines --------

# -------- Field Import/Export --------
import uuid as _field_uuid

def _ensure_field_table():
    _db.execute(
        "CREATE TABLE IF NOT EXISTS field_data ("
        "id TEXT PRIMARY KEY,"
        "name TEXT UNIQUE NOT NULL,"
        "data TEXT NOT NULL,"
        "created INTEGER DEFAULT (strftime('%s','now')),"
        "updated INTEGER DEFAULT (strftime('%s','now'))"
        ")"
    )
    _db.commit()

@app.route('/api/fields/import', methods=['POST'])
@login_required
def import_field():
    _ensure_field_table()
    body = json.loads(request.data)
    name = body.get('name')
    if not name:
        return jsonify({'error': 'field name required'}), 400
    field_id = _field_uuid.uuid4().hex
    now = int(time.time())
    _db.execute(
        'INSERT INTO field_data (id, name, data, created, updated) VALUES (?, ?, ?, ?, ?) '
        'ON CONFLICT(name) DO UPDATE SET data=excluded.data, updated=excluded.updated',
        (field_id, name, json.dumps(body), now, now)
    )
    _db.commit()
    return jsonify({'id': field_id, 'name': name}), 201

@app.route('/api/fields/<name>/export')
@login_required
def export_field(name):
    _ensure_field_table()
    row = _db.execute('SELECT data FROM field_data WHERE name=?', (name,)).fetchone()
    if not row:
        return jsonify({'error': 'field not found'}), 404
    data = json.loads(row[0])
    return jsonify(data)

@app.route('/api/fields/list')
@login_required
def list_fields():
    _ensure_field_table()
    rows = _db.execute('SELECT name, created, updated FROM field_data ORDER BY name').fetchall()
    return json.dumps([{'name': r[0], 'created': r[1], 'updated': r[2]} for r in rows])

@app.route('/api/fields/<name>', methods=['DELETE'])
@login_required
def delete_field(name):
    _ensure_field_table()
    _db.execute('DELETE FROM field_data WHERE name=?', (name,))
    _db.commit()
    return ('', 204)

@app.route('/api/fields/<name>/rename', methods=['PUT'])
@login_required
def rename_field(name):
    _ensure_field_table()
    body = json.loads(request.data)
    new_name = body.get('new_name')
    if not new_name:
        return jsonify({'error': 'new_name required'}), 400
    now = int(time.time())
    _db.execute('UPDATE field_data SET name=?, updated=? WHERE name=?', (new_name, now, name))
    _db.commit()
    return jsonify({'name': new_name})

@app.route('/api/fields/<name>/duplicate', methods=['POST'])
@login_required
def duplicate_field(name):
    _ensure_field_table()
    body = json.loads(request.data)
    new_name = body.get('new_name', name + ' (копия)')
    row = _db.execute('SELECT data FROM field_data WHERE name=?', (name,)).fetchone()
    if not row:
        return jsonify({'error': 'field not found'}), 404
    data = json.loads(row[0])
    field_id = _field_uuid.uuid4().hex
    now = int(time.time())
    _db.execute(
        'INSERT INTO field_data (id, name, data, created, updated) VALUES (?, ?, ?, ?, ?)',
        (field_id, new_name, json.dumps(data), now, now)
    )
    _db.commit()
    return jsonify({'id': field_id, 'name': new_name}), 201

def _get_field_data(name):
    _ensure_field_table()
    row = _db.execute('SELECT data FROM field_data WHERE name=?', (name,)).fetchone()
    if not row:
        return None
    return json.loads(row[0])

def _save_field_data(name, data, bump=True):
    """Persist field data dict. With bump=False keeps the old updated timestamp so
    the sections cache stays valid (AB line changes don't touch sections)."""
    if bump:
        updated = int(time.time())
    else:
        row = _db.execute('SELECT updated FROM field_data WHERE name=?', (name,)).fetchone()
        updated = row[0] if row else int(time.time())
    _db.execute('UPDATE field_data SET data=?, updated=? WHERE name=?', (json.dumps(data), updated, name))
    _db.commit()

@app.route('/api/fields/<name>/element/<key>', methods=['DELETE'])
@login_required
def delete_field_element(name, key):
    data = _get_field_data(name)
    if data is None:
        return jsonify({'error': 'field not found'}), 404
    if key not in data:
        return jsonify({'error': 'element not found'}), 404
    del data[key]
    _save_field_data(name, data)
    return ('', 204)

@app.route('/api/fields/<name>/element/<key>/copy', methods=['POST'])
@login_required
def copy_field_element(name, key):
    body = json.loads(request.data)
    target_name = body.get('target', name)
    new_key = body.get('new_key', key)
    data = _get_field_data(name)
    if data is None:
        return jsonify({'error': 'source field not found'}), 404
    if key not in data:
        return jsonify({'error': 'element not found'}), 404
    target_data = _get_field_data(target_name)
    if target_data is None:
        return jsonify({'error': 'target field not found'}), 404
    import copy as _copy
    target_data[new_key] = _copy.deepcopy(data[key])
    _save_field_data(target_name, target_data)
    return jsonify({'field': target_name, 'key': new_key})

#### Field → Geozone conversion ####

import math as _math

GEOZONE_COLORS = ['#e67e22','#3498db','#2ecc71','#e74c3c','#9b59b6','#1abc9c','#f39c12','#34495e']

def _local_to_latlon(ref_lat, ref_lon, easting, northing):
    """Approximate conversion from local easting/northing (meters) to WGS84."""
    dlat = northing / 111320.0
    dlon = easting / (111320.0 * _math.cos(ref_lat * _math.pi / 180.0))
    return [ref_lat + dlat, ref_lon + dlon]

def _extract_contour_points(contour):
    """Flatten contour structure to [lat, lon, alt] list."""
    pts = []
    if isinstance(contour, list):
        for entry in contour:
            if isinstance(entry, dict):
                pts.extend(entry.get('points', []))
            elif isinstance(entry, (list, tuple)):
                pts.append(entry)
    return pts

def _extract_field_boundary(data):
    """Return boundary as [[lat, lng], ...]."""
    boundary = data.get('boundary', {})
    polygons = boundary.get('polygons', [])
    if not polygons:
        return []
    pts = polygons[0].get('points', [])
    return [[p[0], p[1]] for p in pts if isinstance(p, (list, tuple)) and len(p) >= 2]


def _get_field_ref(data, boundary_pts):
    """Return (ref_lat, ref_lon) from startFix with fallback to boundary first point."""
    start_fix = data.get('field', {}).get('startFix', {})
    ref_lat = start_fix.get('lat')
    ref_lon = start_fix.get('lon')
    if ref_lat is None or ref_lon is None:
        if boundary_pts:
            ref_lat, ref_lon = boundary_pts[0][0], boundary_pts[0][1]
    if ref_lat is None:
        ref_lat = ref_lon = 0
    return ref_lat, ref_lon


def _local_to_latlon_rad(ref_lat, ref_lon, e, n):
    if e == 0 and n == 0:
        return (ref_lat, ref_lon)
    earth_radius = 6378137.0
    dlat = n / earth_radius
    dlon = e / (earth_radius * math.cos(math.radians(ref_lat)))
    return (ref_lat + math.degrees(dlat), ref_lon + math.degrees(dlon))


def _latlon_to_local_rad(ref_lat, ref_lon, lat, lon):
    earth_radius = 6378137.0
    n = math.radians(lat - ref_lat) * earth_radius
    e = math.radians(lon - ref_lon) * earth_radius * math.cos(math.radians(ref_lat))
    return (e, n)


def _ab_extended_endpoints(ea, na, eb, nb, heading):
    """Extend a straight AB segment 100 m beyond both endpoints along the heading
    direction (mirrors the 100 m tail extensions of curves)."""
    if heading is None:
        heading = math.atan2(eb - ea, nb - na)
    ext = 100.0
    return ((ea - math.sin(heading) * ext, na - math.cos(heading) * ext),
            (eb + math.sin(heading) * ext, nb + math.cos(heading) * ext))


def _extract_fast_details(data, ref_lat, ref_lon):
    """Return {type: (geojson, style)} for tracks, headland, abLine (fast parts)."""
    details = {}

    # headLines -> tracks
    headlines_raw = data.get('headLines', [])
    track_lines = []
    for hl in headlines_raw:
        pts = hl.get('points', hl) if isinstance(hl, dict) else hl
        if len(pts) >= 2:
            track_lines.append(pts)
    tracks_geojson = {'type': 'MultiLineString', 'coordinates': [[[p[1], p[0]] for p in ln] for ln in track_lines]} if track_lines else None
    if tracks_geojson:
        details['tracks'] = (tracks_geojson, {'color': '#3498db', 'weight': 2})

    # headland
    headland_raw = data.get('headland', [])
    headland_lines = []
    for hl in headland_raw:
        pts = hl.get('points', hl) if isinstance(hl, dict) else hl
        if len(pts) >= 2:
            headland_lines.append(pts)
    headland_geojson = {'type': 'MultiLineString', 'coordinates': [[[p[1], p[0]] for p in ln] for ln in headland_lines]} if headland_lines else None
    if headland_geojson:
        details['headland'] = (headland_geojson, {'color': '#e67e22', 'weight': 2, 'dashArray': '6,4'})

    # AB lines
    tracks_ab = data.get('tracks', [])
    ab_lines = []
    for ab_entry in tracks_ab:
        if not isinstance(ab_entry, dict):
            continue
        ptA = ab_entry.get('ptA')
        ptB = ab_entry.get('ptB')
        if not ptA or not ptB:
            continue
        ea = ptA.get('easting')
        na = ptA.get('northing')
        eb = ptB.get('easting')
        nb = ptB.get('northing')
        if ea is None or na is None or eb is None or nb is None:
            continue
        (ea2, na2), (eb2, nb2) = _ab_extended_endpoints(ea, na, eb, nb, ab_entry.get('heading'))
        ll_a = _local_to_latlon_rad(ref_lat, ref_lon, ea2, na2)
        ll_b = _local_to_latlon_rad(ref_lat, ref_lon, eb2, nb2)
        coords = [[ll_a[1], ll_a[0]], [ll_b[1], ll_b[0]]]
        curve_pts = ab_entry.get('curvePts', [])
        if curve_pts and isinstance(curve_pts, list) and len(curve_pts) > 2:
            curve_coords = []
            for cp in curve_pts:
                if isinstance(cp, dict):
                    ce = cp.get('easting', 0)
                    cn = cp.get('northing', 0)
                elif isinstance(cp, (list, tuple)) and len(cp) >= 2:
                    ce, cn = cp[0], cp[1]
                else:
                    continue
                ll = _local_to_latlon_rad(ref_lat, ref_lon, ce, cn)
                curve_coords.append([ll[1], ll[0]])
            if len(curve_coords) >= 2:
                coords = curve_coords
        ab_lines.append(coords)
    if ab_lines:
        ab_geojson = {'type': 'MultiLineString', 'coordinates': ab_lines} if len(ab_lines) > 1 else {'type': 'LineString', 'coordinates': ab_lines[0]}
        details['abLine'] = (ab_geojson, {'color': '#e74c3c', 'weight': 2, 'dashArray': '8,4'})

    return details


_TWO_PI = 2 * math.pi


def _nearest_boundary_index(boundary_local, x, y):
    best = 0
    best_d = float('inf')
    for i, (bx, by) in enumerate(boundary_local):
        d = (bx - x) ** 2 + (by - y) ** 2
        if d < best_d:
            best_d = d
            best = i
    return best


def _order_ab_vertices(start, end, count):
    """Mirror AOG BtnMakeABLine_Click vertex ordering."""
    if abs(start - end) <= count * 0.5:
        if start < end:
            start, end = end, start
    else:
        if start > end:
            start, end = end, start
    return start, end


def _curve_arc_points(boundary_local, start, end):
    """Boundary arc from start to end mirroring AOG BtnMakeCurve_Click traversal."""
    count = len(boundary_local)
    is_loop = abs(start - end) > count * 0.5
    if is_loop:
        if start < end:
            start, end = end, start
        limit = end
        end = count
    else:
        if start > end:
            start, end = end, start
    pts = []
    i = start
    while i < end:
        pts.append(boundary_local[i])
        if is_loop and i == count - 1:
            i = -1
            is_loop = False
            end = limit
        i += 1
    return pts


def _make_point_minimum_spacing(pts, min_distance):
    """Split segments longer than min_distance (mirror CABCurve.MakePointMinimumSpacing)."""
    if len(pts) > 3:
        i = 0
        while i < len(pts) - 1:
            j = i + 1
            d = math.hypot(pts[i][0] - pts[j][0], pts[i][1] - pts[j][1])
            if d > min_distance:
                pts.insert(j, ((pts[i][0] + pts[j][0]) / 2.0, (pts[i][1] + pts[j][1]) / 2.0))
                i = -1
            i += 1
    return pts


def _calculate_headings(pts):
    """Return list of (e, n, heading) mirroring CABCurve.CalculateHeadings."""
    cnt = len(pts)
    if cnt <= 3:
        return [(p[0], p[1], 0.0) for p in pts]
    out = []

    def _h(d_e, d_n):
        h = math.atan2(d_e, d_n)
        if h < 0:
            h += _TWO_PI
        return h

    out.append((pts[0][0], pts[0][1], _h(pts[1][0] - pts[0][0], pts[1][1] - pts[0][1])))
    for i in range(1, cnt - 1):
        out.append((pts[i][0], pts[i][1], _h(pts[i + 1][0] - pts[i - 1][0], pts[i + 1][1] - pts[i - 1][1])))
    out.append((pts[cnt - 1][0], pts[cnt - 1][1], _h(pts[cnt - 1][0] - pts[cnt - 2][0], pts[cnt - 1][1] - pts[cnt - 2][1])))
    return out


def _add_first_last_points(pts):
    """Tail extensions mirroring CABCurve.AddFirstLastPoints (100 pts x 1 m)."""
    result = list(pts)
    last = result[-1]
    for i in range(1, 100):
        result.append((last[0] + math.sin(last[2]) * i, last[1] + math.cos(last[2]) * i, last[2]))
    first = result[0]
    for i in range(1, 100):
        result.insert(0, (first[0] - math.sin(first[2]) * i, first[1] - math.cos(first[2]) * i, first[2]))
    return result


def _build_abline_entry(data, ptA_latlon, ptB_latlon, is_curve):
    """Build an AOG-style track entry from two clicked lat/lon points.

    Straight (AB): chord between the boundary vertices nearest to the clicks.
    Curve: boundary arc between the nearest vertices + min spacing + headings
    + 100 m tail extensions (mirrors AOG FormABDraw).
    Returns (entry dict, ref_lat, ref_lon)."""
    boundary_pts = _extract_field_boundary(data)
    ref_lat, ref_lon = _get_field_ref(data, boundary_pts)
    eA, nA = _latlon_to_local_rad(ref_lat, ref_lon, ptA_latlon[0], ptA_latlon[1])
    eB, nB = _latlon_to_local_rad(ref_lat, ref_lon, ptB_latlon[0], ptB_latlon[1])

    if not boundary_pts:
        if is_curve:
            raise ValueError('нет границы поля - кривая невозможна')
        ptA = {'easting': eA, 'northing': nA}
        ptB = {'easting': eB, 'northing': nB}
        heading = math.atan2(eB - eA, nB - nA)
        if heading < 0:
            heading += _TWO_PI
        return {'mode': 2, 'ptA': ptA, 'ptB': ptB, 'heading': heading,
                'curvePts': [], 'name': 'AB %.1f\u00b0' % math.degrees(heading),
                'isVisible': True, 'nudgeDistance': 0}, ref_lat, ref_lon

    boundary_local = [_latlon_to_local_rad(ref_lat, ref_lon, p[0], p[1]) for p in boundary_pts]
    start = _nearest_boundary_index(boundary_local, eA, nA)
    end = _nearest_boundary_index(boundary_local, eB, nB)

    if is_curve:
        pts = _curve_arc_points(boundary_local, start, end)
        if len(pts) < 4:
            raise ValueError('точки слишком близко - кривая невозможна')
        pts = _make_point_minimum_spacing(pts, 1.6)
        pts = _calculate_headings(pts)
        x = sum(math.cos(p[2]) for p in pts) / len(pts)
        y = sum(math.sin(p[2]) for p in pts) / len(pts)
        heading = math.atan2(y, x)
        if heading < 0:
            heading += _TWO_PI
        arc_first = {'easting': pts[0][0], 'northing': pts[0][1]}
        arc_last = {'easting': pts[-1][0], 'northing': pts[-1][1]}
        pts = _add_first_last_points(pts)
        pts = _calculate_headings(pts)
        curvePts = [{'easting': p[0], 'northing': p[1], 'heading': p[2]} for p in pts]
        return {'mode': 4, 'ptA': arc_first, 'ptB': arc_last, 'heading': heading,
                'curvePts': curvePts, 'name': 'Cu %.1f\u00b0' % math.degrees(heading),
                'isVisible': True, 'nudgeDistance': 0}, ref_lat, ref_lon

    start, end = _order_ab_vertices(start, end, len(boundary_local))
    eA2, nA2 = boundary_local[start]
    eB2, nB2 = boundary_local[end]
    heading = math.atan2(eB2 - eA2, nB2 - nA2)
    if heading < 0:
        heading += _TWO_PI
    return {'mode': 2,
            'ptA': {'easting': eA2, 'northing': nA2},
            'ptB': {'easting': eB2, 'northing': nB2},
            'heading': heading, 'curvePts': [],
            'name': 'AB %.1f\u00b0' % math.degrees(heading),
            'isVisible': True, 'nudgeDistance': 0}, ref_lat, ref_lon


def _track_entry_geometry(entry, ref_lat, ref_lon):
    """Return geojson LineString for a track entry (lng, lat order)."""
    curve = entry.get('curvePts') or []
    if len(curve) > 2:
        coords = []
        for cp in curve:
            if isinstance(cp, dict):
                ll = _local_to_latlon_rad(ref_lat, ref_lon, cp.get('easting', 0), cp.get('northing', 0))
            elif isinstance(cp, (list, tuple)) and len(cp) >= 2:
                ll = _local_to_latlon_rad(ref_lat, ref_lon, cp[0], cp[1])
            else:
                continue
            coords.append([ll[1], ll[0]])
        return {'type': 'LineString', 'coordinates': coords}
    ptA = entry.get('ptA', {})
    ptB = entry.get('ptB', {})
    ea = ptA.get('easting', 0)
    na = ptA.get('northing', 0)
    eb = ptB.get('easting', 0)
    nb = ptB.get('northing', 0)
    (ea2, na2), (eb2, nb2) = _ab_extended_endpoints(ea, na, eb, nb, entry.get('heading'))
    ll_a = _local_to_latlon_rad(ref_lat, ref_lon, ea2, na2)
    ll_b = _local_to_latlon_rad(ref_lat, ref_lon, eb2, nb2)
    return {'type': 'LineString', 'coordinates': [[ll_a[1], ll_a[0]], [ll_b[1], ll_b[0]]]}


def _convert_field_worker(data, name, color, now):
    '''Create geozone + field_details for a field.
    Creates its own DB connection to avoid SQLite threading issues.'''
    import sqlite3, json, time
    _local_conn = sqlite3.connect(GPKG_PATH)
    import gpkg_helper as _gh

    # Ensure tables exist
    _gh._ensure_field_details_table(_local_conn)
    _local_conn.execute(
        "CREATE TABLE IF NOT EXISTS field_data ("
        "id TEXT PRIMARY KEY,"
        "name TEXT UNIQUE NOT NULL,"
        "data TEXT NOT NULL,"
        "created INTEGER DEFAULT (strftime('%s','now')),"
        "updated INTEGER DEFAULT (strftime('%s','now'))"
        ")"
    )
    _local_conn.commit()

    zone_points = _extract_field_boundary(data)
    if not zone_points:
        _local_conn.close()
        raise ValueError('no boundary found')

    zones = _gh.list_geozones(_local_conn)
    zone_id = 'zone_' + str(int(time.time()))
    GEOZONE_COLORS = ['#e74c3c','#3498db','#2ecc71','#f39c12','#9b59b6','#1abc9c','#e67e22','#34495e']
    c = GEOZONE_COLORS[len(zones) % len(GEOZONE_COLORS)]
    _gh.create_geozone(_local_conn, zone_id, name, zone_points, c, now)
    _gh.update_geozone(_local_conn, zone_id, {
        'crop': data.get('crop', ''),
        'planted_date': str(data.get('fieldCreatedDate', data.get('startYear', '')))
    })

    ref_lat, ref_lon = _get_field_ref(data, zone_points)

    # fast details (tracks / headland / abLine)
    for d_type, (geo, style) in _extract_fast_details(data, ref_lat, ref_lon).items():
        _gh.create_field_detail(_local_conn, zone_id, d_type, geo, style)

    # sections (HEAVY) - skip if too many to avoid server freeze
    sections_data = data.get('sections', {})
    inner = sections_data.get('sections', []) if isinstance(sections_data, dict) else sections_data
    MAX_SECTIONS = 300
    if len(inner) > MAX_SECTIONS:
        print(f'Conversion: skipping {len(inner)} sections (max {MAX_SECTIONS})')
        inner = []
    if inner and ref_lat is not None and ref_lon is not None:
        sections_color = '#27ae60'
        if isinstance(inner[0], (list, tuple)) and len(inner[0]) >= 1:
            hdr = inner[0][0]
            if isinstance(hdr, (list, tuple)) and len(hdr) >= 3:
                sections_color = '#%02x%02x%02x' % tuple(int(c) & 0xFF for c in hdr[:3])
        section_polys = []
        _ec = 0
        for sec in inner:
            if not isinstance(sec, (list, tuple)) or len(sec) < 4:
                continue
            pts = sec[1:]
            for i in range(len(pts) - 2):
                tri = []
                for j in range(3):
                    pt = pts[i + j]
                    if not isinstance(pt, (list, tuple)) or len(pt) < 2:
                        break
                    ll = _local_to_latlon_rad(ref_lat, ref_lon, pt[0], pt[1])
                    tri.append([ll[1], ll[0]])
                if len(tri) == 3:
                    tri.append(tri[0])
                    section_polys.append([tri])
                    _ec += 1
                    if _ec % 1000 == 0:
                        import eventlet
                        eventlet.sleep(0)
        if section_polys:
            sections_geojson = {'type': 'MultiPolygon', 'coordinates': section_polys}
            _gh.create_field_detail(_local_conn, zone_id, 'sections', sections_geojson, {'color': sections_color, 'weight': 0, 'fillOpacity': 0.3})

    zone = _gh.get_geozone_by_id(_local_conn, zone_id)
    _local_conn.close()
    return json.dumps(zone)


@app.route('/api/fields/<name>/convert', methods=['POST'])
@login_required
def convert_field_to_geozone(name):
    _ensure_field_table()
    row = _db.execute('SELECT data FROM field_data WHERE name=?', (name,)).fetchone()
    if not row:
        return jsonify({'error': 'field not found'}), 404
    data = json.loads(row[0])

    boundary = data.get('boundary', {})
    polygons = boundary.get('polygons', [])
    if not polygons or not polygons[0].get('points'):
        return jsonify({'error': 'no boundary found'}), 400

    zones = gpkg_helper.list_geozones(_db)
    color = GEOZONE_COLORS[len(zones) % len(GEOZONE_COLORS)]
    now = int(time.time())

    try:
        result = _convert_field_worker(data, name, color, now)
        return result
    except Exception as e:
        import traceback as _tb
        _tb.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/geozones/<zone_id>/details')
@login_required
def get_geozone_details(zone_id):
    details = gpkg_helper.get_field_details(_db, zone_id)
    return json.dumps(details)


#### Field preview on map (no geozone created) ####

_SECTIONS_JOBS = {}  # field name -> worker pid
_SECTIONS_CACHE_DIR = '/tmp'


def _field_sections_path(name):
    import hashlib
    h = hashlib.sha1(name.encode('utf-8')).hexdigest()[:16]
    return os.path.join(_SECTIONS_CACHE_DIR, 'field_sections_%s.json' % h)


def _start_sections_worker(name, path):
    worker = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sections_worker.py')
    try:
        proc = subprocess.Popen([sys.executable, worker, name, path],
                                start_new_session=True,
                                stdout=open('/tmp/sections_worker.log', 'a'),
                                stderr=subprocess.STDOUT)
        _SECTIONS_JOBS[name] = proc.pid
        print('sections_worker started for', name, 'pid', proc.pid)
    except Exception as e:
        print('Failed to start sections worker:', e)


def _sections_worker_alive(name):
    pid = _SECTIONS_JOBS.get(name)
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _field_updated(name):
    _ensure_field_table()
    row = _db.execute('SELECT updated FROM field_data WHERE name=?', (name,)).fetchone()
    return row[0] if row else 0


@app.route('/api/fields/<name>/details', methods=['GET'])
@login_required
def field_details_for_preview(name):
    data = _get_field_data(name)
    if not data:
        return jsonify({'error': 'field not found'}), 404
    boundary_pts = _extract_field_boundary(data)
    ref_lat, ref_lon = _get_field_ref(data, boundary_pts)
    details = [{'type': t, 'geometry': g, 'style': s}
               for t, (g, s) in _extract_fast_details(data, ref_lat, ref_lon).items()]
    return jsonify({'name': name, 'boundary': boundary_pts, 'details': details})


@app.route('/api/fields/<name>/abline', methods=['POST'])
@login_required
def field_add_abline(name):
    """Build (and optionally save) an AB/curve line from two clicked points.

    Without 'name' in the body: returns computed geometry for preview only.
    With 'name': appends the AOG-style track entry to data['tracks'] and saves
    (keeps the old 'updated' so the sections cache stays valid)."""
    data = _get_field_data(name)
    if not data:
        return jsonify({'error': 'field not found'}), 404
    body = json.loads(request.data)
    line_type = body.get('type', 'ab')
    ptA = body.get('ptA')
    ptB = body.get('ptB')
    if not ptA or not ptB or not isinstance(ptA, (list, tuple)) or not isinstance(ptB, (list, tuple)) or len(ptA) < 2 or len(ptB) < 2:
        return jsonify({'error': 'ptA/ptB required'}), 400
    is_curve = line_type == 'curve'
    try:
        entry, ref_lat, ref_lon = _build_abline_entry(data, ptA, ptB, is_curve)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    entry['name'] = body.get('name') or entry['name']
    geometry = _track_entry_geometry(entry, ref_lat, ref_lon)
    resp = {'ok': True, 'geometry': geometry,
            'heading_deg': round(math.degrees(entry['heading']), 1),
            'name': entry['name'], 'mode': entry['mode']}
    if body.get('name'):
        data.setdefault('tracks', [])
        data['tracks'].append(entry)
        _save_field_data(name, data, bump=False)
    return jsonify(resp)


@app.route('/api/fields/<name>/sections/status', methods=['GET'])
@login_required
def field_sections_status(name):
    data = _get_field_data(name)
    if not data:
        return jsonify({'error': 'field not found'}), 404
    updated = _field_updated(name)
    path = _field_sections_path(name)

    # clean up dead worker jobs
    if name in _SECTIONS_JOBS and not _sections_worker_alive(name):
        del _SECTIONS_JOBS[name]

    # ready?
    if os.path.exists(path):
        try:
            with open(path) as f:
                header = json.loads(f.readline())
            if header.get('updated') == updated and header.get('version') == 2:
                _SECTIONS_JOBS.pop(name, None)
                return jsonify({'state': 'ready', 'total': header.get('total', 0)})
        except Exception:
            pass

    # already processing?
    if name in _SECTIONS_JOBS:
        return jsonify({'state': 'processing'})

    # stale or missing -> (re)compute
    try:
        os.remove(path)
    except OSError:
        pass
    _start_sections_worker(name, path)
    return jsonify({'state': 'processing'})


@app.route('/api/fields/<name>/sections', methods=['GET'])
@login_required
def field_sections_content(name):
    data = _get_field_data(name)
    if not data:
        return jsonify({'error': 'field not found'}), 404
    updated = _field_updated(name)
    path = _field_sections_path(name)
    if not os.path.exists(path):
        return jsonify({'error': 'not ready'}), 409
    try:
        with open(path) as f:
            header = json.loads(f.readline())
        if header.get('updated') != updated:
            return jsonify({'error': 'stale'}), 409
    except Exception:
        return jsonify({'error': 'invalid cache'}), 500

    def generate():
        try:
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    yield line + '\n'
        except GeneratorExit:
            pass

    return Response(stream_with_context(generate()), mimetype='application/json')


#### Yield data preview ####

_YIELD_JOBS = {}


def _field_yield_path(name):
    import hashlib
    h = hashlib.sha1(name.encode('utf-8')).hexdigest()[:16]
    return os.path.join(_SECTIONS_CACHE_DIR, 'field_yield_%s.json' % h)


def _start_yield_worker(name, path):
    worker = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'yield_worker.py')
    try:
        proc = subprocess.Popen([sys.executable, worker, name, path],
                                start_new_session=True,
                                stdout=open('/tmp/yield_worker.log', 'a'),
                                stderr=subprocess.STDOUT)
        _YIELD_JOBS[name] = proc.pid
        print('yield_worker started for', name, 'pid', proc.pid)
    except Exception as e:
        print('Failed to start yield worker:', e)


def _yield_worker_alive(name):
    pid = _YIELD_JOBS.get(name)
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


@app.route('/api/fields/<name>/yield/status', methods=['GET'])
@login_required
def field_yield_status(name):
    data = _get_field_data(name)
    if not data:
        return jsonify({'error': 'field not found'}), 404

    yield_data = data.get('yieldData')
    records = yield_data.get('records') if yield_data else None
    if not records:
        return jsonify({'state': 'empty'})

    updated = _field_updated(name)
    path = _field_yield_path(name)

    if name in _YIELD_JOBS and not _yield_worker_alive(name):
        del _YIELD_JOBS[name]

    if os.path.exists(path):
        try:
            with open(path) as f:
                header = json.loads(f.readline())
            if header.get('updated') == updated and header.get('version') == 1:
                _YIELD_JOBS.pop(name, None)
                return jsonify({'state': 'ready', 'total': header.get('total', 0),
                                'yield_min': header.get('yield_min', 0),
                                'yield_max': header.get('yield_max', 0)})
        except Exception:
            pass

    if name in _YIELD_JOBS:
        return jsonify({'state': 'processing'})

    try:
        os.remove(path)
    except OSError:
        pass
    _start_yield_worker(name, path)
    return jsonify({'state': 'processing'})


@app.route('/api/fields/<name>/yield', methods=['GET'])
@login_required
def field_yield_content(name):
    data = _get_field_data(name)
    if not data:
        return jsonify({'error': 'field not found'}), 404
    updated = _field_updated(name)
    path = _field_yield_path(name)
    if not os.path.exists(path):
        return jsonify({'error': 'not ready'}), 409
    try:
        with open(path) as f:
            header = json.loads(f.readline())
        if header.get('updated') != updated:
            return jsonify({'error': 'stale'}), 409
    except Exception:
        return jsonify({'error': 'invalid cache'}), 500

    def generate():
        try:
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    yield line + '\n'
        except GeneratorExit:
            pass

    return Response(stream_with_context(generate()), mimetype='application/json')


if __name__ == "__main__":

    try:
        update_password(rtkbaseconfig)
        if not rtkbaseconfig.get_web_authentification():
            from flask_login import login_required as _login_required
            import functools
            _login_required = functools.wraps(_login_required)(
                lambda f: f
            )
        load_units(services_list)
        manager_thread = Thread(target=manager, daemon=True)
        manager_thread.start()

        def ndvi_scheduler():
            import time as _time
            import datetime as _dt
            import sqlite3 as _sqlite3

            def _run_all():
                from ndvi_helper import calc_ndvi_for_zone, calc_contrast_ndvi_for_zone
                zones = gpkg_helper.list_geozones(_db)
                if not zones:
                    return
                conn = _sqlite3.connect(GPKG_PATH)
                done_today = set()
                try:
                    for r in conn.execute("SELECT DISTINCT zone_id FROM ndvi_scenes_v2 WHERE date(created_at, 'localtime') = date('now', 'localtime')"):
                        done_today.add(r[0])
                except Exception:
                    pass
                contrast_done_today = set()
                try:
                    for r in conn.execute("SELECT DISTINCT zone_id FROM ndvi_contrast_v2 WHERE date(created_at, 'localtime') = date('now', 'localtime')"):
                        contrast_done_today.add(r[0])
                except Exception:
                    pass
                conn.close()
                for z in zones:
                    zid = z['id']
                    if zid not in done_today:
                        try:
                            calc_ndvi_for_zone(zid)
                        except Exception as e:
                            print(f"NDVI calc for zone {zid}: {e}")
                    if zid not in contrast_done_today:
                        try:
                            calc_contrast_ndvi_for_zone(zid)
                        except Exception as e:
                            print(f"Contrast NDVI calc for zone {zid}: {e}")

            # First pass: run immediately to catch up
            try:
                _run_all()
            except Exception as e:
                print(f"NDVI scheduler first pass error: {e}")

            # Then run daily at 3:00 AM
            while True:
                now = _dt.datetime.now()
                next_run = now.replace(hour=3, minute=0, second=0, microsecond=0)
                if next_run <= now:
                    next_run += _dt.timedelta(days=1)
                _time.sleep((next_run - now).total_seconds())
                try:
                    _run_all()
                except Exception as e:
                    print(f"NDVI scheduler error: {e}")

        import eventlet
        ndvi_thread = eventlet.spawn(ndvi_scheduler)

        def _weather_updater():
            _fetch_weather()
            while True:
                time.sleep(600)
                try:
                    _fetch_weather()
                except Exception as e:
                    print(f"Weather updater error: {e}")
        weather_thread = Thread(target=_weather_updater, daemon=True)
        weather_thread.start()

        app.secret_key = rtkbaseconfig.get_secret_key()
        web_port = int(rtkbaseconfig.get('general', 'web_port'))
        import os; os.system("sysctl -w fs.protected_regular=0")
        socketio.run(app, host='0.0.0.0', port=web_port)
    except Exception as e:
        print(f"Error starting server: {e}")
