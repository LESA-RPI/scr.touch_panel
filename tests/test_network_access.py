"""The private Wi-Fi key appears on the native panel, never public web content."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from test_panel_navigation import view
from test_panel_control import remote_owner
import room_controls
from panel_remote import snapshot


TEST_KEY = "synthetic-room-test-key"


def test_private_key_is_omitted_from_generated_and_checked_in_browser_content():
    root = Path(__file__).resolve().parents[1]
    environment = dict(os.environ, SCR_ROOM_NETWORK_PASSWORD=TEST_KEY)
    reply = subprocess.run(
        [sys.executable, "-c", "import json,sys; sys.path.insert(0,'app'); from export_room_content import content; print(json.dumps(content()))"],
        cwd=root, env=environment, capture_output=True, text=True, check=True,
    )
    assert TEST_KEY not in reply.stdout
    assert "network_password" not in json.loads(reply.stdout)
    assert TEST_KEY not in (root / "browser/room-content.json").read_text(encoding="utf-8")


def test_private_key_is_omitted_from_public_controller_state(remote_owner, monkeypatch):
    monkeypatch.setattr(room_controls, "ROOM_NETWORK_PASSWORD", TEST_KEY)
    value = snapshot(remote_owner)
    assert TEST_KEY not in json.dumps(value)
    assert "network_password" not in value


@pytest.mark.parametrize("key", ["", TEST_KEY])
def test_native_network_card_shows_configured_key_or_host_help(view, monkeypatch, key):
    monkeypatch.setattr(room_controls, "ROOM_NETWORK_NAME", "SCR_AP")
    monkeypatch.setattr(room_controls, "ROOM_NETWORK_PASSWORD", key)
    view.open_guide()
    view.root.update()

    def labels(widget):
        for child in widget.winfo_children():
            if child.winfo_class() == "Label":
                yield child.cget("text")
            yield from labels(child)

    text = list(labels(view.body))
    assert "1. Join Wi-Fi: SCR_AP" in text
    assert ("Wi-Fi key: " + key if key else "Need the Wi-Fi key?\nAsk the room host.") in text
