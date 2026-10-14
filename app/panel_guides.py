"""Short display-only room guides. No command execution or hardware access."""

DEMO = (
    ('Lighting', 'room',
     'White-light colour changes from warm to cool. Light level controls the drive input.\n\n'
     'Fid, Sat and Dul recall existing eight-channel mixtures. The panel confirms fixture drive settings; it does not measure brightness.\n\n'
     'Open Room to try the controls with the room host.'),
    ('Room controls', 'on',
     'Beta provides everyday lighting, weather, help and panel status. Legacy opens the original room controls.\n\n'
     'Changing pages does not change the lights. Opening Legacy ends the Beta lighting session and restores its starting scene.\n\n'
     'The room also has blinds and other controls. Ask the host before demonstrations.'),
    ('Sensors and experiments', 'experiment',
     'The room brings together lighting, environmental readings and sensing systems.\n\n'
     'System lists advertised services. A listed service does not prove that a sensor is producing valid data.\n\n'
     'Practice runs instructions and panel annotations only. Sensor recording belongs to a separate experiment system.'),
    ('How it connects', 'health',
     'This cabinet panel is a client. The Ubuntu room computer hosts the existing ROS services.\n\n'
     'The connection badge describes this panel\'s lighting adapter. Tap it for System and troubleshooting.\n\n'
     'Visitor weather comes from Open-Meteo model data. It is separate from indoor sensors and room controls.'),
)

SUPPORT = (
    ('Lighting', 'room',
     'Ready means the lighting adapter is available. Sending means a request is awaiting readback.\n\n'
     'If Uncertain appears, stop changing lights and ask the room host. A failed response can leave the result unknown.\n\n'
     'If Offline appears, check the panel network cable and the room computer. Legacy also needs the room services.', ''),
    ('Power', 'on',
     'An undervoltage warning means the Pi supply voltage is too low. This can slow the panel and affect storage reliability.\n\n'
     'Check the supply, cable and connector. A separately powered LCD does not rule out a Pi power problem.\n\n'
     'Do not hide the warning or keep power-cycling to clear it. Shut down normally before changing power.',
     'Panel terminal: vcgencmd get_throttled'),
    ('Ubuntu checks', 'health',
     'Use a Terminal on the Ubuntu room computer. These commands inspect state; they do not start devices.\n\n'
     'ROS owns room controls. Status owns the TV display and its clients. Session presence alone does not prove health.',
     'hostname; uptime\nfree -m; df -h /\ntmux list-sessions\nsource /opt/ros/indigo/setup.bash\nsource ~/catkin_ws/devel/setup.bash\ntimeout 10 rosservice list'),
    ('Start services', 'health',
     'Room host only: stop experiments and check tmux sessions first. Use the installed launchers from their own folders.\n\n'
     'startROS.py destroys an existing ROS session. startStatus.py destroys an existing Status session. Do not run either as a quick connection fix.\n\n'
     'These are installed launch paths, not a qualified automatic recovery procedure.',
     'cd ~/catkin_ws/src/scr_control\npython startROS.py\n\ncd ~/scr.status_display\npython startStatus.py'),
    ('Restart computer', 'off',
     'Room host only: stop recordings and coordinate with other room users. A room-computer restart interrupts shared controls and feeds.\n\n'
     'Use the Ubuntu desktop Restart action, or the command below in its Terminal. Wait for the desktop and network, then check ROS and Status.\n\n'
     'Room-computer service autostart is not verified. Do not assume that a reboot restores everything.',
     'Ubuntu room computer only:\nsudo reboot'),
)


def connection(state, live=True):
    """Adapter state only; no claim of continuous or physical device health."""
    if not live:
        return 'Preview', 'link-off', 'neutral'
    return {'ready': ('Ready', 'link-ok', 'good'),
            'applying': ('Sending', 'clock', 'waiting'),
            'connecting': ('Checking', 'clock', 'waiting'),
            'failed': ('Uncertain', 'link-off', 'warning')}.get(state, ('Offline', 'link-off', 'neutral'))
