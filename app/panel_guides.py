"""Short display-only room guides. No command execution or hardware access."""

from help_reference import commands as reference_commands

DEMO = (
    (
        "Lighting",
        "on",
        "Use Lights on and Lights off on Home for everyday lighting.\n\n"
        "Room tools → Lighting brings White light, Scenes, Programmes and Channels together. Opening a tab does not change the lights.\n\n"
        "A highlighted button shows the last confirmed setting. If a result is uncertain, stop and ask the room host.",
    ),
    (
        "Room controls",
        "home",
        "Home always returns to everyday lighting controls. Opening a page does not change the lights.\n\n"
        "Legacy opens the original interface after restoring the starting lighting scene. Use Home in the Legacy bar to return.\n\n"
        "Lift blinds, Open slats and Close & lower are on Home. Room tools → Screen & controls saves whether blind movement is enabled and whether the controls are shown. Movement is disabled by default and also requires a connected controller.",
    ),
    (
        "Sensors and experiments",
        "experiment",
        "Experiment mode guides a repeatable sequence of instructions and saves panel annotations.\n\n"
        "It does not start a recorder. Arrange recording separately and coordinate the study with the room host.\n\n"
        "Room tools → System & help shows room service availability. Availability alone does not prove usable sensor data.",
    ),
    (
        "How it connects",
        "health",
        "The touch panel and trusted-network website share the same room controls. Legacy’s original controls remain on the touch panel.\n\n"
        "The lighting badge shows this panel’s connection: Ready, Sending, Offline or Uncertain. Tap it for System & help.\n\n"
        "Weather is an outdoor model estimate, separate from indoor measurements. Source details are under Room tools → Date & weather.",
    ),
)

SUPPORT = (
    (
        "Lighting",
        "room",
        "Ready means the lighting adapter is available. Sending means a request is awaiting readback.\n\n"
        "If Uncertain appears, stop changing lights and ask the room host. A failed response can leave the result unknown.\n\n"
        "If Offline appears, check the panel network cable and the room computer. Legacy also needs the room services.",
        "",
    ),
    (
        "Power",
        "on",
        "Low supply voltage can slow the Pi and affect storage reliability. Check its supply, cable and connector; a separately powered LCD does not rule out a Pi power problem.\n\n"
        "Open the reference to distinguish current warnings from earlier ones. Do not hide warnings or repeatedly power-cycle. Shut down normally before changing power.",
        reference_commands("Power"),
    ),
    (
        "Ubuntu checks",
        "health",
        "Use a Terminal on the Ubuntu room computer. These commands inspect state; they do not start devices.\n\n"
        "ROS owns room controls. Status owns the TV display and its clients. Session presence alone does not prove health.",
        reference_commands("Ubuntu checks"),
    ),
    (
        "Start services",
        "health",
        "Room host only: stop experiments and check tmux sessions first. "
        "startROS.py replaces the ROS session; startStatus.py replaces Status. Do not use them as a quick connection fix.\n\n"
        "Installed paths below are instructions only, not automatic recovery.",
        reference_commands("Start services"),
    ),
    (
        "Restart computer",
        "off",
        "Room host only: stop recordings and coordinate with other room users. Restarting interrupts shared controls and feeds.\n\n"
        "Use the Ubuntu Restart action or its Terminal command below. After the desktop and network return, check ROS and Status; service autostart is not verified.",
        reference_commands("Restart computer"),
    ),
)


def connection(state, live=True):
    """Adapter state only; no claim of continuous or physical device health."""
    if not live:
        return "Preview", "link-off", "neutral"
    return {
        "ready": ("Ready", "link-ok", "good"),
        "applying": ("Sending", "clock", "waiting"),
        "connecting": ("Checking", "clock", "waiting"),
        "failed": ("Uncertain", "link-off", "warning"),
    }.get(state, ("Offline", "link-off", "neutral"))
