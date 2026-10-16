# -*- coding: utf-8 -*-
"""Optional Open-Meteo model weather. Called as a bounded background helper."""
from __future__ import print_function
import argparse
import datetime
import json
import math
import logging
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
    value = {'temperature_f': current['temperature_2m'], 'condition': condition,
             'code': code, 'sunrise': daily['sunrise'][0], 'sunset': daily['sunset'][0],
             'model_time': current['time']}
    if current.get('apparent_temperature') is not None:
        value['feels_like_f'] = current['apparent_temperature']
    for source, key in [('temperature_2m_max', 'high_f'), ('temperature_2m_min', 'low_f'),
                        ('precipitation_probability_max', 'rain_chance')]:
        if daily.get(source) and daily[source][0] is not None:
            value[key] = daily[source][0]
    return validate(value)


def local_time(text):
    return datetime.datetime.strptime(text[:16], '%Y-%m-%dT%H:%M')


def validate(value):
    if not isinstance(value, dict):
        raise ValueError('Invalid weather reply')
    temperature = float(value['temperature_f'])
    if math.isnan(temperature) or math.isinf(temperature):
        raise ValueError('Invalid weather temperature')
    text_types = (str,) if str is type(u'') else (basestring,)
    for key in ('condition', 'sunrise', 'sunset', 'model_time'):
        if not isinstance(value[key], text_types) or not 1 <= len(value[key]) <= 100:
            raise ValueError('Invalid weather text')
    for key in ('sunrise', 'sunset', 'model_time'):
        local_time(value[key])
    if local_time(value['sunrise']) >= local_time(value['sunset']):
        raise ValueError('Invalid daylight interval')
    code = int(value['code'])
    result = {'temperature_f': temperature, 'temperature_c': (temperature - 32) * 5.0 / 9,
            'condition': value['condition'], 'code': code, 'sunrise': value['sunrise'],
            'sunset': value['sunset'], 'model_time': value['model_time']}
    for key in ('feels_like_f', 'high_f', 'low_f', 'rain_chance'):
        if value.get(key) is None:
            continue
        extra = float(value[key])
        if math.isnan(extra) or math.isinf(extra) or isinstance(value[key], bool):
            raise ValueError('Invalid weather detail')
        if key == 'rain_chance' and not 0 <= extra <= 100:
            raise ValueError('Invalid precipitation probability')
        result[key] = extra
        if key.endswith('_f'):
            result[key[:-1] + 'c'] = (extra - 32) * 5.0 / 9
    if 'high_f' in result and 'low_f' in result and result['low_f'] > result['high_f']:
        raise ValueError('Invalid daily temperature range')
    return result


def details(value, unit='f', earlier=False):
    """Compact optional forecast details; never present old daily values as today's."""
    if earlier:
        return 'Earlier weather: ' + value['model_time'].replace('T', ' ')
    lines = []
    if 'feels_like_' + unit in value:
        lines.append(u'Feels like %.0f° %s' % (value['feels_like_' + unit], unit.upper()))
    daily = []
    for label, key in [('High', 'high_'), ('Low', 'low_')]:
        if key + unit in value:
            daily.append(label + (u' %.0f°' % value[key + unit]))
    if 'rain_chance' in value:
        daily.append('Rain today %.0f%%' % value['rain_chance'])
    if daily:
        lines.append(u' · '.join(daily))
    return '\n'.join(lines)


def measurements(value, unit='f', earlier=False):
    """Aligned forecast readings; missing values stay distinct from measured zero."""
    if earlier:
        return []
    result=[]
    for label,key in [('Feels like','feels_like_'+unit),('Rain today','rain_chance'),
                      ('High','high_'+unit),('Low','low_'+unit)]:
        number=value.get(key)
        result.append((label, u'—' if number is None else (u'%.0f%%' if key=='rain_chance' else u'%.0f°') % number))
    return result


def daylight(value, now):
    rise, setting = local_time(value['sunrise']), local_time(value['sunset'])
    if now.date() != rise.date():
        return None
    fraction = max(0, min(1, (now - rise).total_seconds() / (setting - rise).total_seconds()))
    if now >= setting:
        label = 'After sunset · night'
    else:
        target, event = (rise, 'rises') if now < rise else (setting, 'sets')
        minutes = int(math.ceil((target - now).total_seconds() / 60))
        hours, minutes = divmod(minutes, 60)
        label = 'Sun %s in %s' % (event, ('%d h %02d min' % (hours, minutes)) if hours else '%d min' % minutes)
    return {'fraction': fraction, 'label': label, 'now': now.strftime('%H:%M'),
            'sunrise': rise.strftime('%H:%M'), 'sunset': setting.strftime('%H:%M')}


def fetch(latitude, longitude, timezone):
    url = 'https://api.open-meteo.com/v1/forecast?' + urlencode({
        'latitude': latitude, 'longitude': longitude, 'timezone': timezone,
        'current': 'temperature_2m,weather_code,apparent_temperature',
        'daily': 'sunrise,sunset,temperature_2m_max,temperature_2m_min,precipitation_probability_max',
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
        print(json.dumps(fetch(args.latitude, args.longitude, args.timezone)))
    except Exception:
        logging.exception('Weather refresh failed')
        print(json.dumps({'error': 'Weather unavailable; the room controls still work.'}))
