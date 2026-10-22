"""Generated browser content must follow the panel's owned guidance and controls."""

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from export_room_content import content
from panel_version import VERSION
from room_controls import SCENES, GRADIENT, PROGRAMMES
from scr_touch_panel_lights import PRESETS


def test_browser_fallback_is_current_generated_content():
    path = Path(__file__).resolve().parents[1] / "browser/room-content.json"
    assert json.loads(path.read_text(encoding="utf-8")) == json.loads(
        json.dumps(content())
    ), "Run python app/export_room_content.py browser/room-content.json"
    assert content()["app_version"] == VERSION


def test_browser_and_panel_scenes_use_the_qualified_mixtures():
    exported = content()
    assert set(scene["id"] for scene in SCENES) == set(PRESETS) - {"Off"}
    assert exported["presets"] == PRESETS


def test_browser_extended_lighting_uses_shared_metadata_and_separate_actions():
    exported = content()
    assert exported["gradient"] == GRADIENT
    assert exported["programmes"] == PROGRAMMES
    assert GRADIENT["id"] not in PRESETS
    assert {programme["id"] for programme in PROGRAMMES} == {"Sun", "Circ"}
