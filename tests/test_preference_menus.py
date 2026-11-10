"""Visible binary choices and longer menus keep saved values and room guards."""

import pytest

from test_panel_navigation import panel, shared_worker, view


def widgets(parent):
    yield parent
    for child in parent.winfo_children():
        yield from widgets(child)


def select(view, title, label):
    row, = [w.master for w in widgets(view.body) if isinstance(w, panel.tk.Label)
            and w.cget("text") == title]
    buttons = [w for w in widgets(row) if isinstance(w, panel.tk.Button)]
    if buttons:
        assert len(buttons) == 2
        assert all(button.winfo_ismapped() and button.winfo_height() >= 44 for button in buttons)
        assert all(button.winfo_width() >= button.winfo_reqwidth() for button in buttons)
        assert all(button.winfo_rootx() >= row.winfo_rootx()
                   and button.winfo_rootx() + button.winfo_width() <= row.winfo_rootx() + row.winfo_width()
                   for button in buttons)
        assert len([button for button in buttons if button.cget("text").startswith("✓ ")]) == 1
        button, = [button for button in buttons if button.cget("text").removeprefix("✓ ") == label]
        button.invoke()
        view.root.update()
        saved, = [w for w in widgets(view.body) if isinstance(w, panel.tk.Button)
                  and w.cget("text") == "✓ " + label]
        assert saved.winfo_ismapped()
        return
    menu, = [w for w in widgets(view.body) if isinstance(w, panel.tk.OptionMenu)
             and any(isinstance(c, panel.tk.Label) and c.cget("text") == title
                     for c in w.master.winfo_children())]
    assert menu.winfo_ismapped() and menu.winfo_height() >= 44
    options = menu["menu"]
    index, = [i for i in range(options.index("end") + 1)
              if options.entrycget(i, "label") == label]
    options.invoke(index)
    view.root.update()


def texts(view):
    return [w.cget("text") for w in widgets(view.body) if isinstance(w, panel.tk.Label)]


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_visible_binary_choices_and_longer_menus_save_without_room_requests(view, theme):
    def blocked(*args, **kwargs):
        pytest.fail("Preference selection must not request room equipment")

    view.request = view.start_worker = blocked
    view.choose_theme(theme)
    view.open_advanced("appearance")
    view.root.update()
    assert "Automatic schedule" not in texts(view)
    select(view, "Theme", "Automatic")
    assert view.theme_choice == "auto" and "Automatic schedule" in texts(view)
    select(view, "Theme", "Light")
    assert view.theme_choice == "light" and "Automatic schedule" not in texts(view)
    select(view, "Touch explanations", "Off")
    assert not view.help_on
    view.open_advanced("clock")
    view.root.update()
    select(view, "Time format", "12-hour")
    select(view, "Temperature", "Celsius (°C)")
    assert not view.clock_24 and view.temperature_unit == "c"
    view.open_advanced("screen")
    view.root.update()
    select(view, "Screen saver", "15 minutes")
    select(view, "Blinds on Home", "Hidden")
    assert view.idle_timeout == 900 and view.blinds_display == "hidden"


def test_explicit_blind_permission_action_requires_a_connected_adapter(view):
    shared_worker(view)
    requests = []
    view.request = lambda *args: requests.append(args)
    view.open_advanced("screen")
    view.root.update()

    def permission_buttons():
        return [w for w in widgets(view.body) if isinstance(w, panel.tk.Button)
                and w.cget("text") in ("Lock blind movement", "Unlock blind movement")]

    assert not permission_buttons() and not view.blinds_enabled
    view.adapter_metadata({"blinds_connected": True})
    view.root.update()
    permission, = permission_buttons()
    assert permission.cget("text") == "Unlock blind movement"
    permission.invoke()
    view.root.update()
    assert view.blinds_enabled
    permission, = permission_buttons()
    assert permission.cget("text") == "Lock blind movement"
    permission.invoke()
    view.root.update()
    assert not view.blinds_enabled
    view.adapter_metadata({"blinds_connected": False})
    view.root.update()
    assert not permission_buttons() and not requests
    view.worker = None
