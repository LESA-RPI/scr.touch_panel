"""Retained page frame, neutral rail, connection sheet and Legacy return strip."""
import time
import tkinter as tk
from design_tokens import THEMES
from panel_common import monotonic, scheduled_theme, FONT
from ui_widgets import S, Button, Sheet, label, slot, font

PAGE_WIDGETS = (
    "light_buttons", "home_power_buttons", "scene_buttons", "blind_buttons", "programme_buttons",
    "home_blinds", "home_blind_key", "weather_symbol", "weather_feels", "weather_facts", "weather_notice",
    "daylight_label", "saver_weather", "advanced_detail", "diagnostics_message", "diagnostics_check",
    "diagnostics_age", "diagnostics_rows", "system_connection_row", "power_label", "health_details",
    "services_label", "power_buttons", "map_canvas", "map_hits",
)


class PanelFrame:
    def set_theme(self):
        if self.theme is not None and self.theme_choice == "auto" and monotonic()-self.last_touch < 60:
            return
        now = time.localtime()
        chosen = scheduled_theme(now.tm_hour*60+now.tm_min, self.args.light_at, self.args.dark_at)
        chosen = chosen if self.theme_choice == "auto" else self.theme_choice
        if chosen == self.theme:
            return
        self.cancel_intent()
        self.theme = chosen
        for name, value in THEMES[chosen].items():
            setattr(self, name, value)
        self.sheet = None
        self.sheet_name = None
        self.mix_notes = []
        self.preference_rows = []
        self.readback_labels = []
        self.connection_badges = []
        self.navigation_buttons = []
        self.body_cache.clear()
        self.detail_cache.clear()
        self.body_key = None
        for child in self.root.winfo_children():
            if child != self.dock:
                child.destroy()
        self.root.config(bg=self.bg)
        self.blank_hint = None
        self.rail = tk.Frame(self.root, bg=self.bg, width=168)
        self.rail.place(x=0, y=0, width=168, relheight=1)
        tk.Frame(self.rail, bg=self.border, width=S["line"]).place(relx=1, x=-1, y=0, relheight=1)
        if self.artwork:
            tk.Label(self.rail, image=self.artwork, bg="white", bd=0).place(relx=.5, y=24, anchor="n")
        else:
            label(self, self.rail, "LESA", "title").place(relx=.5, y=32, anchor="n")
        self.rail_buttons = {}
        for index, (title, icon, action) in enumerate((
                ("Home", "home", lambda: self.open_home()),
                ("Lights", "on", lambda: self.open_lighting()),
                ("Guide", "guide", lambda: self.open_guide()),
                ("Settings", "advanced", lambda: self.open_advanced("screen")))):
            button = Button(self, self.rail, title, action, "link")
            button.config(image=self.icon(icon, self.ink, 32), compound="top", padx=0)
            button._icon = icon
            button.place(x=12, y=108+index*122, width=144, height=116)
            self.rail_buttons[title] = button
            self.navigation_buttons.append(button)
        self.home_button = self.rail_buttons["Home"]
        self.banner = tk.Frame(self.root, bg=self.bg)
        self.banner.place(x=196, y=28, width=1056, height=56)
        self.page_title = label(self, self.banner, "Smart Conference Room", "heading")
        self.page_title.config(font=font("heading", True))
        self.page_title.pack(side="left")
        label(self, self.banner, "Beta", "small", True).pack(side="left", padx=12)
        self.status_chip = Button(self, self.banner, "", lambda: self.open_connection_sheet())
        self.status_chip.pack(side="right", fill="y")
        self.connection_badges.append((self.status_chip, False))
        self.navigation_buttons.append(self.status_chip)
        self.clock = label(self, self.banner, textvariable=self.visitor_time, muted=True)
        self.stage = tk.Frame(self.root, bg=self.bg)
        self.stage.place(x=196, y=108, width=1056, height=664)
        self.body = None
        self.build_dock()
        self.render()

    def build_dock(self):
        for child in self.dock.winfo_children():
            child.destroy()
        self.dock.config(bg=self.bg)
        row = tk.Frame(self.dock, bg=self.bg)
        row.pack(fill="both", expand=True, padx=S["pad"], pady=20)
        if self.artwork:
            tk.Label(row, image=self.artwork, bg="white", bd=0).pack(side="left", padx=(0, 24))
        else:
            label(self, row, "LESA", "title").pack(side="left", padx=(0, 32))
        home = Button(self, row, "Back to Home", lambda: self.open_home())
        home.pack(side="right", fill="y")
        self.navigation_buttons.append(home)
        text = tk.Frame(row, bg=self.bg)
        text.pack(side="left", fill="both", expand=True)
        label(self, text, "Legacy controls", "title").pack(anchor="w", pady=(4, 8))
        label(self, text, "The original app. Lighting on the website pauses until you go back.", "small", True).pack(anchor="w")

    def open_home(self):
        self.close_sheet()
        self.show("room")

    def open_lighting(self):
        self.close_sheet()
        self.show("room", advanced_page="lighting")

    def open_advanced(self, page=None):
        if self.release_target or self.closing or self.power_busy() or getattr(self, "legacy_stopping_at", None):
            return
        page = page or self.last_advanced_page
        if page in ("white", "scenes", "programmes", "channels"):
            self.lighting_tab, page = page, "lighting"
        if page == "lighting":
            self.open_lighting()
            return
        if page not in ("screen", "appearance", "clock", "system", "about"):
            page = "screen"
        self.last_advanced_page, self.settings_category = page, page
        self.close_sheet()
        self.show("health" if page == "system" else "settings", advanced_page=page)

    def split_page(self):
        side = tk.Frame(self.body, bg=self.bg, width=300)
        side.pack(side="left", fill="y", padx=(0, 36))
        side.pack_propagate(False)
        content = tk.Frame(self.body, bg=self.bg)
        content.pack(side="left", fill="both", expand=True)
        return side, content

    def route(self):
        if self.idle_active:
            return ("saver",), self.screensaver_view, ""
        if self.advanced_page == "lighting":
            return ("lights", self.lighting_tab, bool(self.light_capabilities.get("programmes"))), self.lighting_contents, "Lights"
        if self.advanced_page:
            return ("settings", self.advanced_page), self.settings_view, "Settings"
        if self.mode == "guide":
            return ("guide", self.guide_page), self.guide_view, "Guide"
        return ("home",), self.room_view, "Smart Conference Room"

    def render(self):
        self.close_sheet()
        self.dock.withdraw()
        if self.mode == "original":
            self.root.withdraw()
            self.dock.geometry("1280x112+0+0")
            self.dock.deiconify()
            self.dock.lift()
            return
        if self.root.state() == "withdrawn":
            self.root.deiconify()
        for binding in ("<ButtonPress-1>", "<ButtonRelease-1>", "<B1-Motion>"):
            self.root.unbind(binding)
        if self.blank_hint:
            self.blank_hint.place_forget()
        if self.mode == "black":
            for widget in (self.rail, self.banner, self.stage):
                widget.place_forget()
            self.root.config(bg="black")
            if self.blank_hint is None:
                self.blank_hint = label(self, self.root, "Hold anywhere for 2 seconds to return", "small", True)
            self.blank_hint.place(relx=.5, rely=1, y=-18, anchor="s")
            self.root.bind("<ButtonPress-1>", self.begin_hold)
            self.root.bind("<ButtonRelease-1>", lambda e: self.cancel_hold())
            self.root.bind("<B1-Motion>", self.move_hold)
            return
        self.root.config(bg=self.bg)
        key, build, title = self.route()
        if self.idle_active:
            self.rail.place_forget()
            self.banner.place_forget()
            self.stage.place(x=0, y=0, width=1280, height=800)
        else:
            self.rail.place(x=0, y=0, width=168, relheight=1)
            self.banner.place(x=196, y=28, width=1056, height=56)
            self.stage.place(x=196, y=108, width=1056, height=664)
            self.page_title.config(text=title)
            self.clock.pack_forget()
            if title != "Smart Conference Room":
                self.clock.pack(side="right", padx=(0, 16))
        if self.body_key != key:
            if self.body is not None:
                self.body_cache[self.body_key] = (self.body, {n: getattr(self, n) for n in PAGE_WIDGETS if hasattr(self, n)})
                self.body.pack_forget()
            cached = self.body_cache.pop(key, None)
            for n in PAGE_WIDGETS:
                setattr(self, n, [] if n in ("light_buttons", "home_power_buttons", "scene_buttons", "blind_buttons", "programme_buttons", "power_buttons") else None)
            if cached:
                self.body, references = cached
                self.__dict__.update(references)
            else:
                self.body = tk.Frame(self.stage, bg=self.bg)
                self.body.pack(fill="both", expand=True)
                build()
            self.body_key = key
        self.body.pack(fill="both", expand=True)
        self.refresh_page()
        self.update_navigation_buttons()
        self.install_wake_bindings()

    def rebuild_advanced_detail(self):
        # Capability changes are the only reason a retained tab needs a new layout.
        self.render()

    def refresh_page(self):
        self.refresh_preferences()
        self.refresh_home_blinds()
        self.update_light_buttons()
        self.refresh_confirmation_age()
        self.update_weather(force=True)
        self.update_mix_notes()
        if self.advanced_page == "system":
            self.refresh_system_facts()
            self.update_room_diagnostics()

    def update_navigation_buttons(self):
        busy = bool(self.release_target or self.closing or self.power_busy() or getattr(self, "legacy_stopping_at", None))
        current = "Lights" if self.advanced_page == "lighting" else "Settings" if self.advanced_page else "Guide" if self.mode == "guide" else "Home"
        for button in getattr(self, "navigation_buttons", []):
            if button.winfo_exists():
                button.config(state="disabled" if busy else "normal")
        for title, button in getattr(self, "rail_buttons", {}).items():
            if button.winfo_exists():
                selected = title == current
                button.style(selected=selected)
                button.config(image=self.icon(button._icon, self.bg if selected else self.ink, 32), font=font("text", selected))

    def connection_state(self):
        recovery = self.recovery_snapshot(ignore_touch=True)
        if recovery["status"] in ("uncertain", "needs_staff"):
            return "Check needed", recovery.get("detail") or "A change could not be confirmed. Check connection confirms current settings.", self.warning
        if self.light_state == "failed":
            return "Check needed", "A change could not be confirmed. Press Check connection to confirm current settings.", self.warning
        if self.light_state == "connecting" or recovery["status"] in ("checking", "returning"):
            return "Connecting…", "The panel is reading the lights. Controls appear in a moment.", self.muted
        if self.pending or self.queued_intent or self.light_state == "applying" or recovery["status"] == "writing":
            return "Working…", "A change is on its way. Other lighting buttons wait until it is confirmed.", self.muted
        if self.light_state == "disconnected":
            return "Lighting offline", "The panel cannot reach the lighting service. Check connection tries again without changing anything.", self.warning
        return "Ready", "Lighting controls work on the panel and the room website.", self.good

    def update_connection_badges(self):
        title, detail, colour = self.connection_state()
        self.connection_text.set(title)
        for button, _ in getattr(self, "connection_badges", []):
            if button.winfo_exists():
                button.config(text="●  " + title, fg=self.ink)
                # Colour belongs to the status dot, not to the chip border or text.
                button.config(image=self.status_dot(colour), compound="left", text="  " + title)
        row = getattr(self, "system_connection_row", None)
        if row is not None and row.winfo_exists():
            row.value_button.config(text=title + "  ›")
        if getattr(self, "sheet_name", None) == "status":
            self.sheet_detail.config(text=detail)
            self.sheet_readback.config(text=self.readback_sentence(confirmed_only=True))
            self.sheet_facts.config(text=self.connection_facts())
            state = self.recovery_snapshot(ignore_touch=True)
            self.sheet_check.config(text="Checking…" if state["status"] == "checking" else "Check connection",
                                    state="normal" if state["can_check"] else "disabled")

    def status_dot(self, colour):
        key = ("status-dot", colour)
        if key not in self.icon_cache:
            from PIL import Image, ImageDraw
            image = Image.new("RGBA", (14, 14))
            ImageDraw.Draw(image).ellipse((2, 2, 12, 12), fill=colour)
            self.photo(key, image)
        return self.icon_cache[key]

    def readback_sentence(self, confirmed_only=False):
        power = getattr(self, "confirmed_power", None)
        scene = getattr(self, "confirmed_scene", None)
        text = "Lights are " + power if power in ("on", "off") else "Lights not confirmed yet"
        if power == "on" and scene:
            text += " · " + scene
        elif power == "on":
            text += " · " + self.confirmed_light
        stamp = getattr(self, "confirmed_at", None)
        if stamp is not None:
            seconds = max(0, int(monotonic()-stamp))
            age = "%d s ago" % seconds if seconds < 60 else "%d min ago" % (seconds//60) if seconds < 3600 else "%d h ago" % (seconds//3600)
            text += " · confirmed " + age
        if not confirmed_only and self.light_state == "applying":
            return "Sending… Wait for confirmation."
        if not confirmed_only and self.light_state in ("failed", "connecting"):
            text = {"failed": "Check needed", "connecting": "Reading the lights…"}[self.light_state] + " · Last known: " + text.lower()
        return text

    def readback_label(self, parent, small=False):
        widget = label(self, parent, self.readback_sentence(), "small" if small else "text", muted=True)
        self.wrap_label(widget)
        self.readback_labels.append(widget)
        return widget

    def update_readback_labels(self):
        if not getattr(self, "readback_labels", []):
            return
        text = self.readback_sentence()
        for widget in getattr(self, "readback_labels", []):
            if widget.winfo_exists():
                widget.config(text=text)

    def make_sheet(self, title, name):
        self.close_sheet()
        self.sheet = Sheet(self, title)
        self.sheet_name = name
        self.install_wake_bindings()
        return self.sheet.content

    def close_sheet(self):
        sheet = getattr(self, "sheet", None)
        if sheet is not None and sheet.winfo_exists():
            sheet.destroy()
            self.root.focus_set()
        self.sheet, self.sheet_name = None, None

    def connection_facts(self):
        blinds = self.blind_state()
        return "Blinds: %s\nProgramme: %s" % (blinds["reason"], (self.programme + " requested; live state unavailable") if self.programme else "None requested")

    def open_connection_sheet(self):
        if self.release_target or self.closing or self.power_busy():
            return
        content = self.make_sheet("Room connection", "status")
        self.sheet_detail = label(self, content, wraplength=610)
        self.sheet_detail.pack(fill="x", pady=(0, 24))
        self.sheet_readback = label(self, content, size="small", wraplength=610)
        self.sheet_readback.pack(fill="x", pady=(0, 24))
        self.sheet_facts = label(self, content, size="small", muted=True, wraplength=610)
        self.sheet_facts.pack(fill="x", pady=(0, 24))
        self.sheet_check = slot(self, content, "Check connection", lambda: self.check_connection_after_release())
        label(self, content, "Reads current light settings without changing them. After an uncertain handoff, stops Sun/Circ and confirms stable settings while keeping light levels.", "small", True, wraplength=610).pack(fill="x", pady=16)
        slot(self, content, "Open Legacy controls", lambda: self.show("original"), pady=(12, 0))
        self.update_connection_badges()
