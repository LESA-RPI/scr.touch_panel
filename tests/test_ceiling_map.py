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
        centers = [(sum(canvas.coords(dot)[::2]) / 2,
                    sum(canvas.coords(dot)[1::2]) / 2) for dot in dots]
        assert all(0 < x < canvas.winfo_width() and 0 < y < canvas.winfo_height()
                   for x, y in centers)
        left, top, right, bottom = 42, 12, canvas.winfo_width() - 18, canvas.winfo_height() - 32
        cell_width = (right - left) / CEILING_MAP["grid"]["columns"]
        cell_height = (bottom - top) / CEILING_MAP["grid"]["rows"]
        assert all(canvas.itemcget(dot, "fill") == family["colours"][theme] for dot in dots)
        for point, center in zip(family["positions"], centers):
            column, row = point["cell"]
            assert center == pytest.approx((left + (column - 1 + point["u"]) * cell_width,
                                            bottom - (row - 1 + point["v"]) * cell_height))
        # Canvas y increases downwards, so row one belongs below row five.
        assert all(a[1] > b[1]
                   for i, a in enumerate(centers) for j, b in enumerate(centers)
                   if family["positions"][i]["cell"][1] < family["positions"][j]["cell"][1])
        labels = [w for w in widgets(view.body) if isinstance(w, panel.tk.Label)]
        assert any(w.cget("text").startswith(
            "%s · %d ceiling positions." % (family["label"], len(dots))
        ) for w in labels)
        point = family["positions"][0]
        canvas.event_generate("<ButtonPress-1>", x=round(centers[0][0]), y=round(centers[0][1]))
        canvas.event_generate("<ButtonRelease-1>", x=round(centers[0][0]), y=round(centers[0][1]))
        view.root.update()
        assert not view.press_active
        assert any(w.cget("text").startswith("%s · R%dC%d · Reference %s" % (
            family["label"], *point["cell"], point["reference_id"]
        )) for w in labels)
        empty = next((column, row) for column in range(1, 15) for row in range(1, 6)
                     if [column, row] not in [p["cell"] for p in family["positions"]])
        canvas.event_generate("<ButtonPress-1>", x=round(left + (empty[0] - 0.5) * cell_width),
                              y=round(bottom - (empty[1] - 0.5) * cell_height))
        canvas.event_generate("<ButtonRelease-1>", x=round(left + (empty[0] - 0.5) * cell_width),
                              y=round(bottom - (empty[1] - 0.5) * cell_height))
        view.root.update()
        assert any(w.cget("text").startswith("%s · R%dC%d · No registered position" % (
            family["label"], *empty
        )) for w in labels)
        assert all(w.winfo_height() >= w.winfo_reqheight()
                   for w in labels if w.winfo_ismapped())
