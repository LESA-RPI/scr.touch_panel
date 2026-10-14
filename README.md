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
| Room | Adjust lighting or choose an existing scene |
| Visitor | See clock/weather and the room demo guide |
| Practice | Try instructions and annotations; no sensor recording starts |
| System | See panel readings, connection information and troubleshooting |
| Settings | Set appearance, time/weather units and idle timeout; find credits |
| Legacy | Open the original controls and return to Beta by touch |

Light changes send automatically. Large values show your selection; the feedback
area shows the last confirmed controller settings and their age. **Ready** means
the lighting adapter is available. It does not confirm every room sensor is healthy
or measure physical brightness. **What do these do?** explains the controls.

The clock/weather view appears after five idle minutes by default. Its first wake
touch returns to the prior page without activating controls. **Settings → Screen**
offers Off, 1, 5 or 15 minutes. Idle does not interrupt Practice, Legacy, held
touches, pending commands or uncertain lighting. Preferences save appearance and
idle choices, not light settings or recording state.

Opening Legacy restores Beta's starting light scene before handing over control.
If a result is uncertain, stop changing lights and ask the room host. **System →
Troubleshooting** shows checks and operator instructions; it does not execute
commands. The visitor guide also operates no devices. A two-second stationary
press leaves the black screen; black pixels do not turn off the backlight.

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
layout and touch checks. Browser/tablet clients are planned, not implemented.

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
separate; do not install them over system packages. The older Ubuntu installation
used Python 2.7. The launcher retains that default for compatibility; the fresh
setup explicitly selects Python 3 for both applications and the ROS helper.

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
remain acceptance limits. Service presence is not physical device health. Practice
journals have `recording: false`; recorder integration needs a separate adapter.

General panel code belongs here. Project-X owns its optional recorder integration.
Future clients should share one command owner and preserve experiment ownership.
Technical contracts remain available to maintainers and agents through the links
above. Private configuration, captures and incident history stay outside Git.

Beta: **Diyanko Bhowmik**, with Codex assistance. Original contributors remain in
Git history. The supplied LESA logo is retained unchanged.
