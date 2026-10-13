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
try:
    import Tkinter as tk
    from tkFont import Font
except ImportError:
    import tkinter as tk
    from tkinter.font import Font

FONT = 'Ubuntu'
CHANNELS = ('Blue 1', 'Blue 2', 'Blue 3', 'Lime', 'Amber', 'Orange', 'Red 1', 'Red 2')
CHANNEL_COLOURS = ('#4764bc', '#337cb9', '#2198c2', '#86a83b', '#c69c32', '#d47d34', '#ba6052', '#a84658')
PALETTES = {'dark': ('#111b24', '#192a38', '#f2f6f8', '#aabfcc', '#17455c'),
            'light': ('#f5f8fa', '#ffffff', '#12384b', '#476373', '#daeff9')}
ACCENT = '#0072b2'
DEFAULT_PROFILE = {'title': 'Room activity practice', 'sensors': 'Ceiling and colour sensors',
                   'stages': ['Leave the room empty', 'Please sit still',
                              'Make small seated movements', 'Walk around the room',
                              'Leave the room empty again'],
                   'annotations': ['Activity started', 'Activity finished', 'Unexpected event']}
TIPS = {'Lights on': 'Standard white: selects 3500 K and light-level input 1000 for all lights.',
        'Lights off': 'Sends zero drive to all light channels. The panel screen stays on.',
        'Advanced controls': 'Adjust eight colour-channel drives. Values are controller percentages, not measured light.',
        'Room': 'Everyday lighting and static presets. Touch a slider; no Apply button is needed.',
        'Experiment': 'Instructions, practice time and named annotations. No sensor recording starts.',
        'System': 'Panel resources and advertised room services. Presence does not prove sensor health.',
        'Original controls': 'Restores the trial baseline, then shows the existing room program.',
        'Blank screen': 'Shows black pixels. Hold still for 2 seconds to return; the backlight remains on.',
        'Settings': 'Appearance, date/time and screen options. Changes last for this trial.',
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


class Panel(object):
    def __init__(self, args):
        self.args, self.profile = args, profile(args.profile)
        self.started, self.run_id, self.sequence = monotonic(), uuid.uuid4().hex, 0
        self.boot_id, self.last_touch = boot_identity(), -60
        self.clock_24 = getattr(args, 'clock_format', '24') == '24'
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
        self.light_buttons = []
        self.last_heartbeat, self.request_seq = -10, 0
        self.journal = None
        if args.journal:
            self.journal = os.fdopen(os.open(args.journal, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w')
        self.root = tk.Tk()
        self.icon_cache = {}
        for key, size, width in [('title', 27, 1200), ('sensors', 18, 1130), ('annotations', 19, 270)]:
            labels = self.profile[key] if key == 'annotations' else [self.profile[key]]
            if any(Font(root=self.root, font=(FONT, size)).measure(label) > width for label in labels):
                self.root.destroy()
                if self.journal:
                    self.journal.close()
                raise ValueError('Shorten profile %s text to fit the touch layout' % key)
        self.root.title('LESA interactive room panel (beta)')
        if (self.root.winfo_screenwidth(), self.root.winfo_screenheight()) != (1280, 800) and not args.windowed:
            self.root.destroy()
            raise ValueError('Expected 1280x800; use --windowed for local review')
        self.root.geometry('1280x800+0+0')
        self.root.overrideredirect(not args.windowed)
        self.root.attributes('-topmost', True)
        self.root.bind('<Escape>', lambda event: self.close('escape'))
        self.root.protocol('WM_DELETE_WINDOW', lambda: self.close('window_close'))
        self.root.bind_all('<ButtonRelease-1>', self.slider_released, add='+')
        self.root.bind_all('<ButtonPress-1>', lambda event: setattr(self, 'last_touch', monotonic()), add='+')
        self.cct, self.intensity = tk.IntVar(value=3500), tk.IntVar(value=1000)
        self.channel_values = [tk.IntVar(value=value) for value in PRESETS['Fid']]
        self.status_text = tk.StringVar(value='Touch a slider or preset to change the lights. Recorder not connected.')
        self.light_text = tk.StringVar(value='Lighting not connected - controls are unavailable')
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
        if self.journal:
            self.journal.write(line)
            self.journal.flush()
            os.fsync(self.journal.fileno())
        sys.stdout.write(line)
        sys.stdout.flush()

    def label(self, parent, text='', size=20, muted=False):
        return tk.Label(parent, text=text, font=(FONT, size), fg=self.muted if muted else self.ink,
                        bg=parent.cget('bg'), anchor='w', justify='left')

    def button(self, parent, text, action, accent=False):
        button = tk.Button(parent, text=text, command=action, font=(FONT, 19),
                         fg='white' if accent else self.ink, bg=ACCENT if accent else self.control,
                         activebackground=ACCENT if accent else self.control,
                         activeforeground='white' if accent else self.ink, disabledforeground=self.muted,
                         bd=0, highlightthickness=0, padx=14, pady=12, takefocus=True)
        button.bind('<ButtonPress-1>', lambda event: self.show_tip(text), add='+')
        return button

    def show_tip(self, text):
        if self.help_on and not self.pending and self.light_state != 'failed':
            tip = TIPS.get(text)
            if text.endswith(' preset'):
                tip = 'Applies the existing ' + text + ' to all lights. Its name matches Original controls.'
            if text in self.profile['annotations']:
                tip = 'Saves "' + text + '" as a panel annotation. It is not a recording label yet.'
            if tip:
                self.status_text.set(tip)

    def toggle_tips(self):
        self.help_on = not self.help_on
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
        for text, action, accent in items:
            button = self.button(row, text, action, accent)
            button.pack(side='left', fill='both', expand=True, padx=(0, 10))
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
        self.label(self.banner, 'Interactive room (beta)', 21).pack(side='left')
        self.clock = self.label(self.banner, size=17, muted=True)
        self.clock.pack(side='right', padx=12)
        self.button(self.banner, 'Theme: ' + self.theme_choice.title(), self.cycle_theme).pack(side='right')
        self.tips_button = self.button(self.banner, 'Tips: ' + ('On' if self.help_on else 'Off'), self.toggle_tips)
        self.tips_button.pack(side='right', padx=10)
        self.nav = tk.Frame(self.root, bg=self.bg, height=64)
        self.nav.pack_propagate(False)
        self.nav.grid_propagate(False)
        self.nav_buttons = {}
        for index, (text, mode) in enumerate([('Room', 'room'), ('Experiment', 'experiment'),
                           ('System', 'health'), ('Original controls', 'original')]):
            self.nav.columnconfigure(index, weight=1, uniform='nav')
            button = self.button(self.nav, text, lambda mode=mode: self.show(mode))
            button.config(image=self.icon(mode, self.ink), compound='left')
            button.grid(row=0, column=index, sticky='nsew', padx=(0, 10 if index < 3 else 0))
            self.nav_buttons[mode] = button
        self.nav.rowconfigure(0, weight=1)
        self.footer = tk.Frame(self.root, bg=self.bg, height=88)
        self.footer.pack_propagate(False)
        self.label(self.footer, 'LESA  /  Smart Conference Room', 10, True).pack(side='bottom', anchor='w')
        self.button(self.footer, 'Blank screen', lambda: self.show('black')).pack(side='right', pady=8)
        self.button(self.footer, 'Settings', lambda: self.show('settings')).pack(side='right', padx=10, pady=8)
        status = self.label(self.footer, size=17, muted=True)
        status.config(textvariable=self.status_text, wraplength=770)
        status.pack(side='left', fill='both', expand=True)
        self.body = tk.Frame(self.root, bg=self.bg)
        self.build_dock()
        self.render()
        if section == 'channels' and self.mode == 'room':
            self.channel_view()

    def build_dock(self):
        for child in self.dock.winfo_children():
            child.destroy()
        self.dock.configure(bg=self.bg)
        top = tk.Frame(self.dock, bg=self.bg, height=44)
        top.pack(fill='x', padx=24)
        top.pack_propagate(False)
        self.label(top, 'LESA   /   Original room controls', 19).pack(side='left')
        self.label(top, 'Choose a mode below to return', 17, True).pack(side='right')
        nav = tk.Frame(self.dock, bg=self.bg, height=64)
        nav.pack(fill='both', expand=True, padx=24, pady=(0, 4))
        for index, (text, mode) in enumerate([('Room', 'room'), ('Experiment', 'experiment'),
                           ('System', 'health'), ('Original controls', 'original')]):
            nav.columnconfigure(index, weight=1, uniform='dock')
            button = self.button(nav, text, lambda mode=mode: self.show(mode), mode == 'original')
            button.config(image=self.icon(mode, 'white' if mode == 'original' else self.ink), compound='left')
            button.grid(row=0, column=index, sticky='nsew', padx=(0, 10 if index < 3 else 0))
        nav.rowconfigure(0, weight=1)

    def cycle_theme(self):
        self.choose_theme({'auto': 'light', 'light': 'dark', 'dark': 'auto'}[self.theme_choice])

    def show(self, mode):
        if self.release_target is not None or self.closing:
            return
        self.cancel_intent()
        if mode == 'original':
            self.trial_deadline = None
        if mode == 'original' and self.worker:
            self.release_target = 'original'
            self.status_text.set('Waiting for light adapter cleanup before showing Original controls...')
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
                        'room': 'Drag a slider or tap a preset. Trial changes restore before Original controls or exit.',
                        'experiment': 'Practice only. Activity buttons save panel annotations; recorder not connected.',
                        'settings': 'Settings apply to this trial. Hold one spot for 2 seconds to leave a blank screen.',
                        'about': 'Panel credits and source repository. No room settings change.'}
            if mode in messages:
                self.status_text.set(messages[mode])
        self.render()
        self.emit('mode_changed', target=mode)

    def render(self):
        self.cancel_intent()
        self.light_buttons = []
        for child in self.body.winfo_children():
            child.destroy()
        self.dock.withdraw()
        self.tips_button.config(text='Tips: ' + ('On' if self.help_on else 'Off'))
        for key, button in self.nav_buttons.items():
            button.config(bg=ACCENT if key == self.mode else self.control,
                          fg='white' if key == self.mode else self.ink,
                          activebackground=ACCENT if key == self.mode else self.control,
                          activeforeground='white' if key == self.mode else self.ink,
                          image=self.icon(key, 'white' if key == self.mode else self.ink))
        if self.mode == 'original':
            self.root.withdraw()
            self.dock.deiconify()
            self.dock.update_idletasks()
            self.dock.geometry('1280x112+0+0')
            self.dock.lift()
            return
        self.root.deiconify()
        self.root.lift()
        for widget in (self.banner, self.nav, self.footer, self.body):
            widget.pack_forget()
        for binding in ('<ButtonPress-1>', '<ButtonRelease-1>', '<B1-Motion>'):
            self.root.unbind(binding)
        if self.mode == 'black':
            self.root.configure(bg='black')
            self.root.bind('<ButtonPress-1>', self.begin_hold)
            self.root.bind('<ButtonRelease-1>', lambda event: self.cancel_hold())
            self.root.bind('<B1-Motion>', self.move_hold)
            return
        self.root.configure(bg=self.bg)
        self.banner.pack(fill='x', padx=24, pady=(8, 6))
        self.nav.pack(fill='x', padx=24, pady=(0, 14))
        self.footer.pack(side='bottom', fill='x', padx=24, pady=(8, 10))
        self.body.pack(fill='both', expand=True, padx=24)
        getattr(self, self.mode + '_view')()

    def room_view(self):
        self.label(self.body, 'Room lighting', 28).pack(anchor='w')
        state = self.label(self.body, size=19, muted=True)
        state.config(textvariable=self.light_text)
        state.pack(anchor='w', pady=(0, 10))
        row = tk.Frame(self.body, bg=self.bg)
        row.pack(fill='both', expand=True)
        left, right = tk.Frame(row, bg=self.bg), tk.Frame(row, bg=self.bg, width=464)
        left.pack(side='left', fill='both', expand=True, padx=(0, 24))
        right.pack(side='right', fill='both')
        right.pack_propagate(False)
        self.slider_group(left, 'White-light colour', self.cct, 1600, 10000, 100, 'K  /  warm to cool')
        self.slider_group(left, 'Light level', self.intensity, 0, 1900, 25, 'lookup units')
        self.label(left, 'Changes send automatically; the latest selection wins.\n'
                   'Light level is a controller value, not measured brightness.', 17, True).pack(anchor='w')
        self.label(right, 'Presets and demonstrations', 21).pack(anchor='w', pady=(0, 8))
        self.light_buttons.extend(self.row_buttons(right, [('Lights on', self.lights_on, False),
                                 ('Lights off', lambda: self.preset('Off'), False)]))
        self.light_buttons.extend(self.row_buttons(right, [(name + ' preset', lambda name=name: self.preset(name), False)
                                                           for name in ('Fid', 'Sat')]))
        self.light_buttons.extend(self.row_buttons(right, [('Dul preset', lambda: self.preset('Dul'), False),
                                                           ('Advanced controls', self.channel_view, False)])[:1])
        self.label(right, 'Three existing spectral presets.\nChoose one to apply it to all lights.', 17, True).pack(anchor='w', pady=5)
        self.label(right, 'Blinds disabled: window covers fitted.', 16, True).pack(anchor='w', pady=4)
        self.update_light_buttons()

    def slider_group(self, parent, title, variable, low, high, step, unit):
        group = tk.Frame(parent, bg=self.surface, height=156)
        group.pack(fill='x', pady=(0, 16))
        group.pack_propagate(False)
        heading = tk.Frame(group, bg=self.surface)
        heading.pack(fill='x', padx=16, pady=(10, 2))
        self.label(heading, title, 21).pack(side='left')
        self.label(heading, unit, 16, True).pack(side='right')
        row = tk.Frame(group, bg=self.surface, height=80)
        row.pack(fill='x', padx=16, pady=(2, 8))
        row.pack_propagate(False)
        minus_area, plus_area = tk.Frame(row, width=64), tk.Frame(row, width=64)
        minus_area.pack(side='left', fill='y')
        plus_area.pack(side='right', fill='y')
        minus_area.pack_propagate(False)
        plus_area.pack_propagate(False)
        minus = self.button(minus_area, '-', lambda: self.step_slider(variable, low, high, -step))
        plus = self.button(plus_area, '+', lambda: self.step_slider(variable, low, high, step))
        minus.pack(fill='both', expand=True)
        plus.pack(fill='both', expand=True)
        middle = tk.Frame(row, bg=self.surface)
        middle.pack(fill='both', expand=True, padx=12)
        value = self.label(middle, size=19)
        value.config(textvariable=variable, anchor='center')
        value.pack(fill='x')
        scale = tk.Scale(middle, variable=variable, from_=low, to=high, resolution=step, orient='horizontal',
                         bg=self.surface, troughcolor=self.control, activebackground=ACCENT,
                         highlightthickness=0, bd=0, width=38, sliderlength=64, showvalue=False)
        scale.pack(fill='x', expand=True)
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
        for child in self.body.winfo_children():
            child.destroy()
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
            self.status_text.set('Lighting unavailable. Use Original controls or ask staff.')
            return
        # Immutable complete intent, one unsent selection shared by all light controls.
        arguments = json.loads(json.dumps(arguments))
        self.queued_intent = (action, arguments, self.view_generation)
        if self.intent_timer is not None:
            self.root.after_cancel(self.intent_timer)
        self.intent_timer = self.root.after(250, self.dispatch_intent)
        self.light_text.set('Selection queued; waiting for your touch to settle...')

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
        self.light_text.set('Applying selected settings...')
        self.status_text.set('Applying lighting. Please wait for fixture drive confirmation.')
        if not self.request(action, arguments):
            self.light_state = 'failed'
            self.cancel_intent()
            self.light_text.set('Lighting adapter unavailable. Use Original controls or ask staff.')
        self.update_light_buttons()

    def update_light_buttons(self):
        for button in self.light_buttons:
            if button.winfo_exists():
                button.config(state='normal' if self.light_state in ('ready', 'applying')
                              and not self.release_target and not self.closing else 'disabled')

    def experiment_view(self):
        title = self.label(self.body, self.profile['title'], 27)
        title.config(wraplength=1200)
        title.pack(anchor='w')
        tk.Label(self.body, text='PRACTICE ONLY   /   Nothing is being recorded', font=(FONT, 20),
                 bg='#fff2db', fg='#6e4b0b', padx=16, pady=8).pack(anchor='w', pady=(0, 10))
        area = tk.Frame(self.body, bg=self.surface, height=228)
        area.pack(fill='x', pady=6)
        area.pack_propagate(False)
        self.stage_label = self.label(area, size=32)
        self.stage_label.config(wraplength=1130, height=2)
        self.stage_label.pack(anchor='w', padx=22, pady=(8, 2))
        self.run_label = self.label(area, size=17, muted=True)
        self.run_label.pack(anchor='w', padx=22)
        self.timer_label = self.label(area, size=30)
        self.timer_label.pack(anchor='w', padx=22, pady=3)
        metadata = self.label(area, 'Profile describes: ' + self.profile['sensors'], 16, True)
        metadata.config(wraplength=1130)
        metadata.pack(anchor='w', padx=22, pady=(0, 8))
        self.row_buttons(self.body, [('Start practice', self.start_preview, True),
                                     ('Pause practice', self.stop_preview, False),
                                     ('Previous instruction', self.previous_stage, False),
                                     ('Next instruction', self.next_stage, False)])
        self.row_buttons(self.body, [(label, lambda label=label: self.mark(label), False)
                                    for label in self.profile['annotations']])
        annotation = self.label(self.body, size=17, muted=True)
        annotation.config(textvariable=self.annotation_text)
        annotation.pack(anchor='w', pady=4)
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
            self.emit('annotation', label=label, scope='panel_practice')
            text = 'Saved on panel' if self.journal else 'Written to panel output only'
            self.annotation_text.set('%s: %s at %s. Not added to a recording.' % (text, label, time.strftime('%H:%M:%S')))
        except (IOError, OSError) as error:
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
        self.label(self.body, 'Panel resources', 28).pack(anchor='w', pady=(0, 12))
        self.health_rows = {}
        for key, title in [('ram', 'Memory'), ('disk', 'Storage')]:
            row = tk.Frame(self.body, bg=self.bg)
            row.pack(fill='x', pady=8)
            self.label(row, title + ' used', 23).pack(side='left')
            value = self.label(row, size=23)
            value.pack(side='right')
            canvas = tk.Canvas(self.body, height=24, bg=self.surface, bd=0, highlightthickness=0)
            canvas.pack(fill='x', pady=(0, 14))
            canvas.bind('<Configure>', lambda event: self.update_health())
            self.health_rows[key] = (value, canvas)
        self.health_details = self.label(self.body, size=23)
        self.health_details.pack(anchor='w', pady=12)
        self.power_label = self.label(self.body, size=19)
        self.power_label.pack(anchor='w', pady=(0, 8))
        self.services_label = self.label(self.body, size=17, muted=True)
        self.services_label.config(wraplength=1200)
        self.services_label.pack(anchor='w', pady=(0, 8))
        self.label(self.body, 'Live readings refresh every 5 seconds. Load average is not CPU percent.', 18, True).pack(anchor='w', pady=10)
        self.update_health()

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
        self.label(self.body, 'Panel settings', 28).pack(anchor='w', pady=(0, 12))
        appearance = self.setting_row('Appearance', 'Choose a theme')
        self.row_buttons(appearance, [('Auto', lambda: self.choose_theme('auto'), self.theme_choice == 'auto'),
                                     ('Light', lambda: self.choose_theme('light'), self.theme_choice == 'light'),
                                     ('Dark', lambda: self.choose_theme('dark'), self.theme_choice == 'dark')])
        clock = self.setting_row('Date & time', getattr(self.args, 'timezone', os.environ.get('TZ', 'System timezone')))
        self.label(clock, time.strftime('%a %d %b %Y'), 20).pack(side='left', padx=12)
        self.button(clock, ('24-hour' if self.clock_24 else '12-hour') + ' clock',
                    self.toggle_clock).pack(side='right', pady=8, padx=10)
        schedule = '%02d:%02d to %02d:%02d' % (divmod(self.args.light_at, 60) + divmod(self.args.dark_at, 60))
        times = self.setting_row('Light theme schedule', schedule)
        self.row_buttons(times, [('Light -1 h', lambda: self.adjust_schedule('light_at', -60), False),
                                 ('Light +1 h', lambda: self.adjust_schedule('light_at', 60), False),
                                 ('Dark -1 h', lambda: self.adjust_schedule('dark_at', -60), False),
                                 ('Dark +1 h', lambda: self.adjust_schedule('dark_at', 60), False)])
        screen = self.setting_row('Blank screen', 'Use the button below', height=74)
        self.label(screen, 'Hold one spot for 2 seconds to return.\nBlack pixels leave the backlight on.', 18, True).pack(
            side='left', padx=12, pady=8)
        self.row_buttons(self.body, [('Back to Room', lambda: self.show('room'), False),
                                     ('About panel', lambda: self.show('about'), False),
                                     ('Return to Original' if self.keep_switcher else 'End trial and restore',
                                      lambda: self.close('exit'), False)])

    def about_view(self):
        self.label(self.body, 'About this panel', 28).pack(anchor='w', pady=(0, 20))
        self.label(self.body, 'LESA interactive room panel (beta)', 24).pack(anchor='w', pady=(0, 12))
        self.label(self.body, 'Built by Diyanko Bhowmik', 21).pack(anchor='w', pady=(0, 8))
        self.label(self.body, 'With Codex assistance. Original contributors are retained in repository history.',
                   17, True).pack(anchor='w', pady=(0, 18))
        self.label(self.body, 'Source: github.com/LESA-RPI/scr.touch_panel', 18, True).pack(anchor='w', pady=(0, 24))
        self.button(self.body, 'Back to Settings', lambda: self.show('settings')).pack(anchor='w')

    def setting_row(self, title, detail, height=84):
        row = tk.Frame(self.body, bg=self.surface, height=height)
        row.pack(fill='x', pady=(0, 10))
        row.pack_propagate(False)
        heading = tk.Frame(row, bg=self.surface, width=300)
        heading.pack(side='left', fill='y', padx=16)
        heading.pack_propagate(False)
        self.label(heading, title, 20).pack(anchor='w', pady=(12, 0))
        self.label(heading, detail, 16, True).pack(anchor='w')
        controls = tk.Frame(row, bg=self.surface)
        controls.pack(side='right', fill='both', expand=True, padx=(0, 10))
        return controls

    def toggle_clock(self):
        self.clock_24 = not self.clock_24
        self.render()
        self.emit('clock_format_selected', format='24' if self.clock_24 else '12')

    def choose_theme(self, choice):
        self.theme_choice, self.theme = choice, None
        self.set_theme()
        self.emit('theme_selected', choice=choice, resolved=self.theme)

    def adjust_schedule(self, key, delta):
        value = (getattr(self.args, key) + delta) % 1440
        if value != (self.args.dark_at if key == 'light_at' else self.args.light_at):
            setattr(self.args, key, value)
            self.emit('theme_schedule_changed', light_at=self.args.light_at, dark_at=self.args.dark_at)
            self.set_theme()
            self.render()

    def start_worker(self):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scr_touch_panel_lights.py')
        receipt = self.args.journal + '.lights-' + uuid.uuid4().hex[:8] + '.jsonl'
        self.worker = subprocess.Popen([getattr(self.args, 'adapter_python', '/usr/bin/python2.7'), '-u', '-B', path,
                                        '--receipt', receipt, '--parent-pid', str(os.getpid()),
                                        '--expected-master', self.args.expected_master],
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=sys.stderr, close_fds=True)
        self.light_state = 'connecting'
        self.light_text.set('Checking starting drive settings on 10 lights...')
        self.worker_buffer = ''
        self.request('acquire')

    def request(self, action, arguments=None):
        if self.pending or not self.worker or self.worker.poll() is not None:
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

    def poll_worker(self):
        if self.closed:
            return
        self.poll_status()
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
                if not self.pending or response.get('request_id') != self.pending['request_id']:
                    continue
                if response.get('version') != 1 or response.get('state') not in ('ready', 'completed', 'released', 'failed'):
                    self.pending = None
                    self.cancel_intent()
                    self.light_state = 'failed'
                    self.status_text.set('Invalid adapter reply; lights disabled. Ask staff.')
                    worker.stdin.close()
                    continue
                action, self.pending = self.pending['action'], None
                self.emit('light_result', result=response)
                state = response['state']
                self.light_state = {'completed': 'ready', 'released': 'disconnected'}.get(state, state)
                detail = response.get('detail', 'Lighting ready; starting preset: ' + response.get('baseline', '?'))
                self.light_text.set(detail)
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
                    self.status_text.set(detail + ' / Use Original controls or ask staff.')
                elif self.queued_intent and self.intent_timer is None:
                    self.dispatch_intent()
                self.update_light_buttons()
            if worker.poll() is not None:
                if self.pending or self.light_state != 'disconnected':
                    self.cancel_intent()
                    self.pending = None
                    self.light_state = 'failed'
                    self.status_text.set('Light adapter stopped. Result unconfirmed; further commands disabled.')
                    self.light_text.set('Lighting disconnected; check the retained receipt')
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
            self.emit('panel_closed', reason=self.closing or 'mainloop_exit', light_state=self.light_state)
            self.closed = True
            if self.worker:
                self.worker.stdin.close()
            if self.journal:
                self.journal.close()
            self.root.destroy()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duration', type=float, default=600, help='Trial lifetime: 1..1800 s; 0 requires --keep-switcher')
    parser.add_argument('--keep-switcher', action='store_true', help='Keep touch navigation above Original after leaving the beta')
    parser.add_argument('--start-mode', choices=['room', 'original'], default='room', help='Initial view with --keep-switcher')
    parser.add_argument('--profile', help='Data-only JSON: title, sensors, stages, annotations')
    parser.add_argument('--journal', help='New private JSONL UI journal; never an existing recording context file')
    parser.add_argument('--logo', default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                                      'assets', 'lesa-logo.jpeg'), help='Original local logo; no asset is modified')
    parser.add_argument('--theme', choices=['auto', 'light', 'dark'], default='auto')
    parser.add_argument('--light-at', type=clock_minutes, default=420, help='Local HH:MM, default 07:00')
    parser.add_argument('--dark-at', type=clock_minutes, default=1140, help='Local HH:MM, default 19:00')
    parser.add_argument('--timezone', default='America/New_York', help='Process-local timezone for schedule and clock')
    parser.add_argument('--clock-format', choices=['12', '24'], default='24', help='Clock style; also adjustable in Settings')
    parser.add_argument('--font', default='Ubuntu', help='An installed font family; default Ubuntu')
    parser.add_argument('--tips', choices=['on', 'off'], default='on', help='Short touch explanations; also switchable in the header')
    parser.add_argument('--dark-brand', choices=['wordmark', 'original'], default='wordmark',
                        help='Plain LESA text in dark mode, or original logo on a white plate')
    parser.add_argument('--adapter-python', default='/usr/bin/python2.7', help='Installed ROS interpreter, independent of the UI')
    parser.add_argument('--expected-master', default=os.environ.get('SCR_PANEL_MASTER'),
                        help='Approved ROS_MASTER_URI, or private SCR_PANEL_MASTER environment setting')
    parser.add_argument('--live-lights', action='store_true', help='Existing ROS environment; requires --journal and fresh owner check')
    parser.add_argument('--windowed', action='store_true', help='Local 1280x800 review without screen-size enforcement')
    args = parser.parse_args(argv)
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
            panel.finish_close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
