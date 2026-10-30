"""Room signage: neutral controls and typography; colour for data and warnings."""

THEMES = {
    "light": {
        "bg": "#ffffff",
        "surface": "#f5f6f7",
        "ink": "#24292d",
        "muted": "#596269",
        "control": "#e0e5e8",
        "border": "#c9ced2",
        "accent": "#364047",
        "selected_ink": "#ffffff",
        "accent_pressed": "#444f57",
        "pressed": "#d2d9dd",
        "icon_colour": "#515d65",
        "good": "#1d6f44",
        "warning": "#875709",
        "weather_warm": "#a16a24",
        "weather_cool": "#3b7590",
    },
    "dark": {
        "bg": "#171717",
        "surface": "#202020",
        "ink": "#f2f2f2",
        "muted": "#bdbdbd",
        "control": "#303030",
        "border": "#4d4d4d",
        "accent": "#d2d2d2",
        "selected_ink": "#202020",
        "accent_pressed": "#f2f2f2",
        "pressed": "#414141",
        "icon_colour": "#c7cbce",
        "good": "#89caa2",
        "warning": "#e8b86a",
        "weather_warm": "#e5b874",
        "weather_cool": "#8cb8db",
    },
}

WEATHER_ACCENTS = {
    name: "weather_warm" for name in ("sun", "moon", "cloud-sun", "cloud-moon")
}
WEATHER_ACCENTS.update(
    {name: "weather_cool" for name in ("cloud-rain", "cloud-snow", "cloud-lightning")}
)
