"""Shared room-control labels and readiness. No hardware access or discovery."""

from scr_touch_panel_lights import PRESETS

LIGHTING_TABS = (
    ("White light", "white"),
    ("Scenes", "scenes"),
    ("Programmes", "programmes"),
    ("Channels", "channels"),
)
SCENES = tuple(
    {"id": name, "label": name, "detail": "Original eight-channel room mixture."}
    for name in PRESETS
    if name != "Off"
)
GRADIENT = {"id": "Gradient", "label": "Gradient",
            "detail": "Original spatial pattern across the ten room lights."}
PROGRAMMES = (
    {"id": "Sun", "label": "Original Sun programme",
     "detail": "Original colour and light-level curve, staggered across the room."},
    {"id": "Circ", "label": "Original Circ programme",
     "detail": "Original colour and light-level curve across the whole room."},
)
UNAVAILABLE_LIGHTING = "Original programmes are unavailable while the Status connection is not configured."
BLINDS_UNAVAILABLE = "Not available yet: the blind adapter is not connected."
BLIND_ACTIONS = (
    ("lift", "Lift blinds"),
    ("open", "Open slats"),
    ("close", "Close & lower"),
)


def blind_readiness(enabled, connected, busy=False):
    if not enabled:
        return {
            "enabled": False,
            "connected": bool(connected),
            "available": False,
            "detail": "Disabled",
            "reason": "Controls locked in settings",
        }
    if not connected:
        return {
            "enabled": True,
            "connected": False,
            "available": False,
            "detail": "Disabled",
            "reason": "Controller not connected",
        }
    if busy:
        return {
            "enabled": True,
            "connected": True,
            "available": False,
            "detail": "Busy",
            "reason": "Room controls busy",
        }
    return {
        "enabled": True,
        "connected": True,
        "available": True,
        "detail": "Ready",
        "reason": "Controls unlocked",
    }

# Room website shown as a QR code on the panel's About page. After changing it,
# regenerate the image: npx qrcode -o assets/website-qr.png -w 200 -q 2 "<address>"
WEBSITE_URL = "http://192.168.0.28:8768/"
