"""Room guide and read-only system/help presentation."""

from panel_guides import DEMO, GUIDE_SECTIONS
from panel_guides import SUPPORT
from panel_guides import CEILING_MAP
from panel_common import CHANNELS, CHANNEL_COLOURS
from command_reference import command_tokens
from help_reference import reference
import sys
import tkinter as tk


class PanelGuidance:
    def system_contents(self):
        self.health_rendered = None
        if getattr(self, "system_diagnostics_visible", False):
            self.power_buttons = []
            self.original_fallback_button = None
            self.room_diagnostics_contents()
            return
        heading = tk.Frame(self.body, bg=self.bg, height=50)
        heading.pack(fill="x", pady=(0, 8))
        heading.pack_propagate(False)
        self.label(heading, "System & help", 27).pack(side="left")
        self.power_buttons = []
        fallback = self.button(heading, "Open Legacy", lambda: self.show("original"))
        fallback.config(font=(self.font_family, 15), pady=8, padx=12)
        fallback.pack(side="right", padx=(12, 0), fill="y")
        self.original_fallback_button = fallback
        for operation, title in (
            ("shutdown", "Shut down panel"),
            ("reboot", "Restart panel"),
        ):
            button = self.button(
                heading,
                title,
                lambda operation=operation: self.confirm_power(operation),
            )
            button.config(font=(self.font_family, 15), pady=8, padx=12)
            button.pack(side="right", padx=(12, 0), fill="y")
            self.power_buttons.append((button, operation))
        self.poll_power()
        if not self.support_commands_visible:
            self.label(
                self.body,
                "Checks are read-only. Restart and shutdown affect this panel.",
                15,
                True,
            ).pack(anchor="w", pady=(0, 10))
        overview = tk.Frame(self.body, bg=self.bg)
        overview.pack(fill="x", pady=(0, 12))
        overview.columnconfigure(0, weight=1, uniform="system")
        overview.columnconfigure(1, minsize=12)
        overview.columnconfigure(2, weight=1, uniform="system")
        overview.rowconfigure(0, weight=1)
        cards = []
        for column, title in ((0, "Panel health"), (2, "Room connection")):
            card = tk.Frame(
                overview,
                bg=self.bg,
                highlightbackground=self.border,
                highlightthickness=1,
            )
            card.grid(row=0, column=column, sticky="nsew")
            content = tk.Frame(card, bg=self.bg)
            content.pack(fill="both", expand=True, padx=14, pady=10)
            self.label(content, title, 17).pack(anchor="w", pady=(0, 6))
            cards.append(content)
        self.health_details = self.label(cards[0], size=15)
        self.wrap_label(self.health_details).pack(fill="x", pady=(0, 6))
        self.power_label = self.label(cards[0], size=15, muted=True)
        self.wrap_label(self.power_label).pack(fill="x")
        row = tk.Frame(cards[1], bg=self.bg)
        row.pack(fill="x", pady=(0, 4))
        self.label(row, "Lighting", 15, True).pack(side="left", padx=(0, 12))
        state = self.label(row, size=20)
        state.config(textvariable=self.connection_text)
        state.pack(side="left")
        self.system_blind_status_label = self.label(row, size=13, muted=True)
        self.system_blind_status_label.pack(side="right")
        self.update_blind_buttons()
        self.services_label = self.label(cards[1], size=13, muted=True)
        self.wrap_label(self.services_label).pack(fill="x")
        diagnostics = self.button(cards[1], "Room services", self.toggle_room_diagnostics)
        diagnostics.config(font=(self.font_family, 15), pady=8)
        diagnostics.pack(anchor="w", pady=(6, 0))
        self.recovery_contents(cards[1])
        topic = tk.Frame(self.body, bg=self.bg, height=58)
        topic.pack(fill="x", pady=(0, 4))
        topic.pack_propagate(False)
        self.label(topic, "Help topic", 18).pack(side="left", padx=(0, 20))
        selected = tk.StringVar(value=SUPPORT[self.support_page][0])
        menu = tk.OptionMenu(
            topic,
            selected,
            *[item[0] for item in SUPPORT],
            command=lambda name: self.choose_support(
                [item[0] for item in SUPPORT].index(name)
            ),
        )
        menu.config(
            font=(self.font_family, 18),
            bg=self.control,
            fg=self.ink,
            highlightthickness=1,
            highlightbackground=self.border,
            highlightcolor=self.ink,
            bd=0,
            padx=18,
            pady=10,
            activebackground=self.pressed_colour(),
            activeforeground=self.ink,
            image=self.icon("dropdown", self.ink, 24),
            compound="right",
            indicatoron=False,
        )
        menu["menu"].config(
            font=(self.font_family, 18),
            bg=self.control,
            fg=self.ink,
            activebackground=self.pressed_colour(),
            activeforeground=self.ink,
            activeborderwidth=0,
        )
        menu.pack(side="left", fill="y")
        title, kind, text, commands = SUPPORT[self.support_page]
        card = tk.Frame(
            self.body, bg=self.bg, highlightbackground=self.border, highlightthickness=1
        )
        card.pack(fill="x", pady=(6, 0))
        content = tk.Frame(card, bg=self.bg)
        content.pack(fill="x", padx=20, pady=14)
        show_commands = commands and self.support_commands_visible
        if not show_commands:
            for index, paragraph in enumerate(text.split("\n\n")):
                self.wrap_label(self.label(content, paragraph, 15)).pack(
                    fill="x", pady=(4 if index else 0, 0)
                )
        else:
            overview.pack_forget()
            guide = reference(title)
            steps = guide["steps"]
            self.support_step = max(0, min(self.support_step, len(steps) - 1))
            step = steps[self.support_step]
            commands = step["commands"]
            context = self.label(
                content, guide["machine"] + " · " + guide["effect"], 14, True
            )
            if title in ("Start services", "Restart computer"):
                context.config(fg=self.warning)
            context.pack(anchor="w", pady=(4, 8))
            self.label(content, step["title"], 22).pack(anchor="w", pady=(0, 8))
            self.wrap_label(self.label(content, step["why"], 16)).pack(
                fill="x", pady=(0, 12)
            )
            mono = "Consolas" if sys.platform == "win32" else "DejaVu Sans Mono"
            code = tk.Text(
                content,
                font=(mono, 13),
                height=len(commands.splitlines()),
                width=1,
                bg=self.control,
                fg=self.ink,
                bd=0,
                highlightthickness=0,
                padx=16,
                pady=12,
                wrap="none",
                takefocus=False,
                cursor="arrow",
            )
            for kind, colour, style in (
                ("command", self.ink, "bold"),
                ("option", self.muted, "normal"),
                ("path", self.accent, "normal"),
                ("string", self.accent, "normal"),
                ("number", self.muted, "normal"),
                ("comment", self.muted, "italic"),
                ("operator", self.ink, "bold"),
            ):
                code.tag_configure(kind, foreground=colour, font=(mono, 13, style))
            for token in command_tokens(commands):
                code.insert("end", token["text"], token["kind"])
            code.config(state="disabled")
            code.pack(fill="x")
            self.label(content, "What to expect", 16).pack(anchor="w", pady=(12, 4))
            self.wrap_label(self.label(content, step["expect"], 15, True)).pack(
                fill="x", pady=(0, 8)
            )
            if len(steps) > 1:
                self.label(
                    content,
                    "Step %d of %d · use the same Terminal"
                    % (self.support_step + 1, len(steps)),
                    14,
                    True,
                ).pack(anchor="w")
            self.label(
                content, "Reference only · nothing is executed by this panel", 14, True
            ).pack(anchor="w", pady=(4, 0))
            if len(steps) > 1:
                nav = self.row_buttons(
                    content,
                    [
                        ("Back to guidance", self.toggle_support_commands, False),
                        ("Previous step", lambda: self.change_support_step(-1), False),
                        ("Next step", lambda: self.change_support_step(1), False),
                    ],
                    height=54,
                )
                for button in nav:
                    button.config(font=(self.font_family, 17), pady=8)
                nav[1].config(state="normal" if self.support_step else "disabled")
                nav[2].config(
                    state="normal" if self.support_step < len(steps) - 1 else "disabled"
                )
        if commands and (not show_commands or len(steps) == 1):
            self.row_buttons(
                content,
                [
                    (
                        "Back to guidance" if show_commands else "View command steps",
                        self.toggle_support_commands,
                        False,
                    )
                ],
                height=60,
            )
        self.update_health()

    def toggle_room_diagnostics(self):
        self.system_diagnostics_visible = not getattr(self, "system_diagnostics_visible", False)
        self.rebuild_advanced_detail()

    def room_diagnostics_contents(self):
        heading = tk.Frame(self.body, bg=self.bg)
        heading.pack(fill="x", pady=(0, 12))
        self.label(heading, "Room services", 27).pack(side="left")
        back = self.button(heading, "Back to System & help", self.toggle_room_diagnostics)
        back.config(font=(self.font_family, 17), pady=10)
        back.pack(side="right")
        self.wrap_label(self.label(
            self.body, "Advertised room services. Listed does not confirm fresh sensor data.", 16, True
        )).pack(fill="x", pady=(0, 12))
        self.diagnostics_message = self.wrap_label(self.label(self.body, size=17))
        self.diagnostics_message.pack(fill="x", pady=(0, 8))
        row = tk.Frame(self.body, bg=self.bg)
        row.pack(fill="x", pady=(0, 14))
        self.diagnostics_age = self.label(row, size=15, muted=True)
        self.diagnostics_age.pack(side="left")
        self.diagnostics_check = self.button(row, "Check now", self.check_room_diagnostics)
        self.diagnostics_check.config(font=(self.font_family, 17), pady=10)
        self.diagnostics_check.pack(side="right")
        self.diagnostics_rows = tk.Frame(
            self.body, bg=self.bg, highlightthickness=1, highlightbackground=self.border
        )
        self.diagnostics_rows.pack(fill="x", pady=(0, 14))
        self.diagnostics_rows_key = None
        self.wrap_label(self.label(
            self.body,
            "Indoor readings: check the room TV/Status display. A verified indoor-data feed is not connected here.",
            15, True,
        )).pack(fill="x")
        self.update_room_diagnostics()

    def check_room_diagnostics(self):
        self.refresh_status()
        self.update_room_diagnostics()

    def update_room_diagnostics(self):
        data = self.room_diagnostics()
        detail = ("Checking now. " if data["checking"] else "") + data["detail"]
        age = data["age_s"]
        if age is None:
            observed = "No successful service check yet."
        elif age < 60:
            observed = "Last successful check: %d seconds ago" % max(0, int(age))
        elif age < 3600:
            observed = "Last successful check: %d minutes ago" % int(age // 60)
        else:
            observed = "Last successful check: %d hours ago" % int(age // 3600)
        for label, text in ((self.diagnostics_message, detail), (self.diagnostics_age, observed)):
            if label.cget("text") != text:
                label.config(text=text)
        colour = self.warning if data["state"] == "unavailable" else self.ink
        if self.diagnostics_message.cget("fg") != colour:
            self.diagnostics_message.config(fg=colour)
        check = self.diagnostics_check
        state, text = ("normal" if data["can_check"] else "disabled"), ("Checking…" if data["checking"] else "Check now")
        if check.cget("state") != state or check.cget("text") != text:
            check.config(state=state, text=text)
        entries = tuple((item["name"], item["state"]) for item in data["services"])
        if entries != self.diagnostics_rows_key:
            self.diagnostics_rows_key = entries
            for child in self.diagnostics_rows.winfo_children():
                child.destroy()
            if not entries:
                self.label(self.diagnostics_rows, "No observed service results yet.", 17, True).pack(
                    anchor="w", padx=18, pady=18
                )
            for name, status in entries:
                row = tk.Frame(self.diagnostics_rows, bg=self.bg)
                row.pack(fill="x", padx=18, pady=10)
                self.label(row, name, 19).pack(side="left")
                result = self.label(row, "Listed" if status == "listed" else "Missing", 17)
                result.config(fg=self.good if status == "listed" else self.warning)
                result.pack(side="right")

    def open_guide(self):
        if self.mode == "guide":
            self.choose_guide(-1)
        else:
            self.show("guide")

    def choose_guide(self, index):
        self.guide_page = index
        if index >= 0:
            self.guide_section = DEMO[index]["section"]
        self.show("guide")

    def choose_guide_section(self, section):
        self.guide_section = section
        self.choose_guide(-1)

    def guide_view(self):
        if self.guide_page < 0:
            self.label(self.body, "Demo & guide", 27).pack(anchor="w", pady=(0, 6))
            self.label(
                self.body,
                "Explore the room or learn the controls. Browsing starts no equipment.",
                17,
                True,
            ).pack(anchor="w", pady=(0, 8))
            hub = tk.Frame(self.body, bg=self.bg)
            hub.pack(fill="both", expand=True, pady=(0, 10))
            phone = tk.Frame(hub, bg=self.bg, width=240)
            phone.pack(side="right", fill="y", padx=(24, 0))
            phone.pack_propagate(False)
            self.website_qr(phone)
            topics = tk.Frame(hub, bg=self.bg)
            topics.pack(side="left", fill="both", expand=True)
            for column, (title, section) in enumerate(GUIDE_SECTIONS):
                topics.columnconfigure(column, weight=1, uniform="guide")
                group = tk.Frame(topics, bg=self.bg)
                group.grid(row=0, column=column, sticky="nsew", padx=(0, 20) if column == 0 else 0)
                heading = self.label(group, title, 20)
                heading.config(font=(self.font_family, 20, "bold"))
                heading.pack(anchor="w", pady=(0, 10))
                for index, topic in enumerate(DEMO):
                    if topic["section"] != section:
                        continue
                    row = tk.Frame(group, bg=self.bg, height=80)
                    row.pack(fill="x", pady=(0, 8))
                    row.pack_propagate(False)
                    button = self.button(
                        row, topic["title"] + "  ›\n" + topic["caption"],
                        lambda index=index: self.choose_guide(index),
                    )
                    button.config(
                        font=(self.font_family, 18), image=self.icon(topic["icon"], self.icon_colour, 24),
                        compound="left", wraplength=390, justify="left", anchor="w",
                        bg=self.bg, highlightbackground=self.bg, highlightcolor=self.bg,
                        padx=12, pady=6,
                    )
                    button.pack(fill="both", expand=True)
            return
        indices = [i for i, topic in enumerate(DEMO) if topic["section"] == self.guide_section]
        topic = DEMO[self.guide_page]
        position = indices.index(self.guide_page)
        section = dict((key, label) for label, key in GUIDE_SECTIONS)[self.guide_section]
        heading = tk.Frame(self.body, bg=self.bg)
        heading.pack(fill="x", pady=(0, 12))
        tk.Label(heading, image=self.icon(topic["icon"], self.icon_colour), bg=self.bg).pack(
            side="left", padx=(0, 12)
        )
        self.label(heading, topic["title"], 27).pack(side="left")
        self.label(
            heading, "%s · %d of %d" % (section, position + 1, len(indices)), 15, True
        ).pack(side="right")
        flexible = bool(topic.get("map"))
        background = self.surface if flexible else self.bg
        card = tk.Frame(
            self.body,
            bg=background,
            highlightbackground=self.border,
            highlightthickness=1 if flexible else 0,
        )
        card.pack(fill="both" if flexible else "x", expand=flexible)
        content = tk.Frame(card, bg=background)
        content.pack(
            fill="both" if flexible else "x", expand=flexible,
            padx=24 if flexible else 0, pady=22 if flexible else 0,
        )
        if topic.get("map"):
            self.ceiling_map(content)
        else:
            if topic.get("visual"):
                visual = self.guide_visual(content, topic["visual"])
            for paragraph in topic["text"].split("\n\n"):
                size = 16 if topic.get("actions") else 17 if topic.get("visual") else 21
                gap = 4 if topic.get("actions") else 8 if topic.get("visual") else 18
                self.wrap_label(self.label(content, paragraph, size)).pack(
                    fill="x", pady=(0, gap)
                )
        if topic.get("actions"):
            self.wrap_label(self.label(
                content, "Applying a scene changes the room lights. Wait for confirmation.", 14, True
            )).pack(fill="x")
            actions = self.row_buttons(
                content,
                [("Lights on (Fid)", self.lights_on, False),
                 ("Apply Gradient", lambda: self.apply("gradient", immediate=True), False),
                 ("Open Lighting", lambda: self.open_advanced("lighting"), False)],
                height=52,
            )
            for button in actions:
                button.config(font=(self.font_family, 17), pady=8)
            self.style_guide_link(actions[2])
            actions[1]._gradient = True
            self.light_buttons.extend(actions[:2])
            self.feedback_card(content, padding=8)
            if topic.get("visual"):
                self.light_feedback_card.pack_configure(side="bottom", before=visual)
            self.update_light_buttons()
        elif topic["links"]:
            links = self.row_buttons(
                content,
                [
                    (
                        link["label"],
                        lambda page=link["page"]: (
                            self.open_home() if page == "home" else self.open_advanced(page)
                        ),
                        False,
                    )
                    for link in topic["links"]
                ],
                height=56,
            )
            for button in links:
                self.style_guide_link(button)
        buttons = self.row_buttons(
            self.body,
            [
                (section + " topics", lambda: self.choose_guide(-1), False),
                ("Previous", lambda: self.change_guide(-1), False),
                ("Next", lambda: self.change_guide(1), False),
            ],
            height=56,
        )
        # Keep navigation reachable; the topic card takes the remaining height.
        navigation = buttons[0].master
        navigation.config(width=654)
        navigation.pack_configure(side="bottom", fill="none", anchor="w", before=card)
        for column, width in ((0, 300), (2, 180), (4, 150)):
            navigation.columnconfigure(column, weight=0, uniform="", minsize=width)
        for button, kind in zip(buttons, ("guide", "chevron-left", "chevron-right")):
            button.config(
                image=self.icon(kind, self.ink, 24), compound="left",
                font=(self.font_family, 17), pady=8,
            )
        buttons[1].config(state="normal" if position else "disabled")
        buttons[2].config(
            state="normal" if position < len(indices) - 1 else "disabled"
        )
        for button, kind in zip(buttons, ("guide", "chevron-left", "chevron-right")):
            button.config(
                image=self.icon(
                    kind,
                    self.muted if button.cget("state") == "disabled" else self.ink,
                    24,
                )
            )

    def style_guide_link(self, button):
        background = button.master.cget("bg")
        button.config(
            bg=background, highlightbackground=background, highlightcolor=background,
            image=self.icon("chevron-right", self.ink, 20), compound="right",
            font=(self.font_family, 17), pady=8,
        )

    def change_guide(self, delta):
        indices = [i for i, topic in enumerate(DEMO) if topic["section"] == self.guide_section]
        position = max(0, min(len(indices) - 1, indices.index(self.guide_page) + delta))
        self.guide_page = indices[position]
        self.render()

    def choose_support(self, index):
        if index != self.support_page:
            self.support_page = index
            self.support_step = 0
            self.support_commands_visible = False
            (
                self.rebuild_advanced_detail()
                if self.advanced_page == "system"
                else self.render()
            )

    def toggle_support_commands(self):
        self.support_commands_visible = not self.support_commands_visible
        (
            self.rebuild_advanced_detail()
            if self.advanced_page == "system"
            else self.render()
        )

    def change_support_step(self, delta):
        steps = reference(SUPPORT[self.support_page][0])["steps"]
        self.support_step = max(0, min(len(steps) - 1, self.support_step + delta))
        self.rebuild_advanced_detail()

    def ceiling_map(self, parent):
        families = CEILING_MAP["families"]
        selected = families[0]
        columns, rows = CEILING_MAP["grid"]["columns"], CEILING_MAP["grid"]["rows"]

        def draw(event=None):
            width, height = canvas.winfo_width(), canvas.winfo_height()
            if width < 150 or height < 80:
                return
            canvas.delete("all")
            left, top, right, bottom = 42, 12, width - 18, height - 32
            cell_width, cell_height = (right - left) / columns, (bottom - top) / rows
            for column in range(columns + 1):
                x = left + column * cell_width
                canvas.create_line(x, top, x, bottom, fill=self.border)
                if column < columns:
                    canvas.create_text(
                        x + cell_width / 2, bottom + 18, text=str(column + 1),
                        font=(self.font_family, 12), fill=self.muted,
                    )
            for row in range(rows + 1):
                y = bottom - row * cell_height
                canvas.create_line(left, y, right, y, fill=self.border)
                if row < rows:
                    canvas.create_text(
                        left - 20, y - cell_height / 2, text=str(row + 1),
                        font=(self.font_family, 12), fill=self.muted,
                    )
            radius = min(8, max(4, min(cell_width, cell_height) / 5))
            for column, row in selected["positions"]:
                x = left + (column - 0.5) * cell_width
                y = bottom - (row - 0.5) * cell_height
                canvas.create_oval(
                    x - radius, y - radius, x + radius, y + radius,
                    fill=self.accent, outline="", tags="sensor",
                )

        def choose(family):
            nonlocal selected
            selected = family
            detail.config(text="%s · %d ceiling positions. %s" % (
                family["label"], len(family["positions"]), family["description"]
            ))
            for button, candidate in zip(buttons, families):
                active = candidate is selected
                button.config(
                    font=(self.font_family, 17, "bold" if active else "normal"),
                    bg=self.control, fg=self.ink,
                    highlightbackground=self.control,
                    activebackground=self.pressed_colour(), activeforeground=self.ink,
                )
            draw()

        buttons = self.row_buttons(
            parent,
            [(family["label"], lambda family=family: choose(family), False)
             for family in families],
            height=52,
        )
        for button in buttons:
            button.config(font=(self.font_family, 17), pady=8)
        detail = self.wrap_label(self.label(parent, size=16))
        detail.pack(fill="x", pady=(4, 8))
        canvas = tk.Canvas(
            parent, height=220, bg=parent.cget("bg"),
            highlightthickness=0, borderwidth=0,
        )
        canvas.pack(fill="both", expand=True)
        canvas.bind("<Configure>", draw)
        self.wrap_label(self.label(
            parent, CEILING_MAP["orientation"] + " " + CEILING_MAP["note"], 13, True
        )).pack(side="bottom", fill="x", pady=(6, 0), before=canvas)
        choose(selected)

    def guide_visual(self, parent, kind):
        canvas = tk.Canvas(
            parent, height=60 if kind == "channels" else 190, bg=parent.cget("bg"),
            highlightthickness=0, borderwidth=0,
        )
        canvas.pack(fill="x", pady=(0, 6 if kind == "channels" else 10))

        def draw(event=None):
            width = canvas.winfo_width()
            if width < 150:
                return
            canvas.delete("all")
            if kind == "channels":
                cell = width / len(CHANNELS)
                for index, (name, colour) in enumerate(zip(CHANNELS, CHANNEL_COLOURS)):
                    left, right = index * cell + 8, (index + 1) * cell - 8
                    canvas.create_rectangle(left, 4, right, 24, fill=colour, outline="")
                    canvas.create_text(
                        (left + right) / 2, 42, text=name,
                        font=(self.font_family, 13), fill=self.ink,
                    )
            elif kind == "distance":
                for center, name, columns, rows in (
                    (width / 4, "COMBO", 8, 8),
                    (width * 3 / 4, "IRMA", 25, 20),
                ):
                    canvas.create_text(
                        center, 18,
                        text="%s · %d × %d · %d cells" % (name, columns, rows, columns * rows),
                        font=(self.font_family, 16), fill=self.ink,
                    )
                    cell = 120 / rows
                    left, top = center - columns * cell / 2, 38
                    for column in range(columns + 1):
                        x = left + column * cell
                        canvas.create_line(
                            x, top, x, top + rows * cell, fill=self.muted, tags=name.lower()
                        )
                    for row in range(rows + 1):
                        y = top + row * cell
                        canvas.create_line(
                            left, y, left + columns * cell, y, fill=self.muted, tags=name.lower()
                        )
                canvas.create_text(
                    width / 2, 176, text="Distance samples · schematic examples, no live readings",
                    font=(self.font_family, 12), fill=self.muted,
                )

        canvas.bind("<Configure>", draw)
        return canvas
