"""Master-detail room guide, static ceiling reference and panel-only Wi-Fi."""
from pathlib import Path
import tkinter as tk
import room_controls
from panel_guides import DEMO, CEILING_MAP
from ui_widgets import S, Button, ListRow, Segmented, Card, label, font

TOUR = tuple(x for x in DEMO if x["section"] == "room")
HOWTO = (
    {"title": "Lighting", "text": "Lights on and Lights off on Home cover everyday use. Lights holds White light, Scenes, Programmes and Channels; opening a tab never changes the lights. The line under the controls says what the lights are doing and when that was confirmed.", "page": "lighting"},
    {"title": "Blinds", "text": "Lift blinds raises the whole room. Open slats tilts them open. Close & lower tilts them closed and lowers them. Blinds stay locked until someone unlocks them in Settings → Screen.", "page": "screen"},
    {"title": "If something looks wrong", "text": "The chip at the top right always says what the room connection is doing. Tap it for details, Check connection and Legacy controls. If a change is uncertain, wait for it to be checked before trying again.", "page": "system"},
)
TOPICS = TOUR + HOWTO


class GuidePage:
    def open_guide(self):
        self.show("guide")

    def choose_guide(self, index):
        # Public topic indices follow the shared guide content, including the map.
        self.guide_page = index
        self.show("guide")

    def guide_view(self):
        side, content = self.split_page()
        index = self.guide_page if self.guide_page >= 0 else 0
        index = min(index, len(TOPICS)-1)
        for start, title, topics in ((0, "ROOM TOUR", TOUR), (len(TOUR), "USING THE CONTROLS", HOWTO)):
            label(self, side, title, "small", True).pack(anchor="w", padx=12, pady=(12, 8))
            for offset, topic in enumerate(topics):
                i = start + offset
                area = tk.Frame(side, bg=self.bg, height=S["tap"])
                area.pack(fill="x", pady=(0, 4))
                area.pack_propagate(False)
                ListRow(self, area, topic["title"], lambda n=i: self.choose_guide(n),
                        i == index, icon=("sensors", "on", "health", "scenes", "on", "blinds", "link-ok")[i]).pack(fill="both", expand=True)
        topic = TOPICS[index]
        label(self, content, topic["title"], "title").pack(anchor="w", pady=(0, 16))
        if topic.get("map"):
            self.ceiling_map(content)
            return
        text = topic["text"].replace("Room tools → Lighting", "Lights").replace("Room tools", "Settings").replace("Screen & controls", "Settings → Screen").replace("System & help", "System")
        label(self, content, text, wraplength=710).pack(fill="x", pady=(0, 24))
        if topic.get("visual") == "channels":
            from panel_common import CHANNELS, CHANNEL_COLOURS
            row = tk.Frame(content, bg=self.bg)
            row.pack(fill="x", pady=(0, 24))
            for name, colour in zip(CHANNELS, CHANNEL_COLOURS):
                cell = tk.Frame(row, bg=self.bg)
                cell.pack(side="left", expand=True)
                tk.Frame(cell, bg=colour, width=28, height=40).pack()
                label(self, cell, name, "small").pack()
        if topic.get("page"):
            Button(self, content, "Open " + ("Lights" if topic["page"] == "lighting" else "Settings") + "  ›",
                   lambda: self.open_advanced(topic["page"]), "link").pack(anchor="w", ipady=16)
        self.website_qr(content)

    def website_qr(self, parent, compact=False):
        path = Path(__file__).resolve().parents[1] / "assets/website-qr.png"
        key = ("website-qr", compact)
        if key not in self.icon_cache:
            from PIL import Image, ImageTk
            image = Image.open(path)
            image = image.resize((100, 100) if compact else (128, 128), Image.Resampling.NEAREST)
            self.icon_cache[key] = ImageTk.PhotoImage(image, master=self.root)
        card = Card(self, parent)
        card.pack(side="bottom", fill="x", pady=(S["space"], 0))
        tk.Label(card, image=self.icon_cache[key], bg="white", bd=0).pack(side="right", padx=16, pady=16)
        text = tk.Frame(card, bg=self.surface)
        text.pack(side="left", fill="both", expand=True, padx=16, pady=16)
        label(self, text, "Room controls on your phone", "text").pack(anchor="w")
        label(self, text, "1. Join Wi-Fi: " + room_controls.ROOM_NETWORK_NAME, "small").pack(anchor="w", pady=(12, 4))
        label(self, text, "Wi-Fi key: " + room_controls.ROOM_NETWORK_PASSWORD if room_controls.ROOM_NETWORK_PASSWORD
              else "Need the Wi-Fi key?\nAsk the room host.", "small", True).pack(anchor="w")
        label(self, text, "2. Scan the QR code to open the room website.", "small", True).pack(anchor="w", pady=(8, 0))
        return card

    def ceiling_map(self, parent):
        families = CEILING_MAP["families"]
        selected = getattr(self, "map_family", families[0]["id"])
        family = next(f for f in families if f["id"] == selected)
        segment = Segmented(self, parent, [(f["label"], f["id"]) for f in families], selected,
                            lambda value: choose(value))
        segment.pack(fill="x", pady=(0, 12))
        canvas = tk.Canvas(parent, bg=self.bg, highlightthickness=0, height=300)
        canvas.pack(fill="x")
        detail = label(self, parent, size="small", wraplength=710)
        detail.pack(fill="x", pady=(16, 12))
        label(self, parent, CEILING_MAP["orientation"] + " " + CEILING_MAP["note"], "small", True, wraplength=710).pack(fill="x")
        self.map_canvas = canvas
        self.map_hits = []
        selected_reference = None
        columns, rows = CEILING_MAP["grid"]["columns"], CEILING_MAP["grid"]["rows"]

        def geometry():
            cell = min((canvas.winfo_width()-46)/columns, (canvas.winfo_height()-48)/rows)
            return 32, 24, cell

        def draw(event=None):
            canvas.delete("all")
            self.map_hits = []
            left, top, cell = geometry()
            if cell <= 0:
                return
            bottom = top + rows*cell
            for col in range(columns+1):
                x = left+col*cell
                canvas.create_line(x, top, x, bottom, fill=self.border)
                if col < columns:
                    canvas.create_text(x+cell/2, bottom+16, text="R%d" % (col+1), font=font("small"), fill=self.muted)
            for row in range(rows+1):
                y = bottom-row*cell
                canvas.create_line(left, y, left+columns*cell, y, fill=self.border)
                if row < rows:
                    canvas.create_text(left-18, y-cell/2, text="C%d" % (row+1), font=font("small"), fill=self.muted)
            def xy(p):
                return left+(p["cell"][0]-1+p["u"])*cell, bottom-(p["cell"][1]-1+p["v"])*cell
            for fixture in CEILING_MAP["fixtures"]:
                for point in fixture["positions"]:
                    x, y = xy(point)
                    half = cell*.3
                    if fixture["kind"] == "troffer":
                        canvas.create_rectangle(x-half, y-half, x+half, y+half, fill=self.control, outline="")
                    elif fixture["kind"] == "hvac":
                        canvas.create_rectangle(x-half*.7, y-half*.7, x+half*.7, y+half*.7, outline=self.muted)
                        for offset in (-half*.3, half*.3):
                            canvas.create_line(x-half*.5, y+offset, x+half*.5, y+offset, fill=self.muted)
                    else:
                        canvas.create_line(x-4, y-4, x+4, y+4, fill=self.muted)
                        canvas.create_line(x-4, y+4, x+4, y-4, fill=self.muted)
            for point in family["positions"]:
                x, y = xy(point)
                ref = point["reference_id"]
                # A 44 × 44 hit box per marker, including edge markers.
                hx, hy = round(x), round(y)
                self.map_hits.append((hx-22, hy-22, hx+22, hy+22, point))
                radius = 10 if ref == selected_reference else 6
                canvas.create_oval(x-radius, y-radius, x+radius, y+radius,
                                   fill=family["colours"][self.theme], outline=self.ink if ref == selected_reference else "", width=S["line"])

        def choose(value):
            nonlocal family, selected_reference
            self.map_family = value
            family = next(f for f in families if f["id"] == value)
            selected_reference = None
            segment.select(value)
            detail.config(text=family["label"] + " · Tap a marker to see its cell and reference.\n" + family["description"])
            draw()

        def inspect(event):
            nonlocal selected_reference
            candidates = [hit for hit in self.map_hits if hit[0] <= event.x <= hit[2] and hit[1] <= event.y <= hit[3]]
            if not candidates:
                return
            hit = min(candidates, key=lambda h: (event.x-(h[0]+22))**2 + (event.y-(h[1]+22))**2)
            point = hit[4]
            selected_reference = point["reference_id"]
            detail.config(text="%s · R%d C%d · reference %s\n%s" % (family["label"], *point["cell"], selected_reference, family["description"]))
            draw()

        canvas.bind("<Configure>", draw)
        canvas.bind("<ButtonRelease-1>", inspect)
        choose(selected)
