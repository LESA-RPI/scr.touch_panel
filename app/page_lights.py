"""White light, scenes, programmes and the eight channel controls."""
import tkinter as tk
from room_controls import LIGHTING_TABS, SCENES, GRADIENT, PROGRAMMES
from scr_touch_panel_lights import PRESETS, setter_words, GRADIENT as GRADIENT_MIXES
from panel_common import CHANNELS, CHANNEL_COLOURS
from touch_slider import TouchSlider
from ui_widgets import S, Card, Button, Segmented, ValueLabel, label, slot, font


def acquired_controls(response):
    """Only a uniform acquired drive can seed room-wide channel controls."""
    values = None
    baseline = response.get("baseline")
    if baseline in PRESETS:
        values = list(PRESETS[baseline])
    else:
        fixtures = response.get("fixture_words", [])
        words = response.get("words")
        if fixtures:
            words = fixtures[0][1] if all(item[1] == fixtures[0][1] for item in fixtures) else None
        if isinstance(words, list) and len(words) == 8 and all(type(v) is int and 0 <= v <= 65535 for v in words):
            # The adapter rounds drive percentages to words. Admit only exact mixes.
            candidate = [round(v * 100 / 65535) for v in words]
            if tuple(words) == setter_words(candidate):
                values = candidate
    cct, level = response.get("cct"), response.get("intensity")
    white = (cct, level) if (type(cct) is int and 1600 <= cct <= 10000
                            and type(level) is int and 0 <= level <= 1900) else None
    return values, white


class LightsPage:
    def choose_lighting_tab(self, tab):
        if tab in dict((key, title) for title, key in LIGHTING_TABS):
            self.lighting_tab = tab
            self.open_lighting()

    def lighting_contents(self):
        Segmented(self, self.body, LIGHTING_TABS, self.lighting_tab,
                  self.choose_lighting_tab).pack(fill="x", pady=(0, S["space"]))
        footer = tk.Frame(self.body, bg=self.bg)
        footer.pack(side="bottom", fill="x")
        tk.Frame(footer, bg=self.border, height=S["line"]).pack(fill="x", pady=(0, 16))
        self.readback_label(footer, small=True).pack(fill="x")
        if self.lighting_tab == "white":
            self.white_slider("Colour temperature", self.cct, 1600, 10000, 100, "K")
            self.white_slider("Light level", self.intensity, 0, 1900, 50, "of 1,900")
            row = tk.Frame(self.body, bg=self.bg, height=S["tap"])
            row.pack(fill="x")
            row.pack_propagate(False)
            button = Button(self, row, "Apply Warm white", lambda: self.previous_on(), "primary")
            button.pack(side="left", fill="y")
            self.light_buttons.append(button)
            label(self, row, "3,500 K at level 1,000.\nSliders apply when you let go.", "small", True).pack(side="left", padx=S["space"])
            self.mix_note(self.body, "white")
        elif self.lighting_tab == "scenes":
            grid = tk.Frame(self.body, bg=self.bg)
            grid.pack(fill="x")
            for index, scene in enumerate(SCENES + (GRADIENT,)):
                grid.columnconfigure(index % 2, weight=1, uniform="scene")
                card = tk.Frame(grid, bg=self.bg, height=196)
                card.grid(row=index // 2, column=index % 2, sticky="nsew",
                          padx=(0, 24) if index % 2 == 0 else 0, pady=(0, 24))
                card.grid_propagate(False)
                name = scene["id"]
                button = Button(self, card, name, lambda n=name: self.preset(n))
                button.place(x=0, y=0, relwidth=1, relheight=1)
                button._gradient = name == "Gradient"
                button.config(anchor="nw", padx=24, pady=16, font=font("title"))
                self.light_buttons.append(button)
                self.scene_buttons.append((button, name))
                # Labels and bars forward native touches to the one scene command.
                detail = label(self, card, scene["detail"], "small", True, wraplength=440)
                detail.place(x=24, y=58)
                current = label(self, card, "", "small")
                current.place(relx=1, x=-24, y=22, anchor="ne")
                button._current = current
                bars = tk.Canvas(card, bg=self.bg, height=72, highlightthickness=0)
                bars.place(x=24, y=102, relwidth=1, width=-48)
                mix = PRESETS.get(name) or tuple(sum(values[i] for values in GRADIENT_MIXES.values()) / len(GRADIENT_MIXES) for i in range(8))
                def draw(event, canvas=bars, values=mix):
                    canvas.delete("all")
                    w = canvas.winfo_width() / 8
                    for i, value in enumerate(values):
                        canvas.create_rectangle(i*w, 72-max(4, value*.72), (i+1)*w-6, 72,
                                                fill=CHANNEL_COLOURS[i], outline="")
                bars.bind("<Configure>", draw)
                for child in (detail, current, bars):
                    child.bind("<ButtonRelease-1>", lambda e, b=button: b.invoke())
            label(self, self.body, "Tap a scene to apply it to the whole room. The bars show its eight-channel mixture.", "small", True).pack(anchor="w")
        elif self.lighting_tab == "programmes":
            if not self.light_capabilities.get("programmes"):
                label(self, self.body, "Programmes are not available on this panel.", muted=True).pack(anchor="w")
                return
            grid = tk.Frame(self.body, bg=self.bg)
            grid.pack(fill="x")
            for column, programme in enumerate(PROGRAMMES):
                grid.columnconfigure(column, weight=1, uniform="programme")
                card = Card(self, grid)
                card.grid(row=0, column=column, sticky="nsew", padx=(0, 24) if column == 0 else 0)
                label(self, card, programme["label"], "title").pack(anchor="w", padx=24, pady=(24, 12))
                label(self, card, programme["detail"], "small", True, wraplength=420).pack(fill="x", padx=24)
                button = slot(self, card, "Start " + programme["label"],
                              lambda n=programme["id"]: self.programme_command(n), "primary", padx=24, pady=24)
                button._programme = programme["id"]
                self.programme_buttons.append(button)
            button = slot(self, self.body, "Stop programmes", lambda: self.programme_command("Stop"), pady=24)
            button._programme = "Stop"
            self.programme_buttons.append(button)
            label(self, self.body, "Any other light change stops a running programme.", "small", True).pack(anchor="w")
        else:
            card = Card(self, self.body)
            card.pack(fill="x")
            for index, (name, colour, variable) in enumerate(zip(CHANNELS, CHANNEL_COLOURS, self.channel_values)):
                card.columnconfigure(index // 4, weight=1, uniform="channels")
                row = tk.Frame(card, bg=self.surface, height=100)
                row.grid(row=index % 4, column=index // 4, sticky="ew", padx=24, pady=4)
                row.pack_propagate(False)
                head = tk.Frame(row, bg=self.surface)
                head.pack(fill="x")
                tk.Frame(head, bg=colour, width=12, height=12).pack(side="left", padx=(0, 10))
                label(self, head, name).pack(side="left")
                ValueLabel(self, head, variable, "small", "%").pack(side="right")
                scale = self.new_slider(row, variable, 0, 100, 1, "channels")
                scale.pack(fill="x", pady=(8, 0))
            label(self, self.body, "Changes apply when you let go. Values are drive levels, not measured brightness.", "small", True).pack(anchor="w", pady=16)
            self.mix_note(self.body, "channels")

    def new_slider(self, parent, variable, low, high, step, action):
        scale = TouchSlider(parent, variable, low, high, step, "horizontal",
                            parent.cget("bg"), self.control, self.accent, self.border, self.ink)
        scale._action = action
        self.bind_slider(scale, action)
        self.light_buttons.append(scale)
        return scale

    def white_slider(self, title, variable, low, high, step, unit):
        card = Card(self, self.body, height=150)
        card.pack(fill="x", pady=(0, S["space"]))
        card.pack_propagate(False)
        caption = tk.Frame(card, bg=self.surface, width=230)
        caption.pack(side="left", fill="y", padx=24, pady=24)
        caption.pack_propagate(False)
        label(self, caption, title, "small", True).pack(anchor="w")
        row = tk.Frame(caption, bg=self.surface)
        row.pack(fill="x")
        ValueLabel(self, row, variable).pack(side="left")
        label(self, row, unit, "small", True).pack(side="left", padx=8, anchor="s", pady=6)
        track = tk.Frame(card, bg=self.surface)
        track.pack(side="left", fill="both", expand=True, padx=(0, 24), pady=24)
        self.new_slider(track, variable, low, high, step, "cct").pack(fill="x", pady=(10, 8))
        label(self, track, "1,600 K warm" if unit == "K" else "0", "small", True).pack(side="left")
        label(self, track, "10,000 K cool" if unit == "K" else "1,900", "small", True).pack(side="right")

    def mix_note(self, parent, kind):
        note = label(self, parent, size="small", muted=True, wraplength=1000)
        note.pack(fill="x", pady=12)
        note._mix_kind = kind
        self.mix_notes.append(note)
        self.update_mix_notes()

    def seed_controls(self, response, request=None):
        channels, white = acquired_controls(response)
        if request and request.get("action") == "cct" and response.get("state") == "completed":
            args = request["arguments"]
            white = (args["cct"], args["intensity"])
        self.controls_known = {"channels": channels is not None, "white": white is not None}
        for var, value in zip(self.channel_values, channels or [0] * 8):
            var.set(value)
        self.cct.set(white[0] if white else 5800)
        self.intensity.set(white[1] if white else 0)
        self.update_mix_notes()

    def update_mix_notes(self):
        for note in getattr(self, "mix_notes", []):
            if note.winfo_exists():
                known = getattr(self, "controls_known", {}).get(note._mix_kind, False)
                note.config(text="Controls show the confirmed room settings." if known else
                            "This room mix cannot be shown by these controls. A change applies a new mix.")
