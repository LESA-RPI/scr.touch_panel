"""Room guide and read-only system/help presentation."""

from panel_guides import DEMO
from panel_guides import SUPPORT
from command_reference import command_tokens
from help_reference import reference
import sys
import tkinter as tk


class PanelGuidance:
    def system_contents(self):
        self.health_rendered = None
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
            ("shutdown", "Shut down Pi"),
            ("reboot", "Restart Pi"),
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
                "Read-only checks. Available services may not be producing sensor data.",
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
        blinds = self.blind_state()
        blind_label = (
            "Disabled"
            if not blinds["enabled"]
            else (
                "Disconnected"
                if not blinds["connected"]
                else "Ready" if blinds["available"] else "Busy"
            )
        )
        self.label(row, "Blinds · " + blind_label, 13, True).pack(side="right")
        self.services_label = self.label(cards[1], size=13, muted=True)
        self.wrap_label(self.services_label).pack(fill="x")
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
            highlightcolor=self.accent,
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
            activebackground=self.accent,
            activeforeground=self.selected_ink,
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

    def open_guide(self):
        self.guide_page = -1
        self.show("guide")

    def choose_guide(self, index):
        self.guide_page = index
        self.show("guide")

    def guide_view(self):
        if self.guide_page < 0:
            self.label(self.body, "Demo & guide", 27).pack(anchor="w", pady=(0, 6))
            self.label(
                self.body,
                "Choose a topic. Exploring this guide does not operate equipment.",
                17,
                True,
            ).pack(anchor="w", pady=(0, 18))
            topics = tk.Frame(self.body, bg=self.bg)
            topics.pack(fill="both", expand=True, pady=(0, 10))
            captions = [
                "White light and saved scenes",
                "Home, Legacy and blinds",
                "Instructions, markers and recording",
                "Panel, services and weather",
            ]
            for index, ((title, kind, text), caption) in enumerate(zip(DEMO, captions)):
                row, column = divmod(index, 2)
                topics.rowconfigure(row, weight=1, uniform="guide")
                topics.columnconfigure(column, weight=1, uniform="guide")
                card = tk.Frame(
                    topics,
                    bg=self.bg,
                    highlightbackground=self.border,
                    highlightthickness=1,
                )
                card.grid(
                    row=row,
                    column=column,
                    sticky="nsew",
                    padx=(0, 16) if column == 0 else 0,
                    pady=(0, 16) if row == 0 else 0,
                )
                button = self.button(
                    card,
                    title + "\n" + caption,
                    lambda index=index: self.choose_guide(index),
                )
                button.config(
                    font=(self.font_family, 20),
                    image=self.icon(kind, self.icon_colour),
                    compound="top",
                    wraplength=520,
                    justify="center",
                    bg=self.bg,
                    padx=20,
                    pady=18,
                    highlightthickness=0,
                )
                button.pack(fill="both", expand=True)
            return
        title, kind, text = DEMO[self.guide_page]
        heading = tk.Frame(self.body, bg=self.bg)
        heading.pack(fill="x", pady=(0, 12))
        self.label(heading, "Demo & guide", 27).pack(side="left")
        self.label(
            heading, "%d of %d topics" % (self.guide_page + 1, len(DEMO)), 17, True
        ).pack(side="right")
        card = tk.Frame(
            self.body,
            bg=self.surface,
            highlightbackground=self.border,
            highlightthickness=1,
        )
        card.pack(fill="both", expand=True)
        content = tk.Frame(card, bg=self.surface)
        content.pack(fill="both", expand=True, padx=24, pady=22)
        row = tk.Frame(content, bg=self.surface)
        row.pack(fill="x", pady=(0, 20))
        tk.Label(row, image=self.icon(kind, self.icon_colour), bg=self.surface).pack(
            side="left", padx=(0, 12)
        )
        self.label(row, title, 26).pack(side="left")
        for paragraph in text.split("\n\n"):
            self.wrap_label(self.label(content, paragraph, 21)).pack(
                fill="x", pady=(0, 18)
            )
        buttons = self.row_buttons(
            self.body,
            [
                ("All topics", self.open_guide, False),
                ("Previous", lambda: self.change_guide(-1), False),
                ("Next", lambda: self.change_guide(1), False),
            ],
        )
        for button, kind in zip(buttons, ("guide", "chevron-left", "chevron-right")):
            button.config(image=self.icon(kind, self.ink, 24), compound="left")
        buttons[1].config(state="normal" if self.guide_page else "disabled")
        buttons[2].config(
            state="normal" if self.guide_page < len(DEMO) - 1 else "disabled"
        )
        for button, kind in zip(buttons, ("guide", "chevron-left", "chevron-right")):
            button.config(
                image=self.icon(
                    kind,
                    self.muted if button.cget("state") == "disabled" else self.ink,
                    24,
                )
            )

    def change_guide(self, delta):
        self.guide_page = max(0, min(len(DEMO) - 1, self.guide_page + delta))
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
