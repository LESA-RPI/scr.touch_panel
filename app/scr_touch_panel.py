#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Independent SCR touchscreen. Author: Diyanko Bhowmik, with Codex assistance.

Python 3.11+, installed Tk and Pillow. Data-only profiles and
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
import threading
import time
import uuid
from io import BytesIO
from scr_touch_panel_lights import PRESETS, setter_words
from event_journal import EventJournal
from preferences import Preferences, load as load_preferences
import weather as weather_data
import panel_icons
from touch_slider import TouchSlider
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
PALETTES = {'dark': ('#151a20', '#151a20', '#f0f3f6', '#b5c0ca', '#27333f'),
            'light': ('#ffffff', '#ffffff', '#12384b', '#476373', '#edf1f4')}
ACCENT = '#176b72'
NAVIGATION = [('Home', 'room'), ('Room tools', 'advanced'),
              ('Demo & guide', 'guide'), ('Legacy', 'original')]
ADVANCED_PAGES = [('White light', 'white'), ('Scenes & channels', 'scenes'),
                  ('Experiment mode', 'experiment'), ('Appearance', 'appearance'),
                  ('Date & weather', 'clock'), ('Screen', 'screen'),
                  ('System & help', 'system'), ('About', 'about')]
DEFAULT_PROFILE = {'title': 'Room activity instructions', 'sensors': 'Ceiling and colour sensors',
                   'stages': ['Leave the room empty', 'Please sit still',
                              'Make small seated movements', 'Walk around the room',
                              'Leave the room empty again'],
                   'annotations': ['Activity started', 'Activity finished', 'Unexpected event']}
TIPS = {'Lights on': 'Standard white: selects 3500 K and light-level input 1000 for all lights.',
        'Lights off': 'Sends zero drive to all light channels. The panel screen stays on.',
        'Advanced controls': 'Adjust eight colour-channel drives. Values are controller percentages, not measured light.',
        'Room': 'Everyday lighting. Changes send automatically after your touch settles.',
        'Visitor': 'Room introduction and a large clock. Opening this page does not change lighting.',
        'Experiment mode': 'Instructions, elapsed time and panel annotations. No sensor recording starts.',
        'System': 'Panel resources and advertised room services. Presence does not prove sensor health.',
        'Legacy': 'Restores the starting lighting, then shows the original room controls.',
        'Blank screen': 'Shows black pixels. Hold still for 2 seconds to return; the backlight remains on.',
        'Settings': 'Appearance, date/time and screen options. Appearance choices can be saved on this device.',
        'About panel': 'Panel credits and source repository. No room settings change.',
        'Start instructions': 'Starts the instruction timer only. It does not start sensor collection.',
        'Next instruction': 'Shows the next instruction. The final instruction does not wrap.',
        'End trial and restore': 'Restores confirmed trial changes and returns to the original program.'}


def monotonic():
    if hasattr(time, 'monotonic'):
        return time.monotonic()
    with open('/proc/uptime') as stream:
        return float(stream.read().split()[0])


def set_changed(variable, value):
    """Avoid scheduling redraws for unchanged clock/status values."""
    if not hasattr(variable, 'get') or variable.get() != value:
        variable.set(value)


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


def confirmed_power(response):
    """Describe uniform controller readback, never optical or continuously live state."""
    if response.get('state') == 'ready' and response.get('baseline') in PRESETS:
        return 'off' if response['baseline'] == 'Off' else 'on'
    values = response.get('words')
    if (response.get('state') == 'completed' and isinstance(values, list) and len(values) == 8
            and all(isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 65535 for v in values)):
        return 'on' if any(values) else 'off'
    return None


def confirmed_scene(response):
    """Match an admitted baseline or exact confirmed drive words, never a selection."""
    if response.get('state') == 'ready' and response.get('baseline') in PRESETS:
        return response['baseline']
    if response.get('state') == 'completed' and confirmed_power(response) is not None:
        values = tuple(response['words'])
        return next((name for name, preset in PRESETS.items() if values == setter_words(preset)), None)
    return None


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
        self.advanced_page, self.last_advanced_page = None, 'white'
        self.guide_page, self.support_page = -1, 0
        self.support_commands_visible = False
        self.started, self.run_id, self.sequence = monotonic(), uuid.uuid4().hex, 0
        self.boot_id, self.last_touch = boot_identity(), self.started
        self.idle_timeout = getattr(args, 'idle_timeout', 300)
        self.blinds_display = getattr(args, 'blinds_display', 'disabled')
        self.idle_active, self.press_active = False, False
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
        self.health_worker, self.health_pending = None, None
        self.worker, self.pending, self.worker_buffer = None, None, ''
        self.queued_intent, self.intent_timer, self.slider_drag = None, None, None
        self.view_generation = 0
        self.light_state, self.release_target = 'disconnected', None
        self.confirmed_light = 'Not checked'
        self.confirmed_at, self.light_message = None, 'Lighting not connected'
        self.confirmed_power = None
        self.confirmed_scene = None
        self.home_power_buttons = []
        self.scene_buttons = []
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
        self.connection_text = tk.StringVar()
        self.visitor_time, self.visitor_date = tk.StringVar(), tk.StringVar()
        self.preference_text = tk.StringVar(value=self.preference_summary())
        self.weather_text = tk.StringVar(value='Not configured. A location is needed.')
        self.home_weather_text = tk.StringVar(value='Weather not configured')
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
        if hasattr(self, 'feedback_message'):
            set_changed(self.feedback_message, self.light_message.replace(' input / level ', ' · level '))
            set_changed(self.feedback_detail, 'Recent settings: ' + self.confirmed_light.replace(' input / level ', ' · level ') + suffix)
        card = getattr(self, 'light_feedback_card', None)
        if card is not None and card.winfo_exists():
            edge = '#b88036' if self.light_state == 'failed' else ACCENT if self.pending or self.queued_intent else self.border
            if getattr(card, '_edge', None) != edge:
                card.config(highlightbackground=edge)
                card._edge = edge
        self.update_power_highlights()

    def feedback_card(self, parent):
        """Keep results in the page flow, with separate message and readback lines."""
        if not hasattr(self, 'feedback_message'):
            self.feedback_message = tk.StringVar()
            self.feedback_detail = tk.StringVar()
        card = tk.Frame(parent, bg=parent.cget('bg'), highlightbackground=self.border, highlightthickness=1)
        card.pack(fill='x', pady=(12, 0))
        self.light_feedback_card = card
        content = tk.Frame(card, bg=card.cget('bg'))
        content.pack(fill='x', padx=14, pady=12)
        message = self.label(content, size=15)
        message.config(textvariable=self.feedback_message)
        self.wrap_label(message).pack(fill='x')
        detail = self.label(content, size=14, muted=True)
        detail.config(textvariable=self.feedback_detail)
        self.wrap_label(detail).pack(fill='x', pady=(4, 0))
        self.refresh_confirmation_age()

    def update_power_highlights(self):
        certain = self.light_state == 'ready' and not any((self.pending, self.queued_intent, self.release_target, self.closing))
        state = getattr(self, 'confirmed_power', None) if certain else None
        for button, power, label in getattr(self, 'home_power_buttons', []):
            if button.winfo_exists():
                selected = state == power
                style = (selected, self.control, self.ink, self.icon_colour)
                if getattr(button, '_power_style', None) == style:
                    continue
                button._power_style = style
                button.config(bg=ACCENT if selected else self.control,
                              highlightbackground=ACCENT if selected else self.border,
                              fg='white' if selected else self.ink,
                              activebackground='#10575e' if selected else self.pressed_colour(),
                              text=label,
                              image=self.icon(power, 'white' if selected else self.icon_colour))
        for button, name in getattr(self, 'scene_buttons', []):
            if button.winfo_exists():
                selected = certain and getattr(self, 'confirmed_scene', None) == name
                style = (selected, self.control, self.ink)
                if getattr(button, '_scene_style', None) == style:
                    continue
                button._scene_style = style
                button.config(bg=ACCENT if selected else self.control,
                              highlightbackground=ACCENT if selected else self.border,
                              fg='white' if selected else self.ink,
                              activebackground='#10575e' if selected else self.pressed_colour(),
                              activeforeground='white' if selected else self.ink,
                              text=name)

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
            self.idle_active = True
            self.show('visitor')
            self.status_text.set('Touch anywhere for Home and light controls.')
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
        self.idle_active = False
        self.activity(False)
        self.show('room')

    def pressed_colour(self):
        return '#d8e4ee' if getattr(self, 'theme', 'light') == 'light' else '#394b5c'

    def button(self, parent, text, action, accent=False):
        button = tk.Button(parent, text=text, command=action, font=(FONT, 19),
                         fg='white' if accent else self.ink, bg=ACCENT if accent else self.control,
                         activebackground='#10575e' if accent else self.pressed_colour(),
                         activeforeground='white' if accent else self.ink, disabledforeground=self.muted,
                         bd=0, relief='flat', highlightthickness=1,
                         highlightbackground=ACCENT if accent else self.border, highlightcolor=ACCENT,
                         padx=14, pady=13, takefocus=True)
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

    def photo(self, key, image):
        if key not in self.icon_cache:
            buffer = BytesIO()
            image.save(buffer, format='PNG')
            self.icon_cache[key] = tk.PhotoImage(data=base64.b64encode(buffer.getvalue()).decode('ascii'))
        return self.icon_cache[key]

    def icon(self, kind, colour, size=32):
        key = (kind, colour, size)
        if key not in self.icon_cache:
            self.photo(key, panel_icons.control(kind, colour, size))
        return self.icon_cache[key]

    def row_buttons(self, parent, items, height=64):
        row = tk.Frame(parent, bg=parent.cget('bg'), height=height)
        row.pack(fill='x', pady=6)
        row.grid_propagate(False)
        row.rowconfigure(0, weight=1)
        buttons = []
        for index, (text, action, accent) in enumerate(items):
            button = self.button(row, text, action, accent)
            # Spacer columns keep the actual button widths equal, including the last.
            row.columnconfigure(index * 2, weight=1, uniform='buttons')
            if index:
                row.columnconfigure(index * 2 - 1, minsize=12)
            button.grid(row=0, column=index * 2, sticky='nsew')
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
        advanced_page = getattr(self, 'advanced_page', None)
        self.theme = chosen
        self.bg, self.surface, self.ink, self.muted, self.control = PALETTES[chosen]
        self.border = '#cbd6df' if chosen == 'light' else '#3b4a58'
        self.icon_colour = '#386a73' if chosen == 'light' else '#91c1c7'
        self.connection_badges = []
        for child in self.root.winfo_children():
            if child != self.dock:
                child.destroy()
        self.root.configure(bg=self.bg)
        self.banner = tk.Frame(self.root, bg=self.bg, height=76)
        self.banner.pack(fill='x', padx=24, pady=(8, 6))
        self.banner.pack_propagate(False)
        if self.artwork:
            tk.Label(self.banner, image=self.artwork, bg='white', bd=0, padx=8).pack(side='left', anchor='n', padx=(0, 18))
        else:
            brand = self.label(self.banner, 'LESA', 30)
            brand.config(fg=ACCENT)
            brand.pack(side='left', padx=(0, 18))
        identity = tk.Frame(self.banner, bg=self.bg)
        identity.pack(side='left', anchor='s')
        self.label(identity, 'Smart Conference Room', 32).pack(side='left', anchor='s')
        beta = self.label(identity, 'Beta', 16)
        beta.config(fg=self.icon_colour, bg=self.control, padx=10, pady=4)
        beta.pack(side='left', anchor='s', padx=(12, 0), pady=(0, 10))
        self.clock = self.label(self.banner, size=17, muted=True)
        navigation = tk.Frame(self.banner, bg=self.bg, width=444, height=64)
        navigation.pack(side='right')
        navigation.pack_propagate(False)
        for column, text, action in [(0, 'Home', self.open_home),
                                     (2, 'Legacy', lambda: self.show('original'))]:
            slot = tk.Frame(navigation, bg=self.bg, width=140, height=64)
            slot.grid(row=0, column=column, padx=(0, 12) if column == 0 else 0)
            slot.pack_propagate(False)
            button = self.button(slot, text, action)
            button.config(image=self.icon('home' if column == 0 else 'original', self.ink, 24),
                          compound='left', font=(FONT, 17), padx=6)
            button.pack(fill='both', expand=True)
            if column == 0:
                self.home_button = button
        self.tips_button = self.button(self.banner, 'Tips: ' + ('On' if self.help_on else 'Off'), self.toggle_tips)
        self.add_connection_badge(navigation, column=1)
        self.nav = tk.Frame(self.root, bg=self.bg)
        self.nav_buttons = {}
        self.footer = tk.Frame(self.root, bg=self.bg, height=80)
        self.footer.pack_propagate(False)
        self.tools_footer_button = self.guide_footer_button = None
        for text, mode, gap in (('Demo & guide', 'guide', 0), ('Room tools', 'advanced', 12)):
            button = self.button(self.footer, text, lambda mode=mode: self.open_guide() if mode == 'guide' else self.show(mode))
            button.config(width=224, image=self.icon(mode, self.ink, 24), compound='left', font=(FONT, 18))
            if mode == 'advanced':
                self.tools_footer_button = button
            else:
                self.guide_footer_button = button
            button.pack(side='right', padx=(0, gap), pady=8)
        status = self.label(self.footer, size=17, muted=True)
        status.config(textvariable=self.status_text)
        self.wrap_label(status)
        status.pack(side='left', fill='both', expand=True)
        self.body = tk.Frame(self.root, bg=self.bg)
        self.build_dock()
        self.render()
        if advanced_page:
            return
        if section == 'channels' and self.mode == 'room':
            self.channel_view()
        elif section == 'lighting' and self.mode == 'room':
            self.open_lighting()

    def build_dock(self):
        # The 144px footprint covers only the preserved application's banner.
        for child in self.dock.winfo_children():
            child.destroy()
        self.dock.configure(bg=self.bg)
        top = tk.Frame(self.dock, bg=self.bg, height=76)
        top.pack(fill='x', padx=24, pady=(8, 6))
        top.pack_propagate(False)
        if self.artwork:
            tk.Label(top, image=self.artwork, bg='white', bd=0, padx=8).pack(side='left', anchor='n', padx=(0, 18))
        else:
            self.label(top, 'LESA', 30).pack(side='left', padx=(0, 18))
        identity = tk.Frame(top, bg=self.bg)
        identity.pack(side='left', anchor='s')
        self.label(identity, 'Smart Conference Room', 32).pack(side='left', anchor='s')
        beta = self.label(identity, 'Beta', 16)
        beta.config(fg=self.icon_colour, bg=self.control, padx=10, pady=4)
        beta.pack(side='left', anchor='s', padx=(12, 0), pady=(0, 10))
        navigation = tk.Frame(top, bg=self.bg, width=444, height=64)
        navigation.pack(side='right')
        navigation.pack_propagate(False)
        home_slot = tk.Frame(navigation, bg=self.bg, width=140, height=64)
        home_slot.pack(side='left', padx=(0, 12));home_slot.pack_propagate(False)
        home = self.button(home_slot, 'Home', self.open_home)
        home.config(font=(FONT, 17), padx=6, image=self.icon('home', self.ink, 24), compound='left')
        home.pack(fill='both', expand=True)
        mode = tk.Label(navigation, text='Legacy view', font=(FONT, 20), bg=self.control,
                        fg=self.ink, image=self.icon('original', self.ink, 24), compound='left', padx=16)
        mode.pack(side='left', fill='both', expand=True)
        row = tk.Frame(self.dock, bg=self.bg, height=48)
        row.pack(fill='x', padx=24, pady=(0, 6));row.pack_propagate(False)
        for title, kind, action, gap in [('Demo & guide', 'guide', self.open_guide, 0),
                                         ('Room tools', 'advanced', lambda: self.show('advanced'), 12)]:
            slot = tk.Frame(row, bg=self.bg, width=224, height=48)
            slot.pack(side='right', padx=(0, gap));slot.pack_propagate(False)
            button = self.button(slot, title, action)
            button.config(font=(FONT, 17), pady=6, image=self.icon(kind, self.ink, 24), compound='left')
            button.pack(fill='both', expand=True)
        self.label(row, 'Legacy controls below · Home returns to the main screen', 16, True).pack(side='left', fill='y')

    def add_connection_badge(self, parent, legacy=False, column=None):
        frame = tk.Frame(parent, bg=self.bg, width=140, height=64)
        if column is None:
            frame.pack(side='right', padx=(8, 0))
        else:
            frame.grid(row=0, column=column, padx=(0, 12))
        frame.pack_propagate(False)
        button = self.button(frame, '', lambda: self.open_advanced('system'))
        button.config(font=(FONT, 15), padx=6, compound='left')
        button.pack(fill='both', expand=True)
        self.connection_badges.append((button, legacy))
        self.update_connection_badges()

    def update_connection_badges(self):
        text, kind, colour = connection(self.light_state, self.args.live_lights)
        if hasattr(self, 'connection_text'):
            set_changed(self.connection_text, text)
        colours = {'good': '#23794c' if self.theme == 'light' else '#87c6a1',
                   'waiting': self.icon_colour, 'warning': '#9a650b' if self.theme == 'light' else '#e6ba66',
                   'neutral': self.muted}
        for button, legacy in getattr(self, 'connection_badges', []):
            if button.winfo_exists():
                label, icon, ink = ('Legacy', 'original', self.muted) if legacy else (text, kind, colours[colour])
                if button.cget('text') != label:
                    button.config(text=label, fg=ink, activeforeground=ink, image=self.icon(icon, ink))

    def cycle_theme(self):
        self.choose_theme({'auto': 'light', 'light': 'dark', 'dark': 'auto'}[self.theme_choice])

    def show(self, mode, advanced_page=None):
        if self.release_target is not None or self.closing:
            return
        if mode == 'advanced':
            self.open_advanced()
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
            self.blank_advanced_return = self.advanced_page
        self.cancel_hold()
        self.mode, self.section = mode, ('lighting' if advanced_page == 'white' else
                                        'channels' if advanced_page == 'scenes' else 'basic')
        self.advanced_page = advanced_page
        if self.light_state != 'failed' and not self.pending:
            messages = {'health': 'Live panel readings. No system settings change.',
                        'room': '',
                        'advanced': 'Fine adjustments and room tools. Opening a page does not operate devices.',
                        'visitor': 'Visitor view does not change lighting. Recording status is unavailable here.',
                        'experiment': 'Experiment mode: instructions and annotations. Recorder not connected.',
                        'settings': 'Appearance settings belong to this device; they do not change room lighting.',
                        'about': 'Panel credits and source repository. No room settings change.'}
            messages.update(guide='',
                            support='Instructions only. Commands are not executed by this panel.')
            if mode in messages:
                self.status_text.set(messages[mode])
        self.render()
        self.emit('mode_changed', target=mode)

    def render(self):
        self.cancel_intent()
        self.light_buttons = []
        self.home_power_buttons = []
        self.scene_buttons = []
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
        if self.idle_active:
            self.banner.pack_forget()
            self.footer.pack_forget()
            self.rebuild_body(self.screensaver_view)
            self.install_wake_bindings()
            return
        if not self.banner.winfo_manager():
            self.banner.pack(fill='x', padx=24, pady=(8, 6))
        self.clock.pack_forget()
        if getattr(self, 'advanced_page', None):
            self.tools_footer_button.pack_forget()
        elif not self.tools_footer_button.winfo_manager():
            self.tools_footer_button.pack(side='right', padx=(0, 12), pady=8)
        if self.mode == 'guide':
            self.guide_footer_button.pack_forget()
        elif not self.guide_footer_button.winfo_manager():
            placement = {'before': self.tools_footer_button} if self.tools_footer_button.winfo_manager() else {}
            self.guide_footer_button.pack(side='right', pady=8, **placement)
        if self.tools_footer_button.winfo_manager():
            self.tools_footer_button.pack_configure(padx=(0, 12) if self.guide_footer_button.winfo_manager() else 0)
        if not self.footer.winfo_manager():
            self.footer.pack(side='bottom', fill='x', padx=24, pady=(8, 10))
        if (getattr(self, 'advanced_page', None) and
                getattr(self, 'advanced_shell', None) is self.body):
            self.rebuild_advanced_detail()
        else:
            self.rebuild_body(self.advanced_view if getattr(self, 'advanced_page', None)
                              else getattr(self, self.mode + '_view'))
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
        controls.columnconfigure(1, minsize=16)
        groups = ('Lights', 'Blinds') if self.blinds_display == 'disabled' else ('Lights',)
        for index, title in enumerate(groups):
            controls.columnconfigure(index * 2, weight=1, uniform='essentials')
            group = tk.Frame(controls, bg=self.bg)
            group.grid(row=0, column=index * 2, sticky='nsew')
            self.label(group, title, 25).pack(anchor='w')
            self.label(group, 'Whole room' if title == 'Lights' else 'Unavailable', 16, True).pack(anchor='w', pady=(2, 16))
            actions = [('Lights on', self.lights_on, False),
                       ('Lights off', lambda: self.preset('Off'), False)] if index == 0 else [
                       ('Open slats', None, False), ('Close & lower', None, False)]
            for title, action, accent in actions:
                button = self.row_buttons(group, [(title, action, accent)], height=104)[0]
                button.config(font=(FONT, 22))
                if index == 0:
                    button.config(image=self.icon('on' if title == 'Lights on' else 'off',
                                                'white' if accent else self.icon_colour), compound='left')
                    self.light_buttons.append(button)
                    self.home_power_buttons.append((button, 'on' if title == 'Lights on' else 'off', title))
                else:
                    # Intentionally no callback, adapter or opt-in switch until qualified.
                    button.config(state='disabled', bg=self.bg, highlightbackground=self.border,
                                  disabledforeground=self.muted)
            caption = self.label(group, 'Standard room lighting' if index == 0 else 'Disabled', 17, True)
            self.wrap_label(caption).pack(fill='x', pady=(8, 0))
        self.feedback_card(left)
        self.label(right, getattr(self.args, 'weather_name', 'Local time'), 18, True).pack(anchor='w')
        clock = self.label(right, size=64)
        clock.config(textvariable=self.visitor_time)
        clock.pack(anchor='w', pady=(12, 0))
        date = self.label(right, size=23)
        date.config(textvariable=self.visitor_date)
        self.wrap_label(date).pack(fill='x', pady=(0, 6))
        self.weather_contents(right, compact=True)
        self.update_light_buttons()

    def advanced_view(self):
        shell = self.body
        self.advanced_shell = shell
        self.advanced_sidebar_buttons = []
        self.advanced_detail = None
        sidebar = tk.Frame(shell, bg=self.bg, width=280)
        sidebar.pack(side='left', fill='y', padx=(0, 28), pady=(10, 0))
        sidebar.pack_propagate(False)
        sidebar.grid_propagate(False)
        sidebar.columnconfigure(0, weight=1)
        self.label(sidebar, 'Room tools', 25).grid(row=0, column=0, sticky='w', pady=(0, 16))
        for index, (label, page) in enumerate(ADVANCED_PAGES, 1):
            sidebar.rowconfigure(index, weight=1, uniform='tools')
            button = self.button(sidebar, label, lambda page=page: self.open_advanced(page),
                                 self.advanced_page == page)
            button.config(font=(FONT, 16), anchor='w', padx=12, pady=8,
                          image=self.icon('date' if page == 'clock' else page, 'white' if self.advanced_page == page else self.ink, 24), compound='left')
            button.grid(row=index, column=0, sticky='nsew', pady=(0, 10))
            self.advanced_sidebar_buttons.append((button, page))
        self.rebuild_advanced_detail()

    def rebuild_advanced_detail(self):
        """Keep the sidebar mapped while replacing only the selected tool."""
        shell = self.body
        for button, page in self.advanced_sidebar_buttons:
            selected = self.advanced_page == page
            colour = ACCENT if selected else self.control
            if button.cget('bg') != colour:
                button.config(bg=colour, fg='white' if selected else self.ink,
                              highlightbackground=ACCENT if selected else self.border,
                              activebackground='#10575e' if selected else self.pressed_colour(),
                              activeforeground='white' if selected else self.ink,
                              image=self.icon('date' if page == 'clock' else page, 'white' if selected else self.ink, 24))
        previous = self.advanced_detail
        detail = tk.Frame(shell, bg=self.bg)
        self.body = detail
        try:
            page = self.advanced_page
            if page == 'white':
                self.label(detail, 'White light', 27).pack(anchor='w', pady=(0, 6))
                self.label(detail, 'Selected values apply after your touch settles.', 17, True).pack(anchor='w', pady=(0, 6))
                self.slider_group(detail, 'Colour temperature', self.cct, 1600, 10000, 100, 'K')
                self.slider_group(detail, 'Light level', self.intensity, 0, 1900, 25, 'controller units')
                self.feedback_card(detail)
                self.update_light_buttons()
            elif page == 'scenes':
                self.channels_view()
            elif page == 'experiment':
                self.experiment_view()
            elif page == 'system':
                self.system_contents()
            elif page == 'about':
                self.about_contents(detail)
            else:
                self.settings_category = page
                self.settings_contents(detail)
                saved = self.label(detail, size=15, muted=True)
                saved.config(textvariable=self.preference_text, height=2)
                self.wrap_label(saved).pack(fill='x', pady=(8, 0))
        finally:
            self.body = shell
        if previous is not None:
            previous.pack_forget()
        detail.pack(side='left', fill='both', expand=True, pady=(10, 0))
        self.advanced_detail = detail
        if previous is not None:
            previous.destroy()

    def open_advanced(self, page=None):
        page = page or self.last_advanced_page
        if page not in dict((key, label) for label, key in ADVANCED_PAGES):
            return
        target = 'room' if page in ('white', 'scenes') else ('experiment' if page == 'experiment' else
                  'health' if page == 'system' else 'about' if page == 'about' else 'settings')
        if self.release_target or self.closing:
            return
        if getattr(self, 'mode', None) == target and getattr(self, 'advanced_page', None) == page:
            return
        self.last_advanced_page = page
        self.show(target, advanced_page=page)

    def open_home(self):
        if self.mode != 'room' or getattr(self, 'advanced_page', None):
            self.show('room')

    def open_lighting(self):
        self.open_advanced('white')

    def open_channels(self):
        self.open_advanced('scenes')

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
        self.label(self.body, 'Touch anywhere for Home and light controls' if self.idle_active else 'Clock & weather', 28).pack(anchor='w', pady=(0, 16))
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
        self.label(left, 'Home has Lights on and Lights off.\nOpening Home does not change the lights.', 17, True).pack(anchor='w', pady=(0, 12))
        self.row_buttons(left, [('Home · light controls', lambda: self.show('room'), True)], height=76)
        self.weather_contents(right)

    def screensaver_view(self):
        top = tk.Frame(self.body, bg=self.bg, height=76)
        top.pack(fill='x', padx=28, pady=(28, 0))
        top.pack_propagate(False)
        if self.artwork:
            tk.Label(top, image=self.artwork, bg='white', bd=0).pack(side='left', anchor='n', padx=(0, 20))
        self.label(top, 'Smart Conference Room', 28).pack(side='left', anchor='s')
        self.label(top, 'SCREEN SAVER', 17, True).pack(side='right')
        bottom = tk.Frame(self.body, bg=self.bg)
        bottom.pack(side='bottom', fill='x', padx=100, pady=(0, 44))
        self.row_buttons(bottom, [('Touch anywhere for room controls', self.return_from_idle, True)], height=88)
        hint = self.label(bottom, 'Opens Home with Lights on and Lights off', 17, True)
        hint.config(anchor='center')
        hint.pack(fill='x', pady=(12, 0))
        row = tk.Frame(self.body, bg=self.bg)
        row.pack(fill='both', expand=True, padx=48, pady=(32, 16))
        row.columnconfigure(0, weight=1, uniform='idle')
        row.columnconfigure(1, weight=1, uniform='idle')
        left = tk.Frame(row, bg=self.bg)
        left.grid(row=0, column=0, sticky='nsew', padx=(0, 36))
        right = tk.Frame(row, bg=self.bg)
        right.grid(row=0, column=1, sticky='nsew', padx=(36, 0))
        self.label(left, 'LOCAL TIME', 16, True).pack(anchor='w', pady=(28, 0))
        clock = self.label(left, size=76)
        clock.config(textvariable=self.visitor_time)
        clock.pack(anchor='w', pady=(8, 4))
        date = self.label(left, size=21)
        date.config(textvariable=self.visitor_date)
        self.wrap_label(date).pack(fill='x')
        self.weather_contents(right, compact=True, large=True)

    def weather_contents(self, right, compact=False, large=False):
        self.label(right, 'OUTDOOR WEATHER' if compact else 'WEATHER · ' + getattr(self.args, 'weather_name', 'Local area'), 16, True).pack(anchor='w')
        reading = tk.Frame(right, bg=right.cget('bg'))
        reading.pack(fill='x', pady=(6, 2) if compact else (18, 6))
        self.weather_symbol_size = 144 if large else 96
        self.weather_symbol = tk.Canvas(reading, width=self.weather_symbol_size, height=self.weather_symbol_size,
                                        bg=right.cget('bg'), highlightthickness=0)
        self.weather_symbol.pack(side='right', pady=0 if compact else 12)
        size = 72 if large else 50 if compact else 68
        temperature = self.label(reading, size=size)
        temperature.config(textvariable=self.weather_temperature)
        temperature.pack(side='left')
        self.label(reading, self.temperature_unit.upper(), 24, True).pack(side='left', anchor='s', pady=18, padx=4)
        condition = self.label(right, size=26 if large else 23)
        condition.config(textvariable=self.weather_condition)
        self.wrap_label(condition).pack(fill='x')
        status = self.label(right, size=16, muted=True)
        status.config(textvariable=self.home_weather_text, height=2)
        self.wrap_label(status).pack(fill='x', pady=(6, 0))
        self.daylight_label = self.label(right, size=21)
        self.daylight_label.pack(anchor='w', pady=(8, 2) if compact else (18, 2))
        self.daylight_canvas = tk.Canvas(right, height=70, bg=right.cget('bg'), highlightthickness=0)
        self.daylight_canvas.pack(fill='x')
        self.daylight_canvas.bind('<Configure>', lambda event: self.update_weather(force=True))
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
        sunrise, sunset = weather_data.local_time(data['sunrise']), weather_data.local_time(data['sunset'])
        current_day = sunrise.date() == now.date() == sunset.date()
        night = current_day and not sunrise <= now < sunset
        kind = panel_icons.weather_kind(data['code'], night)
        # Earlier daylight data cannot establish whether it is currently day or night.
        if not current_day and data['code'] in (0, 1, 2):
            kind = 'circle-question-mark'
        size = self.weather_symbol_size
        key = ('weather', kind, self.theme, size)
        if key not in self.icon_cache:
            self.photo(key, panel_icons.weather(kind, self.theme, size))
        self.weather_symbol.create_image(size // 2, size // 2, image=self.icon_cache[key])
        day = weather_data.daylight(data, now)
        if day is None:
            self.daylight_label.config(text='Daylight times are from another date')
            return
        self.daylight_label.config(text=day['label'])
        left, right, y = 12, max(24, canvas.winfo_width()-12), 36
        position = left + (right-left) * day['fraction']
        canvas.create_line(left, y, right, y, fill=self.control, width=6, capstyle='round')
        if position > left:
            canvas.create_line(left, y, position, y, fill=self.icon_colour, width=6, capstyle='round')
        canvas.create_oval(position-7, y-7, position+7, y+7, fill=self.icon_colour, outline=self.surface, width=2)
        canvas.create_text(min(right-28, max(left+28, position)), 12, text=day['now'], font=(FONT, 15), fill=self.ink)
        canvas.create_text(left, 58, text='Sunrise ' + day['sunrise'], anchor='w', font=(FONT, 15), fill=self.muted)
        canvas.create_text(right, 58, text='Sunset ' + day['sunset'], anchor='e', font=(FONT, 15), fill=self.muted)

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
        group = tk.Frame(parent, bg=self.surface, height=190, highlightbackground=self.border, highlightthickness=1)
        group.pack(fill='x', pady=(0, 12))
        group.pack_propagate(False)
        self.label(group, title, 18).pack(anchor='w', padx=20, pady=(8, 0))
        row = tk.Frame(group, bg=self.surface, height=62)
        row.pack(fill='x', padx=20, pady=(4, 0))
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
        scale = TouchSlider(group, variable=variable, from_=low, to=high, resolution=step,
                            orient='horizontal', background=self.surface, track=self.control,
                            accent=ACCENT, border=self.border, ink=self.ink)
        scale.pack(fill='x', padx=20, pady=(4, 0))
        limits = tk.Frame(group, bg=self.surface)
        limits.pack(fill='x', padx=20, pady=(4, 4))
        self.label(limits, 'Min {:,} {}'.format(low, unit), 13, True).pack(side='left')
        self.label(limits, 'Max {:,} {}'.format(high, unit), 13, True).pack(side='right')
        self.bind_slider(scale, 'cct')
        self.light_buttons.extend([minus, plus, scale])

    def step_slider(self, variable, low, high, step):
        variable.set(max(low, min(high, variable.get() + step)))
        self.cct_apply()

    def bind_slider(self, scale, action):
        generation = self.view_generation
        if isinstance(scale, TouchSlider):
            scale.on_start = lambda: self.slider_pressed(scale, action, generation)
            scale.on_end = lambda: self.slider_released(None)
        else:
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
        self.open_advanced('scenes')

    def channels_view(self):
        self.label(self.body, 'Scenes & channels', 27).pack(anchor='w')
        self.label(self.body, 'Room scenes keep their Legacy names. Inputs below are selected values.', 16, True).pack(anchor='w', pady=(4, 8))
        buttons = self.row_buttons(self.body, [(name, lambda name=name: self.preset(name), False)
                                               for name in ('Fid', 'Sat', 'Dul')], height=62)
        self.light_buttons.extend(buttons)
        self.scene_buttons = list(zip(buttons, ('Fid', 'Sat', 'Dul')))
        editor = tk.Frame(self.body, bg=self.bg)
        editor.pack(fill='x', pady=14)
        for index, (name, value) in enumerate(zip(CHANNELS, self.channel_values)):
            editor.columnconfigure(index, weight=1, uniform='channel')
            cell = tk.Frame(editor, bg=self.bg)
            cell.grid(row=0, column=index, sticky='nsew', padx=4)
            self.label(cell, name, 15).pack()
            tk.Frame(cell, height=8, bg=CHANNEL_COLOURS[index]).pack(fill='x', pady=8)
            number = self.label(cell, size=16)
            number.config(textvariable=value)
            number.pack()
            scale = TouchSlider(cell, variable=value, from_=100, to=0, resolution=1,
                                orient='vertical', background=self.bg, track=self.control,
                                accent=ACCENT, border=self.border, ink=self.ink, length=200)
            scale.pack(fill='both', expand=True)
            self.bind_slider(scale, 'channels')
            self.light_buttons.append(scale)
        self.feedback_card(self.body)
        self.update_light_buttons()

    def preset(self, name):
        for variable, value in zip(self.channel_values, PRESETS[name]):
            variable.set(value)
        self.apply('channels', immediate=True, values=list(PRESETS[name]))

    def lights_on(self):
        self.cct.set(3500)
        self.intensity.set(1000)
        self.apply('cct', immediate=True, cct=self.cct.get(), intensity=self.intensity.get())

    def cct_apply(self):
        self.apply('cct', cct=self.cct.get(), intensity=self.intensity.get())

    def channels_apply(self):
        self.apply('channels', values=[item.get() for item in self.channel_values])

    def apply(self, action, immediate=False, **arguments):
        if self.mode != 'room' or self.light_state not in ('ready', 'applying') or self.release_target or self.closing:
            self.status_text.set('Lighting unavailable. Use Legacy or ask staff.')
            return
        # Immutable complete intent, one unsent selection shared by all light controls.
        arguments = json.loads(json.dumps(arguments))
        self.queued_intent = (action, arguments, self.view_generation)
        if self.intent_timer is not None:
            self.root.after_cancel(self.intent_timer)
        self.intent_timer = None
        if immediate:
            if self.pending:
                self.lighting_feedback('Selected: ' + light_selection(action, arguments) + ' / waiting for current request')
            self.dispatch_intent()
            return
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
        self.status_text.set('Updating lights. Waiting for confirmation…')
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
        self.update_power_highlights()

    def experiment_view(self):
        self.label(self.body, 'Experiment mode', 27).pack(anchor='w')
        title = self.label(self.body, self.profile['title'], 17, True)
        self.wrap_label(title).pack(fill='x')
        self.label(self.body, 'Recorder not connected · instructions and panel annotations only', 17, True).pack(anchor='w', pady=(6, 8))
        area = tk.Frame(self.body, bg=self.surface, height=184)
        area.pack(fill='x', pady=6)
        area.pack_propagate(False)
        self.stage_label = self.label(area, size=24)
        self.stage_label.config(height=2)
        self.wrap_label(self.stage_label).pack(fill='x', padx=22, pady=(8, 2))
        status = tk.Frame(area, bg=self.surface, height=50)
        status.pack(fill='x', padx=22)
        status.pack_propagate(False)
        self.run_label = self.label(status, size=17, muted=True)
        self.run_label.pack(side='left')
        self.timer_label = self.label(status, size=26)
        self.timer_label.pack(side='right')
        metadata = self.label(area, 'Profile describes: ' + self.profile['sensors'], 16, True)
        self.wrap_label(metadata).pack(fill='x', padx=22, pady=(0, 4))
        self.row_buttons(self.body, [('Start instructions', self.start_preview, True),
                                     ('Pause', self.stop_preview, False)], height=60)
        self.row_buttons(self.body, [('Previous instruction', self.previous_stage, False),
                                     ('Next instruction', self.next_stage, False)], height=60)
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
            self.annotation_text.set('Final instruction reached. Instructions paused; recorder not connected.')
        self.update_session()

    def update_session(self):
        if self.mode != 'experiment':
            return
        elapsed = self.elapsed + (monotonic() - self.run_started if self.running else 0)
        self.stage_label.config(text=self.profile['stages'][self.stage])
        self.timer_label.config(text='Elapsed  %02d:%02d' % divmod(int(elapsed), 60))
        self.run_label.config(text='Instruction %d of %d   /   %s' % (
            self.stage + 1, len(self.profile['stages']), 'Running' if self.running else 'Paused'))

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
                                     ('Demo guide', self.open_guide, False)])
        self.update_health()

    def system_contents(self):
        self.label(self.body, 'System & help', 27).pack(anchor='w', pady=(0, 8))
        self.label(self.body, 'Read-only checks. Available services may not be producing sensor data.', 15, True).pack(anchor='w', pady=(0, 10))
        overview = tk.Frame(self.body, bg=self.bg, height=160)
        overview.pack(fill='x', pady=(0, 12))
        overview.grid_propagate(False)
        overview.columnconfigure(0, weight=1, uniform='system')
        overview.columnconfigure(1, minsize=12)
        overview.columnconfigure(2, weight=1, uniform='system')
        overview.rowconfigure(0, weight=1)
        cards = []
        for column, title in ((0, 'Panel health'), (2, 'Room connection')):
            card = tk.Frame(overview, bg=self.bg, highlightbackground=self.border, highlightthickness=1)
            card.grid(row=0, column=column, sticky='nsew')
            content = tk.Frame(card, bg=self.bg)
            content.pack(fill='both', expand=True, padx=14, pady=10)
            self.label(content, title, 17).pack(anchor='w', pady=(0, 6))
            cards.append(content)
        self.health_details = self.label(cards[0], size=15)
        self.wrap_label(self.health_details).pack(fill='x', pady=(0, 6))
        self.power_label = self.label(cards[0], size=15, muted=True)
        self.wrap_label(self.power_label).pack(fill='x')
        row = tk.Frame(cards[1], bg=self.bg)
        row.pack(fill='x', pady=(0, 4))
        self.label(row, 'Lighting', 15, True).pack(side='left', padx=(0, 12))
        state = self.label(row, size=20)
        state.config(textvariable=self.connection_text)
        state.pack(side='left')
        self.label(row, 'Blinds · Disabled', 14, True).pack(side='right')
        self.services_label = self.label(cards[1], size=13, muted=True)
        self.wrap_label(self.services_label).pack(fill='x')
        topic = tk.Frame(self.body, bg=self.bg, height=58)
        topic.pack(fill='x', pady=(0, 4))
        topic.pack_propagate(False)
        self.label(topic, 'Help topic', 18).pack(side='left', padx=(0, 20))
        selected = tk.StringVar(value=SUPPORT[self.support_page][0])
        menu = tk.OptionMenu(topic, selected, *[item[0] for item in SUPPORT],
                             command=lambda name: self.choose_support([item[0] for item in SUPPORT].index(name)))
        menu.config(font=(FONT, 18), bg=self.control, fg=self.ink, highlightthickness=1,
                    highlightbackground=self.border, highlightcolor=ACCENT, bd=0, padx=18, pady=10,
                    activebackground=self.pressed_colour(), activeforeground=self.ink,
                    image=self.icon('dropdown', self.ink, 24), compound='right', indicatoron=False)
        menu['menu'].config(font=(FONT, 18), bg=self.control, fg=self.ink,
                            activebackground=ACCENT, activeforeground='white', activeborderwidth=0)
        menu.pack(side='left', fill='y')
        title, kind, text, commands = SUPPORT[self.support_page]
        card = tk.Frame(self.body, bg=self.bg, highlightbackground=self.border, highlightthickness=1)
        card.pack(fill='x', pady=(6, 0))
        content = tk.Frame(card, bg=self.bg)
        content.pack(fill='x', padx=14, pady=10)
        show_commands = commands and self.support_commands_visible
        if not show_commands:
            for index, paragraph in enumerate(text.split('\n\n')):
                self.wrap_label(self.label(content, paragraph, 15)).pack(fill='x', pady=(4 if index else 0, 0))
        else:
            overview.pack_forget()
            self.label(content, 'Room host · reference commands', 12, True).pack(anchor='w', pady=(8, 4))
            code = self.label(content, commands, 13)
            code.config(font=('monospace', 13), bg=self.control, padx=10, pady=6)
            self.wrap_label(code).pack(fill='x')
            self.label(content, 'Reference only. This panel does not execute these commands.', 14, True).pack(anchor='w', pady=(8, 0))
        if commands:
            self.row_buttons(content, [('Back to guidance' if show_commands else 'Room host reference',
                                        self.toggle_support_commands, False)], height=60)
        self.update_health()

    def open_guide(self):
        self.guide_page = -1
        self.show('guide')

    def choose_guide(self, index):
        self.guide_page = index
        self.show('guide')

    def guide_view(self):
        if self.guide_page < 0:
            self.label(self.body, 'Demo & guide', 27).pack(anchor='w', pady=(0, 6))
            self.label(self.body, 'Choose a topic. Exploring this guide does not operate equipment.', 17, True).pack(anchor='w', pady=(0, 18))
            topics = tk.Frame(self.body, bg=self.bg)
            topics.pack(fill='both', expand=True, pady=(0, 10))
            captions = ['White light and saved scenes', 'Home, Legacy and blinds',
                        'Instructions, markers and recording', 'Panel, services and weather']
            for index, ((title, kind, text), caption) in enumerate(zip(DEMO, captions)):
                row, column = divmod(index, 2)
                topics.rowconfigure(row, weight=1, uniform='guide')
                topics.columnconfigure(column, weight=1, uniform='guide')
                card = tk.Frame(topics, bg=self.bg, highlightbackground=self.border, highlightthickness=1)
                card.grid(row=row, column=column, sticky='nsew', padx=(0, 16) if column == 0 else 0,
                          pady=(0, 16) if row == 0 else 0)
                button = self.button(card, title + '\n' + caption, lambda index=index: self.choose_guide(index))
                button.config(font=(FONT, 20), image=self.icon(kind, self.icon_colour), compound='top',
                              wraplength=520, justify='center', bg=self.bg, padx=20, pady=18, highlightthickness=0)
                button.pack(fill='both', expand=True)
            return
        title, kind, text = DEMO[self.guide_page]
        heading = tk.Frame(self.body, bg=self.bg)
        heading.pack(fill='x', pady=(0, 12))
        self.label(heading, 'Demo & guide', 27).pack(side='left')
        self.label(heading, '%d of %d topics' % (self.guide_page+1, len(DEMO)), 17, True).pack(side='right')
        card = tk.Frame(self.body, bg=self.surface, highlightbackground=self.border, highlightthickness=1)
        card.pack(fill='both', expand=True)
        content = tk.Frame(card, bg=self.surface)
        content.pack(fill='both', expand=True, padx=24, pady=22)
        row = tk.Frame(content, bg=self.surface)
        row.pack(fill='x', pady=(0, 20))
        tk.Label(row, image=self.icon(kind, self.icon_colour), bg=self.surface).pack(side='left', padx=(0, 12))
        self.label(row, title, 26).pack(side='left')
        for paragraph in text.split('\n\n'):
            self.wrap_label(self.label(content, paragraph, 21)).pack(fill='x', pady=(0, 18))
        buttons = self.row_buttons(self.body, [('All topics', self.open_guide, False),
                                               ('Previous', lambda: self.change_guide(-1), False),
                                               ('Next', lambda: self.change_guide(1), False)])
        for button, kind in zip(buttons, ('guide','chevron-left','chevron-right')):
            button.config(image=self.icon(kind, self.ink, 24), compound='left')
        buttons[1].config(state='normal' if self.guide_page else 'disabled')
        buttons[2].config(state='normal' if self.guide_page < len(DEMO)-1 else 'disabled')
        for button, kind in zip(buttons, ('guide', 'chevron-left', 'chevron-right')):
            button.config(image=self.icon(kind, self.muted if button.cget('state') == 'disabled' else self.ink, 24))

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
            self.support_commands_visible = False
            self.render()

    def toggle_support_commands(self):
        self.support_commands_visible = not self.support_commands_visible
        self.render()

    def update_health(self):
        if self.mode != 'health':
            return
        now = monotonic()
        pending = getattr(self, 'health_pending', None)
        if pending is not None:
            self.health_cache, self.health_pending = pending, None
        worker = getattr(self, 'health_worker', None)
        if now - self.health_at >= 5 and (worker is None or not worker.is_alive()):
            self.health_at = now
            def read_resources():
                # No Tk calls on this thread; a slow SD or power query cannot hold a touch.
                try:
                    self.health_pending = health()
                except Exception as error:
                    self.health_pending = {'error': str(error)}
            self.health_worker = threading.Thread(target=read_resources, name='scr-panel-resources')
            self.health_worker.daemon = True
            self.health_worker.start()
        if not self.status_worker and now - self.room_status_at >= 60:
            self.start_status()
        h = self.health_cache
        if not h:
            self.health_details.config(text='Checking panel resources…')
            self.services_label.config(text=self.room_status)
            return
        if 'error' in h:
            self.health_details.config(text='Resource reading unavailable: ' + h['error'])
            return
        if getattr(self, 'advanced_page', None) == 'system':
            self.health_details.config(text='Memory: %d / %d MiB free\nStorage: %.1f GiB free · CPU: %.1f C' %
                (h['ram_available'], h['ram_total'], h['disk_available'], h['temperature']))
            self.power_label.config(text='Power: ' + h['power'])
            self.services_label.config(text=self.room_status)
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
        self.settings_contents(content)

    def settings_contents(self, content):
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
            note = self.label(content, 'Auto waits for idle time. Experiment mode keeps its theme.', 17, True)
            self.wrap_label(note).pack(fill='x', pady=(8, 0))
            self.label(content, 'Touch explanations', 21).pack(anchor='w', pady=(14, 4))
            self.row_buttons(content, [('Tips on', lambda: self.choose_tips(True), self.help_on),
                                       ('Tips off', lambda: self.choose_tips(False), not self.help_on)])
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
            source = self.label(content, size=16, muted=True)
            source.config(textvariable=self.weather_text, height=3)
            self.wrap_label(source).pack(fill='x', pady=(12, 0))
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
                'Recent settings shows the last confirmed light settings.', 18)
            self.wrap_label(note).pack(fill='x', pady=(12, 8))
        elif key == 'screen':
            self.label(content, 'Screen saver', 25).pack(anchor='w', pady=(0, 8))
            self.row_buttons(content, [(label, lambda seconds=seconds: self.choose_idle(seconds),
                                       self.idle_timeout == seconds)
                                      for label, seconds in [('Off', 0), ('1 min', 60), ('5 min', 300), ('15 min', 900)]])
            note = self.label(content, 'Touch once for Home and lighting controls.\nPauses during experiments, Legacy and light commands.', 17, True)
            self.wrap_label(note).pack(fill='x', pady=(8, 12))
            self.label(content, 'Blank screen', 21).pack(anchor='w', pady=(0, 6))
            note = self.label(content, 'Black pixels only; the backlight stays on.\nHold one spot for 2 seconds to return.', 18)
            self.wrap_label(note).pack(fill='x', pady=(0, 8))
            self.row_buttons(content, [('Blank screen', lambda: self.show('black'), False),
                                       ('Clock & weather', lambda: self.show('visitor'), False)])
            self.label(content, 'Blinds on Home', 21).pack(anchor='w', pady=(12, 4))
            self.row_buttons(content, [('Show disabled', lambda: self.choose_blinds_display('disabled'), self.blinds_display == 'disabled'),
                                       ('Hide', lambda: self.choose_blinds_display('hidden'), self.blinds_display == 'hidden')])
        else:
            self.about_contents(content)

    def choose_settings(self, category):
        if getattr(self, 'advanced_page', None):
            self.open_advanced(category if category != 'help' else 'system')
            return
        if category == self.settings_category:
            return
        self.settings_category = category
        self.render()

    def choose_blinds_display(self, choice):
        if choice not in ('disabled', 'hidden') or choice == self.blinds_display:
            return
        self.blinds_display = choice
        self.save_preferences()
        self.render()
        self.emit('blinds_display_selected', choice=choice)

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
        self.support_page = 0
        self.open_advanced('system')

    def choose_tips(self, enabled):
        if enabled == self.help_on:
            return
        self.help_on = enabled
        self.save_preferences()
        self.render()
        self.emit('help_selected', enabled=self.help_on)

    def about_view(self):
        self.about_contents(self.body)
        self.button(self.body, 'Appearance', lambda: self.open_advanced('appearance')).pack(anchor='w')

    def about_contents(self, parent):
        self.label(parent, 'Smart Conference Room', 27).pack(anchor='w', pady=(0, 8))
        self.label(parent, 'Touch panel · Beta mode', 20, True).pack(anchor='w', pady=(0, 28))
        self.label(parent, 'Built by Diyanko Bhowmik', 21).pack(anchor='w', pady=(0, 10))
        note = self.label(parent, 'Original contributors are credited in the repository history.', 17, True)
        self.wrap_label(note).pack(fill='x', pady=(0, 22))
        self.label(parent, 'Source: github.com/LESA-RPI/scr.touch_panel', 18, True).pack(anchor='w', pady=(0, 20))
        self.label(parent, 'Icons: Lucide · lucide.dev', 17, True).pack(anchor='w')

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
                                   'blinds_display': self.blinds_display,
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
        self.confirmed_power = None
        self.confirmed_scene = None
        self.lighting_feedback('Checking the current light settings…')
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
        if getattr(self, 'mode', None) == 'health' and getattr(self, 'health_pending', None) is not None:
            self.update_health()
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
                    self.confirmed_power = confirmed_power(response)
                    self.confirmed_scene = confirmed_scene(response)
                    detail = 'Light settings confirmed.'
                elif state == 'ready':
                    detail = 'Lighting ready.'
                    self.confirmed_light = response.get('baseline', '?') + ' scene'
                    self.confirmed_at = monotonic()
                    self.confirmed_power = confirmed_power(response)
                    self.confirmed_scene = confirmed_scene(response)
                elif state == 'released':
                    self.confirmed_light = 'Session ended'
                    self.confirmed_at = None
                    self.confirmed_power = None
                    self.confirmed_scene = None
                self.lighting_feedback(detail)
                self.status_text.set('' if state in ('ready', 'completed') else detail)
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
        self.hold = self.root.after(2000, self.return_from_blank)

    def return_from_blank(self):
        page = getattr(self, 'blank_advanced_return', None)
        if page:
            self.open_advanced(page)
        else:
            self.show(self.blank_return)

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
        clock = time.strftime('%a %d %b') + '  ' + time.strftime('%H:%M' if self.clock_24 else '%I:%M %p')
        if self.clock.cget('text') != clock:
            self.clock.config(text=clock)
        set_changed(self.visitor_time, time.strftime('%H:%M') if self.clock_24 else time.strftime('%I:%M %p').lstrip('0'))
        set_changed(self.visitor_date, time.strftime('%A, %d %B %Y'))
        set_changed(self.preference_text, self.preference_summary())
        self.update_connection_badges()
        self.refresh_confirmation_age()
        self.update_idle()
        if self.weather_reading:
            old = (self.weather_good is None or monotonic() - self.weather_good > 1800
                   or self.weather_reading['model_time'][:10] != datetime.date.today().isoformat()
                   or self.weather_text.get().startswith('Last available'))
            caption = weather_data.details(self.weather_reading, self.temperature_unit, earlier=old)
        else:
            caption = 'Weather not configured' if self.args.weather_latitude is None else 'Weather unavailable'
        set_changed(self.home_weather_text, caption)
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
    parser.add_argument('--dark-brand', choices=['wordmark', 'original'], default='original',
                        help='Compatibility option; the original logo is retained in both themes')
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
