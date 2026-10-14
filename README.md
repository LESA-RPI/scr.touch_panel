# SCR room touch panel

Touch controls for the LESA Smart Conference Room. The original application and
the beta client have separate entrypoints:

| Version | Entrypoint | Purpose |
|---|---|---|
| Original | [main.py](main.py) | Existing room lighting, blinds and demo controls; requires the installed room environment |
| Beta | [app/scr_touch_panel.py](app/scr_touch_panel.py) | Lighting, status, settings and experiment practice, with touch access to Original |

The original source remains unchanged. Beta complements it; complete feature
parity is a promotion requirement, not a current claim. Project-X is an optional
consumer and maintains its recorder integration separately.

## Start with a local beta preview

Use a desktop Python 3.11 or newer with Tk available. `python -m tkinter` checks
Tk and opens its version window ([Python documentation](https://docs.python.org/3/library/tkinter.html)).
On a new Linux desktop, install the distribution's Tk and virtual-environment
packages first. On Windows, use `python` instead of `python3` below and activate
the environment with `.venv\Scripts\Activate.ps1`.

```sh
git clone https://github.com/LESA-RPI/scr.touch_panel.git
cd scr.touch_panel
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r app/requirements.txt
python -B app/scr_touch_panel.py --windowed --duration 600 --theme light
```

This preview does not move room devices or start recording. Lighting is disabled
until a connected adapter is admitted. The installed panel layout is 1280 × 800;
`--windowed` permits desktop review on other screens. It is a Tk desktop client;
browser/tablet clients are future work.

## Use the installed room panel

On the cabinet, **Legacy** opens the original controls. Its touch navigation strip
returns to **Beta**. Both applications remain separate. Credits are under
**Settings → About panel**. The light theme uses a white background with blue
controls; navigation remains in the same position across modes.

The existing Pi can run the beta with its installed Python 2.7/Tk/Pillow stack.
Do not apply the modern preview requirements to that legacy environment.
The launcher [app/start_panel.sh](app/start_panel.sh) reads private deployment
settings, sources the custom ROS workspace, starts one original application if
needed, and opens Beta. Setup, autostart and rollback are in
[the operating guide](WORKFLOWS.md#startup-and-rollback).

Connected control requires the existing room ROS master and custom SCR service
bindings. The UI and ROS helper can use different interpreters. A modern UI does
not require upgrading the room servers. The current helper defaults to the
installed Python 2.7 ROS environment. A new interpreter or transport needs
separate interface validation; ROS 2 is not a drop-in ROS 1 replacement.

Sliders send the latest selection after 250 ms without movement. The adapter
requires an exactly restorable Fid, Sat, Dul or Off baseline; it restores that
baseline before Original controls or exit. Uncertain results disable writes.
Displayed light levels are controller inputs, not optical measurements.
Read [connected-control checks](WORKFLOWS.md#before-connected-control) before
enabling the adapter. Room ownership must also be checked outside this Pi.

System reports panel readings and advertised service presence, not physical
sensor or blind health. Experiment practice saves panel annotations with
`recording: false`. A two-second stationary press leaves the black screen;
black pixels do not turn off its backlight.

**Visitor** shows a large clock, short room instructions and optional local
weather. **Practice** names the existing experiment practice page; it does not
start a recorder. Room scenes retain Fid, Sat and Dul names shared with Legacy.
Visitor → Demo guide explains lighting, room controls, sensing and connections.
The guide is informational and does not operate devices.
Lighting feedback distinguishes selection, sending and confirmed controller
drive settings. Large values are labelled selected; the feedback area retains
the last confirmed drive inputs until matching readback arrives. It is a historical
confirmation, not continuous monitoring or measured optical brightness.
**What do these do?** opens a short lighting guide without changing lights.

The installed launcher saves theme, clock style, weather temperature units, help tips and theme schedule
in a private appearance file. It saves no light settings or recording state.
Weather uses [Open-Meteo](https://open-meteo.com/en/docs), with a location set
outside Git. Requests run in a separate helper and refresh at most every 15
minutes while Visitor is open. Failed refreshes retain clearly labelled old
data. Weather is model data, independent of room sensors and light control.
See [appearance and weather setup](WORKFLOWS.md#appearance-and-weather).

The UI uses Cantarell when installed; `--font` selects another installed family.
Settings → About shows the family Tk actually renders, including any fallback.
Light mode keeps a white surface and neutral controls. Dark mode uses charcoal
and grayscale surfaces, with blue accents. Settings keeps categories beside one
detail pane. Lighting uses large selection values and a fixed feedback area.
Visitor shows a daylight timeline only for valid sunrise/sunset dates; the bar
updates once per minute without animation. Stale weather stays labelled.
Settings → Date & weather switches Celsius/Fahrenheit without another API call.
Prose wraps to allocated card width; feedback and annotation areas reserve space.
The header badge combines an icon, text and colour for the lighting adapter state.
Tap it for System. Ready means the adapter is available; it is not continuous
device-health monitoring. System → Troubleshooting provides checks and operator
startup/reboot instructions. Displayed commands are never executed by the panel.

## Restore or provision hardware

For the installed legacy system, obtain the verified private recovery image and
current restore guide from the room custodian. They preserve the OS, ROS, custom
workspace and private startup/network settings. Git alone is not a system backup.
[Backup and rebuild guidance](WORKFLOWS.md#backup-and-rebuild) covers image checks,
different SD/USB identifiers, new hardware and acceptance tests.

A fresh OS is a separate migration. Keep current Python/Tk/Pillow for new UI
deployments, and validate their room adapter independently. ROS 1 has reached
end of life ([Open Robotics](https://discourse.ros.org/t/ros-noetic-end-of-life-may-31-2025/43160));
do not treat the old cabinet stack as the default for every future device.
Do not change the working fleet during migration trials.

The [fresh Raspberry Pi OS procedure](WORKFLOWS.md#fresh-raspberry-pi-os)
uses distribution Python 3 for both applications and the ROS client. It requires
the room's custom service bindings, not a ROS master on the panel. Fresh-install
work is tracked on `experiment/fresh-pi-setup-20261013` until promotion to `main`.

## Maintain and extend

Run `python -m pytest tests` with pytest installed. Checks cover baseline restore,
uncertain operations, external changes, profiles and dynamic input cancellation.
The installed Pi has had bounded touch/navigation and connected-light trials;
replacement boot, prolonged reliability and new hardware still require validation.
The modern preview has been checked with Python 3.11.10, Tk 8.6 and Pillow 12.0.0.

[The interface contract](docs/interface.md) owns profiles, events and the adapter
boundary. Keep experiments independent of room controls. Use one cohesive commit
for a tested change; keep private captures, credentials, temporary tools and
incident timelines outside this public repository. Preserve published release
identities when consolidating later documentation history.

Beta author: **Diyanko Bhowmik**, with Codex assistance. Original contributors
remain in Git history. The supplied LESA logo is retained unchanged; SHA-256:
`ea6224069408b6cc1e3833793ab7f0d627898ff1c6dd71436818dbc83b4ea13b`.
