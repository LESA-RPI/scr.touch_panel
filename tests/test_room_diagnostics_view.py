"""Room diagnostics reuses the System tool and the existing read-only check."""

import pytest

from test_panel_navigation import panel, view, shared_worker


def widgets(parent):
    yield parent
    for child in parent.winfo_children():
        yield from widgets(child)


def button(view, text):
    found, = [w for w in widgets(view.body)
              if isinstance(w, panel.tk.Button) and w.cget("text") == text]
    return found


@pytest.mark.parametrize("origin", ["home", "system"])
@pytest.mark.parametrize("remembered", ["services", "commands"])
def test_contextual_status_opens_visible_lighting_recovery_without_a_room_action(view, origin, remembered):
    worker = shared_worker(view)
    view.open_advanced("system")
    if remembered == "services":
        view.toggle_room_diagnostics()
    else:
        view.support_page, view.support_step, view.support_commands_visible = 3, 1, True
        view.rebuild_advanced_detail()
    if origin == "home":
        view.open_home()
        view.open_advanced("system")
        assert getattr(view, "system_diagnostics_visible", False) == (remembered == "services")
        assert view.support_commands_visible == (remembered == "commands")
        view.open_home()
    view.recovery.mark_uncertain("An earlier result needs checking")
    assert view.recovery.settled.wait(2)
    view.light_state = "failed"
    view.update_connection_badges()
    view.connection_badges[0][0].invoke()
    view.root.update()
    assert view.mode == "health" and view.advanced_page == "system"
    assert not view.system_diagnostics_visible and not view.support_commands_visible
    assert (view.support_page, view.support_step) == (0, 0)
    assert view.recovery_button.winfo_ismapped()
    assert view.recovery_button.cget("text") == "Check connection"
    assert view.recovery_button.cget("state") == "normal"
    assert button(view, "Restart panel").winfo_ismapped()
    assert button(view, "Shut down panel").winfo_ismapped()
    assert not worker.stdin.getvalue()
    view.worker = None


def test_home_and_system_blind_status_follow_connection_permission_and_busy_state(view):
    worker = shared_worker(view)
    controls = tuple(view.blind_buttons)
    assert len(controls) == 3
    view.blinds_enabled, view.blinds_connected = False, False
    view.tick()
    assert view.blind_status_label.cget("text") == "Not connected"
    assert all(control.winfo_ismapped() for control in controls)
    view.open_advanced("system")
    assert view.system_blind_status_label.cget("text") == "Blinds · Not connected"
    view.adapter_metadata({"blinds_connected": True})
    view.tick()
    assert view.system_blind_status_label.cget("text") == "Blinds · Locked in settings"
    view.blinds_enabled = True
    view.tick()
    assert view.system_blind_status_label.cget("text") == "Blinds · Ready"
    view.pending = {"action": "blind"}
    view.tick()
    assert view.system_blind_status_label.cget("text") == "Blinds · Room controls busy"
    view.pending = None
    view.open_home()
    view.root.update()
    assert tuple(view.blind_buttons) == controls
    assert all(control.winfo_ismapped() and control.cget("state") == "normal" for control in controls)
    view.adapter_metadata({"blinds_connected": False})
    view.tick()
    assert view.blind_status_label.cget("text") == "Not connected"
    assert all(control.winfo_ismapped() and control.cget("state") == "disabled" for control in controls)
    assert not worker.stdin.getvalue()
    view.worker = None


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
