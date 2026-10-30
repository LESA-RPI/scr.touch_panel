"""Primary touch destinations stay put; focus and confirmation stay explicit."""

import tkinter.font as tkfont

import pytest

from test_panel_navigation import view


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_primary_navigation_keeps_its_touch_positions_and_marks_current_page(view, theme):
    view.choose_theme(theme)
    view.root.update()
    buttons = (view.home_button, view.tools_footer_button, view.guide_footer_button)
    positions = [(b.winfo_rootx(), b.winfo_rooty(), b.winfo_width(), b.winfo_height()) for b in buttons]
    for action, current in (
        (view.open_guide, 2),
        (lambda: view.open_advanced("lighting"), 1),
        (lambda: view.open_advanced("screen"), 1),
        (view.open_home, 0),
    ):
        action()
        view.root.update()
        assert all(b.winfo_ismapped() for b in buttons)
        assert [(b.winfo_rootx(), b.winfo_rooty(), b.winfo_width(), b.winfo_height()) for b in buttons] == positions
        assert [tkfont.Font(root=view.root, font=b.cget("font")).actual("weight") for b in buttons] == [
            "bold" if index == current else "normal" for index in range(3)
        ]


def test_keyboard_focus_is_visible_without_touch_halo_or_touch_guard_changes(view):
    button = view.home_button
    button.focus_force()
    view.root.update()
    view.press_active = True
    view.button_focus(True)
    assert button.cget("highlightcolor") == view.ink
    view.button_focus(False)
    assert button.cget("highlightcolor") == button.cget("bg")
    assert view.press_active is True
    view.press_active = False


def test_connection_readout_explains_uncertainty_and_remains_a_help_shortcut(view):
    view.args.live_lights = True
    view.light_state = "failed"
    view.recovery.state["status"] = "uncertain"
    view.update_connection_badges()
    view.root.update()
    button = view.connection_badges[0][0]
    assert button.cget("text") == "Uncertain"
    assert button.cget("bg") == button.cget("highlightbackground") == view.bg
    assert button.winfo_reqwidth() <= button.winfo_width()
    button.invoke()
    view.root.update()
    assert view.advanced_page == "system"
