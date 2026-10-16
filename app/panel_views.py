"""Room, lighting and settings views for the Tk owner."""

from room_controls import BLIND_ACTIONS
from panel_version import BUILD_COMMIT
from room_controls import LIGHTING_TABS
from room_controls import UNAVAILABLE_LIGHTING, BLINDS_UNAVAILABLE
from room_controls import SCENES, WEBSITE_URL
from touch_slider import TouchSlider
from panel_version import VERSION
import os
import time
import tkinter as tk
from panel_common import ADVANCED_PAGES, CHANNELS, CHANNEL_COLOURS


class PanelViews:
    def room_view(self):
        self.blind_buttons = []
        row = tk.Frame(self.body, bg=self.bg)
        row.pack(fill="both", expand=True, pady=(22, 10))
        row.columnconfigure(0, weight=48, uniform="home")
        row.columnconfigure(1, weight=52, uniform="home")
        row.rowconfigure(0, weight=1)
        left, right = tk.Frame(row, bg=self.bg), tk.Frame(row, bg=self.bg)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 28))
        right.grid(row=0, column=1, sticky="nsew", padx=(28, 0))
        controls = tk.Frame(left, bg=self.bg)
        controls.pack(fill="x", pady=(20, 12))
        controls.columnconfigure(1, minsize=16)
        groups = (
            ("Lights", "Blinds") if self.blinds_display == "disabled" else ("Lights",)
        )
        for index, title in enumerate(groups):
            controls.columnconfigure(index * 2, weight=1, uniform="essentials")
            group = tk.Frame(controls, bg=self.bg)
            group.grid(row=0, column=index * 2, sticky="nsew")
            self.label(group, title, 25).pack(anchor="w")
            self.label(group, "Whole room", 16, True).pack(anchor="w", pady=(2, 16))
            actions = (
                [
                    ("Lights on", self.lights_on, False),
                    ("Lights off", lambda: self.preset("Off"), False),
                ]
                if index == 0
                else [
                    (label, lambda name=name: self.blind_command(name), False)
                    for name, label in BLIND_ACTIONS
                ]
            )
            for title, action, accent in actions:
                button = self.row_buttons(
                    group, [(title, action, accent)], height=104 if index == 0 else 65
                )[0]
                button.config(font=(self.font_family, 22 if index == 0 else 19))
                if index == 0:
                    button.config(
                        image=self.icon(
                            "on" if title == "Lights on" else "off",
                            self.selected_ink if accent else self.icon_colour,
                        ),
                        compound="left",
                    )
                    self.light_buttons.append(button)
                    self.home_power_buttons.append(
                        (button, "on" if title == "Lights on" else "off", title)
                    )
                else:
                    self.blind_buttons.append(button)
            caption = self.label(
                group,
                (
                    "Standard room lighting"
                    if index == 0
                    else self.blind_state()["detail"]
                ),
                17,
                True,
            )
            if index:
                self.blind_status_label = caption
            self.wrap_label(caption).pack(fill="x", pady=(8, 0))
        self.feedback_card(left)
        self.label(
            right, getattr(self.args, "weather_name", "Local time"), 18, True
        ).pack(anchor="w")
        clock = self.label(right, size=64)
        clock.config(textvariable=self.visitor_time)
        clock.pack(anchor="w", pady=(12, 0))
        date = self.label(right, size=23)
        date.config(textvariable=self.visitor_date)
        self.wrap_label(date).pack(fill="x", pady=(0, 6))
        self.weather_contents(right, compact=True)
        self.update_light_buttons()

    def advanced_view(self):
        shell = self.body
        self.advanced_shell = shell
        self.advanced_sidebar_buttons = []
        self.advanced_detail = None
        self.advanced_detail_key = None
        sidebar = tk.Frame(shell, bg=self.bg, width=280)
        sidebar.pack(side="left", fill="y", padx=(0, 28), pady=(10, 0))
        sidebar.pack_propagate(False)
        sidebar.grid_propagate(False)
        sidebar.columnconfigure(0, weight=1)
        self.label(sidebar, "Room tools", 25).grid(
            row=0, column=0, sticky="w", pady=(0, 16)
        )
        for index, (label, page) in enumerate(ADVANCED_PAGES, 1):
            sidebar.rowconfigure(index, weight=1, uniform="tools")
            button = self.button(
                sidebar,
                label,
                lambda page=page: self.open_advanced(page),
                self.advanced_page == page,
            )
            button.config(
                font=(self.font_family, 16),
                anchor="w",
                padx=12,
                pady=8,
                image=self.icon(
                    "date" if page == "clock" else page,
                    self.selected_ink if self.advanced_page == page else self.ink,
                    24,
                ),
                compound="left",
            )
            button.grid(row=index, column=0, sticky="nsew", pady=(0, 10))
            self.advanced_sidebar_buttons.append((button, page))
        self.rebuild_advanced_detail()

    def rebuild_advanced_detail(self):
        """Keep the sidebar mapped while replacing only the selected tool."""
        shell = self.body
        previous = self.advanced_detail
        old_key = self.advanced_detail_key
        self.remember_detail()
        for button, page in self.advanced_sidebar_buttons:
            selected = self.advanced_page == page
            colour = self.accent if selected else self.control
            if button.cget("bg") != colour:
                button.config(
                    bg=colour,
                    fg=self.selected_ink if selected else self.ink,
                    highlightbackground=self.accent if selected else self.border,
                    activebackground=(
                        self.accent_pressed if selected else self.pressed_colour()
                    ),
                    activeforeground=self.selected_ink if selected else self.ink,
                    image=self.icon(
                        "date" if page == "clock" else page,
                        self.selected_ink if selected else self.ink,
                        24,
                    ),
                )
        key = self.lighting_tab if self.advanced_page == "lighting" else None
        if key is not None and key == old_key:
            self.detail_cache.pop(key, None)
            self.refresh_page()
            return
        cached = (
            self.detail_cache.pop(key, None)
            if key is not None and key != old_key
            else None
        )
        if cached:
            detail, references = cached
            self.__dict__.update(references)
            self.refresh_page()
            if previous is not None:
                previous.pack_forget()
            self.root.focus_set()
            detail.pack(side="left", fill="both", expand=True, pady=(10, 0))
            self.advanced_detail, self.advanced_detail_key = detail, key
            if old_key is None and previous is not None:
                previous.destroy()
            return
        self.clear_page_references()
        detail = tk.Frame(shell, bg=self.bg)
        self.body = detail
        try:
            page = self.advanced_page
            if page == "lighting":
                self.lighting_contents()
            elif page == "experiment":
                self.experiment_view()
            elif page == "system":
                self.system_contents()
            elif page == "about":
                self.about_contents(detail)
            else:
                self.settings_category = page
                self.settings_contents(detail)
                saved = self.label(detail, size=15, muted=True)
                saved.config(textvariable=self.preference_text)
                self.wrap_label(saved).pack(fill="x", pady=(8, 0))
        finally:
            self.body = shell
        if previous is not None:
            previous.pack_forget()
        self.root.focus_set()
        detail.pack(side="left", fill="both", expand=True, pady=(10, 0))
        self.advanced_detail = detail
        self.advanced_detail_key = key
        if previous is not None and (old_key is None or old_key == key):
            self.detail_cache.pop(old_key, None)
            previous.destroy()

    def open_advanced(self, page=None):
        page = page or self.last_advanced_page
        tab = None
        if page in ("white", "scenes", "programmes", "channels"):
            tab = "channels" if page == "scenes" else page
            page = "lighting"
        if page not in dict((key, label) for label, key in ADVANCED_PAGES):
            return
        target = (
            "room"
            if page == "lighting"
            else (
                "experiment"
                if page == "experiment"
                else (
                    "health"
                    if page == "system"
                    else "about" if page == "about" else "settings"
                )
            )
        )
        if self.release_target or self.closing:
            return
        if (
            getattr(self, "mode", None) == target
            and getattr(self, "advanced_page", None) == page
        ):
            if tab is not None and tab != self.lighting_tab:
                self.choose_lighting_tab(tab)
            return
        if tab is not None:
            self.lighting_tab = tab
        self.last_advanced_page = page
        self.show(target, advanced_page=page)

    def open_home(self):
        if self.mode != "room" or getattr(self, "advanced_page", None):
            self.show("room")

    def open_lighting(self):
        self.open_advanced("white")

    def choose_lighting_tab(self, tab):
        if tab not in dict((key, label) for label, key in LIGHTING_TABS):
            return
        self.cancel_intent()
        self.lighting_tab = tab
        self.rebuild_advanced_detail()

    def lighting_contents(self):
        self.label(self.body, "Lighting", 27).pack(anchor="w")
        tabs = self.row_buttons(
            self.body,
            [
                (
                    label,
                    lambda key=key: self.choose_lighting_tab(key),
                    self.lighting_tab == key,
                )
                for label, key in LIGHTING_TABS
            ],
            height=54,
        )
        for button in tabs:
            button.config(font=(self.font_family, 17))
        if self.lighting_tab == "white":
            self.label(
                self.body, "Selected values apply after your touch settles.", 16, True
            ).pack(anchor="w", pady=(2, 8))
            self.slider_group(
                self.body,
                "Colour temperature",
                self.cct,
                1600,
                10000,
                100,
                "K",
                compact=True,
            )
            self.slider_group(
                self.body,
                "Light level",
                self.intensity,
                0,
                1900,
                25,
                "controller units",
                compact=True,
            )
            self.feedback_card(self.body)
        elif self.lighting_tab == "scenes":
            self.label(
                self.body, "Original scene names and mixtures from Legacy.", 16, True
            ).pack(anchor="w", pady=(2, 8))
            grid = tk.Frame(self.body, bg=self.bg)
            grid.pack(fill="x")
            for index, scene in enumerate(SCENES):
                grid.columnconfigure(index % 2, weight=1, uniform="scene")
                card = tk.Frame(
                    grid,
                    bg=self.surface,
                    highlightthickness=1,
                    highlightbackground=self.border,
                )
                card.grid(
                    row=index // 2,
                    column=index % 2,
                    sticky="nsew",
                    padx=(0, 10) if index % 2 == 0 else 0,
                    pady=(0, 10),
                )
                self.label(card, scene["label"], 21).pack(
                    anchor="w", padx=16, pady=(8, 0)
                )
                note = self.label(card, scene["detail"], 15, True)
                self.wrap_label(note).pack(fill="x", padx=16, pady=(0, 6))
                button = self.button(
                    card, "Apply scene", lambda name=scene["id"]: self.preset(name)
                )
                button.config(font=(self.font_family, 15), pady=8)
                button.pack(fill="x", padx=16, pady=(0, 10), ipady=3)
                button._scene_label = "Apply scene"
                self.light_buttons.append(button)
                self.scene_buttons.append((button, scene["id"]))
            self.wrap_label(self.label(self.body, UNAVAILABLE_LIGHTING, 16, True)).pack(
                fill="x", pady=(4, 8)
            )
            self.feedback_card(self.body)
        elif self.lighting_tab == "programmes":
            self.wrap_label(self.label(self.body, UNAVAILABLE_LIGHTING, 18, True)).pack(
                fill="x", pady=16
            )
        else:
            self.channels_view(embedded=True)
        self.update_light_buttons()

    def slider_group(
        self, parent, title, variable, low, high, step, unit, compact=False
    ):
        group = tk.Frame(
            parent,
            bg=self.surface,
            highlightbackground=self.border,
            highlightthickness=1,
        )
        group.pack(fill="x", pady=(0, 8))
        if not compact:
            self.label(group, title, 18).pack(anchor="w", padx=20, pady=(6, 0))
        row = tk.Frame(group, bg=self.surface, height=56)
        row.pack(fill="x", padx=20, pady=(14, 0) if compact else (8, 0))
        row.pack_propagate(False)
        minus_area, plus_area = tk.Frame(row, width=64), tk.Frame(row, width=64)
        plus_area.pack(side="right", fill="y")
        minus_area.pack(side="right", fill="y", padx=(8, 8))
        minus_area.pack_propagate(False)
        plus_area.pack_propagate(False)
        minus = self.button(
            minus_area, "-", lambda: self.step_slider(variable, low, high, -step)
        )
        plus = self.button(
            plus_area, "+", lambda: self.step_slider(variable, low, high, step)
        )
        for button in (minus, plus):
            button.config(pady=8)
        minus.pack(fill="both", expand=True)
        plus.pack(fill="both", expand=True)
        if compact:
            self.label(row, title, 18).pack(side="left", padx=(0, 20))
        value = self.label(row, size=30 if compact else 33)
        value.config(textvariable=variable)
        value.pack(side="left")
        self.label(row, unit, 16, True).pack(side="left", padx=10, anchor="s", pady=12)
        scale = TouchSlider(
            group,
            variable=variable,
            from_=low,
            to=high,
            resolution=step,
            orient="horizontal",
            background=self.surface,
            track=self.control,
            accent=self.accent,
            border=self.border,
            ink=self.ink,
        )
        scale.pack(fill="x", padx=20, pady=(4, 0))
        limits = tk.Frame(group, bg=self.surface)
        limits.pack(fill="x", padx=20, pady=(4, 8))
        self.label(limits, "Min {:,} {}".format(low, unit), 13, True).pack(side="left")
        self.label(limits, "Max {:,} {}".format(high, unit), 13, True).pack(
            side="right"
        )
        self.bind_slider(scale, "cct")
        self.light_buttons.extend([minus, plus, scale])

    def channel_view(self):
        self.open_advanced("scenes")

    def channels_view(self, embedded=False):
        if not embedded:
            self.label(self.body, "Lighting channels", 27).pack(anchor="w")
        self.label(
            self.body, "Adjust the eight room-wide channel percentages.", 16, True
        ).pack(anchor="w", pady=(4, 8))
        editor = tk.Frame(self.body, bg=self.bg)
        editor.pack(fill="x", pady=14)
        for index, (name, value) in enumerate(zip(CHANNELS, self.channel_values)):
            editor.columnconfigure(index, weight=1, uniform="channel")
            cell = tk.Frame(editor, bg=self.bg)
            cell.grid(row=0, column=index, sticky="nsew", padx=4)
            self.label(cell, name, 15).pack()
            tk.Frame(cell, height=8, bg=CHANNEL_COLOURS[index]).pack(fill="x", pady=8)
            number = self.label(cell, size=16)
            number.config(textvariable=value)
            number.pack()
            scale = TouchSlider(
                cell,
                variable=value,
                from_=100,
                to=0,
                resolution=1,
                orient="vertical",
                background=self.bg,
                track=self.control,
                accent=self.accent,
                border=self.border,
                ink=self.ink,
                length=200,
            )
            scale.pack(fill="both", expand=True)
            self.bind_slider(scale, "channels")
            self.light_buttons.append(scale)
        self.feedback_card(self.body)
        self.update_light_buttons()

    def experiment_view(self):
        self.label(self.body, "Experiment mode", 27).pack(anchor="w")
        title = self.label(self.body, self.profile["title"], 17, True)
        self.wrap_label(title).pack(fill="x")
        self.label(
            self.body,
            "Recorder not connected · instructions and panel annotations only",
            17,
            True,
        ).pack(anchor="w", pady=(6, 8))
        area = tk.Frame(self.body, bg=self.surface, height=184)
        area.pack(fill="x", pady=6)
        area.pack_propagate(False)
        self.stage_label = self.label(area, size=24)
        self.stage_label.config(height=2)
        self.wrap_label(self.stage_label).pack(fill="x", padx=22, pady=(8, 2))
        status = tk.Frame(area, bg=self.surface, height=50)
        status.pack(fill="x", padx=22)
        status.pack_propagate(False)
        self.run_label = self.label(status, size=17, muted=True)
        self.run_label.pack(side="left")
        self.timer_label = self.label(status, size=26)
        self.timer_label.pack(side="right")
        metadata = self.label(
            area, "Profile describes: " + self.profile["sensors"], 16, True
        )
        self.wrap_label(metadata).pack(fill="x", padx=22, pady=(0, 4))
        self.row_buttons(
            self.body,
            [
                ("Start instructions", self.start_preview, True),
                ("Pause", self.stop_preview, False),
            ],
            height=60,
        )
        self.row_buttons(
            self.body,
            [
                ("Previous instruction", self.previous_stage, False),
                ("Next instruction", self.next_stage, False),
            ],
            height=60,
        )
        self.row_buttons(
            self.body,
            [
                (label, lambda label=label: self.mark(label), False)
                for label in self.profile["annotations"]
            ],
        )
        annotation = self.label(self.body, size=16, muted=True)
        annotation.config(textvariable=self.annotation_text, height=2)
        self.wrap_label(annotation).pack(fill="x")
        self.update_session()

    def settings_contents(self, content):
        key = self.settings_category
        if key == "appearance":
            self.label(content, "Appearance", 25).pack(anchor="w", pady=(0, 6))
            self.label(content, "Choose how this panel looks.", 18, True).pack(
                anchor="w", pady=(0, 8)
            )
            self.row_buttons(
                content,
                [
                    (
                        name.title(),
                        lambda name=name: self.choose_theme(name),
                        self.theme_choice == name,
                    )
                    for name in ("light", "dark", "auto")
                ],
            )
            self.label(content, "Automatic schedule", 21).pack(anchor="w", pady=(10, 8))
            schedule = "Light from %02d:%02d · Dark from %02d:%02d" % (
                divmod(self.args.light_at, 60) + divmod(self.args.dark_at, 60)
            )
            self.label(content, schedule, 20).pack(anchor="w", pady=(0, 6))
            self.row_buttons(
                content,
                [
                    (
                        text,
                        lambda field=field, delta=delta: self.adjust_schedule(
                            field, delta
                        ),
                        False,
                    )
                    for text, field, delta in [
                        ("Light −1 h", "light_at", -60),
                        ("Light +1 h", "light_at", 60),
                        ("Dark −1 h", "dark_at", -60),
                        ("Dark +1 h", "dark_at", 60),
                    ]
                ],
            )
            note = self.label(
                content,
                "Auto waits for idle time. Experiment mode keeps its theme.",
                17,
                True,
            )
            self.wrap_label(note).pack(fill="x", pady=(8, 0))
            self.label(content, "Touch explanations", 21).pack(anchor="w", pady=(14, 4))
            self.row_buttons(
                content,
                [
                    ("Tips on", lambda: self.choose_tips(True), self.help_on),
                    ("Tips off", lambda: self.choose_tips(False), not self.help_on),
                ],
            )
        elif key == "clock":
            self.label(content, "Date & weather", 25).pack(anchor="w", pady=(0, 8))
            self.label(content, time.strftime("%A, %d %B %Y"), 23).pack(
                anchor="w", pady=(0, 6)
            )
            self.label(
                content, getattr(self.args, "timezone", "System timezone"), 18, True
            ).pack(anchor="w", pady=(0, 10))
            self.row_buttons(
                content,
                [
                    (
                        name + "-hour",
                        lambda name=name: self.choose_clock(name),
                        self.clock_24 == (name == "24"),
                    )
                    for name in ("12", "24")
                ],
            )
            self.label(content, "Weather temperature", 21).pack(anchor="w", pady=(6, 4))
            self.row_buttons(
                content,
                [
                    (
                        label,
                        lambda unit=unit: self.choose_temperature(unit),
                        self.temperature_unit == unit,
                    )
                    for label, unit in [("Celsius (°C)", "c"), ("Fahrenheit (°F)", "f")]
                ],
            )
            self.label(
                content, "Display units only. No room settings change.", 17, True
            ).pack(anchor="w", pady=8)
            source = self.label(content, size=16, muted=True)
            source.config(textvariable=self.weather_text, height=3)
            self.wrap_label(source).pack(fill="x", pady=(12, 0))
        elif key == "help":
            self.label(content, "Help & guidance", 25).pack(anchor="w", pady=(0, 14))
            note = self.label(
                content, "Tips explain controls in the bottom message area.", 18
            )
            self.wrap_label(note).pack(fill="x", pady=(0, 8))
            self.row_buttons(
                content,
                [
                    ("Tips on", lambda: self.choose_tips(True), self.help_on),
                    ("Tips off", lambda: self.choose_tips(False), not self.help_on),
                ],
            )
            note = self.label(
                content,
                "White-light colour: lower K is warmer; higher K is cooler.\n"
                "Light level: controller input, not measured brightness.\n"
                "Fid / Sat / Dul: saved eight-channel mixtures from Legacy.\n"
                "Selected values send automatically after your touch settles.\n"
                "Recent settings shows the last confirmed light settings.",
                18,
            )
            self.wrap_label(note).pack(fill="x", pady=(12, 8))
        elif key == "screen":
            self.label(content, "Screen & controls", 25).pack(anchor="w", pady=(0, 4))
            self.label(content, "Screen saver", 19).pack(anchor="w")
            self.row_buttons(
                content,
                [
                    (
                        label,
                        lambda seconds=seconds: self.choose_idle(seconds),
                        self.idle_timeout == seconds,
                    )
                    for label, seconds in [
                        ("Off", 0),
                        ("1 min", 60),
                        ("5 min", 300),
                        ("15 min", 900),
                    ]
                ],
                height=50,
            )
            self.label(
                content,
                "First touch opens Home. Pauses during experiments and commands.",
                14,
                True,
            ).pack(anchor="w", pady=(0, 6))
            self.label(content, "Display", 19).pack(anchor="w")
            self.row_buttons(
                content,
                [
                    ("Blank screen", lambda: self.show("black"), False),
                    ("Preview screen saver", lambda: self.show("visitor"), False),
                ],
                height=50,
            )
            self.label(
                content,
                "Blank keeps the backlight on. Hold 2 seconds to return.",
                14,
                True,
            ).pack(anchor="w", pady=(0, 6))
            self.label(content, "Blind controls", 19).pack(anchor="w")
            if self.blind_state()["connected"]:
                self.row_buttons(
                    content,
                    [
                        (
                            "Locked",
                            lambda: self.choose_blinds_enabled(False),
                            not self.blinds_enabled,
                        ),
                        (
                            "Unlocked",
                            lambda: self.choose_blinds_enabled(True),
                            self.blinds_enabled,
                        ),
                    ],
                    height=50,
                )
            self.wrap_label(
                self.label(
                    content,
                    (
                        BLINDS_UNAVAILABLE
                        if not self.blind_state()["connected"]
                        else self.blind_state()["reason"]
                    ),
                    14,
                    True,
                )
            ).pack(fill="x", pady=(0, 6))
            self.label(content, "Blinds on Home", 19).pack(anchor="w")
            self.row_buttons(
                content,
                [
                    (
                        "Show",
                        lambda: self.choose_blinds_display("disabled"),
                        self.blinds_display == "disabled",
                    ),
                    (
                        "Hide",
                        lambda: self.choose_blinds_display("hidden"),
                        self.blinds_display == "hidden",
                    ),
                ],
                height=50,
            )
        else:
            self.about_contents(content)

    def about_contents(self, parent):
        self.label(parent, "Smart Conference Room", 27).pack(anchor="w", pady=(0, 8))
        self.label(parent, "Touch panel · " + VERSION, 20, True).pack(
            anchor="w", pady=(0, 28)
        )
        if BUILD_COMMIT:
            self.label(parent, "Build " + BUILD_COMMIT, 15, True).pack(
                anchor="w", pady=(0, 16)
            )
        self.label(parent, "Built by Diyanko Bhowmik", 21).pack(
            anchor="w", pady=(0, 10)
        )
        note = self.label(
            parent,
            "Original contributors are credited in the repository history.",
            17,
            True,
        )
        self.wrap_label(note).pack(fill="x", pady=(0, 22))
        self.label(
            parent, "Source: github.com/LESA-RPI/scr.touch_panel", 18, True
        ).pack(anchor="w", pady=(0, 20))
        self.label(parent, "Icons: Lucide · lucide.dev", 17, True).pack(anchor="w")
        self.website_qr(parent)

    def website_qr(self, parent):
        """QR code for the room website, so visitors can open it on a phone."""
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "assets",
            "website-qr.png",
        )
        try:
            image = self.icon_cache.get("website-qr") or tk.PhotoImage(file=path)
        except tk.TclError:
            return  # Missing artwork only hides the code; About still works.
        self.icon_cache["website-qr"] = image
        card = tk.Frame(parent, bg=parent.cget("bg"))
        card.place(relx=1.0, rely=0.0, anchor="ne")
        # A white border keeps the code scannable in the dark theme too.
        tk.Label(card, image=image, bg="#ffffff", bd=0, padx=8, pady=8).pack(anchor="e")
        self.label(card, "Room website", 19).pack(anchor="e", pady=(12, 2))
        address = WEBSITE_URL.split("//")[1].rstrip("/")
        self.label(card, address, 15, True).pack(anchor="e")
        self.label(card, "Scan on the room network", 15, True).pack(anchor="e")
