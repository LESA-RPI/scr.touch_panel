"""Export the panel-owned guide/help text for browser fallback and offline review."""

import argparse
import json
from pathlib import Path
from panel_guides import DEMO, SUPPORT, GUIDE_SECTIONS, CEILING_MAP
from design_tokens import THEMES, WEATHER_ACCENTS
from help_reference import reference
from command_reference import command_tokens
from room_controls import (
    LIGHTING_TABS,
    SCENES,
    GRADIENT,
    PROGRAMMES,
    BLIND_ACTIONS,
    PRESETS,
    PREVIOUS_ON,
    UNAVAILABLE_LIGHTING,
    BLINDS_UNAVAILABLE,
    DEFAULT_ROOM_NETWORK_NAME,
)
from panel_version import VERSION
from panel_common import CHANNELS, CHANNEL_COLOURS
import xml.etree.ElementTree as ET


def content():
    names = {
        "tools": "sliders-horizontal",
        "home": "house",
        "lighting": "lightbulb",
        "white": "lightbulb",
        "off": "lightbulb-off",
        "scenes": "layers",
        "sensors": "flask-conical",
        "appearance": "sun-moon",
        "clock": "calendar-days",
        "screen": "monitor",
        "system": "activity",
        "about": "info",
        "guide": "book-open",
        "legacy": "external-link",
    }
    names.update(
        {
            "weather-" + name: name
            for name in (
                "sun",
                "moon",
                "cloud-sun",
                "cloud-moon",
                "cloud",
                "cloud-rain",
                "cloud-snow",
                "cloud-lightning",
                "cloud-fog",
                "circle-question-mark",
            )
        }
    )
    folder = Path(__file__).resolve().parents[1] / "assets/icons/svg"
    names.update({path.stem: path.stem for path in sorted(folder.glob("*.svg"))})
    icons = {}
    for key, name in names.items():
        svg = ET.parse(
            Path(__file__).resolve().parents[1] / "assets/icons/svg" / (name + ".svg")
        ).getroot()
        icons[key] = [
            {"tag": node.tag.split("}")[-1], "attributes": node.attrib} for node in svg
        ]
    return {
        "version": 1,
        "app_version": VERSION,
        "icons": icons,
        "themes": THEMES,
        "weather_accents": WEATHER_ACCENTS,
        "lighting_tabs": LIGHTING_TABS,
        "scenes": SCENES,
        "gradient": GRADIENT,
        "programmes": PROGRAMMES,
        "presets": PRESETS,
        "previous_on": PREVIOUS_ON,
        "unavailable_lighting": UNAVAILABLE_LIGHTING,
        "blinds_unavailable": BLINDS_UNAVAILABLE,
        "generated_from": "app/export_room_content.py",
        "blind_actions": BLIND_ACTIONS,
        "network_name": DEFAULT_ROOM_NETWORK_NAME,
        "channels": [{"label": name, "colour": colour} for name, colour in zip(CHANNELS, CHANNEL_COLOURS)],
        "guide": list(DEMO),
        "guide_sections": GUIDE_SECTIONS,
        "ceiling_map": CEILING_MAP,
        "help": [
            {
                "title": title,
                "text": text,
                "commands": commands,
                "command_tokens": command_tokens(commands),
                "reference": reference(title),
            }
            for title, kind, text, commands in SUPPORT
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output")
    args = parser.parse_args()
    Path(args.output).write_text(
        json.dumps(content(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
