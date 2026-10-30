"""Exploring registered ceiling positions never operates room equipment."""

import pytest

from test_panel_navigation import view, panel
from panel_guides import CEILING_MAP, DEMO


def widgets(parent):
    yield parent
    for child in parent.winfo_children():
        yield from widgets(child)


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_ceiling_family_selection_uses_reference_positions_without_room_requests(view, theme):
    def blocked(*args, **kwargs):
        pytest.fail("A reference map must never request a room action")

    view.request = view.start_worker = blocked
    view.choose_theme(theme)
    view.choose_guide(next(i for i, topic in enumerate(DEMO) if topic.get("map")))
    view.root.update()
    canvas, = [w for w in widgets(view.body) if isinstance(w, panel.tk.Canvas)]
    for family in CEILING_MAP["families"]:
        button, = [w for w in widgets(view.body)
                   if isinstance(w, panel.tk.Button) and w.cget("text") == family["label"]]
        button.invoke()
        view.root.update()
        dots = canvas.find_withtag("sensor")
        assert len(dots) == len(family["positions"])
        assert button.cget("bg") == view.accent
        centers = [(sum(canvas.coords(dot)[::2]) / 2,
                    sum(canvas.coords(dot)[1::2]) / 2) for dot in dots]
        assert all(0 < x < canvas.winfo_width() and 0 < y < canvas.winfo_height()
                   for x, y in centers)
        # Canvas y increases downwards, so row one belongs below row five.
        assert all(a[1] > b[1]
                   for i, a in enumerate(centers) for j, b in enumerate(centers)
                   if family["positions"][i][1] < family["positions"][j][1])
        labels = [w for w in widgets(view.body) if isinstance(w, panel.tk.Label)]
        assert any(w.cget("text").startswith(
            "%s · %d ceiling positions." % (family["label"], len(dots))
        ) for w in labels)
        assert all(w.winfo_height() >= w.winfo_reqheight()
                   for w in labels if w.winfo_ismapped())
