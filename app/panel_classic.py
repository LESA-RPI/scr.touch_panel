"""Familiar controls rendered by the same Tk owner as the Beta layout."""

import tkinter as tk

from touch_slider import TouchSlider


class PanelClassic:
    def classic_view(self):
        self.classic_buttons, self.classic_sliders = {}, []
        heading = tk.Frame(self.body, bg=self.bg)
        heading.pack(fill="x", pady=(8, 4))
        self.label(heading, "Classic controls", 25).pack(side="left")
        self.label(heading, "Same room controls · familiar layout", 16, True).pack(
            side="right"
        )
        self.feedback_card(self.body)
        self.light_feedback_card.pack_configure(side="bottom", pady=(10, 4))
        row = tk.Frame(self.body, bg=self.bg)
        row.pack(fill="both", expand=True, pady=(8, 0))
        row.columnconfigure(0, weight=34, uniform="classic")
        row.columnconfigure(1, weight=66, uniform="classic")
        row.rowconfigure(0, weight=1)
        sliders = tk.Frame(row, bg=self.bg)
        sliders.grid(row=0, column=0, sticky="nsew", padx=(0, 20))
        sliders.rowconfigure(0, weight=1)
        for index, (title, variable, high, low, step, unit) in enumerate(
            (
                ("Colour temperature", self.cct, 10000, 1600, 100, "K"),
                ("Light level", self.intensity, 1900, 0, 25, "controller units"),
            )
        ):
            sliders.columnconfigure(index, weight=1, uniform="classic-sliders")
            group = tk.Frame(sliders, bg=self.surface)
            group.grid(row=0, column=index, sticky="nsew", padx=(0, 10))
            title_label = self.label(group, title, 16)
            title_label.config(anchor="center", height=2)
            self.wrap_label(title_label).pack(fill="x", padx=8, pady=(8, 0))
            number = self.label(group, size=26)
            number.config(textvariable=variable, anchor="center")
            number.pack(fill="x", pady=(4, 0))
            unit_label = self.label(group, unit, 12, True)
            unit_label.config(anchor="center")
            unit_label.pack(fill="x")
            self.label(group, str(high), 12, True).pack(pady=(6, 0))
            scale = TouchSlider(
                group, variable=variable, from_=high, to=low, resolution=step,
                orient="vertical", background=self.surface, track=self.control,
                accent=self.accent, border=self.border, ink=self.ink, length=240,
            )
            scale._action = "cct"
            scale.pack(fill="both", expand=True, padx=12)
            self.label(group, str(low), 12, True).pack(pady=(0, 8))
            self.bind_slider(scale, "cct")
            self.light_buttons.append(scale)
            self.classic_sliders.append(scale)
        controls = tk.Frame(row, bg=self.bg)
        controls.grid(row=0, column=1, sticky="nsew")
        actions = (
            ("on", "Lights on", self.lights_on, "light"),
            ("off", "Lights off", lambda: self.preset("Off"), "light"),
            ("stop", "Stop programmes", lambda: self.programme_command("Stop"), "programme"),
            ("gradient", "Gradient", lambda: self.preset("Gradient"), "light"),
            ("sun", "Sun", lambda: self.programme_command("Sun"), "programme"),
            ("circ", "Circ", lambda: self.programme_command("Circ"), "programme"),
            ("sat", "Sat", lambda: self.preset("Sat"), "light"),
            ("fid", "Fid", lambda: self.preset("Fid"), "light"),
            ("dul", "Dul", lambda: self.preset("Dul"), "light"),
            ("lift", "Lift blinds", lambda: self.blind_command("lift"), "blind"),
            ("open", "Open slats", lambda: self.blind_command("open"), "blind"),
            ("close", "Close & lower", lambda: self.blind_command("close"), "blind"),
        )
        for index, (key, title, action, kind) in enumerate(actions):
            line, column = divmod(index, 3)
            controls.rowconfigure(line, weight=1, uniform="classic-buttons")
            controls.columnconfigure(column, weight=1, uniform="classic-buttons")
            button = self.button(controls, title, action)
            button.config(font=(self.font_family, 19), wraplength=230, padx=8, pady=10, compound="left")
            button.grid(row=line, column=column, sticky="nsew", padx=(0, 10), pady=(0, 10))
            self.classic_buttons[key] = button
            if kind == "programme":
                button._programme = "Stop" if key == "stop" else title
                self.programme_buttons.append(button)
            elif kind == "blind":
                self.blind_buttons.append(button)
            else:
                self.light_buttons.append(button)
                if key in ("on", "off"):
                    self.home_power_buttons.append((button, key, title))
                else:
                    button._scene_label = title
                    button._gradient = key == "gradient"
                    self.scene_buttons.append((button, title))
        self.update_light_buttons()
