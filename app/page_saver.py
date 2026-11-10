"""Quiet clock/weather views; the Panel owns all idle and wake rules."""
import datetime
import tkinter as tk
import panel_icons
import weather as weather_data
from panel_common import monotonic, set_changed
from ui_widgets import S, label


class SaverPage:
    def sync_idle_clock(self, *unused):
        value = self.visitor_time.get()
        digits, period = value.rsplit(" ", 1) if value.endswith((" AM", " PM")) else (value, "")
        set_changed(self.idle_digits, digits)
        set_changed(self.idle_period, period)

    def screensaver_view(self):
        centre = tk.Frame(self.body, bg=self.bg)
        centre.place(relx=.5, rely=.42, anchor="center")
        row = tk.Frame(centre, bg=self.bg)
        row.pack()
        label(self, row, textvariable=self.idle_digits, size=S["display"]*2).pack(side="left")
        label(self, row, textvariable=self.idle_period, size="heading", muted=True).pack(side="left", anchor="s", pady=36)
        label(self, centre, textvariable=self.visitor_date, size="heading").pack(pady=(0, 28))
        self.saver_weather = label(self, centre, size="title", muted=True)
        self.saver_weather.pack()
        label(self, self.body, "Smart Conference Room", "small", True).place(x=56, rely=1, y=-76, anchor="sw")
        self.readback_label(self.body, small=True).place(x=56, rely=1, y=-36, anchor="sw", width=380)
        label(self, self.body, "Touch anywhere for room controls", "title", True).place(relx=.5, rely=1, y=-40, anchor="s")
        qr = tk.Frame(self.body, bg=self.bg)
        qr.place(relx=1, rely=1, x=-56, y=-40, width=250, height=128, anchor="se")
        self.saver_qr(qr)
        self.update_weather()

    def saver_qr(self, parent):
        import room_controls
        # Reuse the same QR artwork; the password remains in the Guide card only.
        from pathlib import Path
        key = "saver-qr"
        if key not in self.icon_cache:
            from PIL import Image, ImageTk
            image = Image.open(Path(__file__).resolve().parents[1] / "assets/website-qr.png")
            self.icon_cache[key] = ImageTk.PhotoImage(image.resize((110, 110), Image.Resampling.NEAREST))
        tk.Label(parent, image=self.icon_cache[key], bg="white", bd=0).pack(side="right")
        label(self, parent, "Room website\nWi-Fi " + room_controls.ROOM_NETWORK_NAME, "small", True).pack(side="right", padx=12)

    def weather_contents(self, parent):
        row = tk.Frame(parent, bg=self.bg)
        row.pack(fill="x", pady=(4, 12))
        self.weather_symbol = label(self, row)
        self.weather_symbol.pack(side="left", padx=(0, 12))
        label(self, row, textvariable=self.weather_temperature, size=S["display"] // 2).pack(side="left", padx=(0, 12))
        text = tk.Frame(row, bg=self.bg)
        text.pack(side="left", fill="x", expand=True)
        label(self, text, textvariable=self.weather_condition, size="title", wraplength=200).pack(anchor="w")
        self.weather_feels = label(self, text, size="small", muted=True)
        self.weather_feels.pack(anchor="w", pady=(4, 0))
        self.weather_facts = label(self, parent, size="text", muted=True, wraplength=440)
        self.weather_facts.pack(fill="x")
        self.daylight_label = label(self, parent, size="small", muted=True, wraplength=440)
        self.daylight_label.pack(side="bottom", fill="x", pady=(0, 8))
        self.weather_notice = label(self, parent, size="small", muted=True, wraplength=440)
        self.weather_notice.pack(side="bottom", fill="x", pady=(0, 12))
        self.update_weather(force=True)

    def weather_is_earlier(self):
        data = self.weather_reading
        return bool(data and (self.weather_good is None or monotonic()-self.weather_good > 1800
                    or any(data[key][:10] != datetime.date.today().isoformat() for key in ("model_time", "sunrise", "sunset"))
                    or self.weather_text.get().startswith("Last available")))

    def update_weather(self, force=False):
        data = self.weather_reading
        old = self.weather_is_earlier()
        suffix = "_c" if self.temperature_unit == "c" else "_f"
        def temp(key):
            value = (data or {}).get(key+suffix)
            return "—" if value is None else "%.0f°" % value
        condition = (data or {}).get("condition", "Weather unavailable")
        set_changed(self.weather_temperature, temp("temperature"))
        set_changed(self.weather_condition, condition + (" · earlier" if old else ""))
        rain = (data or {}).get("rain_chance")
        facts = "High %s · Low %s · Rain today %s" % (temp("high"), temp("low"), "—" if rain is None else "%d%%" % rain)
        if not data:
            facts = "Weather unavailable right now."
        if getattr(self, "saver_weather", None) is not None and self.saver_weather.winfo_exists():
            self.saver_weather.config(text=(temp("temperature") + " " + condition + " · " + facts if data else facts) + (" · earlier forecast" if old else ""))
            self.saver_weather.config(image=self.weather_icon(data, 32) if data else "", compound="left", padx=12)
        if not getattr(self, "weather_symbol", None) or not self.weather_symbol.winfo_exists():
            return
        self.weather_facts.config(text=facts)
        self.weather_feels.config(text="Feels like " + temp("feels_like") if data else "")
        self.weather_notice.config(text="Earlier forecast · check Date & weather" if old else "")
        if data:
            sunrise, sunset = weather_data.local_time(data["sunrise"]), weather_data.local_time(data["sunset"])
            self.weather_symbol.config(image=self.weather_icon(data, 56))
            self.daylight_label.config(text="Sunrise %s     Sunset %s" % (sunrise.strftime("%H:%M"), sunset.strftime("%H:%M")) if not old else "Daylight information is not current")
        else:
            self.weather_symbol.config(image="")
            self.daylight_label.config(text="Daylight times unavailable")

    def weather_icon(self, data, size):
        now = datetime.datetime.now()
        sunrise, sunset = weather_data.local_time(data["sunrise"]), weather_data.local_time(data["sunset"])
        current = sunrise.date() == now.date() == sunset.date()
        kind = panel_icons.weather_kind(data["code"], current and not sunrise <= now < sunset)
        if not current and data["code"] in (0, 1, 2):
            kind = "circle-question-mark"
        key = ("weather", kind, self.theme, size)
        if key not in self.icon_cache:
            self.photo(key, panel_icons.weather(kind, self.theme, size))
        return self.icon_cache[key]
