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
    view.open_home()
    view.guide_footer_button.invoke()
    view.root.update()
    assert view.mode == "guide" and view.guide_page == index
    view.guide_footer_button.invoke()
    view.root.update()
    assert view.mode == "guide" and view.guide_page == -1
    view.choose_guide(index)
    view.root.update()
    all_topics, = [w for w in widgets(view.body)
                   if w.winfo_class() == "Button" and w.cget("text") == "Back to topics"]
    all_topics.invoke()
    view.root.update()
    assert view.guide_page == -1
    overview = [w for w in widgets(view.body)
                if w.winfo_class() == "Button" and "\n" in w.cget("text")]
    assert {w.cget("text") for w in overview} == {
        topic["title"] + "  ›\n" + topic["caption"] for topic in DEMO
    }
    assert all(w.winfo_ismapped() and w.winfo_height() >= 44 for w in overview)
    assert {"Room tour", "Control help"}.issubset({
        w.cget("text") for w in widgets(view.body) if w.winfo_class() == "Label"
    })


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
    view.lighting_feedback("Light settings confirmed.")
    view.root.update()
    action = view.light_buttons[0]
    readback_gap = view.light_feedback_card._detail.winfo_rooty() - (action.winfo_rooty() + action.winfo_height())
    assert 0 <= readback_gap <= 24
    for button in view.light_buttons:
        view.light_state = "ready"  # Each mock request has received its confirmation.
        view.update_light_buttons()
        assert button.cget("state") == "normal"
        button.invoke()
    assert requests == [("channels", {"values": list(PRESETS["Fid"])}), ("gradient", {})]
    lighting, = [w for w in widgets(view.body)
                 if w.winfo_class() == "Button" and w.cget("text") == "Open Lighting"]
    assert lighting not in view.light_buttons and lighting.winfo_height() >= 44
    lighting.invoke()
    view.root.update()
    assert view.advanced_page == "lighting"
    assert len(requests) == 2  # The adjacent page link never sends a lighting command.
    view.worker = None


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_distance_illustrations_are_readable_reference_grids_without_live_requests(view, theme):
    def blocked(*args, **kwargs):
        pytest.fail("A sampling-grid illustration must not request room equipment")

    view.request = view.start_worker = blocked
    view.choose_theme(theme)
    view.choose_guide(next(i for i, topic in enumerate(DEMO) if topic.get("visual") == "distance"))
    view.root.update()
    canvas, = [w for w in widgets(view.body) if w.winfo_class() == "Canvas"]
    labels = [canvas.itemcget(item, "text") for item in canvas.find_all() if canvas.type(item) == "text"]
    assert "COMBO · 8 × 8 · 64 cells" in labels
    assert "IRMA · 25 × 20 · 500 cells" in labels
    assert any("schematic" in label and "no live readings" in label for label in labels)
    for item in canvas.find_all():
        if canvas.type(item) == "text":
            left, top, right, bottom = canvas.bbox(item)
            assert 0 <= left < right <= canvas.winfo_width()
            assert 0 <= top < bottom <= canvas.winfo_height()
    for family in ("combo", "irma"):
        left, top, right, bottom = canvas.bbox(family)
        assert right - left >= 120 and bottom - top >= 120
        assert 0 <= top < bottom <= canvas.winfo_height()
    for label in widgets(view.body):
        if label.winfo_class() == "Label" and label.winfo_ismapped():
            assert label.winfo_height() >= label.winfo_reqheight()


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
    assert all(w.winfo_height() >= 44 for w in widgets(view.body)
               if w.winfo_class() == "Button" and w.winfo_ismapped())
    recovery = view.recovery_snapshot()
    if recovery["can_check"] and recovery["status"] not in ("normal", "writing"):
        assert view.recovery_button.winfo_ismapped() and view.recovery_button.winfo_height() >= 44
    for index, button in enumerate(view.light_buttons):
        disabled = guard != "unsupported-gradient" or index == 1
        assert button.cget("state") == ("disabled" if disabled else "normal")
        if disabled:
            button.invoke()
    assert not requests
    view.running = False
    view.worker = None
