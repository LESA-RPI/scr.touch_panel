"""Clock, weather and screensaver presentation for the Tk owner."""

import datetime
import panel_icons
import tkinter as tk
import weather as weather_data
from panel_common import monotonic, set_changed


class PanelScreensaver:
    def sync_idle_clock(self, *unused):
        value = self.visitor_time.get()
        digits, period = (
            value.rsplit(" ", 1) if value.endswith((" AM", " PM")) else (value, "")
        )
        set_changed(self.idle_digits, digits)
        set_changed(self.idle_period, period)

    def screensaver_view(self):
        top = tk.Frame(self.body, bg=self.bg, height=76)
        top.pack(fill="x", padx=28, pady=(28, 0))
        top.pack_propagate(False)
        if self.artwork:
            tk.Label(top, image=self.artwork, bg="white", bd=0).pack(
                side="left", anchor="n", padx=(0, 20)
            )
        self.label(top, "Smart Conference Room", 28).pack(side="left", anchor="s")
        self.label(top, "SCREEN SAVER", 17, True).pack(side="right")
        bottom = tk.Frame(self.body, bg=self.bg)
        bottom.pack(side="bottom", fill="x", padx=100, pady=(0, 44))
        self.row_buttons(
            bottom,
            [("Touch anywhere to open controls", self.return_from_idle, True)],
            height=72,
        )
        hint = self.label(bottom, "Home gives you Lights on and Lights off", 17, True)
        hint.config(anchor="center")
        hint.pack(fill="x", pady=(12, 0))
        row = tk.Frame(self.body, bg=self.bg)
        row.pack(fill="both", expand=True, padx=48, pady=(44, 24))
        row.columnconfigure(0, weight=46, uniform="idle")
        row.columnconfigure(1, minsize=1)
        row.columnconfigure(2, weight=54, uniform="idle")
        left = tk.Frame(row, bg=self.bg)
        left.grid(row=0, column=0, sticky="nsew", padx=(18, 32))
        tk.Frame(row, bg=self.border, width=1).grid(
            row=0, column=1, sticky="ns", pady=(0, 20)
        )
        right = tk.Frame(row, bg=self.bg)
        right.grid(row=0, column=2, sticky="nsew", padx=(32, 18))
        self.label(left, "LOCAL TIME", 16, True).pack(anchor="w")
        time_row = tk.Frame(left, bg=self.bg)
        time_row.pack(fill="x", pady=(20, 12))
        self.sync_idle_clock()
        clock = self.label(time_row, size=104)
        clock.config(textvariable=self.idle_digits)
        clock.pack(side="left")
        period = self.label(time_row, size=24, muted=True)
        period.config(textvariable=self.idle_period)
        period.pack(side="left", anchor="s", padx=(12, 0), pady=(0, 22))
        date = self.label(left, size=21)
        date.config(textvariable=self.visitor_date)
        self.wrap_label(date).pack(fill="x")
        self.weather_contents(right, compact=True, large=True)

    def weather_contents(self, right, compact=False, large=False):
        heading = tk.Frame(right, bg=right.cget("bg"))
        heading.pack(fill="x")
        self.label(
            heading,
            (
                "OUTDOOR WEATHER"
                if compact
                else "WEATHER · " + getattr(self.args, "weather_name", "Local area")
            ),
            16,
            True,
        ).pack(side="left")
        if large:
            self.label(
                heading, getattr(self.args, "weather_name", "Local area"), 14, True
            ).pack(side="right")
        reading = tk.Frame(right, bg=right.cget("bg"))
        reading.pack(
            fill="x", pady=(12, 4) if large else (6, 2) if compact else (18, 6)
        )
        self.weather_symbol_size = 128 if large else 96
        self.weather_symbol = tk.Canvas(
            reading,
            width=self.weather_symbol_size,
            height=self.weather_symbol_size,
            bg=right.cget("bg"),
            highlightthickness=0,
        )
        self.weather_symbol_key = None
        self.weather_symbol_item = None
        self.weather_symbol.pack(side="right", pady=0 if compact else 12)
        size = 72 if large else 50 if compact else 68
        temperature = self.label(reading, size=size)
        temperature.config(textvariable=self.weather_temperature)
        temperature.pack(side="left")
        self.label(reading, self.temperature_unit.upper(), 24, True).pack(
            side="left", anchor="s", pady=18, padx=4
        )
        condition = self.label(right, size=26 if large else 23)
        condition.config(textvariable=self.weather_condition)
        self.wrap_label(condition).pack(fill="x")
        self.weather_measurements = tk.Frame(right, bg=right.cget("bg"))
        self.weather_measurements.pack(fill="x", pady=(10 if large else 6, 2))
        self.weather_metric_cells = []
        self.weather_metric_values = []
        for index, (title, unused) in enumerate(weather_data.measurements({})):
            self.weather_measurements.columnconfigure(
                index % 2, weight=1, uniform="forecast"
            )
            cell = tk.Frame(self.weather_measurements, bg=right.cget("bg"))
            cell.grid(
                row=index // 2,
                column=index % 2,
                sticky="ew",
                padx=(0, 18) if index % 2 == 0 else (18, 0),
                pady=4 if large else 2,
            )
            cell.columnconfigure(0, weight=1)
            self.label(cell, title, 17 if large else 16, True).grid(
                row=0, column=0, sticky="w"
            )
            value = self.label(cell, "—", 17 if large else 16)
            value.grid(row=0, column=1, sticky="e", padx=(12, 0))
            self.weather_metric_cells.append(cell)
            self.weather_metric_values.append(value)
        self.weather_notice = self.label(self.weather_measurements, size=16, muted=True)
        self.wrap_label(self.weather_notice)
        self.daylight_label = self.label(right, size=21)
        self.daylight_label.pack(anchor="w", pady=(8, 2) if compact else (18, 2))
        self.daylight_canvas = tk.Canvas(
            right, height=60, bg=right.cget("bg"), highlightthickness=0
        )
        self.daylight_drawn = None
        self.daylight_canvas.pack(fill="x")
        self.daylight_canvas.bind("<Configure>", lambda event: self.update_daylight())
        self.update_weather(force=True)
        self.start_weather()

    def weather_is_earlier(self):
        data = self.weather_reading
        return bool(
            data
            and (
                self.weather_good is None
                or monotonic() - self.weather_good > 1800
                or any(
                    data[key][:10] != datetime.date.today().isoformat()
                    for key in ("model_time", "sunrise", "sunset")
                )
                or self.weather_text.get().startswith("Last available")
            )
        )

    def update_weather(self, force=False):
        if (
            self.mode not in ("room", "visitor")
            or self.mode == "room"
            and self.section != "basic"
        ):
            return
        now = datetime.datetime.now()
        minute = now.strftime("%Y-%m-%dT%H:%M")
        earlier = self.weather_is_earlier()
        render_key = (minute, earlier)
        if not force and render_key == self.weather_rendered_minute:
            return
        self.weather_rendered_minute = render_key
        data = self.weather_reading
        readings = weather_data.measurements(data or {}, self.temperature_unit, earlier)
        show = bool(data and not earlier)
        for index, cell in enumerate(self.weather_metric_cells):
            if show:
                if not cell.winfo_manager():
                    cell.grid()
                if self.weather_metric_values[index].cget("text") != readings[index][1]:
                    self.weather_metric_values[index].config(text=readings[index][1])
            elif cell.winfo_manager():
                cell.grid_remove()
        if show:
            if self.weather_notice.winfo_manager():
                self.weather_notice.grid_remove()
        else:
            notice = (
                weather_data.details(data, self.temperature_unit, earlier=True)
                if data
                else "Weather unavailable"
            )
            self.weather_notice.config(text=notice)
            self.weather_notice.grid(row=0, column=0, columnspan=2, sticky="ew", pady=4)
        if not data:
            set_changed(self.weather_temperature, "—")
            set_changed(self.weather_condition, "Weather unavailable")
            if self.weather_symbol_key is not None:
                self.weather_symbol.delete(self.weather_symbol_item)
                self.weather_symbol_key = None
                self.weather_symbol_item = None
            self.update_daylight()
            return
        primary = (
            data["temperature_c"]
            if self.temperature_unit == "c"
            else data["temperature_f"]
        )
        set_changed(self.weather_temperature, "%.0f°" % primary)
        set_changed(self.weather_condition, data["condition"])
        sunrise, sunset = weather_data.local_time(
            data["sunrise"]
        ), weather_data.local_time(data["sunset"])
        current_day = sunrise.date() == now.date() == sunset.date()
        night = current_day and not sunrise <= now < sunset
        kind = panel_icons.weather_kind(data["code"], night)
        # Earlier daylight data cannot establish whether it is currently day or night.
        if not current_day and data["code"] in (0, 1, 2):
            kind = "circle-question-mark"
        size = self.weather_symbol_size
        key = ("weather", kind, self.theme, size)
        if key not in self.icon_cache:
            self.photo(key, panel_icons.weather(kind, self.theme, size))
        if self.weather_symbol_key != key:
            if self.weather_symbol_item is None:
                self.weather_symbol_item = self.weather_symbol.create_image(
                    size // 2, size // 2, image=self.icon_cache[key]
                )
            else:
                self.weather_symbol.itemconfigure(
                    self.weather_symbol_item, image=self.icon_cache[key], state="normal"
                )
            self.weather_symbol_key = key
        self.update_daylight()

    def update_daylight(self):
        """Resize the daylight line without repainting the forecast or its icon."""
        canvas = self.daylight_canvas
        data = self.weather_reading
        earlier = self.weather_is_earlier()
        day = (
            weather_data.daylight(data, datetime.datetime.now())
            if data and not earlier
            else None
        )
        text = (
            day["label"]
            if day
            else (
                "Daylight times unavailable"
                if not data
                else (
                    "Daylight information is not current"
                    if earlier
                    else "Daylight times are from another date"
                )
            )
        )
        key = (
            canvas.winfo_width(),
            text,
            None if day is None else tuple(sorted(day.items())),
        )
        if key == self.daylight_drawn:
            return
        self.daylight_drawn = key
        if self.daylight_label.cget("text") != text:
            self.daylight_label.config(text=text)
        canvas.delete("all")
        if day is None or canvas.winfo_width() < 2:
            return
        left, right, y = 8, max(24, canvas.winfo_width() - 8), 22
        position = left + (right - left) * day["fraction"]
        canvas.create_line(
            left, y, right, y, fill=self.control, width=6, capstyle="round"
        )
        if position > left:
            canvas.create_line(
                left, y, position, y, fill=self.icon_colour, width=6, capstyle="round"
            )
        canvas.create_oval(
            position - 7,
            y - 7,
            position + 7,
            y + 7,
            fill=self.icon_colour,
            outline=self.surface,
            width=2,
        )
        canvas.create_text(
            left,
            46,
            text="Sunrise " + day["sunrise"],
            anchor="w",
            font=(self.font_family, 15),
            fill=self.muted,
        )
        canvas.create_text(
            right,
            46,
            text="Sunset " + day["sunset"],
            anchor="e",
            font=(self.font_family, 15),
            fill=self.muted,
        )
