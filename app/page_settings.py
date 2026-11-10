"""Saved preferences and read-only panel/room facts."""
import tkinter as tk
import time
from panel_version import VERSION, BUILD_COMMIT
from help_reference import reference
from ui_widgets import S, Button, ListRow, PrefRow, label, slot

CATEGORIES = (("Screen", "screen"), ("Appearance", "appearance"),
              ("Date & weather", "clock"), ("System", "system"), ("About", "about"))


class SettingsPage:
    def settings_view(self):
        side, content = self.split_page()
        for title, key in CATEGORIES:
            area = tk.Frame(side, bg=self.bg, height=S["tap"])
            area.pack(fill="x", pady=(0, 4))
            area.pack_propagate(False)
            ListRow(self, area, title, lambda k=key: self.open_advanced(k),
                    key == self.advanced_page, icon=key).pack(fill="both", expand=True)
        self.advanced_detail = content
        key = self.advanced_page
        label(self, content, dict((key, title) for title, key in CATEGORIES)[key], "title").pack(anchor="w", pady=(0, 16))
        if key == "screen":
            self.pref_row(content, "idle", "Screen saver", "Clock and weather after the panel is left alone")
            self.pref_row(content, "blinds_display", "Blind buttons on Home", "Show or hide the blind controls")
            self.pref_row(content, "blinds_enabled", "Blind movement", "Locked keeps the blind buttons from moving anything")
            slot(self, content, "Preview screen saver", lambda: self.show("visitor"), pady=(24, 12))
            slot(self, content, "Blank screen", lambda: self.show("black"))
            label(self, content, "Blank keeps the backlight on. Hold 2 seconds to return.", "small", True).pack(anchor="w", pady=12)
        elif key == "appearance":
            self.pref_row(content, "theme", "Panel theme", "Automatic uses the saved day and night times")
            self.pref_row(content, "clock", "Clock", "Time format on this panel")
            self.pref_row(content, "temperature", "Temperature", "Display units for outdoor weather")
            self.pref_row(content, "tips", "Touch explanations", "Short explanations for room controls")
            self.pref_row(content, "schedule", "Automatic schedule", "Light by day and dark at night")
        elif key == "clock":
            self.pref_row(content, "clock", "Time format", "Time format on this panel")
            self.pref_row(content, "temperature", "Temperature", "Display units for outdoor weather")
            label(self, content, "Troy, NY · " + getattr(self.args, "timezone", "System timezone"), muted=True).pack(anchor="w", pady=24)
            date = label(self, content, textvariable=self.visitor_date)
            date.pack(anchor="w")
            label(self, content, textvariable=self.weather_text, size="small", muted=True, wraplength=680).pack(fill="x", pady=24)
            label(self, content, "Source: Open-Meteo · outdoor model estimate", "small", True).pack(anchor="w")
        elif key == "system":
            self.system_contents(content)
        else:
            self.about_contents(content)
        note = label(self, content, textvariable=self.preference_text, size="small", muted=True, wraplength=680)
        note.pack(side="bottom", fill="x", pady=(16, 0))

    def pref_options(self, key):
        return {
            "idle": ([("Off", 0), ("After 1 minute", 60), ("After 5 minutes", 300), ("After 15 minutes", 900)], self.idle_timeout, self.choose_idle),
            "theme": ([("Automatic", "auto"), ("Light", "light"), ("Dark", "dark")], self.theme_choice, self.choose_theme),
            "clock": ([("12-hour", "12"), ("24-hour", "24")], "24" if self.clock_24 else "12", self.choose_clock),
            "temperature": ([("°F", "f"), ("°C", "c")], self.temperature_unit, self.choose_temperature),
            "blinds_display": ([("Shown", "disabled"), ("Hidden", "hidden")], self.blinds_display, self.choose_blinds_display),
            "blinds_enabled": ([("Locked", False), ("Unlocked", True)], self.blinds_enabled, self.choose_blinds_enabled),
            "tips": ([("On", True), ("Off", False)], self.help_on, self.choose_tips),
        }[key]

    def pref_row(self, parent, key, title, detail):
        if key == "schedule":
            value = "%02d:%02d / %02d:%02d" % (divmod(self.args.light_at, 60) + divmod(self.args.dark_at, 60))
        else:
            choices, current, _ = self.pref_options(key)
            value = next(title for title, v in choices if v == current)
        row = PrefRow(self, parent, title, detail, value, lambda: self.open_preference(key, title))
        row.pack(fill="x")
        row._preference = key
        self.preference_rows.append(row)

    def open_preference(self, key, title=None):
        title = title or {"idle": "Screen saver", "theme": "Panel theme", "clock": "Clock",
                          "temperature": "Temperature", "blinds_display": "Blind buttons on Home",
                          "blinds_enabled": "Blind movement", "tips": "Touch explanations",
                          "schedule": "Automatic schedule"}[key]
        content = self.make_sheet(title, key)
        if key == "schedule":
            for field, title in (("light_at", "Light from"), ("dark_at", "Dark from")):
                label(self, content, title, "title").pack(anchor="w", pady=(0, 12))
                row = tk.Frame(content, bg=self.surface, height=S["tap"])
                row.pack(fill="x", pady=(0, 24))
                row.pack_propagate(False)
                for text, delta in (("−1 hour", -60), ("+1 hour", 60)):
                    Button(self, row, text, lambda f=field, d=delta: self.change_schedule(f, d)).pack(side="left", fill="y", padx=(0, 16))
            label(self, content, "Automatic changes wait until the panel is idle.", "small", True).pack(anchor="w")
            return
        choices, current, choose = self.pref_options(key)
        if key == "blinds_enabled" and not self.blind_state()["connected"]:
            label(self, content, "Blind movement can be unlocked once the blind controls are connected.", muted=True, wraplength=610).pack(fill="x", pady=24)
        for title, value in choices:
            button = slot(self, content, title + ("    Current" if value == current else ""),
                          lambda v=value: self.save_picker(choose, v), pady=(0, 12))
            button.style(selected=value == current)
            if key == "blinds_enabled" and value and not self.blind_state()["connected"]:
                button.config(state="disabled")
        label(self, content, "Saved on this panel. Changing a preference never moves equipment.", "small", True, wraplength=610).pack(fill="x", pady=24)

    def save_picker(self, choose, value):
        self.close_sheet()
        choose(value)
        self.refresh_preferences()

    def change_schedule(self, field, delta):
        self.adjust_schedule(field, delta)
        self.open_preference("schedule")

    def refresh_preferences(self):
        for row in getattr(self, "preference_rows", []):
            if row.winfo_exists():
                key = row._preference
                if key == "schedule":
                    value = "%02d:%02d / %02d:%02d" % (divmod(self.args.light_at, 60) + divmod(self.args.dark_at, 60))
                else:
                    choices, current, _ = self.pref_options(key)
                    value = next(title for title, v in choices if v == current)
                row.value_button.config(text=value + "  ›")

    def system_contents(self, parent):
        row = PrefRow(self, parent, "Room connection", "Check connection, what each state means", self.connection_text.get(), self.open_connection_sheet)
        row.pack(fill="x")
        self.system_connection_row = row
        head = tk.Frame(parent, bg=self.bg, height=52)
        head.pack(fill="x", pady=(16, 0))
        head.pack_propagate(False)
        label(self, head, "Room services").pack(side="left")
        self.diagnostics_check = Button(self, head, "Check now", lambda: self.check_room_diagnostics())
        self.diagnostics_check.pack(side="right", fill="y")
        self.diagnostics_message = label(self, parent, size="small", muted=True, wraplength=680)
        self.diagnostics_message.pack(fill="x", pady=(8, 0))
        self.diagnostics_age = label(self, parent, size="small", muted=True)
        self.diagnostics_age.pack(fill="x")
        self.diagnostics_rows = label(self, parent, size="small", wraplength=680)
        self.diagnostics_rows.pack(fill="x", pady=(4, 12))
        label(self, parent, "This panel").pack(anchor="w")
        self.power_label = label(self, parent, size="small", wraplength=680)
        self.power_label.pack(fill="x", pady=(8, 0))
        self.health_details = label(self, parent, size="small", muted=True, wraplength=680)
        self.health_details.pack(fill="x", pady=(4, 12))
        self.services_label = self.diagnostics_message
        slot(self, parent, "Maintenance commands  ›", lambda: self.open_maintenance(), height=52, pady=(0, 12))
        bottom = tk.Frame(parent, bg=self.bg, height=S["tap"])
        bottom.pack(fill="x")
        bottom.pack_propagate(False)
        self.power_buttons = []
        for operation, title in (("reboot", "Restart panel"), ("shutdown", "Shut down panel")):
            button = Button(self, bottom, title, lambda op=operation: self.confirm_power(op))
            button.pack(side="left", fill="y", padx=(0, 12))
            self.power_buttons.append((button, operation))
        slot(self, parent, "Open Legacy controls", lambda: self.show("original"), height=52, pady=(12, 0))
        self.update_room_diagnostics()
        self.refresh_system_facts()

    def refresh_system_facts(self):
        h = self.health_cache
        power = h.get("power", "Power status unavailable")
        if h.get("power_warning") and power in ("OK", "Power status unavailable"):
            power = "A low power supply warning was recorded. Check the Pi power supply."
        self.power_label.config(text="Power reading unavailable." if "error" in h and "power" not in h and not h.get("power_warning") else "Power supply: " + power,
                                fg=self.warning if h.get("power_warning") else self.muted)
        self.health_details.config(text="Processor: %s °C · Memory free: %s / %s MB\nDisk free: %s GB · Running for: %s days" % tuple(
            h.get(k, "—") for k in ("temperature", "ram_available", "ram_total", "disk_available", "uptime")))
        if "error" in h:
            self.health_details.config(text="Resource reading unavailable: " + h["error"])
        allowed = self.power_snapshot()
        for button, operation in getattr(self, "power_buttons", []):
            button.config(state="normal" if allowed.get("available") and allowed.get("actions", {}).get(operation) else "disabled")

    def check_room_diagnostics(self):
        self.refresh_status()
        self.update_room_diagnostics()

    def update_room_diagnostics(self):
        if not getattr(self, "diagnostics_message", None) or not self.diagnostics_message.winfo_exists():
            return
        data = self.room_diagnostics()
        self.diagnostics_message.config(text=data["detail"])
        age = data["age_s"]
        self.diagnostics_age.config(text="No successful service check yet." if age is None else "Last successful check: %d seconds ago" % max(0, age))
        self.diagnostics_rows.config(text=" · ".join(x["name"] + (" listed" if x["state"] == "listed" else " missing") for x in data["services"]) or "No observed service results yet.")
        self.diagnostics_check.config(text="Checking…" if data["checking"] else "Check now", state="normal" if data["can_check"] else "disabled")

    def open_maintenance(self, title=None, step=0):
        content = self.make_sheet("Maintenance commands", "maintenance")
        if title is None:
            label(self, content, "Steps for staff. Commands are shown here, never run by the panel.", muted=True, wraplength=610).pack(fill="x", pady=(0, 24))
            for name in ("Power", "Ubuntu checks", "Start services", "Restart computer"):
                slot(self, content, name + "  ›", lambda n=name: self.open_maintenance(n), pady=(0, 12))
            return
        data = reference(title)
        item = data["steps"][step]
        label(self, content, title, "title").pack(anchor="w")
        label(self, content, data["machine"] + " · " + data["effect"], "small", True, wraplength=610).pack(fill="x", pady=12)
        label(self, content, "%d / %d · %s" % (step+1, len(data["steps"]), item["title"]), wraplength=610).pack(fill="x", pady=12)
        for text in (item["why"], item["commands"], "Expect: " + item["expect"]):
            label(self, content, text, "small", wraplength=610).pack(fill="x", pady=12)
        if step + 1 < len(data["steps"]):
            slot(self, content, "Next step", lambda: self.open_maintenance(title, step+1), pady=12)
        if step:
            slot(self, content, "Previous step", lambda: self.open_maintenance(title, step-1), pady=12)
        slot(self, content, "All maintenance topics", lambda: self.open_maintenance(), pady=12)

    def about_contents(self, parent):
        for title, value in (("Version", VERSION), ("Build", BUILD_COMMIT or "Preview"),
                             ("Touch interface", "Diyanko Bhowmik"), ("Icons", "Lucide · lucide.dev")):
            label(self, parent, title, "small", True).pack(anchor="w", pady=(16, 4))
            label(self, parent, value).pack(anchor="w")
        label(self, parent, "LESA Smart Conference Room.\nOriginal contributors are in the project's Git history.", "small", True).pack(anchor="w", pady=24)
