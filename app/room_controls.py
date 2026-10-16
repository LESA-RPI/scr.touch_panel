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
UNAVAILABLE_LIGHTING = "Gradient, Sun and Circ are not available yet. Their adapters are not connected; use Legacy for the original controls."
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
