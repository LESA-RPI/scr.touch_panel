"""Room diagnostics reuses the System tool and the existing read-only check."""

import pytest

from test_panel_navigation import panel, view


def widgets(parent):
    yield parent
    for child in parent.winfo_children():
        yield from widgets(child)


def button(view, text):
    found, = [w for w in widgets(view.body)
              if isinstance(w, panel.tk.Button) and w.cget("text") == text]
    return found


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_secondary_room_diagnostics_refreshes_cached_results_and_returns_to_help(view, theme):
    data = {
        "state": "available", "checking": False, "can_check": True,
        "detail": "Advertised room services were observed.",
        "observed_at": "2026-10-30T14:00:00Z", "age_s": 120,
        "services": [{"name": name, "state": state} for name, state in (
            ("Lighting", "listed"), ("Blinds", "missing"),
            ("Environment", "listed"), ("TOF", "missing"),
        )],
    }
    checks = []

    def refresh():
        checks.append("check")
        data.update(checking=True, can_check=False)
        return True

    def blocked(*args, **kwargs):
        pytest.fail("Viewing service availability must not request hardware control")

    view.room_diagnostics = lambda: data
    view.refresh_status = refresh
    view.request = view.start_worker = blocked
    view.choose_theme(theme)
    view.open_advanced("system")
    view.root.update()
    assert not getattr(view, "system_diagnostics_visible", False)
    button(view, "Room services").invoke()
    view.root.update()
    assert view.advanced_page == "system" and view.system_diagnostics_visible
    assert len(view.diagnostics_rows.winfo_children()) == 4
    assert "2 minutes ago" in view.diagnostics_age.cget("text")
    assert not checks
    data.update(state="unavailable", detail="Latest check failed. Showing the last successful service results.")
    view.update_health()
    assert "Latest check failed" in view.diagnostics_message.cget("text")
    assert len(view.diagnostics_rows.winfo_children()) == 4
    button(view, "Check now").invoke()
    assert checks == ["check"]
    assert view.diagnostics_check.cget("state") == "disabled"
    assert "Checking now" in view.diagnostics_message.cget("text")
    view.diagnostics_check.invoke()
    assert checks == ["check"]
    view.root.update()
    for label in widgets(view.body):
        if isinstance(label, panel.tk.Label) and label.winfo_ismapped():
            assert label.winfo_height() >= label.winfo_reqheight()
    note, = [w for w in widgets(view.body)
             if isinstance(w, panel.tk.Label) and "verified indoor-data feed" in w.cget("text")]
    assert note.winfo_ismapped() and note.winfo_height() >= note.winfo_reqheight()
    assert view.diagnostics_check.winfo_ismapped()
    data.update(checking=False, can_check=True)
    view.update_health()
    assert view.diagnostics_check.cget("text") == "Check now"
    view.open_home()
    view.open_advanced("system")
    view.root.update()
    view.update_health()  # Reopening must not access the destroyed overview labels.
    button(view, "Back to System & help").invoke()
    view.root.update()
    view.update_health()
    assert not view.system_diagnostics_visible
    assert button(view, "Room services").winfo_ismapped()


def test_unobserved_room_diagnostics_never_invents_missing_services(view):
    view.room_diagnostics = lambda: {
        "state": "unconfigured", "checking": False, "can_check": False,
        "detail": "No approved room master is configured.",
        "observed_at": None, "age_s": None, "services": [],
    }
    view.open_advanced("system")
    view.root.update()
    button(view, "Room services").invoke()
    view.root.update()
    assert view.diagnostics_age.cget("text") == "No successful service check yet."
    assert view.diagnostics_check.cget("state") == "disabled"
    labels = [w.cget("text") for w in widgets(view.diagnostics_rows)
              if isinstance(w, panel.tk.Label)]
    assert labels == ["No observed service results yet."]
