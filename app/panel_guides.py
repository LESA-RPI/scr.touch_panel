"""Short display-only room guides. No command execution or hardware access."""

from help_reference import commands as reference_commands

DEMO = (
    (
        "Lighting",
        "on",
        "Use Lights on and Lights off on Home for everyday lighting.\n\n"
        "Room tools → Lighting brings White light, Scenes, Programmes and Channels together. Opening a tab does not change the lights.\n\n"
        "A highlighted button shows the last confirmed setting. If a result is unconfirmed, do not repeat it. Check connection reads current lighting without changing it; ask the room host if controls stay unavailable.",
    ),
    (
        "Room controls",
        "home",
        "Home opens the everyday room page. Opening a page does not change the lights.\n\n"
        "Legacy opens the original controls. Home stops any Legacy programme and returns to Beta after checking the connection, keeping current light levels. If controls stay unavailable, ask the room host.\n\n"
        "Lift blinds, Open slats and Close & lower are on Home. Room tools → Screen & controls saves whether blind movement is enabled and whether the controls are shown. Movement is disabled by default and also requires a connected controller.",
    ),
    (
        "Sensors and experiments",
        "experiment",
        "Experiment mode guides a repeatable sequence of instructions and saves panel annotations.\n\n"
        "It does not start a recorder. Arrange recording separately. An experiment must reserve lighting before it starts, then close its workers and return verified everyday control when finished.\n\n"
        "Room tools → System & help shows room service availability. Availability alone does not prove usable sensor data.",
    ),
    (
        "How it connects",
        "health",
        "Beta and the trusted-network website share one room controller. Legacy hands control to the unchanged original application.\n\n"
        "The lighting status explains when controls are ready, reserved for an experiment, checking or unconfirmed. Website offline means the page cannot reach the panel. Open System & help for guidance.\n\n"
        "Weather is an outdoor model estimate, separate from indoor measurements. Source details are under Room tools → Date & weather.",
    ),
)

SUPPORT = (
    (
        "Lighting",
        "room",
        "Check connection reads current settings without changing the lights. If a result is unconfirmed, do not repeat the command; ask the room host. Experiment controls return after cleanup.",
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
