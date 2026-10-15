#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Independent SCR touchscreen. Author: Diyanko Bhowmik, with Codex assistance.

Python 2.7/3, installed Tk and Pillow. Data-only profiles and
a private UI journal work standalone. An opt-in adapter uses existing ROS lights.
"""
from __future__ import print_function
import argparse
import base64
import datetime
import json
import math
import os
import select
import signal
import subprocess
import sys
import time
import uuid
from io import BytesIO
from scr_touch_panel_lights import PRESETS
from event_journal import EventJournal
from preferences import Preferences, load as load_preferences
import weather as weather_data
from panel_guides import DEMO, SUPPORT, connection
try:
    import Tkinter as tk
    from tkFont import Font
except ImportError:
    import tkinter as tk
    from tkinter.font import Font

FONT = 'Cantarell'
CHANNELS = ('Blue 1', 'Blue 2', 'Blue 3', 'Lime', 'Amber', 'Orange', 'Red 1', 'Red 2')
CHANNEL_COLOURS = ('#4764bc', '#337cb9', '#2198c2', '#86a83b', '#c69c32', '#d47d34', '#ba6052', '#a84658')
PALETTES = {'dark': ('#16181b', '#202327', '#f0f1f2', '#b9bdc4', '#30343a'),
            'light': ('#ffffff', '#ffffff', '#12384b', '#476373', '#edf1f4')}
ACCENT = '#0072b2'
NAVIGATION = [('Home', 'room'), ('Advanced', 'advanced'),
              ('Demo & guide', 'guide'), ('Legacy', 'original')]
DEFAULT_PROFILE = {'title': 'Room activity practice', 'sensors': 'Ceiling and colour sensors',
                   'stages': ['Leave the room empty', 'Please sit still',
                              'Make small seated movements', 'Walk around the room',
                              'Leave the room empty again'],
                   'annotations': ['Activity started', 'Activity finished', 'Unexpected event']}
TIPS = {'Lights on': 'Standard white: selects 3500 K and light-level input 1000 for all lights.',
        'Lights off': 'Sends zero drive to all light channels. The panel screen stays on.',
        'Advanced controls': 'Adjust eight colour-channel drives. Values are controller percentages, not measured light.',
        'Room': 'Everyday lighting. Changes send automatically after your touch settles.',
        'Visitor': 'Room introduction and a large clock. Opening this page does not change lighting.',
        'Practice': 'Practice instructions and annotations only. No sensor recording starts.',
        'Experiment': 'Instructions, practice time and named annotations. No sensor recording starts.',
        'System': 'Panel resources and advertised room services. Presence does not prove sensor health.',
        'Legacy': 'Restores the starting lighting, then shows the original room controls.',
        'Blank screen': 'Shows black pixels. Hold still for 2 seconds to return; the backlight remains on.',
        'Settings': 'Appearance, date/time and screen options. Appearance choices can be saved on this device.',
        'About panel': 'Panel credits and source repository. No room settings change.',
        'Start practice': 'Starts the practice timer only. It does not start sensor collection.',
        'Next instruction': 'Shows the next instruction. The final instruction does not wrap.',
        'End trial and restore': 'Restores confirmed trial changes and returns to the original program.'}


def monotonic():
    if hasattr(time, 'monotonic'):
        return time.monotonic()
    with open('/proc/uptime') as stream:
        return float(stream.read().split()[0])


def boot_identity():
    try:
        with open('/proc/sys/kernel/random/boot_id') as stream:
            return stream.read().strip()
    except IOError:
        return None


def health():
    result = {}
    try:
        with open('/proc/meminfo') as stream:
            memory = dict((line.split(':')[0], int(line.split()[1])) for line in stream)
        result.update(ram_available=memory['MemAvailable'] // 1024,
                      ram_total=memory['MemTotal'] // 1024, load=os.getloadavg()[0])
        disk = os.statvfs('/')
        result.update(disk_available=disk.f_bavail * disk.f_frsize / float(2 ** 30),
                      disk_used=100 * (1 - disk.f_bfree / float(disk.f_blocks)))
        with open('/sys/class/thermal/thermal_zone0/temp') as stream:
            result['temperature'] = float(stream.read()) / 1000
        with open('/proc/uptime') as stream:
            result['uptime'] = float(stream.read().split()[0]) / 86400
    except (IOError, OSError, KeyError, ValueError) as error:
        result['error'] = str(error)
    try:
        reply = subprocess.check_output(['timeout', '2', 'vcgencmd', 'get_throttled']).decode('ascii').strip()
        flags = int(reply.split('=')[1], 16)
        result['power'] = ('Current undervoltage detected' if flags & 1 else 'No current undervoltage')
        if flags & (1 << 16):
            result['power'] += ' / past warning since boot'
    except (OSError, ValueError, IndexError, subprocess.CalledProcessError):
        result['power'] = 'Power status unavailable'
    return result


def profile(path):
    value = {}
    if path:
        with open(path) as stream:
            value = json.load(stream)
    if not isinstance(value, dict) or set(value) - set(DEFAULT_PROFILE):
        raise ValueError('Profile permits title, sensors, stages and annotations only')
    merged = dict(DEFAULT_PROFILE)
    merged.update(value)
    text_types = (str,) if sys.version_info[0] == 3 else (basestring,)
    for key in ('title', 'sensors'):
        if not isinstance(merged[key], text_types) or not 1 <= len(merged[key]) <= 100:
            raise ValueError('Title/sensors must contain 1..100 characters')
    for key, maximum in [('stages', 20), ('annotations', 4)]:
        items = merged[key]
        limit = 60 if key == 'stages' else 20
        if (not isinstance(items, list) or not 1 <= len(items) <= maximum or
                any(not isinstance(item, text_types) or not 1 <= len(item) <= limit for item in items)
                or len(set(items)) != len(items)):
            raise ValueError('Provide distinct, short %s labels' % key)
    return merged


def clock_minutes(text):
    try:
        hours, minutes = map(int, text.split(':'))
        if not 0 <= hours <= 23 or not 0 <= minutes <= 59:
            raise ValueError()
        return 60 * hours + minutes
    except ValueError:
        raise argparse.ArgumentTypeError('Use HH:MM in the panel local timezone')


def scheduled_theme(now, light_at, dark_at):
    light = light_at <= now < dark_at if light_at < dark_at else now >= light_at or now < dark_at
    return 'light' if light else 'dark'


def light_selection(action, arguments):
    """Describe requested controller inputs; never imply optical measurement."""
    if action == 'cct':
        return '%d K input / level %d' % (arguments['cct'], arguments['intensity'])
    values = tuple(arguments['values'])
    for name, preset in PRESETS.items():
        if values == preset:
            return name + ' scene'
    return 'Custom eight-channel mix'


def confirmation_age(now, confirmed_at):
    if confirmed_at is None:
        return ''
    seconds = max(0, now - confirmed_at)
    if seconds < 60:
        return 'just now'
    if seconds < 3600:
        return '%d min ago' % (seconds // 60)
    if seconds < 86400:
        return '%d h ago' % (seconds // 3600)
    return '%d d ago' % (seconds // 86400)


class Panel(object):
    def __init__(self, args):
        self.args, self.profile = args, profile(args.profile)
        saved, preference_error = load_preferences(getattr(args, 'preferences', None),
                                                  {'light_at': args.light_at, 'dark_at': args.dark_at})
        for key, value in saved.items():
            setattr(args, key, value)
        self.preferences = Preferences(args.preferences) if getattr(args, 'preferences', None) else None
        self.preference_error = preference_error
        self.weather_worker, self.weather_started = None, None
        self.weather_checked, self.weather_good, self.weather_last_text = -900, None, None
        self.weather_reading, self.weather_rendered_minute = None, None
        self.settings_category = 'appearance'
        self.guide_page, self.support_page = 0, 0
        self.started, self.run_id, self.sequence = monotonic(), uuid.uuid4().hex, 0
        self.boot_id, self.last_touch = boot_identity(), self.started
        self.idle_timeout = getattr(args, 'idle_timeout', 300)
        self.idle_active, self.press_active, self.idle_return = False, False, None
        self.clock_24 = getattr(args, 'clock_format', '24') == '24'
        self.temperature_unit = getattr(args, 'temperature_unit', 'f')
        self.help_on = getattr(args, 'tips', 'on') == 'on'
        self.status_worker, self.status_started, self.room_status_at = None, None, -60
        self.room_status = 'Room services: not checked'
        self.closed, self.closing = False, None
        self.stage, self.running, self.elapsed, self.run_started = 0, False, 0.0, None
        self.keep_switcher = getattr(args, 'keep_switcher', False)
        self.mode, self.section, self.blank_return = (getattr(args, 'start_mode', 'room')
                                                     if self.keep_switcher else 'room'), 'basic', 'room'
        self.trial_deadline = self.started + args.duration if args.duration and self.mode != 'original' else None
        self.hold = self.hold_origin = None
        self.theme_choice, self.theme = args.theme, None
        self.health_at, self.health_cache = -10, {}
        self.worker, self.pending, self.worker_buffer = None, None, ''
        self.queued_intent, self.intent_timer, self.slider_drag = None, None, None
        self.view_generation = 0
        self.light_state, self.release_target = 'disconnected', None
        self.confirmed_light = 'Not checked'
        self.confirmed_at, self.light_message = None, 'Lighting not connected'
        self.light_buttons = []
        self.last_heartbeat, self.request_seq = -10, 0
        self.journal = EventJournal(args.journal, sys.stdout)
        self.pending_annotation = None
        self.root = tk.Tk()
        self.font_family = Font(root=self.root, font=(FONT, 19)).actual('family')
        self.icon_cache = {}
        for key, size, width in [('title', 27, 1200), ('sensors', 18, 1130), ('annotations', 19, 270)]:
            labels = self.profile[key] if key == 'annotations' else [self.profile[key]]
            if any(Font(root=self.root, font=(FONT, size)).measure(label) > width for label in labels):
                self.root.destroy()
                if self.journal:
                    self.journal.close()
                raise ValueError('Shorten profile %s text to fit the touch layout' % key)
        self.root.title('LESA Smart Conference Room (beta)')
        if (self.root.winfo_screenwidth(), self.root.winfo_screenheight()) != (1280, 800) and not args.windowed:
            self.root.destroy()
            raise ValueError('Expected 1280x800; use --windowed for local review')
        self.root.geometry('1280x800+0+0')
        self.root.overrideredirect(not args.windowed)
        self.root.attributes('-topmost', True)
        self.root.bind('<Escape>', lambda event: self.close('escape'))
        self.root.protocol('WM_DELETE_WINDOW', lambda: self.close('window_close'))
        self.root.bind_all('<ButtonRelease-1>', self.slider_released, add='+')
        self.root.bind_all('<ButtonPress-1>', lambda event: self.activity(True), add='+')
        self.root.bind_all('<ButtonRelease-1>', lambda event: self.activity(False), add='+')
        self.root.bind_all('<KeyPress>', lambda event: self.activity(), add='+')
        self.root.bind_class('PanelWake', '<ButtonPress-1>', lambda event: self.wake_idle(True))
        self.root.bind_class('PanelWake', '<ButtonRelease-1>', lambda event: self.wake_idle(False))
        self.root.bind_class('PanelWake', '<B1-Motion>', lambda event: 'break' if self.idle_active else None)
        self.root.bind_class('PanelWake', '<KeyPress>', lambda event: self.wake_idle(False))
        self.cct, self.intensity = tk.IntVar(value=3500), tk.IntVar(value=1000)
        self.channel_values = [tk.IntVar(value=value) for value in PRESETS['Fid']]
        self.status_text = tk.StringVar(value='Use Lights on or Lights off. Fine adjustments are in Advanced.')
        self.light_text = tk.StringVar(value='Lighting not connected - controls are unavailable')
        self.visitor_time, self.visitor_date = tk.StringVar(), tk.StringVar()
        self.preference_text = tk.StringVar(value=self.preference_summary())
        self.weather_text = tk.StringVar(value='Not configured. A location is needed.')
        self.weather_temperature = tk.StringVar(value='—')
        self.weather_condition = tk.StringVar(value='Weather unavailable')
        self.annotation_text = tk.StringVar(value=('Annotations belong to the panel journal, separate from recordings.'
                                                  if args.journal else 'Annotations go to panel output only. No recording starts.'))
        self.artwork = None
        if args.logo:
            from PIL import Image
            artwork = Image.open(args.logo)
            # Viewport of the supplied 900-square logo. Keep its original pixels and colours.
            if artwork.size == (900, 900):
                artwork = artwork.crop((55, 160, 780, 578))
            resampling = getattr(Image, 'Resampling', Image)
            artwork.thumbnail((116, 66), resampling.LANCZOS)
            buffer = BytesIO()
            artwork.save(buffer, format='PNG')
            self.artwork = tk.PhotoImage(data=base64.b64encode(buffer.getvalue()).decode('ascii'))
        self.dock = tk.Toplevel(self.root)
        self.dock.overrideredirect(True)
        self.dock.attributes('-topmost', True)
        self.dock.withdraw()
        self.set_theme()
        if args.live_lights and self.mode != 'original':
            self.start_worker()
        self.tick()
        self.root.after(100, self.poll_worker)
        self.emit('panel_opened', duration_s=args.duration, profile=self.profile, author='Diyanko Bhowmik')

    def emit(self, event, **values):
        self.sequence += 1
        values.update(version=1, event=event, mode=self.mode, panel_run_id=self.run_id,
                      boot_id=self.boot_id,
                      sequence=self.sequence, utc=datetime.datetime.utcnow().isoformat() + 'Z',
                      elapsed_s=round(monotonic() - self.started, 3), instruction_index=self.stage,
                      instruction=self.profile['stages'][self.stage], recording=False)
        line = json.dumps(values, sort_keys=True) + '\n'
        try:
            self.journal.append(line, self.sequence, durable=event == 'annotation')
        except (IOError, OSError) as error:
            if event == 'annotation':
                raise
            self.status_text.set('Panel journal unavailable: ' + str(error))
        return self.sequence

    def label(self, parent, text='', size=20, muted=False):
        return tk.Label(parent, text=text, font=(FONT, size), fg=self.muted if muted else self.ink,
                        bg=parent.cget('bg'), anchor='w', justify='left')

    def wrap_label(self, label):
        """Wrap to allocated width, including narrower settings/weather cards."""
        label.config(wraplength=600)
        def fit(event):
            width = max(1, event.width - 2*label.winfo_pixels(str(label.cget('padx'))) - 8)
            if label.winfo_pixels(str(label.cget('wraplength'))) != width:
                label.config(wraplength=width)
        label.bind('<Configure>', fit)
        return label

    def lighting_feedback(self, message):
        self.light_message = message
        self.refresh_confirmation_age()

    def refresh_confirmation_age(self):
        age = confirmation_age(monotonic(), getattr(self, 'confirmed_at', None))
        suffix = ' / ' + age if age else ''
        text = (self.light_message + '\nLast confirmed drive: ' +
                getattr(self, 'confirmed_light', 'Not checked') + suffix)
        if not hasattr(self.light_text, 'get') or self.light_text.get() != text:
            self.light_text.set(text)

    def activity(self, pressed=None):
        self.last_touch = monotonic()
        if pressed is not None:
            self.press_active = pressed

    def idle_eligible(self):
        return (self.idle_timeout > 0 and self.mode in ('room', 'advanced', 'settings', 'health', 'guide', 'support', 'about')
                and self.light_state in ('ready', 'disconnected') and not self.running
                and not any((self.pending, self.queued_intent, self.intent_timer, self.slider_drag,
                             self.release_target, self.closing, self.press_active)))

    def update_idle(self):
        if self.idle_active:
            if self.light_state == 'failed':
                self.return_from_idle()
            return
        if self.idle_eligible() and monotonic() - self.last_touch >= self.idle_timeout:
            self.idle_return = (self.mode, self.section)
            self.idle_active = True
            self.show('visitor')
            self.status_text.set('Idle clock and weather. Touch anywhere to return.')
            self.root.focus_set()

    def install_wake_bindings(self):
        def visit(widget):
            if widget == self.dock:
                return
            tags = widget.bindtags()
            if 'PanelWake' not in tags:
                widget.bindtags(('PanelWake',) + tags)
            for child in widget.winfo_children():
                visit(child)
        visit(self.root)

    def wake_idle(self, pressed):
        if not self.idle_active:
            return None
        self.activity(pressed)
        if not pressed:
            self.root.after_idle(self.return_from_idle)
        return 'break'

    def return_from_idle(self):
        if not self.idle_active:
            return
        mode, section = self.idle_return
        self.idle_active, self.idle_return = False, None
        self.activity(False)
        self.show(mode)
        if mode == 'room' and section == 'channels':
            self.channel_view()
        elif mode == 'room' and section == 'lighting':
            self.open_lighting()

    def button(self, parent, text, action, accent=False):
        button = tk.Button(parent, text=text, command=action, font=(FONT, 19),
                         fg='white' if accent else self.ink, bg=ACCENT if accent else self.control,
                         activebackground=ACCENT if accent else self.control,
                         activeforeground='white' if accent else self.ink, disabledforeground=self.muted,
                         bd=0, highlightthickness=0, padx=14, pady=14, takefocus=True)
        button.bind('<ButtonPress-1>', lambda event: self.show_tip(text), add='+')
        return button

    def show_tip(self, text):
        if self.help_on and not self.pending and self.light_state != 'failed':
            tip = TIPS.get(text)
            if text in ('Fid', 'Sat', 'Dul'):
                tip = 'Applies the room\'s ' + text + ' spectral scene to all lights. The name matches Legacy.'
            if text in self.profile['annotations']:
                tip = 'Saves "' + text + '" as a panel annotation. It is not a recording label yet.'
            if tip:
                self.status_text.set(tip)

    def toggle_tips(self):
        self.help_on = not self.help_on
        self.save_preferences()
        self.render()
        self.emit('help_selected', enabled=self.help_on)

    def icon(self, kind, colour):
        key = (kind, colour)
        if key not in self.icon_cache:
            from PIL import Image, ImageDraw
            image = Image.new('RGBA', (96, 96))
            draw = ImageDraw.Draw(image)
            def line(points):
                draw.line([(x*3, y*3) for x, y in points], fill=colour, width=6)
            def rect(box):
                x1, y1, x2, y2 = box
                line(((x1, y1), (x2, y1), (x2, y2), (x1, y2), (x1, y1)))
            if kind == 'room':
                for y, x in ((8, 11), (16, 22), (24, 15)):
                    line(((3, y), (29, y)))
                    draw.ellipse(((x-3)*3, (y-3)*3, (x+3)*3, (y+3)*3), fill=colour)
            elif kind == 'experiment':
                rect((6, 4, 26, 29))
                for y in (10, 17, 24):
                    line(((10, y), (12, y+2), (15, y-2)))
                    line(((18, y), (22, y)))
            elif kind == 'health':
                rect((3, 5, 29, 24))
                line(((6, 17), (11, 17), (14, 10), (18, 21), (22, 15), (26, 15)))
                line(((16, 24), (16, 29)))
                line(((10, 29), (22, 29)))
            elif kind in ('visitor', 'clock'):
                draw.ellipse((12, 12, 84, 84), outline=colour, width=6)
                line(((16, 8), (16, 16), (22, 19)))
            elif kind == 'link-ok':
                draw.ellipse((12, 12, 84, 84), outline=colour, width=6)
                line(((8, 16), (14, 22), (24, 10)))
            elif kind == 'link-off':
                draw.ellipse((12, 12, 84, 84), outline=colour, width=6)
                line(((8, 24), (24, 8)))
            elif kind == 'on':
                draw.ellipse((24, 9, 72, 63), outline=colour, width=6)
                line(((11, 21), (21, 21)))
                line(((11, 25), (21, 25)))
                line(((13, 29), (19, 29)))
            elif kind == 'off':
                draw.ellipse((18, 18, 78, 78), outline=colour, width=6)
                line(((7, 25), (25, 7)))
            elif kind == 'scene':
                for x, y in ((4, 4), (18, 4), (4, 18), (18, 18)):
                    rect((x, y, x + 9, y + 9))
            else:
                line(((13, 5), (4, 14), (13, 23)))
                line(((5, 14), (26, 14), (26, 27)))
            image = image.resize((32, 32), getattr(Image, 'Resampling', Image).LANCZOS)
            buffer = BytesIO()
            image.save(buffer, format='PNG')
            self.icon_cache[key] = tk.PhotoImage(data=base64.b64encode(buffer.getvalue()).decode('ascii'))
        return self.icon_cache[key]

    def row_buttons(self, parent, items, height=64):
        row = tk.Frame(parent, bg=parent.cget('bg'), height=height)
        row.pack(fill='x', pady=6)
        row.pack_propagate(False)
        buttons = []
        for index, (text, action, accent) in enumerate(items):
            button = self.button(row, text, action, accent)
            button.pack(side='left', fill='both', expand=True, padx=(0, 10 if index < len(items) - 1 else 0))
            buttons.append(button)
        return buttons

    def set_theme(self):
        if (self.theme is not None and self.theme_choice == 'auto' and
                (self.mode == 'experiment' or monotonic() - self.last_touch < 60)):
            return
        local = time.localtime()
        chosen = scheduled_theme(local.tm_hour * 60 + local.tm_min, self.args.light_at, self.args.dark_at)
        chosen = chosen if self.theme_choice == 'auto' else self.theme_choice
        if chosen == self.theme:
            return
        self.cancel_intent()
        section = self.section
        self.theme = chosen
        self.bg, self.surface, self.ink, self.muted, self.control = PALETTES[chosen]
        self.border = '#b8c8d4' if chosen == 'light' else '#50565e'
        self.icon_colour = ACCENT if chosen == 'light' else '#6dbce8'
        self.connection_badges = []
        for child in self.root.winfo_children():
            if child != self.dock:
                child.destroy()
        self.root.configure(bg=self.bg)
        self.banner = tk.Frame(self.root, bg=self.bg, height=70)
        self.banner.pack(fill='x', padx=24, pady=(8, 6))
        self.banner.pack_propagate(False)
        if self.artwork and (chosen == 'light' or getattr(self.args, 'dark_brand', 'wordmark') == 'original'):
            tk.Label(self.banner, image=self.artwork, bg='white', bd=0, padx=8).pack(side='left', padx=(0, 18))
        else:
            brand = self.label(self.banner, 'LESA', 30)
            brand.config(fg=ACCENT)
            brand.pack(side='left', padx=(0, 18))
        self.label(self.banner, 'Smart Conference Room', 22).pack(side='left')
        self.clock = self.label(self.banner, size=17, muted=True)
        self.home_button = self.button(self.banner, 'Home', lambda: self.show('room'))
        self.home_button.pack(side='right', padx=12)
        self.tips_button = self.button(self.banner, 'Tips: ' + ('On' if self.help_on else 'Off'), self.toggle_tips)
        self.add_connection_badge(self.banner)
        self.nav = tk.Frame(self.root, bg=self.bg)
        self.nav_buttons = {}
        self.footer = tk.Frame(self.root, bg=self.bg, height=88)
        self.footer.pack_propagate(False)
        self.button(self.footer, 'Demo & guide', lambda: self.show('guide')).pack(side='right', pady=8)
        self.button(self.footer, 'Advanced', lambda: self.show('advanced')).pack(side='right', padx=12, pady=8)
        status = self.label(self.footer, size=17, muted=True)
        status.config(textvariable=self.status_text)
        self.wrap_label(status)
        status.pack(side='left', fill='both', expand=True)
        self.body = tk.Frame(self.root, bg=self.bg)
        self.build_dock()
        self.render()
        if section == 'channels' and self.mode == 'room':
            self.channel_view()
        elif section == 'lighting' and self.mode == 'room':
            self.open_lighting()

    def build_dock(self):
        for child in self.dock.winfo_children():
            child.destroy()
        self.dock.configure(bg=self.bg)
        top = tk.Frame(self.dock, bg=self.bg, height=70)
        top.pack(fill='x', padx=24, pady=(8, 6))
        top.pack_propagate(False)
        if self.artwork and (self.theme == 'light' or getattr(self.args, 'dark_brand', 'wordmark') == 'original'):
            tk.Label(top, image=self.artwork, bg='white', bd=0, padx=8).pack(side='left', padx=(0, 18))
        else:
            brand = self.label(top, 'LESA', 30)
            brand.config(fg=ACCENT)
            brand.pack(side='left', padx=(0, 18))
        self.label(top, 'Smart Conference Room · Legacy', 21).pack(side='left')
        self.label(top, 'Tap Beta to return', 17, True).pack(side='right')
        self.add_connection_badge(top, legacy=True)
        nav = tk.Frame(self.dock, bg=self.bg, height=64)
        nav.pack(fill='both', expand=True, padx=24, pady=(0, 4))
        for index, (text, mode) in enumerate(NAVIGATION):
            text = 'Beta' if mode == 'room' else text
            nav.columnconfigure(index, weight=1, uniform='dock')
            button = self.button(nav, text, lambda mode=mode: self.show(mode), mode == 'original')
            button.config(image=self.icon(mode, 'white' if mode == 'original' else self.ink), compound='left')
            button.grid(row=0, column=index, sticky='nsew', padx=(0, 10 if index < 4 else 0))
        nav.rowconfigure(0, weight=1)

    def add_connection_badge(self, parent, legacy=False):
        frame = tk.Frame(parent, bg=self.bg, width=140, height=64)
        frame.pack(side='right', padx=(8, 0))
        frame.pack_propagate(False)
        button = self.button(frame, '', lambda: self.show('health'))
        button.config(font=(FONT, 15), padx=6, compound='left')
        button.pack(fill='both', expand=True)
        self.connection_badges.append((button, legacy))
        self.update_connection_badges()

    def update_connection_badges(self):
        text, kind, colour = connection(self.light_state, self.args.live_lights)
        colours = {'good': '#23794c' if self.theme == 'light' else '#87c6a1',
                   'waiting': self.icon_colour, 'warning': '#9a650b' if self.theme == 'light' else '#e6ba66',
                   'neutral': self.muted}
        for button, legacy in getattr(self, 'connection_badges', []):
            if button.winfo_exists():
                label, icon, ink = ('Legacy', 'room', self.muted) if legacy else (text, kind, colours[colour])
                if button.cget('text') != label:
                    button.config(text=label, fg=ink, activeforeground=ink, image=self.icon(icon, ink))

    def cycle_theme(self):
        self.choose_theme({'auto': 'light', 'light': 'dark', 'dark': 'auto'}[self.theme_choice])

    def show(self, mode):
        if self.release_target is not None or self.closing:
            return
        if mode != 'visitor':
            self.idle_active = False
        self.cancel_intent()
        if mode == 'original':
            self.trial_deadline = None
        if mode == 'original' and self.worker:
            self.release_target = 'original'
            self.status_text.set('Finishing lighting control before opening Legacy...')
            if self.light_state not in ('ready', 'applying', 'connecting'):
                if not self.worker.stdin.closed:
                    self.worker.stdin.close()
            elif not self.pending:
                self.request('release')
            return
        if self.mode == 'original' and mode != 'original' and self.args.live_lights:
            if not self.worker:
                self.start_worker()
            else:
                self.light_state = 'connecting'
                self.request('acquire')
        if self.mode == 'original' and mode != 'original' and self.keep_switcher:
            self.trial_deadline = monotonic() + self.args.duration if self.args.duration else None
        if mode == 'black':
            self.blank_return = self.mode if self.mode not in ('black', 'original') else 'room'
        self.cancel_hold()
        self.mode, self.section = mode, 'basic'
        if self.light_state != 'failed' and not self.pending:
            messages = {'health': 'Live panel readings. No system settings change.',
                        'room': 'Lights on selects standard white. Blinds are not enabled.',
                        'advanced': 'Fine adjustments and room tools. Opening a page does not operate devices.',
                        'visitor': 'Visitor view does not change lighting. Recording status is unavailable here.',
                        'experiment': 'Practice only. Activity buttons save panel annotations; recorder not connected.',
                        'settings': 'Appearance settings belong to this device; they do not change room lighting.',
                        'about': 'Panel credits and source repository. No room settings change.'}
            messages.update(guide='Explore the room. This guide does not change devices or start recording.',
                            support='Instructions only. Commands are not executed by this panel.')
            if mode in messages:
                self.status_text.set(messages[mode])
        self.render()
        self.emit('mode_changed', target=mode)

    def render(self):
        self.cancel_intent()
        self.light_buttons = []
        self.dock.withdraw()
        self.tips_button.config(text='Tips: ' + ('On' if self.help_on else 'Off'))
        selected_mode = {'guide': 'visitor', 'support': 'health'}.get(self.mode, self.mode)
        for key, button in self.nav_buttons.items():
            button.config(bg=ACCENT if key == selected_mode else self.control,
                          fg='white' if key == selected_mode else self.ink,
                          activebackground=ACCENT if key == selected_mode else self.control,
                          activeforeground='white' if key == selected_mode else self.ink,
                          image=self.icon(key, 'white' if key == selected_mode else self.ink))
        if self.mode == 'original':
            self.root.withdraw()
            self.dock.deiconify()
            self.dock.update_idletasks()
            self.dock.geometry('1280x144+0+0')
            self.dock.lift()
            return
        if self.root.state() == 'withdrawn':
            self.root.deiconify()
            self.root.lift()
        for binding in ('<ButtonPress-1>', '<ButtonRelease-1>', '<B1-Motion>'):
            self.root.unbind(binding)
        if self.mode == 'black':
            for widget in (self.banner, self.nav, self.footer, self.body):
                widget.pack_forget()
            self.root.configure(bg='black')
            self.root.bind('<ButtonPress-1>', self.begin_hold)
            self.root.bind('<ButtonRelease-1>', lambda event: self.cancel_hold())
            self.root.bind('<B1-Motion>', self.move_hold)
            return
        self.root.configure(bg=self.bg)
        if not self.banner.winfo_manager():
            self.banner.pack(fill='x', padx=24, pady=(8, 6))
        if self.mode == 'room' and self.section == 'basic':
            self.home_button.pack_forget()
            self.clock.pack_forget()
        else:
            self.home_button.pack(side='right', padx=12)
            self.clock.pack(side='right', padx=12)
        if not self.footer.winfo_manager():
            self.footer.pack(side='bottom', fill='x', padx=24, pady=(8, 10))
        self.rebuild_body(getattr(self, self.mode + '_view'))
        if self.idle_active:
            self.install_wake_bindings()
        for button in self.footer.winfo_children():
            if isinstance(button, tk.Button) and button.cget('text') == 'Settings':
                selected = self.mode in ('settings', 'about')
                button.config(bg=ACCENT if selected else self.control, fg='white' if selected else self.ink)

    def rebuild_body(self, build):
        """Prepare one unmapped page, then replace and destroy the previous page."""
        previous = self.body
        self.body = tk.Frame(self.root, bg=self.bg)
        try:
            build()
        except Exception:
            self.body.destroy()
            self.body = previous
            raise
        previous.pack_forget()
        self.body.pack(fill='both', expand=True, padx=24)
        previous.destroy()

    def room_view(self):
        row = tk.Frame(self.body, bg=self.bg)
        row.pack(fill='both', expand=True, pady=(22, 10))
        row.columnconfigure(0, weight=48, uniform='home')
        row.columnconfigure(1, weight=52, uniform='home')
        row.rowconfigure(0, weight=1)
        left, right = tk.Frame(row, bg=self.bg), tk.Frame(row, bg=self.bg)
        left.grid(row=0, column=0, sticky='nsew', padx=(0, 28))
        right.grid(row=0, column=1, sticky='nsew', padx=(28, 0))
        controls = tk.Frame(left, bg=self.bg)
        controls.pack(fill='x', pady=(20, 12))
        for index, title in enumerate(('Lights', 'Blinds')):
            controls.columnconfigure(index, weight=1, uniform='essentials')
            group = tk.Frame(controls, bg=self.bg)
            group.grid(row=0, column=index, sticky='nsew', padx=(0, 16) if index == 0 else 0)
            self.label(group, title, 25).pack(anchor='w')
            self.label(group, 'Whole room', 16, True).pack(anchor='w', pady=(2, 16))
            actions = [('Lights on', self.lights_on, True),
                       ('Lights off', lambda: self.preset('Off'), False)] if index == 0 else [
                       ('Open slats', None, False), ('Close & lower', None, False)]
            for title, action, accent in actions:
                button = self.row_buttons(group, [(title, action, accent)], height=104)[0]
                button.config(font=(FONT, 22))
                if index == 0:
                    button.config(image=self.icon('on' if title == 'Lights on' else 'off',
                                                'white' if accent else self.icon_colour), compound='left')
                    self.light_buttons.append(button)
                else:
                    # Intentionally no callback, adapter or opt-in switch until qualified.
                    button.config(state='disabled')
            self.label(group, 'Standard white' if index == 0 else 'Not enabled', 17, True).pack(anchor='w', pady=(8, 0))
        state = self.label(left, size=16, muted=True)
        state.config(textvariable=self.light_text, height=5)
        self.wrap_label(state).pack(fill='x', pady=(8, 0))
        self.label(right, getattr(self.args, 'weather_name', 'Local time'), 18, True).pack(anchor='w')
        clock = self.label(right, size=70)
        clock.config(textvariable=self.visitor_time)
        clock.pack(anchor='w', pady=(12, 0))
        date = self.label(right, size=23)
        date.config(textvariable=self.visitor_date)
        self.wrap_label(date).pack(fill='x', pady=(0, 12))
        self.weather_contents(right, compact=True)
        self.update_light_buttons()

    def advanced_view(self):
        self.label(self.body, 'Advanced', 28).pack(anchor='w', pady=(12, 8))
        self.label(self.body, 'Lighting adjustments, practice and room tools.', 18, True).pack(anchor='w', pady=(0, 18))
        self.row_buttons(self.body, [('Light level & colour', self.open_lighting, False),
                                     ('Scenes & channels', self.open_channels, False)], height=76)
        self.row_buttons(self.body, [('Practice', lambda: self.show('experiment'), False),
                                     ('System & help', lambda: self.show('health'), False)], height=76)
        self.row_buttons(self.body, [('Settings', lambda: self.show('settings'), False),
                                     ('Legacy controls', lambda: self.show('original'), False)], height=76)
        self.row_buttons(self.body, [('Clock & weather', lambda: self.show('visitor'), False),
                                     ('Blank screen', lambda: self.show('black'), False)], height=76)
        note = self.label(self.body, 'Blinds are not enabled on Home. Practice does not start a recording.', 17, True)
        self.wrap_label(note).pack(fill='x', pady=(16, 0))

    def open_lighting(self):
        self.show('room')
        if self.mode != 'room' or self.release_target or self.closing:
            return
        self.section = 'lighting'
        self.light_buttons = []
        self.rebuild_body(self.lighting_view)
        self.home_button.pack(side='right', padx=12)

    def open_channels(self):
        self.show('room')
        if self.mode == 'room' and not self.release_target and not self.closing:
            self.channel_view()
            self.home_button.pack(side='right', padx=12)

    def lighting_view(self):
        self.label(self.body, 'Lighting adjustments', 28).pack(anchor='w')
        self.label(self.body, 'Adjust colour and level, or choose a room scene.', 18, True).pack(anchor='w', pady=(0, 8))
        row = tk.Frame(self.body, bg=self.bg)
        row.pack(fill='both', expand=True)
        left, right = tk.Frame(row, bg=self.bg), tk.Frame(row, bg=self.bg, width=464)
        left.pack(side='left', fill='both', expand=True, padx=(0, 24))
        right.pack(side='right', fill='both')
        right.pack_propagate(False)
        self.slider_group(left, 'White-light colour · selected', self.cct, 1600, 10000, 100, 'K')
        self.slider_group(left, 'Light level · selected', self.intensity, 0, 1900, 25, 'controller units')
        state = self.label(left, size=16, muted=True)
        state.config(textvariable=self.light_text, height=3)
        self.wrap_label(state).pack(fill='x', pady=(0, 4))
        self.label(right, 'Room scenes', 21).pack(anchor='w', pady=(0, 8))
        on_off = self.row_buttons(right, [('Lights on', self.lights_on, False),
                                        ('Lights off', lambda: self.preset('Off'), False)])
        for button, kind in zip(on_off, ('on', 'off')):
            button.config(image=self.icon(kind, self.icon_colour), compound='left')
        self.light_buttons.extend(on_off)
        self.label(right, 'Spectral scenes', 17, True).pack(anchor='w', pady=(8, 0))
        scenes = self.row_buttons(right, [(name, lambda name=name: self.preset(name), False)
                                         for name in ('Fid', 'Sat', 'Dul')])
        for button in scenes:
            button.config(image=self.icon('scene', self.icon_colour), compound='left')
        self.light_buttons.extend(scenes)
        self.label(right, 'Scene codes match Legacy.', 17, True).pack(anchor='w', pady=(4, 4))
        advanced = self.row_buttons(right, [('Advanced controls', self.channel_view, False)])[0]
        advanced.config(image=self.icon('room', self.icon_colour), compound='left')
        self.row_buttons(right, [('What do these do?', self.open_lighting_help, False)])
        self.update_light_buttons()

    def visitor_view(self):
        self.label(self.body, 'Welcome to LESA', 28).pack(anchor='w', pady=(0, 16))
        row = tk.Frame(self.body, bg=self.bg)
        row.pack(fill='both', expand=True)
        for index in (0, 1):
            row.columnconfigure(index, weight=1, uniform='visitor')
        row.rowconfigure(0, weight=1)
        cards = []
        for index in (0, 1):
            frame = tk.Frame(row, bg=self.surface, highlightbackground=self.border, highlightthickness=1)
            frame.grid(row=0, column=index, sticky='nsew', padx=(0, 24) if index == 0 else 0)
            content = tk.Frame(frame, bg=self.surface)
            content.pack(fill='both', expand=True, padx=26, pady=20)
            cards.append(content)
        left, right = cards
        self.label(left, 'LOCAL TIME', 16, True).pack(anchor='w')
        clock = self.label(left, size=70)
        clock.config(textvariable=self.visitor_time, font=(FONT, 70, 'bold'))
        clock.pack(anchor='w', pady=(16, 0))
        date = self.label(left, size=23)
        date.config(textvariable=self.visitor_date)
        date.pack(anchor='w', pady=(0, 18))
        self.label(left, 'Room changes the lighting.\nLegacy opens the original controls.', 17, True).pack(anchor='w', pady=(0, 12))
        self.row_buttons(left, [('Room controls', lambda: self.show('room'), True),
                                ('Demo guide', lambda: self.show('guide'), False)])
        self.weather_contents(right)

    def weather_contents(self, right, compact=False):
        self.label(right, 'OUTDOOR WEATHER' if compact else 'WEATHER · ' + getattr(self.args, 'weather_name', 'Local area'), 16, True).pack(anchor='w')
        reading = tk.Frame(right, bg=self.surface)
        reading.pack(fill='x', pady=(6, 2) if compact else (18, 6))
        self.weather_symbol = tk.Canvas(reading, width=82, height=74, bg=self.surface, highlightthickness=0)
        self.weather_symbol.pack(side='right', pady=0 if compact else 12)
        size = 50 if compact else 68
        temperature = self.label(reading, size=size)
        temperature.config(textvariable=self.weather_temperature)
        temperature.pack(side='left')
        self.label(reading, self.temperature_unit.upper(), 24, True).pack(side='left', anchor='s', pady=18, padx=4)
        condition = self.label(right, size=23)
        condition.config(textvariable=self.weather_condition)
        self.wrap_label(condition).pack(fill='x')
        self.daylight_label = self.label(right, size=21)
        self.daylight_label.pack(anchor='w', pady=(8, 2) if compact else (18, 2))
        self.daylight_canvas = tk.Canvas(right, height=84, bg=self.surface, highlightthickness=0)
        self.daylight_canvas.pack(fill='x')
        self.daylight_canvas.bind('<Configure>', lambda event: self.update_weather(force=True))
        status = self.label(right, size=15, muted=True)
        status.config(textvariable=self.weather_text, height=2)
        self.wrap_label(status).pack(fill='x', pady=(6, 0))
        self.update_weather(force=True)
        self.start_weather()

    def update_weather(self, force=False):
        if self.mode not in ('room', 'visitor') or self.mode == 'room' and self.section != 'basic':
            return
        now = datetime.datetime.now()
        minute = now.strftime('%Y-%m-%dT%H:%M')
        if not force and minute == self.weather_rendered_minute:
            return
        self.weather_rendered_minute = minute
        canvas = self.daylight_canvas
        canvas.delete('all')
        self.weather_symbol.delete('all')
        data = self.weather_reading
        if not data:
            self.daylight_label.config(text='Daylight times unavailable')
            return
        primary = data['temperature_c'] if self.temperature_unit == 'c' else data['temperature_f']
        self.weather_temperature.set(u'%.0f°' % primary)
        self.weather_condition.set(data['condition'])
        code, colour = data['code'], self.icon_colour
        if code in (0, 1):
            self.weather_symbol.create_oval(25, 18, 57, 50, outline=colour, width=3)
            for angle in range(0, 360, 45):
                radians = math.radians(angle)
                self.weather_symbol.create_line(41+22*math.cos(radians), 34+22*math.sin(radians),
                    41+30*math.cos(radians), 34+30*math.sin(radians), fill=colour, width=2)
        else:
            self.weather_symbol.create_line(12, 48, 9, 34, 24, 26, 32, 12, 51, 14, 62, 29,
                75, 31, 78, 47, 65, 54, 23, 54, 12, 48, smooth=True, fill=colour, width=3)
            if code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82):
                for x in (27, 42, 57):
                    self.weather_symbol.create_line(x, 60, x-4, 68, fill=colour, width=2)
        day = weather_data.daylight(data, now)
        if day is None:
            self.daylight_label.config(text='Daylight times are from another date')
            return
        self.daylight_label.config(text=day['label'])
        left, right, y = 12, max(24, canvas.winfo_width()-12), 36
        position = left + (right-left) * day['fraction']
        canvas.create_line(left, y, right, y, fill=self.control, width=8)
        if position > left:
            canvas.create_line(left, y, position, y, fill=self.icon_colour, width=8)
        canvas.create_oval(position-7, y-7, position+7, y+7, fill='#d69c32', outline=self.surface, width=2)
        canvas.create_text(min(right-28, max(left+28, position)), 12, text=day['now'], font=(FONT, 15), fill=self.ink)
        canvas.create_text(left, 69, text='Sunrise ' + day['sunrise'], anchor='w', font=(FONT, 15), fill=self.muted)
        canvas.create_text(right, 69, text='Sunset ' + day['sunset'], anchor='e', font=(FONT, 15), fill=self.muted)

    def start_weather(self):
        now = monotonic()
        if (self.weather_worker or now - self.weather_checked < 900 or
                getattr(self.args, 'weather_latitude', None) is None):
            return
        self.weather_checked, self.weather_started = now, now
        if not self.weather_last_text:
            self.weather_text.set('Loading weather...')
        command = [sys.executable, '-B', os.path.join(os.path.dirname(__file__), 'weather.py'),
                   str(self.args.weather_latitude), str(self.args.weather_longitude), self.args.timezone]
        try:
            self.weather_worker = subprocess.Popen(command, close_fds=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
                                                   if hasattr(subprocess, 'DEVNULL') else subprocess.PIPE)
        except OSError:
            self.weather_text.set('Weather unavailable. Room controls still work.')

    def poll_weather(self):
        worker = getattr(self, 'weather_worker', None)
        if not worker:
            return
        if worker.poll() is None:
            if monotonic() - self.weather_started > 8:
                worker.kill()
            return
        try:
            reply = json.loads(worker.stdout.read(4097).decode('utf-8'))
            data = weather_data.validate(reply)
            text = u'Open-Meteo · model ' + data['model_time'].replace('T', ' ')
            self.weather_reading = data
            self.weather_last_text, self.weather_good = text, monotonic()
            self.weather_text.set(text)
            self.update_weather(force=True)
        except (ValueError, KeyError, TypeError, IOError):
            self.weather_text.set(('Last available weather (refresh failed):\n' + self.weather_last_text)
                                  if self.weather_last_text else 'Weather unavailable. Room controls still work.')
        finally:
            worker.stdout.close()
            if worker.stderr:
                worker.stderr.close()
            self.weather_worker = None

    def slider_group(self, parent, title, variable, low, high, step, unit):
        group = tk.Frame(parent, bg=self.surface, height=166, highlightbackground=self.border, highlightthickness=1)
        group.pack(fill='x', pady=(0, 4))
        group.pack_propagate(False)
        self.label(group, title, 20).pack(anchor='w', padx=16, pady=(8, 0))
        row = tk.Frame(group, bg=self.surface, height=66)
        row.pack(fill='x', padx=16, pady=(4, 0))
        row.pack_propagate(False)
        minus_area, plus_area = tk.Frame(row, width=64), tk.Frame(row, width=64)
        plus_area.pack(side='right', fill='y')
        minus_area.pack(side='right', fill='y', padx=(8, 8))
        minus_area.pack_propagate(False)
        plus_area.pack_propagate(False)
        minus = self.button(minus_area, '-', lambda: self.step_slider(variable, low, high, -step))
        plus = self.button(plus_area, '+', lambda: self.step_slider(variable, low, high, step))
        minus.pack(fill='both', expand=True)
        plus.pack(fill='both', expand=True)
        value = self.label(row, size=33)
        value.config(textvariable=variable)
        value.pack(side='left')
        self.label(row, unit, 16, True).pack(side='left', padx=10, anchor='s', pady=12)
        scale = tk.Scale(group, variable=variable, from_=low, to=high, resolution=step, orient='horizontal',
                         bg=self.surface, troughcolor=self.control, activebackground=ACCENT,
                         highlightthickness=0, bd=0, width=44, sliderlength=64, showvalue=False)
        scale.pack(fill='x', padx=16, pady=(2, 0))
        self.bind_slider(scale, 'cct')
        self.light_buttons.extend([minus, plus, scale])

    def step_slider(self, variable, low, high, step):
        variable.set(max(low, min(high, variable.get() + step)))
        self.cct_apply()

    def bind_slider(self, scale, action):
        generation = self.view_generation
        scale.bind('<ButtonPress-1>', lambda event: self.slider_pressed(scale, action, generation), add='+')
        scale.config(command=lambda value: self.slider_changed(scale, action, generation))

    def slider_pressed(self, scale, action, generation):
        if generation == self.view_generation and scale.cget('state') != 'disabled':
            self.slider_drag = (scale, action, generation)
            if self.help_on:
                self.status_text.set('Warm to cool white: kelvin and controller light-level input.'
                                     if action == 'cct' else 'Eight channel percentages. Changes send automatically.')

    def slider_changed(self, scale, action, generation):
        if self.slider_drag == (scale, action, generation) and generation == self.view_generation:
            self.cct_apply() if action == 'cct' else self.channels_apply()

    def slider_released(self, event):
        drag, self.slider_drag = self.slider_drag, None
        if drag and drag[2] == self.view_generation and self.mode == 'room':
            self.cct_apply() if drag[1] == 'cct' else self.channels_apply()

    def channel_view(self):
        self.cancel_intent()
        self.light_buttons = []
        self.section = 'channels'
        self.rebuild_body(self.channels_view)

    def channels_view(self):
        self.label(self.body, 'Advanced lighting - channel drive percentages', 27).pack(anchor='w')
        editor = tk.Frame(self.body, bg=self.bg)
        editor.pack(fill='both', expand=True, pady=14)
        for index, (name, value) in enumerate(zip(CHANNELS, self.channel_values)):
            editor.columnconfigure(index, weight=1, uniform='channel')
            cell = tk.Frame(editor, bg=self.bg)
            cell.grid(row=0, column=index, sticky='nsew', padx=6)
            self.label(cell, name, 18).pack()
            tk.Frame(cell, height=8, bg=CHANNEL_COLOURS[index]).pack(fill='x', pady=8)
            scale = tk.Scale(cell, variable=value, from_=100, to=0, resolution=1, bg=self.bg, fg=self.ink,
                             troughcolor=self.control, activebackground=ACCENT, highlightthickness=0,
                             bd=0, font=(FONT, 18), width=48, sliderlength=64, length=290)
            scale.pack(fill='both', expand=True)
            self.bind_slider(scale, 'channels')
            self.light_buttons.append(scale)
        self.row_buttons(self.body, [('Back to lighting', lambda: self.show('room'), False)])
        self.update_light_buttons()

    def preset(self, name):
        for variable, value in zip(self.channel_values, PRESETS[name]):
            variable.set(value)
        self.apply('channels', values=list(PRESETS[name]))

    def lights_on(self):
        self.cct.set(3500)
        self.intensity.set(1000)
        self.cct_apply()

    def cct_apply(self):
        self.apply('cct', cct=self.cct.get(), intensity=self.intensity.get())

    def channels_apply(self):
        self.apply('channels', values=[item.get() for item in self.channel_values])

    def apply(self, action, **arguments):
        if self.mode != 'room' or self.light_state not in ('ready', 'applying') or self.release_target or self.closing:
            self.status_text.set('Lighting unavailable. Use Legacy or ask staff.')
            return
        # Immutable complete intent, one unsent selection shared by all light controls.
        arguments = json.loads(json.dumps(arguments))
        self.queued_intent = (action, arguments, self.view_generation)
        if self.intent_timer is not None:
            self.root.after_cancel(self.intent_timer)
        self.intent_timer = self.root.after(250, self.dispatch_intent)
        self.lighting_feedback('Selected: ' + light_selection(action, arguments) + ' / waiting to send')

    def cancel_intent(self):
        if self.intent_timer is not None:
            self.root.after_cancel(self.intent_timer)
        self.intent_timer, self.queued_intent, self.slider_drag = None, None, None
        self.view_generation += 1

    def dispatch_intent(self):
        self.intent_timer = None
        if self.pending:
            return
        intent, self.queued_intent = self.queued_intent, None
        if (not intent or intent[2] != self.view_generation or self.mode != 'room' or
                self.light_state != 'ready' or self.release_target or self.closing):
            return
        action, arguments = intent[:2]
        self.light_state = 'applying'
        self.lighting_feedback('Sending: ' + light_selection(action, arguments) + ' / awaiting confirmation')
        self.status_text.set('Applying lighting. Please wait for fixture drive confirmation.')
        if not self.request(action, arguments):
            self.light_state = 'failed'
            self.cancel_intent()
            self.lighting_feedback('Lighting adapter unavailable. Use Legacy or ask staff.')
        self.update_light_buttons()

    def update_light_buttons(self):
        for button in self.light_buttons:
            if button.winfo_exists():
                button.config(state='normal' if self.light_state in ('ready', 'applying')
                              and not self.release_target and not self.closing else 'disabled')

    def experiment_view(self):
        title = self.label(self.body, self.profile['title'], 27)
        self.wrap_label(title).pack(fill='x')
        tk.Label(self.body, text='PRACTICE ONLY   /   Nothing is being recorded', font=(FONT, 20),
                 bg='#fff2db', fg='#6e4b0b', padx=16, pady=8).pack(anchor='w', pady=(0, 6))
        area = tk.Frame(self.body, bg=self.surface, height=208)
        area.pack(fill='x', pady=6)
        area.pack_propagate(False)
        self.stage_label = self.label(area, size=30)
        self.stage_label.config(height=2)
        self.wrap_label(self.stage_label).pack(fill='x', padx=22, pady=(8, 2))
        status = tk.Frame(area, bg=self.surface, height=60)
        status.pack(fill='x', padx=22)
        status.pack_propagate(False)
        self.run_label = self.label(status, size=17, muted=True)
        self.run_label.pack(side='left')
        self.timer_label = self.label(status, size=30)
        self.timer_label.pack(side='right')
        metadata = self.label(area, 'Profile describes: ' + self.profile['sensors'], 16, True)
        self.wrap_label(metadata).pack(fill='x', padx=22, pady=(0, 4))
        self.row_buttons(self.body, [('Start practice', self.start_preview, True),
                                     ('Pause practice', self.stop_preview, False),
                                     ('Previous instruction', self.previous_stage, False),
                                     ('Next instruction', self.next_stage, False)])
        self.row_buttons(self.body, [(label, lambda label=label: self.mark(label), False)
                                    for label in self.profile['annotations']])
        annotation = self.label(self.body, size=16, muted=True)
        annotation.config(textvariable=self.annotation_text, height=2)
        self.wrap_label(annotation).pack(fill='x')
        self.update_session()

    def start_preview(self):
        if not self.running:
            self.run_started, self.running = monotonic(), True
            self.emit('practice_started')
        self.update_session()

    def stop_preview(self):
        if self.running:
            self.elapsed += monotonic() - self.run_started
            self.running = False
            self.emit('practice_paused')
        self.update_session()

    def mark(self, label='Unexpected event'):
        try:
            sequence = self.emit('annotation', label=label, scope='panel_practice')
            self.pending_annotation = (sequence, label, time.strftime('%H:%M:%S'))
            self.annotation_text.set('Saving annotation: ' + label)
        except (IOError, OSError) as error:
            self.pending_annotation = None
            self.annotation_text.set('Annotation not saved: ' + str(error))

    def previous_stage(self):
        if self.stage > 0:
            self.stage -= 1
            self.emit('instruction_selected')
        self.update_session()

    def next_stage(self):
        if self.stage < len(self.profile['stages']) - 1:
            self.stage += 1
            self.emit('instruction_selected')
        else:
            self.stop_preview()
            self.annotation_text.set('Final instruction reached. Practice paused; no recording was made.')
        self.update_session()

    def update_session(self):
        if self.mode != 'experiment':
            return
        elapsed = self.elapsed + (monotonic() - self.run_started if self.running else 0)
        self.stage_label.config(text=self.profile['stages'][self.stage])
        self.timer_label.config(text='Practice time  %02d:%02d' % divmod(int(elapsed), 60))
        self.run_label.config(text='Instruction %d of %d   /   %s' % (
            self.stage + 1, len(self.profile['stages']), 'Practice running' if self.running else 'Practice paused'))

    def health_view(self):
        self.label(self.body, 'Panel resources', 28).pack(anchor='w', pady=(0, 4))
        self.health_rows = {}
        for key, title in [('ram', 'Memory'), ('disk', 'Storage')]:
            row = tk.Frame(self.body, bg=self.bg)
            row.pack(fill='x', pady=4)
            self.label(row, title + ' used', 23).pack(side='left')
            value = self.label(row, size=23)
            value.pack(side='right')
            canvas = tk.Canvas(self.body, height=24, bg=self.surface, bd=0, highlightthickness=0)
            canvas.pack(fill='x', pady=(0, 10))
            canvas.bind('<Configure>', lambda event: self.update_health())
            self.health_rows[key] = (value, canvas)
        self.health_details = self.label(self.body, size=23)
        self.wrap_label(self.health_details).pack(fill='x', pady=8)
        self.power_label = self.label(self.body, size=19)
        self.power_label.pack(anchor='w', pady=(0, 8))
        self.services_label = self.label(self.body, size=17, muted=True)
        self.wrap_label(self.services_label).pack(fill='x', pady=(0, 8))
        self.label(self.body, 'Readings refresh every 5 seconds. Service presence is not sensor health.', 17, True).pack(anchor='w', pady=4)
        self.row_buttons(self.body, [('Troubleshooting', lambda: self.show('support'), False),
                                     ('Demo guide', lambda: self.show('guide'), False)])
        self.update_health()

    def guide_view(self):
        title, kind, text = DEMO[self.guide_page]
        self.label(self.body, 'Explore the Smart Conference Room', 27).pack(anchor='w', pady=(0, 10))
        card = tk.Frame(self.body, bg=self.surface, highlightbackground=self.border, highlightthickness=1)
        card.pack(fill='both', expand=True)
        content = tk.Frame(card, bg=self.surface)
        content.pack(fill='both', expand=True, padx=24, pady=18)
        row = tk.Frame(content, bg=self.surface)
        row.pack(fill='x', pady=(0, 14))
        tk.Label(row, image=self.icon(kind, self.icon_colour), bg=self.surface).pack(side='left', padx=(0, 12))
        self.label(row, title, 26).pack(side='left')
        self.label(row, '%d of %d' % (self.guide_page+1, len(DEMO)), 17, True).pack(side='right')
        self.wrap_label(self.label(content, text, 21)).pack(fill='x')
        buttons = self.row_buttons(self.body, [('Previous', lambda: self.change_guide(-1), False),
                                               ('Next', lambda: self.change_guide(1), True),
                                               ('Room controls', lambda: self.show('room'), False)])
        buttons[0].config(state='normal' if self.guide_page else 'disabled')
        buttons[1].config(state='normal' if self.guide_page < len(DEMO)-1 else 'disabled')

    def change_guide(self, delta):
        self.guide_page = max(0, min(len(DEMO)-1, self.guide_page+delta))
        self.render()

    def support_view(self):
        self.label(self.body, 'Room troubleshooting · instructions only', 27).pack(anchor='w', pady=(0, 10))
        row = tk.Frame(self.body, bg=self.bg)
        row.pack(fill='both', expand=True)
        topics = tk.Frame(row, bg=self.bg, width=304)
        topics.pack(side='left', fill='y', padx=(0, 24))
        topics.pack_propagate(False)
        content = tk.Frame(row, bg=self.surface, highlightbackground=self.border, highlightthickness=1)
        content.pack(side='right', fill='both', expand=True)
        detail = tk.Frame(content, bg=self.surface)
        detail.pack(fill='both', expand=True, padx=22, pady=16)
        for index, (title, kind, text, commands) in enumerate(SUPPORT):
            button = self.row_buttons(topics, [(title, lambda index=index: self.choose_support(index), index == self.support_page)])[0]
            button.config(image=self.icon(kind, 'white' if index == self.support_page else self.ink), compound='left')
        title, kind, text, commands = SUPPORT[self.support_page]
        self.label(detail, title, 24).pack(anchor='w', pady=(0, 8))
        self.wrap_label(self.label(detail, text, 18)).pack(fill='x')
        if commands:
            code = self.label(detail, commands, 16)
            code.config(font=('monospace', 15), bg=self.control, padx=10, pady=8)
            self.wrap_label(code).pack(fill='x', pady=(12, 0))

    def choose_support(self, index):
        if index != self.support_page:
            self.support_page = index
            self.render()

    def update_health(self):
        if self.mode != 'health':
            return
        now = monotonic()
        if now - self.health_at >= 5:
            self.health_cache, self.health_at = health(), now
        if not self.status_worker and now - self.room_status_at >= 60:
            self.start_status()
        h = self.health_cache
        if 'error' in h:
            self.health_details.config(text='Resource reading unavailable: ' + h['error'])
            return
        self.health_rows['ram'][0].config(text='%d / %d MiB available' % (h['ram_available'], h['ram_total']))
        self.health_rows['disk'][0].config(text='%.1f GiB available  /  %.0f%% used' % (h['disk_available'], h['disk_used']))
        for key, used in [('ram', 100 * (1 - h['ram_available'] / float(h['ram_total']))), ('disk', h['disk_used'])]:
            canvas = self.health_rows[key][1]
            canvas.delete('all')
            canvas.create_rectangle(0, 0, max(1, canvas.winfo_width()) * used / 100, 24, fill=ACCENT, outline='')
        self.health_details.config(text='CPU temperature: %.1f C     /     Uptime: %.1f days\n'
                                       'Load average, one minute: %.2f' %
                                       (h['temperature'], h['uptime'], h['load']))
        self.power_label.config(text='Power: ' + h['power'],
                                fg='#c69c32' if h['power'].startswith('Current') else self.muted)
        self.services_label.config(text=self.room_status)

    def start_status(self):
        self.room_status_at = monotonic()
        master = getattr(self.args, 'expected_master', None)
        if not master or not sys.platform.startswith('linux'):
            self.room_status = 'Room service availability: no approved master configured.'
            return
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scr_touch_panel_lights.py')
        self.status_worker = subprocess.Popen([sys.executable, '-B', path, '--status-only',
                                               '--expected-master', master], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                              close_fds=True)
        self.status_started = monotonic()
        self.room_status = 'Checking advertised room services...'

    def poll_status(self):
        worker = self.status_worker
        if not worker:
            return
        age = monotonic() - self.status_started
        if worker.poll() is None:
            if age > 7:
                worker.kill()
            elif age > 5:
                worker.terminate()
            return
        try:
            result = json.loads(worker.stdout.read().decode('utf-8'))
            services = result['services']
            self.room_status = 'ROS master reachable / advertised services at ' + time.strftime('%H:%M:%S') + '\n'
            self.room_status += '   |   '.join(name + ': ' + ('present' if present else 'missing')
                                             for name, present in services)
        except (ValueError, KeyError):
            self.room_status = 'Room service availability could not be checked. No sensor data was queried.'
        worker.stdout.close()
        worker.stderr.close()
        self.status_worker = None

    def settings_view(self):
        self.label(self.body, 'Panel settings', 28).pack(anchor='w', pady=(0, 4))
        saved = self.label(self.body, size=16, muted=True)
        saved.config(textvariable=self.preference_text)
        self.wrap_label(saved).pack(fill='x', pady=(0, 8))
        row = tk.Frame(self.body, bg=self.bg)
        row.pack(fill='both', expand=True)
        categories = tk.Frame(row, bg=self.bg, width=304)
        categories.pack(side='left', fill='y', padx=(0, 24))
        categories.pack_propagate(False)
        detail = tk.Frame(row, bg=self.surface, highlightbackground=self.border, highlightthickness=1)
        detail.pack(side='right', fill='both', expand=True)
        for title, key in [('Appearance', 'appearance'), ('Date & weather', 'clock'),
                           ('Help & guidance', 'help'), ('Screen', 'screen'), ('About', 'about')]:
            self.row_buttons(categories, [(title, lambda key=key: self.choose_settings(key), self.settings_category == key)])
        content = tk.Frame(detail, bg=self.surface)
        content.pack(fill='both', expand=True, padx=24, pady=18)
        key = self.settings_category
        if key == 'appearance':
            self.label(content, 'Appearance', 25).pack(anchor='w', pady=(0, 6))
            self.label(content, 'Choose how this panel looks.', 18, True).pack(anchor='w', pady=(0, 8))
            self.row_buttons(content, [(name.title(), lambda name=name: self.choose_theme(name), self.theme_choice == name)
                                       for name in ('light', 'dark', 'auto')])
            self.label(content, 'Automatic schedule', 21).pack(anchor='w', pady=(10, 8))
            schedule = 'Light from %02d:%02d · Dark from %02d:%02d' % (divmod(self.args.light_at, 60) + divmod(self.args.dark_at, 60))
            self.label(content, schedule, 20).pack(anchor='w', pady=(0, 6))
            self.row_buttons(content, [(text, lambda field=field, delta=delta: self.adjust_schedule(field, delta), False)
                for text, field, delta in [('Light −1 h', 'light_at', -60), ('Light +1 h', 'light_at', 60),
                                           ('Dark −1 h', 'dark_at', -60), ('Dark +1 h', 'dark_at', 60)]])
            note = self.label(content, 'Auto waits for idle time. Practice keeps its theme.', 17, True)
            self.wrap_label(note).pack(fill='x', pady=(8, 0))
        elif key == 'clock':
            self.label(content, 'Date & weather', 25).pack(anchor='w', pady=(0, 8))
            self.label(content, time.strftime('%A, %d %B %Y'), 23).pack(anchor='w', pady=(0, 6))
            self.label(content, getattr(self.args, 'timezone', 'System timezone'), 18, True).pack(anchor='w', pady=(0, 10))
            self.row_buttons(content, [(name + '-hour', lambda name=name: self.choose_clock(name),
                                       self.clock_24 == (name == '24')) for name in ('12', '24')])
            self.label(content, 'Weather temperature', 21).pack(anchor='w', pady=(6, 4))
            self.row_buttons(content, [(label, lambda unit=unit: self.choose_temperature(unit),
                                       self.temperature_unit == unit)
                                      for label, unit in [(u'Celsius (°C)', 'c'), (u'Fahrenheit (°F)', 'f')]])
            self.label(content, 'Display units only. No room settings change.', 17, True).pack(anchor='w', pady=8)
        elif key == 'help':
            self.label(content, 'Help & guidance', 25).pack(anchor='w', pady=(0, 14))
            note = self.label(content, 'Tips explain controls in the bottom message area.', 18)
            self.wrap_label(note).pack(fill='x', pady=(0, 8))
            self.row_buttons(content, [('Tips on', lambda: self.choose_tips(True), self.help_on),
                                       ('Tips off', lambda: self.choose_tips(False), not self.help_on)])
            note = self.label(content,
                'White-light colour: lower K is warmer; higher K is cooler.\n'
                'Light level: controller input, not measured brightness.\n'
                'Fid / Sat / Dul: saved eight-channel mixtures from Legacy.\n'
                'Selected values send automatically after your touch settles.\n'
                'Last confirmed drive shows the latest successful readback.', 18)
            self.wrap_label(note).pack(fill='x', pady=(12, 8))
        elif key == 'screen':
            self.label(content, 'Idle clock & weather', 25).pack(anchor='w', pady=(0, 8))
            self.row_buttons(content, [(label, lambda seconds=seconds: self.choose_idle(seconds),
                                       self.idle_timeout == seconds)
                                      for label, seconds in [('Off', 0), ('1 min', 60), ('5 min', 300), ('15 min', 900)]])
            note = self.label(content, 'One touch returns to the previous page.\nIdle stays off in Practice, Legacy and during light commands.', 17, True)
            self.wrap_label(note).pack(fill='x', pady=(8, 12))
            self.label(content, 'Blank screen', 21).pack(anchor='w', pady=(0, 6))
            note = self.label(content, 'Black pixels only; the backlight stays on.\nHold one spot for 2 seconds to return.', 18)
            self.wrap_label(note).pack(fill='x', pady=(0, 8))
            self.row_buttons(content, [('Blank screen', lambda: self.show('black'), False)])
        else:
            self.about_contents(content)

    def choose_settings(self, category):
        if category == self.settings_category:
            return
        self.settings_category = category
        self.render()

    def choose_clock(self, format):
        if self.clock_24 == (format == '24'):
            return
        self.clock_24 = format == '24'
        self.save_preferences()
        self.render()
        self.emit('clock_format_selected', format=format)

    def choose_temperature(self, unit):
        if unit == self.temperature_unit:
            return
        self.temperature_unit = unit
        self.save_preferences()
        self.render()
        self.emit('temperature_unit_selected', unit=unit)

    def choose_idle(self, seconds):
        if seconds == self.idle_timeout:
            return
        self.idle_timeout = seconds
        self.activity()
        self.save_preferences()
        self.render()
        self.emit('idle_timeout_selected', seconds=seconds)

    def open_lighting_help(self):
        self.settings_category = 'help'
        self.show('settings')

    def choose_tips(self, enabled):
        if enabled == self.help_on:
            return
        self.help_on = enabled
        self.save_preferences()
        self.render()
        self.emit('help_selected', enabled=self.help_on)

    def about_view(self):
        self.about_contents(self.body)
        self.button(self.body, 'Back to Settings', lambda: self.show('settings')).pack(anchor='w')

    def about_contents(self, parent):
        self.label(parent, 'About this panel', 25).pack(anchor='w', pady=(0, 20))
        self.label(parent, 'Smart Conference Room · Beta', 23).pack(anchor='w', pady=(0, 12))
        self.label(parent, 'Built by Diyanko Bhowmik', 21).pack(anchor='w', pady=(0, 8))
        note = self.label(parent, 'With Codex assistance. Original contributors are retained in repository history.', 17, True)
        self.wrap_label(note).pack(fill='x', pady=(0, 18))
        self.label(parent, 'Source: github.com/LESA-RPI/scr.touch_panel', 18, True).pack(anchor='w', pady=(0, 24))
        self.label(parent, 'Rendered font: ' + self.font_family, 18, True).pack(anchor='w')

    def toggle_clock(self):
        self.clock_24 = not self.clock_24
        self.save_preferences()
        self.render()
        self.emit('clock_format_selected', format='24' if self.clock_24 else '12')

    def choose_theme(self, choice):
        if choice == self.theme_choice:
            return
        self.theme_choice, self.theme = choice, None
        self.save_preferences()
        self.set_theme()
        self.emit('theme_selected', choice=choice, resolved=self.theme)

    def adjust_schedule(self, key, delta):
        value = (getattr(self.args, key) + delta) % 1440
        if value != (self.args.dark_at if key == 'light_at' else self.args.light_at):
            setattr(self.args, key, value)
            self.save_preferences()
            self.emit('theme_schedule_changed', light_at=self.args.light_at, dark_at=self.args.dark_at)
            self.set_theme()
            self.render()

    def preference_summary(self):
        error = (self.preferences.error if self.preferences else None) or self.preference_error
        if error:
            return 'Appearance settings could not be saved or loaded; current choices still work.'
        return ('Appearance choices save automatically on this device.' if self.preferences else
                'Preview preferences last for this session. No room settings are saved.')

    def save_preferences(self):
        if self.preferences:
            self.preference_error = None
            self.preferences.save({'theme': self.theme_choice, 'clock_format': '24' if self.clock_24 else '12',
                                   'temperature_unit': self.temperature_unit,
                                   'idle_timeout': self.idle_timeout,
                                   'tips': 'on' if self.help_on else 'off',
                                   'light_at': self.args.light_at, 'dark_at': self.args.dark_at})

    def start_worker(self):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scr_touch_panel_lights.py')
        receipt = self.args.journal + '.lights-' + uuid.uuid4().hex[:8] + '.jsonl'
        self.worker = subprocess.Popen([getattr(self.args, 'adapter_python', '/usr/bin/python2.7'), '-u', '-B', path,
                                        '--receipt', receipt, '--parent-pid', str(os.getpid()),
                                        '--expected-master', self.args.expected_master],
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=sys.stderr, close_fds=True)
        self.light_state = 'connecting'
        self.confirmed_light = 'Not checked'
        self.confirmed_at = None
        self.lighting_feedback('Checking starting drive settings on 10 lights...')
        self.worker_buffer = ''
        self.worker_ready = False

    def request(self, action, arguments=None):
        if (self.pending or not self.worker or self.worker.poll() is not None or
                not getattr(self, 'worker_ready', False)):
            return False
        self.request_seq += 1
        item = {'version': 1, 'request_id': self.run_id + ':' + str(self.request_seq),
                'action': action, 'arguments': arguments or {}, 'sent_monotonic_s': monotonic()}
        self.emit('light_requested', request=item)
        try:
            self.worker.stdin.write((json.dumps(item) + '\n').encode('utf-8'))
            self.worker.stdin.flush()
        except (IOError, OSError) as error:
            self.light_state = 'failed'
            self.cancel_intent()
            self.status_text.set('Light adapter disconnected: ' + str(error))
            return False
        self.pending = item
        return True

    def poll_journal(self):
        journal = getattr(self, 'journal', None)
        if journal is None:
            return
        for sequence in journal.poll():
            if self.pending_annotation and sequence == self.pending_annotation[0]:
                unused, label, timestamp = self.pending_annotation
                text = 'Saved on panel' if self.args.journal else 'Written to panel output only'
                self.annotation_text.set('%s: %s at %s. Not added to a recording.' % (text, label, timestamp))
                self.pending_annotation = None
        error = journal.error or (journal.output_error if not self.args.journal else None)
        if error:
            if self.pending_annotation:
                self.annotation_text.set('Annotation not saved: ' + error)
                self.pending_annotation = None
            self.status_text.set('Panel journal unavailable: ' + error)

    def poll_worker(self):
        if self.closed:
            return
        self.poll_journal()
        self.poll_status()
        self.poll_weather()
        worker = self.worker
        if worker:
            if worker.poll() is None and not worker.stdin.closed and monotonic() - self.last_heartbeat >= 2:
                try:
                    worker.stdin.write((json.dumps({'version': 1, 'action': 'heartbeat', 'sent_monotonic_s': monotonic()}) + '\n').encode('utf-8'))
                    worker.stdin.flush()
                    self.last_heartbeat = monotonic()
                except (IOError, OSError):
                    pass
            while select.select([worker.stdout], [], [], 0)[0]:
                chunk = os.read(worker.stdout.fileno(), 8192)
                if not chunk:
                    break
                self.worker_buffer += chunk.decode('utf-8')
                if len(self.worker_buffer) > 8192:
                    self.cancel_intent()
                    self.light_state = 'failed'
                    self.status_text.set('Adapter reply too large; lighting disabled. Ask staff.')
                    worker.stdin.close()
                    self.worker_buffer = ''
                    break
            while '\n' in self.worker_buffer:
                line, self.worker_buffer = self.worker_buffer.split('\n', 1)
                try:
                    response = json.loads(line)
                except ValueError:
                    continue
                if (response.get('version') == 1 and response.get('state') == 'initialized' and
                        not self.worker_ready and self.light_state == 'connecting'):
                    self.worker_ready = True
                    self.request('release' if self.release_target or self.closing else 'acquire')
                    continue
                if not self.pending or response.get('request_id') != self.pending['request_id']:
                    continue
                if response.get('version') != 1 or response.get('state') not in ('ready', 'completed', 'released', 'failed'):
                    self.pending = None
                    self.cancel_intent()
                    self.light_state = 'failed'
                    self.status_text.set('Invalid adapter reply; lights disabled. Ask staff.')
                    self.lighting_feedback('Invalid reply. Controls disabled; ask staff.')
                    worker.stdin.close()
                    continue
                completed_request, self.pending = self.pending, None
                action = completed_request['action']
                self.emit('light_result', result=response)
                state = response['state']
                self.light_state = {'completed': 'ready', 'released': 'disconnected'}.get(state, state)
                detail = response.get('detail', 'Lighting ready; starting preset: ' + response.get('baseline', '?'))
                if state == 'failed':
                    # Full exception text remains in the emitted result/receipt.
                    # Keep the touch feedback bounded, even for verbose ROS errors.
                    detail = 'Result unconfirmed. Controls disabled; ask staff.'
                if state == 'completed':
                    self.confirmed_light = light_selection(action, completed_request['arguments'])
                    self.confirmed_at = monotonic()
                    detail = 'Confirmed - ' + detail
                elif state == 'ready':
                    self.confirmed_light = response.get('baseline', '?') + ' scene'
                    self.confirmed_at = monotonic()
                elif state == 'released':
                    self.confirmed_light = 'Session ended'
                    self.confirmed_at = None
                self.lighting_feedback(detail)
                self.status_text.set(detail)
                if action == 'release':
                    if state == 'failed':
                        self.release_target = None
                        self.status_text.set('Restore unconfirmed. Stay here; inspect the receipt before further control.')
                elif self.release_target and state != 'failed':
                    self.request('release')
                elif state == 'failed':
                    self.release_target = None
                    self.cancel_intent()
                    self.status_text.set(detail + ' / Use Legacy or ask staff.')
                elif self.queued_intent and self.intent_timer is None:
                    self.dispatch_intent()
                self.update_light_buttons()
            if worker.poll() is not None:
                if self.pending or self.light_state != 'disconnected':
                    self.cancel_intent()
                    self.pending = None
                    self.light_state = 'failed'
                    self.status_text.set('Light adapter stopped. Result unconfirmed; further commands disabled.')
                    self.lighting_feedback('Disconnected. Last result below is historical; ask staff.')
                self.worker = None
                target, self.release_target = self.release_target, None
                if self.closing:
                    self.finish_close()
                    return
                if target == 'original':
                    self.show('original')
                self.update_light_buttons()
        self.root.after(100, self.poll_worker)

    def begin_hold(self, event):
        self.cancel_hold()
        self.hold_origin = (event.x_root, event.y_root)
        self.hold = self.root.after(2000, lambda: self.show(self.blank_return))

    def move_hold(self, event):
        if self.hold_origin and ((event.x_root - self.hold_origin[0]) ** 2 +
                                 (event.y_root - self.hold_origin[1]) ** 2 > 40 ** 2):
            self.cancel_hold()

    def cancel_hold(self):
        if self.hold is not None:
            self.root.after_cancel(self.hold)
        self.hold = self.hold_origin = None

    def tick(self):
        if self.closed:
            return
        remaining = self.trial_deadline - monotonic() if self.trial_deadline is not None else None
        if remaining is not None and remaining <= 0 and not self.closing:
            self.close('timeout')
        if self.closed:
            return
        self.set_theme()
        self.clock.config(text=time.strftime('%a %d %b') + '  ' + time.strftime('%H:%M' if self.clock_24 else '%I:%M %p'))
        self.visitor_time.set(time.strftime('%H:%M') if self.clock_24 else time.strftime('%I:%M %p').lstrip('0'))
        self.visitor_date.set(time.strftime('%A, %d %B %Y'))
        self.preference_text.set(self.preference_summary())
        self.update_connection_badges()
        self.refresh_confirmation_age()
        self.update_idle()
        if self.mode == 'visitor' or self.mode == 'room' and self.section == 'basic':
            self.start_weather()
            self.update_weather()
            if self.weather_good is not None and monotonic() - self.weather_good > 1800:
                self.weather_text.set('Weather older than 30 minutes:\n' + self.weather_last_text)
        self.update_session()
        self.update_health()
        self.root.after(1000, self.tick)

    def close(self, reason):
        if self.closed or self.closing:
            return
        if self.keep_switcher and reason in ('exit', 'timeout', 'escape', 'window_close'):
            self.show('original')
            return
        self.closing = reason
        if getattr(self, 'weather_worker', None) and self.weather_worker.poll() is None:
            self.weather_worker.kill()
        if self.status_worker and self.status_worker.poll() is None:
            self.status_worker.terminate()
        self.cancel_intent()
        if self.worker and self.light_state in ('ready', 'applying', 'connecting'):
            self.release_target = 'close'
            self.status_text.set('Ending trial. Restoring starting light settings...')
            if not self.pending:
                self.request('release')
        elif self.worker:
            self.worker.stdin.close()
        else:
            self.finish_close()

    def finish_close(self):
        if not self.closed:
            if getattr(self, 'preferences', None):
                self.preferences.close()
                if not self.preferences.done.is_set():
                    self.root.after(50, self.finish_close)
                    return
            if getattr(self, 'weather_worker', None):
                if self.weather_worker.poll() is None:
                    self.weather_worker.kill()
                    self.root.after(50, self.finish_close)
                    return
                self.weather_worker.stdout.close()
                if self.weather_worker.stderr:
                    self.weather_worker.stderr.close()
                self.weather_worker = None
            if not self.journal.closing:
                self.emit('panel_closed', reason=self.closing or 'mainloop_exit', light_state=self.light_state)
                self.journal.close()
            if not self.journal.done.is_set():
                self.root.after(50, self.finish_close)
                return
            self.poll_journal()
            if self.journal.error:
                sys.stderr.write('Panel journal shutdown failed: ' + self.journal.error + '\n')
                sys.stderr.flush()
            if getattr(self, 'preferences', None) and self.preferences.error:
                sys.stderr.write('Appearance settings shutdown failed: ' + self.preferences.error + '\n')
                sys.stderr.flush()
            self.closed = True
            if self.worker:
                self.worker.stdin.close()
            if hasattr(self.root, 'tk'):
                for timer in self.root.tk.call('after', 'info'):
                    self.root.after_cancel(timer)
            self.root.destroy()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duration', type=float, default=600, help='Trial lifetime: 1..1800 s; 0 requires --keep-switcher')
    parser.add_argument('--keep-switcher', action='store_true', help='Keep touch navigation above Original after leaving the beta')
    parser.add_argument('--start-mode', choices=['room', 'original'], default='room', help='Initial view with --keep-switcher')
    parser.add_argument('--profile', help='Data-only JSON: title, sensors, stages, annotations')
    parser.add_argument('--journal', help='New private JSONL UI journal; never an existing recording context file')
    parser.add_argument('--preferences', help='Private appearance JSON file; saved choices override appearance CLI defaults')
    parser.add_argument('--weather-latitude', type=float, help='Optional model weather location, -90..90 degrees')
    parser.add_argument('--weather-longitude', type=float, help='Optional model weather location, -180..180 degrees')
    parser.add_argument('--weather-name', default='Local area', help='Short display name for the configured weather location')
    parser.add_argument('--logo', default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                                      'assets', 'lesa-logo.jpeg'), help='Original local logo; no asset is modified')
    parser.add_argument('--theme', choices=['auto', 'light', 'dark'], default='auto')
    parser.add_argument('--light-at', type=clock_minutes, default=420, help='Local HH:MM, default 07:00')
    parser.add_argument('--dark-at', type=clock_minutes, default=1140, help='Local HH:MM, default 19:00')
    parser.add_argument('--timezone', default='America/New_York', help='Process-local timezone for schedule and clock')
    parser.add_argument('--clock-format', choices=['12', '24'], default='24', help='Clock style; also adjustable in Settings')
    parser.add_argument('--temperature-unit', choices=['c', 'f'], default='f', help='Weather display unit; also adjustable in Settings')
    parser.add_argument('--idle-timeout', type=int, choices=[0, 60, 300, 900], default=300,
                        help='Idle clock/weather after seconds; 0 disables. Default 300; adjustable in Screen settings')
    parser.add_argument('--font', default='Cantarell', help='An installed font family; default Cantarell')
    parser.add_argument('--tips', choices=['on', 'off'], default='on', help='Short touch explanations; also switchable in the header')
    parser.add_argument('--dark-brand', choices=['wordmark', 'original'], default='wordmark',
                        help='Plain LESA text in dark mode, or original logo on a white plate')
    parser.add_argument('--adapter-python', default='/usr/bin/python2.7', help='Installed ROS interpreter, independent of the UI')
    parser.add_argument('--expected-master', default=os.environ.get('SCR_PANEL_MASTER'),
                        help='Approved ROS_MASTER_URI, or private SCR_PANEL_MASTER environment setting')
    parser.add_argument('--live-lights', action='store_true', help='Existing ROS environment; requires --journal and fresh owner check')
    parser.add_argument('--windowed', action='store_true', help='Local 1280x800 review without screen-size enforcement')
    args = parser.parse_args(argv)
    if ((args.weather_latitude is None) != (args.weather_longitude is None) or
            args.weather_latitude is not None and
            not (-90 <= args.weather_latitude <= 90 and -180 <= args.weather_longitude <= 180)):
        parser.error('Weather needs both valid latitude and longitude')
    global FONT
    FONT = args.font
    if (math.isnan(args.duration) or math.isinf(args.duration) or
            not (1 <= args.duration <= 1800 or args.keep_switcher and args.duration == 0)):
        parser.error('Duration must be finite in 1..1800 seconds, or 0 with --keep-switcher')
    if args.light_at == args.dark_at:
        parser.error('Light and dark start times must differ')
    if args.live_lights and (not args.journal or not sys.platform.startswith('linux')):
        parser.error('Live lights require Linux, a new journal and the existing ROS environment')
    if args.live_lights and not args.expected_master:
        parser.error('Live lights require --expected-master or SCR_PANEL_MASTER')
    os.environ['TZ'] = args.timezone
    if hasattr(time, 'tzset'):
        time.tzset()
    panel = Panel(args)
    signal.signal(signal.SIGTERM, lambda signum, frame: panel.close('signal_%d' % signum))
    signal.signal(signal.SIGINT, lambda signum, frame: panel.close('signal_%d' % signum))
    try:
        panel.root.mainloop()
    finally:
        if not panel.closed:
            if panel.worker:
                panel.worker.stdin.close()
                panel.worker.wait()
            panel.journal.close()
            panel.journal.thread.join(timeout=2)
            panel.finish_close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
