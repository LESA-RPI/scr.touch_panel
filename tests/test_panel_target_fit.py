"""Keep recovery and guide touch targets usable with the cabinet's font metrics."""

import pytest
from types import SimpleNamespace

from test_panel_navigation import panel, view
from panel_guides import DEMO


def widgets(parent):
    yield parent
    for child in parent.winfo_children():
        yield from widgets(child)


def visible_buttons(view):
    return [w for parent in (view.body, view.footer) for w in widgets(parent)
            if isinstance(w, panel.tk.Button) and w.winfo_ismapped()]


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_guide_and_home_recovery_keep_full_touch_targets(view, theme):
    view.choose_theme(theme)
    view.choose_guide(-1)
    view.root.update()
    for button in visible_buttons(view):
        assert button.winfo_height() >= 44, button.cget("text")
        if "\n" in button.cget("text"):
            font = panel.Font(root=view.root, font=button.cget("font"))
            width = max(font.measure(line) for line in button.cget("text").splitlines())
            assert width <= button.winfo_width(), button.cget("text")
    navigation_positions = None
    for index in range(len(DEMO)):
        view.choose_guide(index)
        view.root.update()
        assert all(button.winfo_height() >= 44 for button in visible_buttons(view))
        navigation = [next(button for button in visible_buttons(view)
                           if button.cget("text").endswith(" topics"))]
        navigation.extend(next(button for button in visible_buttons(view) if button.cget("text") == label)
                          for label in ("Previous", "Next"))
        positions = [(button.winfo_x(), button.winfo_width()) for button in navigation]
        assert navigation[0].master.winfo_width() <= 700
        if navigation_positions is None:
            navigation_positions = positions
        else:
            assert positions == navigation_positions
    view.args.live_lights = True
    view.light_state = "disconnected"
    view.confirmed_light, view.confirmed_at = "Fid scene", panel.monotonic()
    view.open_home()
    for enabled in (False, True):
        view.blinds_enabled = enabled
        view.update_light_buttons()
        view.root.update()
        assert view.recovery_button.winfo_ismapped() and view.recovery_button.winfo_height() >= 44
    view.recovery.mark_uncertain("A previous test result was not confirmed")
    view.light_state = "failed"
    for enabled, controller, reason in (
        (False, None, "Not connected"),
        (True, None, "Not connected"),
        (True, SimpleNamespace(connected=True), "Room controls busy"),
    ):
        view.blinds_enabled, view.blind_controller = enabled, controller
        view.update_light_buttons()
        view.root.update()
        assert view.blind_status_label.cget("text") == reason
        assert view.recovery_button.winfo_ismapped() and view.recovery_button.winfo_height() >= 44
        assert view.light_feedback_card.winfo_height() >= view.light_feedback_card.winfo_reqheight()
    view.choose_guide(next(i for i, topic in enumerate(DEMO) if topic.get("actions")))
    view.root.update()
    assert all(button.winfo_height() >= 44 for button in visible_buttons(view))
    assert view.recovery_button.winfo_ismapped() and view.recovery_button.winfo_height() >= 44
    assert view.light_feedback_card.winfo_height() >= view.light_feedback_card.winfo_reqheight()


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_map_gives_navigation_and_note_priority_when_font_layout_needs_more_room(view, theme):
    view.choose_theme(theme)
    view.root.geometry("1280x750")
    view.choose_guide(next(i for i, topic in enumerate(DEMO) if topic.get("map")))
    view.root.update()
    buttons = visible_buttons(view)
    assert {"Back to topics", "Previous", "Next"}.issubset({b.cget("text") for b in buttons})
    assert all(button.winfo_height() >= 44 for button in buttons)
    canvas, = [w for w in widgets(view.body) if isinstance(w, panel.tk.Canvas)]
    assert canvas.winfo_height() >= 100
    labels = [w for w in widgets(view.body) if isinstance(w, panel.tk.Label)]
    assert all(label.winfo_height() >= label.winfo_reqheight()
               for label in labels if label.winfo_ismapped())
