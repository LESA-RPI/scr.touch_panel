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

# One sharp (square-cornered) design system for the touch panel and the website. Pixel values; the
# panel uses "panel" (1280 x 800 touch), the website uses "web" (phone to desktop).
SCALE = {
    "panel": {"text": 20, "small": 16, "title": 24, "heading": 34, "display": 120,
              "tap": 72, "space": 24, "pad": 28, "radius": 0, "card_radius": 0, "line": 1},
    "web": {"text": 16, "small": 14, "title": 19, "heading": 30, "display": 84,
            "tap": 48, "space": 20, "pad": 28, "radius": 0, "card_radius": 0, "line": 1},
}


def css():
    """Generated browser/tokens.css: colour roles per theme plus the web scale."""
    def block(selector, values):
        lines = "".join("  --%s:%s;\n" % (name.replace("_", "-"), value) for name, value in values.items())
        return "%s{\n%s}\n" % (selector, lines)

    scale = {name: "%dpx" % value for name, value in SCALE["web"].items()}
    return (
        "/* Generated from app/design_tokens.py by app/export_room_content.py. Do not edit. */\n"
        + block(":root", dict(THEMES["light"], **scale))
        + block("[data-theme=dark]", THEMES["dark"])
        # Follow the device before any script runs, so dark phones never flash light.
        + "@media (prefers-color-scheme: dark){\n"
        + block(":root:not([data-theme=light])", THEMES["dark"])
        + "}\n"
    )


WEATHER_ACCENTS = {
    name: "weather_warm" for name in ("sun", "moon", "cloud-sun", "cloud-moon")
}
WEATHER_ACCENTS.update(
    {name: "weather_cool" for name in ("cloud-rain", "cloud-snow", "cloud-lightning")}
)
