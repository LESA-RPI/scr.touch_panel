"""Shared panel values and pure presentation helpers; no controller instance."""

from scr_touch_panel_lights import PRESETS
from room_controls import BLIND_ACTIONS
from design_tokens import THEMES
import argparse
import json
import os
from scr_touch_panel_lights import setter_words
import subprocess
import sys
import time

FONT = "Cantarell"
CHANNELS = ("Blue 1", "Blue 2", "Blue 3", "Lime", "Amber", "Orange", "Red 1", "Red 2")
CHANNEL_COLOURS = (
    "#4764bc",
    "#337cb9",
    "#2198c2",
    "#86a83b",
    "#c69c32",
    "#d47d34",
    "#ba6052",
    "#a84658",
)
ACCENT = THEMES["light"]["accent"]
ADVANCED_PAGES = [
    ("Lighting", "lighting"),
    ("Experiment mode", "experiment"),
    ("Appearance", "appearance"),
    ("Date & weather", "clock"),
    ("Screen & controls", "screen"),
    ("System & help", "system"),
    ("About", "about"),
]
# Only presentation references travel with retained pages. Controller state, intent
# generations and preferences always belong to the live Panel, never a cached page.
PAGE_REFERENCES = (
    "programme_buttons",
    "light_buttons",
    "home_power_buttons",
    "scene_buttons",
    "blind_buttons",
    "blind_status_label",
    "light_feedback_card",
    "weather_symbol",
    "weather_symbol_size",
    "weather_symbol_key",
    "weather_symbol_item",
    "weather_measurements",
    "weather_metric_cells",
    "weather_metric_values",
    "weather_notice",
    "daylight_label",
    "daylight_canvas",
    "daylight_drawn",
    "weather_rendered_minute",
)
DEFAULT_PROFILE = {
    "title": "Room activity instructions",
    "sensors": "Ceiling and colour sensors",
    "stages": [
        "Leave the room empty",
        "Please sit still",
        "Make small seated movements",
        "Walk around the room",
        "Leave the room empty again",
    ],
    "annotations": ["Activity started", "Activity finished", "Unexpected event"],
}
TIPS = {
    "Lights on": "Standard white: selects 3500 K and light-level input 1000 for all lights.",
    "Lights off": "Sends zero drive to all light channels. The panel screen stays on.",
    "Advanced controls": "Adjust eight colour-channel drives. Values are controller percentages, not measured light.",
    "Room": "Everyday lighting. Changes send automatically after your touch settles.",
    "Visitor": "Room introduction and a large clock. Opening this page does not change lighting.",
    "Experiment mode": "Instructions, elapsed time and panel annotations. No sensor recording starts.",
    "System": "Panel resources and advertised room services. Presence does not prove sensor health.",
    "Legacy": "Hands control to the original interface without changing the lights.",
    "Blank screen": "Shows black pixels. Hold still for 2 seconds to return; the backlight remains on.",
    "Settings": "Appearance, date/time and screen options. Appearance choices can be saved on this device.",
    "About panel": "Panel credits and source repository. No room settings change.",
    "Start instructions": "Starts the instruction timer only. It does not start sensor collection.",
    "Next instruction": "Shows the next instruction. The final instruction does not wrap.",
    "End trial and restore": "Restores confirmed trial changes and returns to the original program.",
}


def monotonic():
    if hasattr(time, "monotonic"):
        return time.monotonic()
    with open("/proc/uptime") as stream:
        return float(stream.read().split()[0])


def set_changed(variable, value):
    """Avoid scheduling redraws for unchanged clock/status values."""
    if not hasattr(variable, "get") or variable.get() != value:
        variable.set(value)


def boot_identity():
    try:
        with open("/proc/sys/kernel/random/boot_id") as stream:
            return stream.read().strip()
    except IOError:
        return None


def health():
    result = {}
    try:
        with open("/proc/meminfo") as stream:
            memory = dict((line.split(":")[0], int(line.split()[1])) for line in stream)
        result.update(
            ram_available=memory["MemAvailable"] // 1024,
            ram_total=memory["MemTotal"] // 1024,
            load=os.getloadavg()[0],
        )
        disk = os.statvfs("/")
        result.update(
            disk_available=disk.f_bavail * disk.f_frsize / float(2**30),
            disk_used=100 * (1 - disk.f_bfree / float(disk.f_blocks)),
        )
        with open("/sys/class/thermal/thermal_zone0/temp") as stream:
            result["temperature"] = float(stream.read()) / 1000
        with open("/proc/uptime") as stream:
            result["uptime"] = float(stream.read().split()[0]) / 86400
    except (IOError, OSError, KeyError, ValueError) as error:
        result["error"] = str(error)
    try:
        reply = (
            subprocess.check_output(["timeout", "2", "vcgencmd", "get_throttled"])
            .decode("ascii")
            .strip()
        )
        flags = int(reply.split("=")[1], 16)
        result["power"] = (
            "Current undervoltage detected" if flags & 1 else "No current undervoltage"
        )
        if flags & (1 << 16):
            result["power"] += " / past warning since boot"
    except (OSError, ValueError, IndexError, subprocess.CalledProcessError):
        result["power"] = "Power status unavailable"
    return result


def profile(path):
    value = {}
    if path:
        with open(path) as stream:
            value = json.load(stream)
    if not isinstance(value, dict) or set(value) - set(DEFAULT_PROFILE):
        raise ValueError("Profile permits title, sensors, stages and annotations only")
    merged = dict(DEFAULT_PROFILE)
    merged.update(value)
    text_types = (str,) if sys.version_info[0] == 3 else (basestring,)
    for key in ("title", "sensors"):
        if not isinstance(merged[key], text_types) or not 1 <= len(merged[key]) <= 100:
            raise ValueError("Title/sensors must contain 1..100 characters")
    for key, maximum in [("stages", 20), ("annotations", 4)]:
        items = merged[key]
        limit = 60 if key == "stages" else 20
        if (
            not isinstance(items, list)
            or not 1 <= len(items) <= maximum
            or any(
                not isinstance(item, text_types) or not 1 <= len(item) <= limit
                for item in items
            )
            or len(set(items)) != len(items)
        ):
            raise ValueError("Provide distinct, short %s labels" % key)
    return merged


def clock_minutes(text):
    try:
        hours, minutes = map(int, text.split(":"))
        if not 0 <= hours <= 23 or not 0 <= minutes <= 59:
            raise ValueError()
        return 60 * hours + minutes
    except ValueError:
        raise argparse.ArgumentTypeError("Use HH:MM in the panel local timezone")


def scheduled_theme(now, light_at, dark_at):
    light = (
        light_at <= now < dark_at
        if light_at < dark_at
        else now >= light_at or now < dark_at
    )
    return "light" if light else "dark"


def light_selection(action, arguments):
    """Describe requested controller inputs; never imply optical measurement."""
    if action == "gradient":
        return "Gradient scene"
    if action == "programme":
        return "Stop programmes" if arguments["name"] == "Stop" else arguments["name"] + " programme"
    if action == "blind":
        return dict(BLIND_ACTIONS)[arguments["name"]]
    if action == "cct":
        return "%d K input / level %d" % (arguments["cct"], arguments["intensity"])
    values = tuple(arguments["values"])
    for name, preset in PRESETS.items():
        if values == preset:
            return name + " scene"
    return "Custom eight-channel mix"


def confirmation_age(now, confirmed_at):
    if confirmed_at is None:
        return ""
    seconds = max(0, now - confirmed_at)
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return "%d min ago" % (seconds // 60)
    if seconds < 86400:
        return "%d h ago" % (seconds // 3600)
    return "%d d ago" % (seconds // 86400)


def confirmed_power(response):
    """Describe confirmed drive readback, never optical or continuously live state."""
    if response.get("state") == "completed" and response.get("scene") == "Gradient" and response.get("fixtures") == 10:
        return "on"
    if response.get("state") == "ready" and response.get("power") in ("on", "off"):
        return response["power"]
    if response.get("state") == "ready" and response.get("baseline") in PRESETS:
        return "off" if response["baseline"] == "Off" else "on"
    values = response.get("words")
    if (
        response.get("state") == "completed"
        and isinstance(values, list)
        and len(values) == 8
        and all(
            isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 65535
            for v in values
        )
    ):
        return "on" if any(values) else "off"
    return None


def confirmed_scene(response):
    """Match an admitted baseline or exact confirmed drive words, never a selection."""
    if response.get("state") == "completed" and response.get("scene") == "Gradient" and response.get("fixtures") == 10:
        return "Gradient"
    if response.get("state") == "ready" and response.get("baseline") in PRESETS:
        return response["baseline"]
    if response.get("state") == "completed" and confirmed_power(response) is not None:
        values = tuple(response["words"])
        return next(
            (
                name
                for name, preset in PRESETS.items()
                if values == setter_words(preset)
            ),
            None,
        )
    return None
