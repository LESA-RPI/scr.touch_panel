"""Weather meaning and pointer limits must remain correct as artwork changes."""

from pathlib import Path
from types import SimpleNamespace
import sys
import tkinter as tk
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from panel_icons import weather_kind
from touch_slider import TouchSlider, selected_value
from command_reference import command_tokens
from panel_guides import SUPPORT
from help_reference import reference


def test_reference_highlighting_preserves_copy_text_and_shell_command_boundaries():
    for title, kind, guidance, commands in SUPPORT:
        assert "".join(token["text"] for token in command_tokens(commands)) == commands
    tokens = command_tokens(
        "timeout 10 rosservice list\nsource ~/catkin_ws/devel/setup.bash\npython startROS.py"
    )
    assert [(t["text"], t["kind"]) for t in tokens if t["kind"] != "text"] == [
        ("timeout", "command"),
        ("10", "number"),
        ("rosservice", "command"),
        ("source", "command"),
        ("~/catkin_ws/devel/setup.bash", "path"),
        ("python", "command"),
        ("startROS.py", "path"),
    ]


def test_help_steps_preserve_copy_text_and_explain_machine_purpose_and_result():
    for title, kind, guidance, commands in SUPPORT:
        guide = reference(title)
        if not commands:
            assert guide["steps"] == []
            continue
        assert guide["machine"] and guide["effect"]
        assert "\n\n".join(step["commands"] for step in guide["steps"]) == commands
        for step in guide["steps"]:
            assert step["title"] and step["why"] and step["expect"]
            assert (
                "".join(token["text"] for token in step["command_tokens"])
                == step["commands"]
            )
    assert all(
        " && python " in step["commands"]
        for step in reference("Start services")["steps"]
    )


def test_weather_symbols_preserve_day_night_and_precipitation_meaning():
    assert weather_kind(0) == "sun"
    assert weather_kind(0, True) == "moon"
    assert weather_kind(2) == "cloud-sun"
    assert weather_kind(2, True) == "cloud-moon"
    for code in (45, 48):
        assert weather_kind(code, True) == "cloud-fog"
    for code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82):
        assert weather_kind(code) == "cloud-rain"
    for code in (71, 73, 75, 77, 85, 86):
        assert weather_kind(code) == "cloud-snow"
    for code in (95, 96, 99):
        assert weather_kind(code) == "cloud-lightning"
    assert weather_kind(-1) == "circle-question-mark"


def test_touch_slider_clamps_drag_outside_track_and_honours_steps_in_both_directions():
    assert selected_value(-1, 1600, 10000, 100) == 1600
    assert selected_value(2, 1600, 10000, 100) == 10000
    assert selected_value(0.51, 1600, 10000, 100) == 5900
    assert selected_value(0, 100, 0, 1) == 100
    assert selected_value(1, 100, 0, 1) == 0
    assert selected_value(0.755, 100, 0, 1) == 25


@pytest.fixture
def slider_canvas(monkeypatch):
    """Exercise real variable traces and slider handlers without a display server."""

    def initialize(canvas, parent, **options):
        canvas.options = {"state": "normal", **options}
        canvas.shapes, canvas.mutations, canvas.bindings = {}, [], {}
        canvas.focused = False

    def configure(canvas, cnf=None, **options):
        if isinstance(cnf, dict):
            options = {**cnf, **options}
        canvas.options.update(options)

    monkeypatch.setattr(tk.Canvas, "__init__", initialize)
    monkeypatch.setattr(tk.Canvas, "configure", configure)

    class Canvas(TouchSlider):
        def bind(self, sequence, callback, **options):
            self.bindings[sequence] = callback

        def cget(self, option):
            return self.options[option]

        def winfo_width(self):
            return self.options["width"]

        def winfo_height(self):
            return self.options["height"]

        def winfo_ismapped(self):
            return getattr(self, "mapped", True)

        def focus_get(self):
            return self if self.focused else None

        def focus_set(self):
            self.focused = True

        def create_line(self, *coords, **options):
            return self.create_shape(coords, options)

        def create_rectangle(self, *coords, **options):
            return self.create_shape(coords, options)

        def create_shape(self, coords, options):
            key = len(self.shapes) + 1
            self.shapes[key] = {"coords": coords, **options}
            self.mutations.append(("create", key))
            return key

        def coords(self, key, *coords):
            self.shapes[key]["coords"] = coords
            self.mutations.append(("coords", key))

        def itemconfigure(self, key, **options):
            self.shapes[key].update(options)
            self.mutations.append(("configure", key))

    interpreter = tk.Tcl()
    created = []

    def create(vertical=False):
        variable = tk.IntVar(master=interpreter, value=50)
        slider = Canvas(
            None,
            variable,
            100 if vertical else 0,
            0 if vertical else 100,
            1,
            "vertical" if vertical else "horizontal",
            "background",
            "track",
            "accent",
            "border",
            "ink",
        )
        created.append(slider)
        return slider

    yield create
    # Real Tcl variable traces retain callbacks and the fake canvas. Break those
    # cycles on this owning thread before later worker tests can trigger GC.
    for slider in created:
        if slider.variable is not None:
            if slider.variable.trace_info():
                slider.cleanup(SimpleNamespace(widget=slider))
            slider.variable = None
        slider.bindings.clear()
    created.clear()


@pytest.mark.parametrize("vertical", [False, True])
def test_slider_retains_canvas_items_and_skips_unchanged_repaints(
    slider_canvas, vertical
):
    slider = slider_canvas(vertical)
    slider.draw()
    items = slider.items
    assert len(items) == len(slider.shapes) == 5
    slider.mutations.clear()
    slider.draw()
    slider.variable.set(50)
    slider.bindings["<Configure>"](SimpleNamespace())
    slider.configure(command=lambda value: None)
    slider.configure(state="normal")
    assert slider.mutations == []
    slider.variable.set(75)
    assert slider.items == items and len(slider.shapes) == 5
    assert slider.mutations and not any(
        kind == "create" for kind, key in slider.mutations
    )


@pytest.mark.parametrize("vertical", [False, True])
def test_slider_retained_shapes_follow_pointer_focus_and_disabled_state(
    slider_canvas, vertical
):
    slider = slider_canvas(vertical)
    calls = []
    slider.command = lambda value: calls.append(value)
    slider.draw()
    items = slider.items
    track, fill, thumb, *grips = items
    slider.focused = True
    slider.bindings["<FocusIn>"](SimpleNamespace())
    assert slider.shapes[thumb]["outline"] == "accent"
    assert slider.shapes[thumb]["width"] == 2
    pointer = lambda point: SimpleNamespace(
        x=24 if vertical else point, y=point if vertical else 24
    )
    slider.press(pointer(26))
    assert slider.variable.get() == slider.start
    assert slider.shapes[fill]["state"] == "hidden"
    assert slider.shapes[thumb]["fill"] == "accent"
    assert all(slider.shapes[key]["fill"] == "background" for key in grips)
    slider.move(pointer(174))
    assert slider.variable.get() == slider.end
    assert slider.shapes[fill]["state"] == "normal"
    slider.release(pointer(174))
    assert slider.shapes[thumb]["fill"] == "track" and not slider.pressed
    assert slider.items == items and len(slider.shapes) == 5
    slider.configure(state="disabled")
    assert slider.shapes[fill]["state"] == "hidden"
    assert slider.shapes[thumb]["outline"] == "border"
    assert all(slider.shapes[key]["fill"] == "border" for key in grips)
    previous, count = slider.variable.get(), len(calls)
    slider.press(pointer(26))
    slider.move(pointer(26))
    slider.key(SimpleNamespace(keysym="Home"))
    assert slider.variable.get() == previous and len(calls) == count
    slider.configure(state="normal")
    slider.focused = False
    slider.bindings["<FocusOut>"](SimpleNamespace())
    assert slider.shapes[thumb]["outline"] == "ink"
    assert slider.shapes[thumb]["width"] == 1


def test_slider_destroy_removes_its_variable_trace(slider_canvas):
    slider = slider_canvas()
    slider.draw()
    assert len(slider.variable.trace_info()) == 1
    slider.cleanup(SimpleNamespace(widget=object()))
    assert len(slider.variable.trace_info()) == 1
    slider.bindings["<Destroy>"](SimpleNamespace(widget=slider))
    assert not slider.variable.trace_info()
    slider.mutations.clear()
    slider.variable.set(75)
    assert slider.mutations == []


def test_hidden_retained_slider_ignores_keys_until_shown(slider_canvas):
    slider = slider_canvas()
    calls = []
    slider.command = calls.append
    slider.mapped = False
    slider.key(SimpleNamespace(keysym="Right"))
    assert slider.variable.get() == 50 and calls == []
    slider.mapped = True
    slider.key(SimpleNamespace(keysym="Right"))
    assert slider.variable.get() == 51 and calls == ["51"]
