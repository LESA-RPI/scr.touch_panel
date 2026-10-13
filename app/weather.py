# -*- coding: utf-8 -*-
"""Optional Open-Meteo model weather. Called as a bounded background helper."""
from __future__ import print_function
import argparse
import json
try:
    from urllib.request import urlopen
    from urllib.parse import urlencode
except ImportError:
    from urllib2 import urlopen
    from urllib import urlencode


def summary(data):
    current, daily = data['current'], data['daily']
    code = current['weather_code']
    descriptions = {0: 'Clear', 1: 'Mostly clear', 2: 'Partly cloudy', 3: 'Overcast',
                    45: 'Fog', 48: 'Freezing fog'}
    condition = descriptions.get(code)
    if condition is None:
        if code in (51, 53, 55, 56, 57):
            condition = 'Drizzle'
        elif code in (61, 63, 65, 66, 67, 80, 81, 82):
            condition = 'Rain'
        elif code in (71, 73, 75, 77, 85, 86):
            condition = 'Snow'
        elif code in (95, 96, 99):
            condition = 'Thunderstorms'
        else:
            condition = 'Conditions unavailable'
    return (u'%.0f F / %.0f C  ·  %s\nSunrise %s  ·  Sunset %s\nModel time %s  ·  Open-Meteo' % (
        current['temperature_2m'], (current['temperature_2m'] - 32) * 5.0 / 9,
        condition, daily['sunrise'][0][11:16], daily['sunset'][0][11:16], current['time'][11:16]))


def fetch(latitude, longitude, timezone):
    url = 'https://api.open-meteo.com/v1/forecast?' + urlencode({
        'latitude': latitude, 'longitude': longitude, 'timezone': timezone,
        'current': 'temperature_2m,weather_code', 'daily': 'sunrise,sunset',
        'temperature_unit': 'fahrenheit', 'forecast_days': 1})
    response = urlopen(url, timeout=5)
    try:
        body = response.read(32769)
    finally:
        response.close()
    if len(body) > 32768:
        raise ValueError('Weather response too large')
    return summary(json.loads(body.decode('utf-8')))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('latitude', type=float)
    parser.add_argument('longitude', type=float)
    parser.add_argument('timezone')
    args = parser.parse_args()
    try:
        print(json.dumps({'text': fetch(args.latitude, args.longitude, args.timezone)}))
    except Exception:
        print(json.dumps({'error': 'Weather unavailable; the room controls still work.'}))
