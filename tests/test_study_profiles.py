"""Session-only instruction setup never starts a recorder or room device."""

import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from panel_common import DEFAULT_PROFILE, profile, validate_profile
from panel_control import command
import panel_remote
import scr_touch_panel as panel
from test_panel_navigation import view


def envelope(value):
    return dict(id="profile-command-0001", revision="current", action="profile",
                arguments={"value": value})


def test_file_and_runtime_profiles_share_validation_and_copy_lists(tmp_path):
    value = {"title": "Demo", "stages": ["Sit", "Stand"]}
    source = tmp_path / "study.json"
    source.write_text(json.dumps(value))
    loaded = validate_profile(value)
    assert profile(source) == loaded
    assert loaded["annotations"] == DEFAULT_PROFILE["annotations"]
    assert loaded["annotations"] is not DEFAULT_PROFILE["annotations"]
    value["stages"].append("Walk")
    assert loaded["stages"] == ["Sit", "Stand"]


@pytest.mark.parametrize("value", [
    None, [], {"script": "anything"}, {"path": "/tmp/study.json"},
    {"stages": []}, {"stages": ["Sit", "Sit"]}, {"stages": ["x" * 61]},
    {"stages": ["Step %d" % i for i in range(21)]},
    {"annotations": []}, {"annotations": ["x" * 21]}, {"title": 7},
])
def test_profile_wire_command_rejects_noninstruction_data(value):
    with pytest.raises(ValueError):
        command(envelope(value))


def test_profile_command_keeps_exact_data_only_shape():
    value = envelope({"title": "Demo"})
    assert command(value) == value
    value["arguments"]["path"] = "study.json"
    with pytest.raises(ValueError):
        command(value)


@pytest.fixture
def owner():
    state = panel.Panel.__new__(panel.Panel)
    state.profile = validate_profile({})
    state.mode, state.running = "guide", False
    state.stage, state.elapsed, state.run_started = 2, 42.0, 10.0
    state.recovery = None
    state.closed = state.closing = state.pending = state.pending_annotation = None
    state.queued_intent = state.intent_timer = state.slider_drag = None
    state.release_target = state.press_active = state.legacy_probe = None
    state.annotations, state.messages, state.events, state.renders = [], [], [], []
    state.annotation_text = SimpleNamespace(set=state.annotations.append)
    state.status_text = SimpleNamespace(set=state.messages.append)
    state.check_profile_fit = lambda value: None
    state.emit = lambda event, **value: state.events.append((event, value, state.stage))
    state.render = lambda: state.renders.append(state.mode)
    state.request = lambda *args, **kwargs: pytest.fail("Loading instructions must not send a room command")
    state.start_worker = lambda *args, **kwargs: pytest.fail("Loading instructions must not acquire hardware")
    return state


@pytest.mark.parametrize("mode", ["guide", "experiment"])
def test_load_resets_session_and_records_full_profile_without_navigation(owner, mode):
    owner.mode = mode
    value = {"title": "Demo", "stages": ["Stand"], "annotations": ["Finished"]}
    owner.load_profile(value)
    assert owner.profile == validate_profile(value)
    assert (owner.stage, owner.elapsed, owner.run_started, owner.running) == (0, 0, None, False)
    assert owner.events == [("profile_loaded", {"profile": owner.profile}, 0)]
    assert owner.annotations == ["Tap a label to mark an event."]
    assert owner.mode == mode and owner.renders == ([mode] if mode == "experiment" else [])
    assert "session" in owner.messages[-1]
    value["stages"].append("Walk")
    assert owner.profile["stages"] == ["Stand"]


@pytest.mark.parametrize("field,value", [
    ("running", True), ("pending", {"id": "pending"}),
    ("pending_annotation", (3, "Mark", "12:00")), ("queued_intent", ("on",)),
    ("intent_timer", "scheduled"), ("slider_drag", "cct"),
    ("release_target", "experiment"), ("press_active", True),
    ("legacy_probe", object()), ("closed", True), ("closing", "exit"),
    ("mode", "original"), ("mode", "black"),
    ("power_busy", lambda: True), ("ownership_blocked", lambda: True),
])
def test_profile_load_refuses_busy_or_owned_state_without_changing_session(owner, field, value):
    old = owner.profile
    setattr(owner, field, value)
    assert not owner.can_load_profile()
    with pytest.raises(RuntimeError, match="Pause instructions"):
        owner.load_profile({"title": "New setup"})
    assert owner.profile is old and owner.stage == 2 and owner.elapsed == 42
    assert not owner.events and not owner.renders and not owner.annotations


def test_invalid_profile_and_font_fit_leave_old_setup_intact(owner):
    old = owner.profile
    with pytest.raises(ValueError):
        owner.load_profile({"callback": "anything"})

    def too_wide(value):
        raise ValueError("Shorten profile annotations text to fit the touch layout")

    owner.check_profile_fit = too_wide
    with pytest.raises(ValueError, match="fit"):
        owner.load_profile({"annotations": ["Wide label"]})
    assert owner.profile is old and not owner.events


def test_profile_loaded_journal_event_identifies_complete_session_setup(owner):
    lines = []
    owner.sequence, owner.started = 0, panel.monotonic()
    owner.run_id, owner.boot_id = "session", None
    owner.journal = SimpleNamespace(append=lambda line, sequence, durable: lines.append((json.loads(line), durable)))
    owner.emit = panel.Panel.emit.__get__(owner)
    owner.load_profile({"title": "Demo", "stages": ["Stand"]})
    event, durable = lines[0]
    assert event["event"] == "profile_loaded" and event["profile"] == owner.profile
    assert event["instruction_index"] == 0 and event["instruction"] == "Stand"
    assert event["recording"] is False and durable is False


def test_runtime_profile_fit_uses_existing_annotation_width_rule(owner, monkeypatch):
    monkeypatch.setattr(panel, "Font", lambda **kwargs: SimpleNamespace(measure=lambda text: 300))
    owner.root = object()
    with pytest.raises(ValueError, match="annotations"):
        panel.Panel.check_profile_fit(owner, validate_profile({}))


def test_four_annotation_labels_fit_the_embedded_panel_before_setup_changes(view):
    before = view.profile
    with pytest.raises(ValueError, match="Shorten profile annotations.*fit"):
        view.load_profile({"annotations": ["Activity completed " + c for c in "ABCD"]})
    assert view.profile is before
    labels = ["Begin", "Finish", "Observer", "Unexpected"]
    view.load_profile({"annotations": labels})
    view.open_advanced("experiment")
    view.root.update()

    def widgets(parent):
        yield parent
        for child in parent.winfo_children():
            yield from widgets(child)

    buttons = [w for w in widgets(view.body)
               if isinstance(w, panel.tk.Button) and w.cget("text") in labels]
    assert len(buttons) == 4
    for button in buttons:
        text_width = panel.Font(root=view.root, font=button.cget("font")).measure(
            button.cget("text")
        )
        assert text_width + 2 * int(button.cget("padx")) + 2 <= button.winfo_width()


@pytest.mark.parametrize("too_tall", ["W" * 60, "First\nSecond\nThird"])
def test_instruction_wrap_fit_preserves_setup_and_leaves_no_temporary_widgets(view, too_tall):
    view.load_profile({"stages": ["W" * 40]})  # Fits across two lines.
    before, children = view.profile, view.root.winfo_children()
    with pytest.raises(ValueError, match="fit two touch-panel lines"):
        view.load_profile({"stages": [too_tall]})
    assert view.profile is before
    assert view.root.winfo_children() == children
    view.open_advanced("experiment")
    view.root.update()
    assert view.stage_label.cget("text") == "W" * 40


def test_profile_api_delegates_to_existing_owner_without_switching_pages(monkeypatch):
    calls = []
    value = {"title": "Demo"}
    owner = SimpleNamespace(
        load_profile=calls.append, emit=lambda *args, **kwargs: None,
        activity=lambda *args: None, pending=None,
    )
    monkeypatch.setattr(panel_remote, "snapshot", lambda state: {"busy": False})
    assert panel_remote.execute(owner, envelope(value))["ok"]
    assert calls == [value]
