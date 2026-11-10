# SCR room touch panel

Touch controls and room guidance for the LESA Smart Conference Room. **Beta**
provides everyday lighting, room guidance and a shared website. **Legacy** opens the
unchanged original application, with a navigation strip above it. Its original
controls and behaviour remain the stable fallback while Beta is under development.

Earlier navigation, reliability and Legacy-parity changes are reviewed in
[PR #3](https://github.com/LESA-RPI/scr.touch_panel/pull/3), on
`fix/panel-navigation-transitions`. The earlier setup is recorded in
[PR #1](https://github.com/LESA-RPI/scr.touch_panel/pull/1). An installed cabinet may
run a different commit; check its release identity before maintenance.

The current source version is **0.2.20**, owned by
[app/panel_version.py](app/panel_version.py).
It is for About and internal development/GitHub tracking; everyday headers say
Beta. Legacy is the preserved older baseline for backtracking, identified by Git
history rather than an invented release number. The Git commit identifies exactly
what is deployed. No automatic tags or
separate release process are required.

## For room users

| Screen | Purpose |
|---|---|
| Home | Lights on/off, optional blind controls and clock/weather |
| Lights | White light, Scenes, Programmes and Channels |
| Guide | Room tour and Using the controls, with a topic list beside the content |
| Settings | Screen, Appearance, Date & weather, System and About |

Home is the default screen. **Lights on applies Fid** on both Beta and the website.
**Warm white** (3500 K, level 1000, the former On setting) is under Lights → White
light. Sliders apply when you let go. Fid, Sat and Dul retain their original
mixtures; Gradient spreads colour across the ten lights. Scenes show their
eight-channel mixtures and identify the confirmed current scene with text.
Sun and Circ Start controls and Stop programmes appear when the programme service
is configured. A programme acknowledgement confirms acceptance, not live operation.
A manual lighting action stops programmes before applying. Browsing another page
keeps the existing controller and does not change lights or start equipment.

The line below the controls reports the last confirmed lights and their age.
The status chip opens **Room connection**, with current connection details,
**Check connection** and **Open Legacy controls**. Check connection reads current
settings; after an uncertain handoff it stops programmes and confirms stable
settings while keeping light levels. Uncertain results block further changes
until checked. Legacy is also available under Settings → System. It opens the
original app on demand while website lighting pauses. Its **Back to Home** button
closes Legacy and checks the lights before returning to Ready.

Blinds are locked by default. Settings → Screen saves movement permission and
whether the blind controls appear on Home. Unlocking is available only with a
connected controller, and does not itself move equipment. When unlocked and
connected, Home offers Lift blinds, Open slats and Close & lower. Acceptance does
not measure physical blind position.

Guide explains lighting, COMBO distance/colour sensing, IRMA distance arrays and
the Color network. Its ceiling map shows one family at a time. Tap a marker for
its reference and R/C cell; mapped positions do not prove connection or recording.
The panel's phone card shows the room Wi-Fi and website QR code. The privately
configured Wi-Fi key appears only on the physical panel; ask the room host if it
is unavailable. The [LESA room guide](https://app.notion.com/p/f8f36eb121b04faeac3259d5ce380308)
provides broader room and research context.

Each saved preference is a row showing its current value; tap it to open a picker.
Preferences belong to this panel and never move equipment. Settings → System
shows dated room-service registrations, **Check now**, panel facts and plain power
warnings. Registration does not prove fresh sensor data. Service checks run only
when requested. Maintenance commands are shown step by step and never executed
by the panel. Restart and Shut down retain their explicit confirmation and
controller-cleanup checks. Indoor measurements remain on TV/Status.

Home shows local time, outdoor conditions, feels-like temperature, today's
high/low, rain chance and sunrise/sunset when available. Date & weather has source
details. Earlier forecasts are marked. The screen saver centres the clock, date
and one weather line, with last confirmed lights and the phone QR along the bottom.
It starts after five idle minutes by default; Screen settings can change this or
preview it. The first wake touch opens Home without activating a control. Active
touches, pending commands, Legacy, blank display and uncertain results keep their
existing idle and control guards.

The panel and website share sharp neutral controls, type and colour tokens.
Current navigation items are inverted; main actions are filled. Colour identifies
channel/scene data, sensor markers, weather and status. Pages retain their widgets
when you return, and slider presses read the live controller generation.
Uniform representable acquired drives seed channel controls. White controls use
confirmed white inputs when available; otherwise neutral values are labelled as
a new mix rather than a representation of the room.

## Try the panel without room hardware

Use Python 3.11 or newer with Tk. `python -m tkinter` checks Tk availability.
On Linux, install the distribution's Tk and virtual-environment packages if
needed. The commands below select the reviewed development branch explicitly:

```sh
git clone https://github.com/LESA-RPI/scr.touch_panel.git
cd scr.touch_panel
git switch fix/panel-navigation-transitions
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r app/requirements.txt
python -B app/scr_touch_panel.py --windowed --duration 600 --theme light
```

On Windows, use `python` in place of `python3` and activate with
`.venv\Scripts\Activate.ps1`. This preview moves no room devices and starts no
recording. The cabinet layout is 1280 × 800. Other hardware needs its own font,
layout and touch checks. The browser client uses the same panel controller when
the optional trusted-network gateway is enabled.

## Install, operate or restore

| Need | Reference |
|---|---|
| Fresh Raspberry Pi OS installation | [Fresh setup](WORKFLOWS.md#fresh-raspberry-pi-os) |
| Enable connected lighting | [Ownership and connection checks](WORKFLOWS.md#before-connected-control) |
| Autostart, switch modes or roll back | [Startup](WORKFLOWS.md#startup-and-rollback) and [recovery](WORKFLOWS.md#switching-and-recovery) |
| Configure theme, font or weather | [Appearance and weather](WORKFLOWS.md#appearance-and-weather) |
| Rebuild after hardware or storage failure | [Backup and rebuild](WORKFLOWS.md#backup-and-rebuild) |
| Add an experiment or client | [Interface contracts](docs/interface.md) and [future surfaces](WORKFLOWS.md#additional-surfaces--agreed-direction) |
| Contribute code or documentation | [Contributor and agent guidance](AGENTS.md) |

The fresh Pi 3 deployment uses Raspberry Pi OS Legacy 32-bit Bookworm with
distribution Python 3.11, Tk 8.6 and Pillow 9.4. Desktop preview dependencies are
separate; do not install them over system packages. The touch panel defaults to
`/usr/bin/python3` and checks for Python 3.11+, Tk and Pillow before startup.
`SCR_PANEL_PYTHON` selects another supported interpreter. Legacy and the ROS
adapter retain their separate interpreter settings: the older Ubuntu installation
used Python 2.7, while the fresh setup explicitly selects Python 3 for each.

Legacy starts from [main.py](main.py); Beta starts from
[app/scr_touch_panel.py](app/scr_touch_panel.py). The installed
[launcher](app/start_panel.sh) reads private deployment settings and starts one
Beta. Beta starts Legacy only when requested, using a compatibility wrapper
that preserves the original source. Existing room ROS services and custom bindings are required for control;
a local ROS master on the panel is not required.

Git preserves source, not a complete system. Obtain private configuration and
custom client/recovery bundles from the room custodian. Check each archive's
manifest and read-error record: an incomplete image is not an exact restore.
Room servers, fixtures and HTTP demo services are separate dependencies.

## Validation and limits

Run `python -m pytest tests` with pytest installed. Tests cover contracts,
restoration, uncertain operations, preferences and idle guards. UI changes also
need target font, internal text-fit, touch and failure-state checks.

Earlier bounded Pi navigation, lighting and autostart trials are historical evidence;
qualify the current release against the installed configuration before use.
Prolonged reliability, physical blind motion and replacement hardware remain
acceptance checks. Service presence is not physical device health.

General panel code belongs here. Project-X owns its optional recorder integration.
The browser and touch interface share one command owner.
On phones and portrait tablets, the website keeps Home, Lights, Guide and Settings in a bottom
navigation bar. Compact tool selection, scrollable lighting tabs and scene rows
leave more room for controls. Changing pages returns to the top; pending messages
remain visible above navigation without changing the panel's page.
The optional gateway permits controls from the configured trusted subnet; it has
no separate staff sign-in. Guide/help content, appearance roles and common actions
come from the panel. Browsing the website never wakes or switches the panel;
only its explicit buttons do.
Technical contracts remain available to maintainers and agents through the links
above. Private configuration, captures and incident history stay outside Git.

Touch interface: **Diyanko Bhowmik**, with Codex assistance. Original contributors remain in
Git history. The supplied LESA logo is retained unchanged.

Control and weather artwork is adapted from [Lucide](https://lucide.dev/). Its licence
and original notices are retained in [assets/icons/LICENSE](assets/icons/LICENSE).

The browser fallback [room-content.json](browser/room-content.json) is generated by
[export_room_content.py](app/export_room_content.py) from panel-owned help, guides,
control metadata and themes. It is not edited separately. After changing those
sources, run `python app/export_room_content.py browser/room-content.json`; CI
checks for drift. README owns the overview, WORKFLOWS owns procedures, and the
panel help is the concise on-screen guidance. Private screenshot/demo generators
stay outside the runtime and public source. Use a small representative preview for
everyday iteration; retain the full matrix for release qualification.
