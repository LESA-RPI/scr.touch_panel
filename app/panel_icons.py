"""Pinned Lucide artwork shared by panel controls and weather presentations."""
from pathlib import Path

ASSETS = Path(__file__).resolve().parents[1] / 'assets' / 'icons'
KINDS = {'room': 'sliders-horizontal', 'advanced': 'sliders-horizontal',
         'experiment': 'flask-conical', 'health': 'activity', 'system': 'activity',
         'visitor': 'clock', 'clock': 'clock', 'date': 'calendar-days', 'link-ok': 'circle-check',
         'link-off': 'circle-slash', 'on': 'lightbulb', 'white': 'lightbulb',
         'off': 'lightbulb-off', 'scene': 'layers', 'scenes': 'layers',
         'home': 'house', 'guide': 'book-open', 'about': 'info',
         'appearance': 'sun-moon', 'screen': 'monitor', 'original': 'external-link',
         'return': 'arrow-left', 'dropdown': 'chevron-right'}


def control(kind, colour, size=32):
    from PIL import Image
    name = KINDS.get(kind, kind)
    with Image.open(str(ASSETS / 'masks' / (name + '.png'))) as source:
        mask = source.getchannel('A').resize((size, size), Image.Resampling.LANCZOS)
    image = Image.new('RGBA', (size, size), colour)
    image.putalpha(mask)
    return image.rotate(-90) if kind == 'dropdown' else image


def weather_kind(code, night=False):
    if code == 0:
        return 'moon' if night else 'sun'
    if code in (1, 2):
        return 'cloud-moon' if night else 'cloud-sun'
    if code == 3:
        return 'cloud'
    if code in (45, 48):
        return 'cloud-fog'
    if code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82):
        return 'cloud-rain'
    if code in (71, 73, 75, 77, 85, 86):
        return 'cloud-snow'
    if code in (95, 96, 99):
        return 'cloud-lightning'
    return 'circle-question-mark'


def weather(name, theme, size):
    from PIL import Image
    with Image.open(str(ASSETS / 'weather' / (name + '-' + theme + '.png'))) as source:
        return source.resize((size, size), Image.Resampling.LANCZOS)
