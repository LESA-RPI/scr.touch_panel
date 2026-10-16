# SCR room touch panel

Touch controls and room guidance for the LESA Smart Conference Room. **Legacy**
is the original room application. **Beta** adds a newer interface and touch access
to Legacy. Beta does not yet cover every Legacy feature.

The fresh Raspberry Pi OS setup and current Beta improvements are under review
in [PR #1](https://github.com/LESA-RPI/scr.touch_panel/pull/1), on
`experiment/fresh-pi-setup-20261013`. `main` remains the earlier baseline until
promotion. An installed cabinet may run a different commit; check its release
identity before maintenance.

## For room users

| Screen | Purpose |
|---|---|
| Home | Stacked Lights on/off beside clock/weather; disabled blinds can be shown or hidden |
| Room tools | Lighting, Experiment mode, system/help and device preferences in one sidebar |
| Demo & guide | Four directly selectable topics, with Previous/Next and All topics; no equipment or recording starts |

Home is the default screen. Room tools → Lighting groups **White light, Scenes,
Programmes and Channels**. Fid, Sat and Dul retain their original mixtures.
Gradient is the original spatial pattern; Sun is a travelling light cycle and
Circ cycles the room together. Their fixture/programme adapters are not connected
in Beta yet, so their Apply/Start controls remain unavailable. Legacy remains
available for the original implementations. Empty Dynamic CCT, Dynamic Intensity
and Auto placeholders and the old Enable Sliders gate are omitted.

Home includes Lift blinds, Open slats and Close & lower. Room tools → Screen &
controls saves a separate **Blind controls** lock, locked by default, and
can show or hide the Home controls. Home shows **Disabled** while movement is
unavailable; the settings page explains the lock or missing connection. Unlocking does not move blinds
or connect a controller. No blind adapter is installed in Beta; actions remain
unavailable until one is connected and qualified. Room tools keeps the tools available
away from everyday on/off controls. Home returns directly from these pages.
The header shows Beta and provides a direct Legacy shortcut with its existing
restoration handover. In Legacy, the matching top bar identifies Legacy view;
Home returns to the main controls. Room tools opens each tool directly beside the sidebar and
remembers the last tool. Experiment mode runs instructions and panel annotations;
its recorder is not connected.

Home and the idle view show outdoor temperature, conditions, feels-like temperature,
today's high/low and rain chance when available, plus daylight. Source/model
details remain under Room tools → Date & weather. Earlier data is clearly dated.
Forecast labels and values use an aligned grid; missing values show a dash.
The screensaver gives the clock larger digits with a smaller AM/PM indicator,
beside weather and the daylight bar. Touch anywhere opens Home.

Light buttons queue immediately on release; sliders send after your touch settles.
Large values show your selection; the feedback
area shows the last confirmed controller settings and their age. **Ready** means
the lighting adapter is available. It does not confirm every room sensor is healthy
or measure physical brightness. The selected Home button reflects the last
confirmed On/Off readback through a coloured highlight; neither is selected while a
request is pending or uncertain.
Lighting → Scenes highlights the preset matching the confirmed drive words.
A custom mix clears the preset highlight. Routine Ready confirmations stay in
the feedback area; the footer is reserved for explanations, progress and problems.
Room tools keeps its sidebar in place while changing tools. Unchanged clock/status
values do not trigger another redraw. Resource checks run in the background so
slow reads do not hold up touches.
Home, the screen saver and Lighting tabs reuse their existing widgets when you
return. Readback, availability and slider bindings refresh before controls are
shown; this does not cache lighting commands or bypass controller checks.

White light shows the minimum and maximum beside each slider. System & help
separates panel health, room connection and guidance. Reference commands are
available through View command steps and are never executed by the panel.
Command references use a verified monospace font with restrained shell highlighting;
the browser can copy each command or the complete topic without formatting.
Command steps explain which computer to use, why the command helps and what
result to expect. The panel shows one step at a time with Previous/Next;
the website shows all steps with individual Copy buttons and reference links.

The full-screen screensaver appears after five idle minutes by default. It has a
large clock, weather and a prominent “Touch anywhere for room controls” prompt,
without the normal control-page navigation. Its first wake touch always opens
Home without activating controls. Screen & controls offers **Preview screen saver**
for the same screen; there is no separate clock/weather page.
Control icons use a consistent Lucide outline
family; weather uses thin, coordinated variants. Dark backgrounds and ordinary
surfaces stay neutral gray. Both themes use restrained teal controls, warm weather
accents and distinct green/amber status colours. Selected controls retain readable text while pressed.
The original LESA logo stays
consistent in both themes. Room tools uses the sidebar height and hides its footer
shortcut while open.
Flat sliders share a 48-pixel touch area, a visible grip and pressed/focus feedback.
Related buttons share widths and spacing; lighting results appear
in a compact outlined card with the historical readback kept separate.
**Room tools → Screen**
offers Off, 1, 5 or 15 minutes. Idle does not interrupt Experiment mode, Legacy, held
touches, pending commands or uncertain lighting. Preferences save appearance and
idle choices, not light settings or recording state.

Opening Legacy restores Beta's starting light scene before handing over control.
If a result is uncertain, stop changing lights and ask the room host. **Room tools →
System & help** shows checks and operator instructions; it does not execute
commands. The visitor guide also operates no devices. A two-second stationary
press leaves the black screen; black pixels do not turn off the backlight.
A small gray hint at the bottom explains the two-second hold.

## Try Beta without room hardware

Use Python 3.11 or newer with Tk. `python -m tkinter` checks Tk availability.
On Linux, install the distribution's Tk and virtual-environment packages if
needed. The commands below select the reviewed development branch explicitly:

```sh
git clone https://github.com/LESA-RPI/scr.touch_panel.git
cd scr.touch_panel
git switch experiment/fresh-pi-setup-20261013
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
separate; do not install them over system packages. Beta defaults to
`/usr/bin/python3` and checks for Python 3.11+, Tk and Pillow before startup.
`SCR_PANEL_PYTHON` selects another supported interpreter. Legacy and the ROS
adapter retain their separate interpreter settings: the older Ubuntu installation
used Python 2.7, while the fresh setup explicitly selects Python 3 for each.

Legacy starts from [main.py](main.py); Beta starts from
[app/scr_touch_panel.py](app/scr_touch_panel.py). The installed
[launcher](app/start_panel.sh) reads private deployment settings and starts one
Legacy application plus Beta. The compatibility wrapper preserves the original
source. Existing room ROS services and custom bindings are required for control;
a local ROS master on the panel is not required.

Git preserves source, not a complete system. Obtain private configuration and
custom client/recovery bundles from the room custodian. Check each archive's
manifest and read-error record: an incomplete image is not an exact restore.
Room servers, fixtures and HTTP demo services are separate dependencies.

## Validation and limits

Run `python -m pytest tests` with pytest installed. Tests cover contracts,
restoration, uncertain operations, preferences and idle guards. UI changes also
need target font, internal text-fit, touch and failure-state checks.

Bounded Pi navigation, lighting and autostart trials have passed. Undervoltage,
prolonged reliability, untested Legacy demos/blinds and replacement hardware
remain acceptance limits. Service presence is not physical device health. Experiment mode
journals have `recording: false`; recorder integration needs a separate adapter.

General panel code belongs here. Project-X owns its optional recorder integration.
The browser and touch interface share one command owner and experiment ownership.
The optional gateway permits controls from the configured trusted subnet; it has
no separate staff sign-in. Guide/help content, appearance roles and common actions
come from the panel. Legacy’s original controls remain on the touch panel.
Technical contracts remain available to maintainers and agents through the links
above. Private configuration, captures and incident history stay outside Git.

Beta: **Diyanko Bhowmik**, with Codex assistance. Original contributors remain in
Git history. The supplied LESA logo is retained unchanged.

Control and weather artwork is adapted from [Lucide](https://lucide.dev/). Its licence
and original notices are retained in [assets/icons/LICENSE](assets/icons/LICENSE).
