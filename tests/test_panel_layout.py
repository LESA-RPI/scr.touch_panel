"""Font-independent native layout and command routing, with no external devices."""
from itertools import combinations
from types import SimpleNamespace
import pytest

from test_panel_navigation import panel, view, shared_worker
from page_guide import TOPICS
from page_lights import acquired_controls
from scr_touch_panel_lights import PRESETS, setter_words
from touch_slider import TouchSlider
from ui_widgets import S, PrefRow


def walk(widget):
    yield widget
    for child in widget.winfo_children():
        yield from walk(child)


def buttons(view, text):
    return [w for w in walk(view.root) if isinstance(w, panel.tk.Button)
            and w.winfo_ismapped() and w.cget("text") == text]


def bounds(widget):
    return (widget.winfo_rootx(), widget.winfo_rooty(),
            widget.winfo_rootx()+widget.winfo_width(), widget.winfo_rooty()+widget.winfo_height())


def assert_layout(view):
    view.root.update()
    interactive = [w for w in walk(view.root) if isinstance(w, (panel.tk.Button, TouchSlider)) and w.winfo_ismapped()]
    screen = bounds(view.root)
    if view.sheet_name:
        interactive = [w for w in walk(view.sheet) if isinstance(w, panel.tk.Button) and w.winfo_ismapped()]
    for widget in interactive:
        box = bounds(widget)
        assert widget.winfo_width() >= 44 and widget.winfo_height() >= 44, (widget, box, widget.cget("text") if isinstance(widget, panel.tk.Button) else "slider")
        assert box[0] >= screen[0] and box[1] >= screen[1] and box[2] <= screen[2] and box[3] <= screen[3], (widget, box, screen)
        ancestor = widget.master
        while ancestor != view.root:
            parent = bounds(ancestor)
            assert box[0] >= parent[0] and box[1] >= parent[1] and box[2] <= parent[2]+1 and box[3] <= parent[3]+1, (widget, box, ancestor, parent)
            ancestor = ancestor.master
        if getattr(widget, "kind", None) == "primary":
            assert widget.winfo_height() >= S["tap"]
    for a, b in combinations(interactive, 2):
        aa, bb = bounds(a), bounds(b)
        assert min(aa[2], bb[2]) <= max(aa[0], bb[0]) or min(aa[3], bb[3]) <= max(aa[1], bb[1]), (a, b, aa, bb)


def routes(view):
    yield "home", view.open_home
    for tab in ("white", "scenes", "programmes", "channels"):
        yield "lights-"+tab, lambda t=tab: view.choose_lighting_tab(t)
    for index in range(len(TOPICS)):
        yield "guide-"+str(index), lambda i=index: view.choose_guide(i)
    for category in ("screen", "appearance", "clock", "system", "about"):
        yield "settings-"+category, lambda c=category: view.open_advanced(c)
    yield "saver", lambda: view.show("visitor")


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_all_pages_sheets_and_marker_targets_fit_without_room_requests(view, monkeypatch, theme):
    shared_worker(view)
    view.choose_theme(theme)
    requests = []
    monkeypatch.setattr(view, "request", lambda *args, **kwargs: requests.append(args))
    for name, navigate in routes(view):
        navigate()
        assert_layout(view)
        if name == "settings-system":
            view.poll_power()  # The live poller consumes the retained power-button references.
        if name == "guide-3":
            assert view.map_hits
            assert all(right-left >= 44 and bottom-top >= 44 for left, top, right, bottom, _ in view.map_hits)
            assert all(0 <= left < right <= view.map_canvas.winfo_width() and
                       0 <= top < bottom <= view.map_canvas.winfo_height()
                       for left, top, right, bottom, _ in view.map_hits)
    view.return_from_idle()
    view.blind_controller = SimpleNamespace(connected=True)
    view.blinds_enabled = True
    view.open_home()
    assert_layout(view)
    assert len(view.blind_buttons) == 3
    for key in ("status", "idle", "theme", "clock", "temperature", "blinds_display", "blinds_enabled", "tips", "schedule"):
        view.open_connection_sheet() if key == "status" else view.open_preference(key)
        assert_layout(view)
        view.close_sheet()
    for title in (None, "Power", "Ubuntu checks", "Start services", "Restart computer"):
        view.open_maintenance(title)
        assert_layout(view)
    view.close_sheet()
    worker, view.worker = view.worker, None
    view.args.live_lights = False
    view.show("original")
    view.root.update()
    assert view.dock.winfo_height() == 112
    assert len([w for w in walk(view.dock) if isinstance(w, panel.tk.Button)]) == 1
    view.open_home()
    view.worker, view.args.live_lights = worker, True
    assert_layout(view)
    assert not requests
    view.worker = None


def test_navigation_and_cached_slider_work_after_recovery_cancellation(view, monkeypatch):
    shared_worker(view)
    view.open_lighting()
    view.root.update()
    white = view.body
    scale = next(w for w in view.light_buttons if isinstance(w, TouchSlider))
    calls = []
    monkeypatch.setattr(view, "cct_apply", lambda: calls.append((view.cct.get(), view.intensity.get())))
    generation = view.view_generation
    view.cancel_intent()  # automatic reconnect cancels while the page is still visible
    assert view.view_generation > generation
    scale.press(SimpleNamespace(x=140, y=24))
    scale.release(SimpleNamespace(x=140, y=24))
    view.root.update()
    assert len(calls) == 1
    for unused in range(3):
        view.open_home()
        view.open_lighting()
        view.root.update()
        assert view.body is white
        scale.press(SimpleNamespace(x=160, y=24))
        scale.release(SimpleNamespace(x=160, y=24))
    assert len(calls) == 4
    view.worker = None


def test_controls_route_through_live_panel_methods_and_preferences_use_sheets(view, monkeypatch):
    shared_worker(view)
    calls = []
    monkeypatch.setattr(view, "lights_on", lambda: calls.append("on"))
    monkeypatch.setattr(view, "preset", lambda name: calls.append(name))
    monkeypatch.setattr(view, "previous_on", lambda: calls.append("warm"))
    monkeypatch.setattr(view, "programme_command", lambda name: calls.append(name))
    view.open_home()
    view.root.update()
    buttons(view, "Lights on")[0].invoke()
    buttons(view, "Lights off")[0].invoke()
    view.choose_lighting_tab("white")
    view.root.update()
    buttons(view, "Apply Warm white")[0].invoke()
    view.choose_lighting_tab("scenes")
    view.root.update()
    buttons(view, "Sat")[0].invoke()
    view.choose_lighting_tab("programmes")
    view.root.update()
    for title in ("Start Sun", "Start Circ", "Stop programmes"):
        buttons(view, title)[0].invoke()
    assert calls == ["on", "Off", "warm", "Sat", "Sun", "Circ", "Stop"]
    view.light_capabilities = {}
    view.render()
    view.root.update()
    assert not buttons(view, "Start Sun") and not buttons(view, "Stop programmes")
    view.open_advanced("appearance")
    view.root.update()
    rows = [w for w in walk(view.body) if isinstance(w, PrefRow)]
    assert rows
    rows[0].value_button.invoke()
    view.root.update()
    assert view.sheet_name == "theme"
    buttons(view, "Dark")[0].invoke()
    view.root.update()
    assert view.theme_choice == "dark" and view.sheet is None
    view.worker = None


def test_first_wake_touch_opens_home_without_issuing_a_light_command(view, monkeypatch):
    shared_worker(view)
    calls = []
    monkeypatch.setattr(view, "request", lambda *args: calls.append(args))
    view.show("visitor")
    view.root.update()
    view.body.event_generate("<ButtonPress-1>", x=80, y=180)
    view.body.event_generate("<ButtonRelease-1>", x=80, y=180)
    view.root.update()
    assert view.mode == "room" and not view.idle_active
    assert not calls
    view.worker = None


def test_acquired_mix_seeds_only_representable_values(view):
    view.seed_controls({"baseline": "Sat"})
    assert [v.get() for v in view.channel_values] == list(PRESETS["Sat"])
    assert view.controls_known == {"channels": True, "white": False}
    view.seed_controls({"fixture_words": [[[1, 1], list(setter_words(PRESETS["Fid"]))], [[2, 1], [0]*8]]})
    assert not view.controls_known["channels"]
    assert [v.get() for v in view.channel_values] == [0]*8
    assert view.intensity.get() == 0
    values, white = acquired_controls({"words": list(setter_words([25]*8)), "cct": 3500, "intensity": 1000})
    assert values == [25]*8 and white == (3500, 1000)


def test_pressed_action_stays_solid_until_confirmation_and_other_controls_dim(view):
    shared_worker(view)
    view.open_home()
    view.root.update()
    view.pending = {"action": "channels", "arguments": {"values": list(PRESETS["Fid"])}}
    view.light_state = "applying"
    view.update_light_buttons()
    on, off = [b for b, _, _ in view.home_power_buttons]
    assert on.cget("text").endswith("Sending…") and on.cget("bg") == view.accent
    assert off.cget("bg") == view.surface
    assert on.blocked and off.cget("state") == "disabled"
    on.event_generate("<FocusOut>")
    on.invoke()
    assert view.queued_intent is None
    view.pending = None
    view.light_state = "ready"
    view.update_light_buttons()
    assert on.cget("text") == "Lights on"
    view.worker = None
