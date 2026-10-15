# SCR room touch panel

Touch controls for the LESA Smart Conference Room. The original application and
the newer Beta client have separate entrypoints and share the existing room
services. Beta does not yet cover every original feature.

## Choose the version

| Version | Source and setup |
|---|---|
| Original application | [main.py](main.py); requires the installed custom ROS clients and room environment |
| Earlier Beta baseline | [app/scr_touch_panel.py](app/scr_touch_panel.py) on `main`; installed launcher expects Ubuntu/Python 2.7 |
| Fresh Pi OS and current Beta | [Branch README](https://github.com/LESA-RPI/scr.touch_panel/blob/experiment/fresh-pi-setup-20261013/README.md); Python 3 setup and newer interface under review in [PR #1](https://github.com/LESA-RPI/scr.touch_panel/pull/1) |

The newer interface calls the original application **Legacy**. This baseline
uses **Original**. Check the cabinet's installed release before maintenance;
the default branch does not identify what is running on a device.

## Try the baseline without room hardware

Use desktop Python 3.11 or newer with Tk available. `python -m tkinter` checks
Tk. On Linux, install distribution Tk and virtual-environment packages if needed.

```sh
git clone https://github.com/LESA-RPI/scr.touch_panel.git
cd scr.touch_panel
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r app/requirements.txt
python -B app/scr_touch_panel.py --windowed --duration 600 --theme light
```

On Windows, use `python` in place of `python3` and activate with
`.venv\Scripts\Activate.ps1`. This preview moves no room devices and starts no
recording. Desktop requirements are separate from the installed Ubuntu stack.
For fresh Raspberry Pi OS, use the branch guide above rather than this launcher.

## Operate the baseline

In this version, Settings returns to Original controls and its touch strip
returns to Beta. Credits are in Settings. Lighting sliders send automatically;
confirmation means controller readback, not measured physical brightness.
Opening Original or exiting waits for restoration of Beta's starting light scene.
If the result is uncertain, stop changing lights and coordinate with the room host.

Practice annotations have `recording: false`; they do not start a sensor recorder.
System reports panel readings and advertised services, not physical sensor health.
A stationary two-second press leaves the black screen; its backlight stays on.
The updated branch has different navigation and additional features.

## Install, maintain or restore

### Browser room overview (read-only trial)

Run `python -B browser/serve.py` with Python 3.11 or newer, then open the printed
local URL. No packages, build tools or room hardware are required. The page shows
room time, this host's resources and optional advertised room-service availability.
Home follows the cabinet layout: stacked Lights and Blinds actions beside a large
clock and optional outdoor weather. Website action buttons are disabled; lighting
uses the cabinet panel and blinds are not enabled. Advanced · diagnostics and
Demo & guide lead to separate views. Diagnostics shows actual host readings and room-interface
registrations. Guide explains room use and failures. All three share fixed navigation,
the original main LESA logo and a white surface. There are no appearance switches,
storage cards or technical status on Overview. Phone, tablet and desktop layouts scroll
normally rather than shrinking or clipping content.

For room-network access and the approved ROS master, use the explicit addresses
in [browser operation](WORKFLOWS.md#read-only-browser-status). The default is
loopback-only. Room hosting requires an explicit trusted client subnet. The optional
independent user service starts the website at boot; its setup and rollback are in
that runbook. This is a separate visitor status page with no controls or recorder
metadata; it does not change the cabinet panel or its launcher. Service presence
is not device health. Browser control and staff authentication remain future work.

| Need | Reference |
|---|---|
| Connect lighting and establish ownership | [Connection checks](WORKFLOWS.md#before-connected-control) |
| Switch modes or recover an uncertain result | [Switching and recovery](WORKFLOWS.md#switching-and-recovery) |
| Set up autostart or roll back | [Startup and rollback](WORKFLOWS.md#startup-and-rollback) |
| Restore hardware or provision a replacement | [Backup and rebuild](WORKFLOWS.md#backup-and-rebuild) |
| Add a profile or experiment adapter | [Interface contracts](docs/interface.md) |

The installed launcher expects the older Python 2.7/Tk/Pillow environment and
custom ROS workspace. Desktop Python 3 preview support does not migrate that
launcher. Existing room servers remain separate dependencies; upgrading the
panel does not require replacing them. Coordinate ownership before live control.

Git preserves source, not a complete system. Obtain private configuration and
recovery bundles from the room custodian. Check manifests, scope and read-error
records: an incomplete image is not an exact clone. Keep captures, credentials,
participant data and host settings outside this public repository.

Run `python -m pytest tests` with pytest installed. Baseline checks cover profiles,
lighting restoration and uncertain results. Earlier bounded cabinet trials do not
qualify another release, replacement hardware or prolonged reliability. Preserve
release hashes and original contributors when cleaning public documentation.

General panel code belongs here; Project-X owns its optional recorder integration.
Read-only browser views are implemented; browser control remains future work.

Beta: **Diyanko Bhowmik**, with Codex assistance. Original contributors remain in
Git history. The supplied LESA logo is retained unchanged.
