"""Guide shortcuts are navigation only and keep the place the visitor left."""

import pytest

from test_panel_navigation import view, shared_worker
from panel_guides import DEMO
from scr_touch_panel_lights import PRESETS


def widgets(parent):
    yield parent
    for child in parent.winfo_children():
        yield from widgets(child)


@pytest.mark.parametrize("index", range(len(DEMO)))
def test_guide_links_open_pages_and_return_to_same_topic(view, index):
    view.choose_guide(index)
    view.root.update()
    for destination in DEMO[index]["links"]:
        view.choose_guide(index)
        view.root.update()
        button, = [w for w in widgets(view.body)
                   if w.winfo_class() == "Button" and w.cget("text") == destination["label"]]
        button.invoke()
        view.root.update()
        if destination["page"] == "home":
            assert view.mode == "room"
        else:
            assert view.advanced_page == destination["page"]
        view.open_guide()
        view.root.update()
        assert view.mode == "guide" and view.guide_page == index
    all_topics, = [w for w in widgets(view.body)
                   if w.winfo_class() == "Button" and w.cget("text") == "All topics"]
    all_topics.invoke()
    view.root.update()
    assert view.guide_page == -1


def test_guide_light_actions_keep_shared_requests_and_one_feedback_card(view):
    shared_worker(view)
    requests = []
    view.request = lambda action, arguments=None: requests.append((action, arguments)) or True
    view.choose_guide(next(i for i, topic in enumerate(DEMO) if topic.get("actions")))
    view.root.update()
    assert not requests  # Opening the story never operates the lights.
    assert len(view.light_buttons) == 2
    assert len([w for w in widgets(view.body)
                if w.winfo_class() == "Button" and w.cget("text") == "Check connection"]) == 1
    for button in view.light_buttons:
        view.light_state = "ready"  # Each mock request has received its confirmation.
        view.update_light_buttons()
        assert button.cget("state") == "normal"
        button.invoke()
    assert requests == [("channels", {"values": list(PRESETS["Fid"])}), ("gradient", {})]
    view.worker = None


@pytest.mark.parametrize("guard", ["failed", "running", "ownership", "unsupported-gradient"])
def test_guide_light_actions_retain_control_and_capability_guards(view, guard):
    shared_worker(view)
    if guard == "failed":
        view.light_state = "failed"
    elif guard == "running":
        view.running = True
    elif guard == "ownership":
        view.recovery.mark_uncertain("An earlier test result was not confirmed")
    else:
        view.light_capabilities["gradient"] = False
    requests = []
    view.request = lambda *args: requests.append(args) or True
    view.choose_guide(next(i for i, topic in enumerate(DEMO) if topic.get("actions")))
    view.root.update()
    assert len(view.light_buttons) == 2
    assert view.light_feedback_card.winfo_height() >= view.light_feedback_card.winfo_reqheight()
    recovery = view.recovery_snapshot()
    if recovery["can_check"] and recovery["status"] not in ("normal", "writing"):
        assert view.recovery_button.winfo_ismapped()
    for index, button in enumerate(view.light_buttons):
        disabled = guard != "unsupported-gradient" or index == 1
        assert button.cget("state") == ("disabled" if disabled else "normal")
        if disabled:
            button.invoke()
    assert not requests
    view.running = False
    view.worker = None
