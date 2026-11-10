"""Everyday room controls and local outdoor weather."""
import tkinter as tk
from room_controls import BLIND_ACTIONS
from ui_widgets import S, Button, label, font


class HomePage:
    def room_view(self):
        self.body.columnconfigure(0, weight=54, uniform="home")
        self.body.columnconfigure(2, weight=46, uniform="home")
        self.body.rowconfigure(0, weight=1)
        left = tk.Frame(self.body, bg=self.bg)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, S["space"] * 2))
        tk.Frame(self.body, bg=self.border, width=S["line"]).grid(row=0, column=1, sticky="ns")
        right = tk.Frame(self.body, bg=self.bg)
        right.grid(row=0, column=2, sticky="nsew", padx=(S["space"] * 2, 0))
        label(self, left, "Lights", "title").pack(anchor="w", pady=(0, 16))
        pair = tk.Frame(left, bg=self.bg, height=166)
        pair.pack(fill="x")
        pair.grid_propagate(False)
        pair.rowconfigure(0, weight=1)
        for column, (title, power, action) in enumerate((
                ("Lights on", "on", lambda: self.lights_on()),
                ("Lights off", "off", lambda: self.preset("Off")))):
            pair.columnconfigure(column, weight=1, uniform="power")
            button = Button(self, pair, title, action, "primary")
            button.config(image=self.icon(power, self.bg, 38), compound="top", font=font("title", True))
            button.grid(row=0, column=column, sticky="nsew", padx=(0, 16) if column == 0 else 0)
            self.light_buttons.append(button)
            self.home_power_buttons.append((button, power, title))
        self.readback_label(left).pack(fill="x", pady=(16, 24))
        link = Button(self, left, "White light, scenes and channels  ›", lambda: self.open_lighting(), "link")
        link.config(anchor="w", padx=0, font=font("text", True))
        link.pack(fill="x", ipady=14)
        self.home_blinds = tk.Frame(left, bg=self.bg)
        self.home_blinds.pack(fill="x", pady=(40, 0))
        self.home_blind_key = None
        self.refresh_home_blinds()
        label(self, right, "Troy, NY", "small", True).pack(anchor="w")
        clock_row = tk.Frame(right, bg=self.bg)
        clock_row.pack(fill="x", pady=(8, 0))
        clock = label(self, clock_row, size="display")
        clock.config(textvariable=self.idle_digits)
        clock.pack(side="left")
        period = label(self, clock_row, size="heading", muted=True)
        period.config(textvariable=self.idle_period)
        period.pack(side="left", anchor="s", padx=(8, 0), pady=(0, 18))
        date = label(self, right, size="title")
        date.config(textvariable=self.visitor_date)
        date.pack(anchor="w", pady=(0, S["space"]))
        self.weather_contents(right)

    def refresh_home_blinds(self):
        host = getattr(self, "home_blinds", None)
        if host is None or not host.winfo_exists():
            return
        state = self.blind_state()
        key = (self.blinds_display, state["enabled"], state["connected"])
        if self.home_blind_key == key:
            return
        self.home_blind_key = key
        for child in host.winfo_children():
            child.destroy()
        self.blind_buttons = []
        if self.blinds_display == "hidden":
            return
        label(self, host, "Blinds", "title").pack(anchor="w", pady=(0, 16))
        if state["enabled"] and state["connected"]:
            row = tk.Frame(host, bg=self.bg, height=S["tap"])
            row.pack(fill="x")
            row.grid_propagate(False)
            row.rowconfigure(0, weight=1)
            for index, (name, title) in enumerate(BLIND_ACTIONS):
                row.columnconfigure(index, weight=1, uniform="blinds")
                button = Button(self, row, title, lambda n=name: self.blind_command(n))
                button.config(padx=4, font=font("small"))
                button.grid(row=0, column=index, sticky="nsew", padx=(0, 8) if index < 2 else 0)
                self.blind_buttons.append(button)
        else:
            text = ("Blinds are locked so they are not moved by accident.\nUnlock in Settings ›"
                    if not state["enabled"] else "Blind controls are not connected right now.")
            button = Button(self, host, text, lambda: self.open_advanced("screen"), "link")
            button.config(wraplength=485, justify="left", anchor="w", padx=0)
            button.pack(fill="x", ipady=14)
