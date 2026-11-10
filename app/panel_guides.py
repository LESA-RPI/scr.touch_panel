"""Short display-only room guides. No command execution or hardware access."""

from help_reference import commands as reference_commands
import json
from pathlib import Path

GUIDE_SECTIONS = (("Room tour", "room"), ("Control help", "controls"))

DEMO = (
    {
        "section": "controls",
        "title": "Lighting",
        "icon": "on",
        "caption": "White light and saved scenes",
        "links": [
            {"label": "Open Lighting", "page": "lighting"},
            {"label": "Open Home", "page": "home"},
        ],
        "text": "Use Lights on and Lights off on Home for everyday lighting.\n\n"
        "Room tools → Lighting brings White light, Scenes, Programmes and Channels together. Opening a tab does not change the lights.\n\n"
        "Last confirmed shows the most recent controller readback and its age. If a change cannot be confirmed, the panel reads the lights again and controls return. Check connection reads current lighting without changing it; ask the room host if controls stay unavailable.",
    },
    {
        "section": "controls",
        "title": "Room controls",
        "icon": "home",
        "caption": "Lighting, blinds and preferences",
        "links": [
            {"label": "Open Home", "page": "home"},
            {"label": "Open Screen & controls", "page": "screen"},
        ],
        "text": "Home opens the everyday room page. Opening a page does not change the lights.\n\n"
        "Lift blinds, Open slats and Close & lower are on Home. Movement is locked by default and requires a connected controller. Screen & controls explains availability and saves whether the controls are shown.\n\n"
        "Room tools also holds appearance, screen and weather preferences. If equipment controls stay unavailable, ask the room host.",
    },
    {
        "section": "controls",
        "title": "Connection & help",
        "icon": "health",
        "caption": "Panel, services and weather",
        "links": [
            {"label": "Open System & help", "page": "system"},
            {"label": "Open Date & weather", "page": "clock"},
        ],
        "text": "Beta and the room-network website share one controller. Join the room Wi-Fi before opening the website; the guide shows the connection details.\n\n"
        "The lighting status explains when controls are ready, checking or unconfirmed. Website offline means the page cannot reach the panel. Open System & help for guidance.\n\n"
        "Weather is an outdoor model estimate, separate from indoor measurements. Source details are under Room tools → Date & weather.",
    },
    {
        "section": "room",
        "title": "A room for research",
        "icon": "home",
        "caption": "Lighting, sensing and shared space",
        "text": "The Smart Conference Room brings lighting and several kinds of sensors into one shared space. Researchers compare their different views to study presence, movement and the room environment.\n\n"
        "Ceiling sensors measure distance or light colour. Four Azure Kinect cameras provide colour, depth and infrared reference views for comparing sensors.\n\n"
        "This tour starts no equipment or recording. A sensor appearing on the map does not mean it is currently connected or recording.",
        "links": [],
    },
    {
        "section": "room",
        "title": "Lighting & colour",
        "visual": "channels",
        "actions": True,
        "icon": "on",
        "caption": "Ten lights, eight channels",
        "text": "Ten lights mix eight channels into white light and colour scenes. Gradient spreads colour across the room. Values are drive settings, not measured brightness.",
        "links": [{"label": "Open Lighting", "page": "lighting"}],
    },
    {
        "section": "room",
        "title": "Distance & colour sensors",
        "visual": "distance",
        "icon": "sensors",
        "caption": "COMBO, IRMA and Color",
        "text": "COMBO combines a coarse 8 × 8 distance grid with light-colour sensing. It times reflected light to estimate distance.\n\n"
        "IRMA Matrix gives a denser 25 × 20 distance view and reflected-signal strength. It measures distance, not body heat.\n\n"
        "Color sensors track light-colour changes without taking a photograph. Raw values need calibration for absolute measurements.",
        "links": [],
    },
    {
        "section": "room",
        "title": "Ceiling map",
        "icon": "health",
        "caption": "Explore the sensor families",
        "text": "Select a sensor family to see its registered ceiling positions.",
        "map": True,
        "links": [],
    },
)

# A small reference snapshot; Project-X remains the owner of geometry and capture.
CEILING_MAP = json.loads(Path(__file__).with_name("ceiling_map.json").read_text(encoding="utf-8"))

SUPPORT = (
    (
        "Lighting",
        "room",
        "Check connection reads current settings without changing the lights. If a change cannot be confirmed, the panel reads the lights again; press the control again if needed.",
        "",
    ),
    (
        "Power",
        "on",
        "Low supply voltage can slow the Pi and affect storage reliability. Check its supply, cable and connector; a separately powered LCD does not rule out a Pi power problem.\n\n"
        "Open the reference to distinguish current warnings from earlier ones. Do not hide warnings or repeatedly power-cycle. Shut down normally before changing power.",
        reference_commands("Power"),
    ),
    (
        "Ubuntu checks",
        "health",
        "Use a Terminal on the Ubuntu room computer. These commands inspect state; they do not start devices.\n\n"
        "ROS owns room controls. Status owns the TV display and its clients. Session presence alone does not prove health.",
        reference_commands("Ubuntu checks"),
    ),
    (
        "Start services",
        "health",
        "Room host only: stop experiments and check tmux sessions first. "
        "startROS.py replaces the ROS session; startStatus.py replaces Status. Do not use them as a quick connection fix.\n\n"
        "Installed paths below are instructions only, not automatic recovery.",
        reference_commands("Start services"),
    ),
    (
        "Restart computer",
        "off",
        "Room host only: stop recordings and coordinate with other room users. Restarting interrupts shared controls and feeds.\n\n"
        "Use the Ubuntu Restart action or its Terminal command below. After the desktop and network return, check ROS and Status; service autostart is not verified.",
        reference_commands("Restart computer"),
    ),
)


def connection(state, live=True):
    """Adapter state only; no claim of continuous or physical device health."""
    if not live:
        return "Preview", "link-off", "neutral"
    return {
        "ready": ("Ready", "link-ok", "good"),
        "applying": ("Sending", "clock", "waiting"),
        "connecting": ("Checking", "clock", "waiting"),
        "failed": ("Uncertain", "link-off", "warning"),
    }.get(state, ("Offline", "link-off", "neutral"))
