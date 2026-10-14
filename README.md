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

## Source status

`main` contains the earlier Ubuntu/Python 2.7 launcher. The fresh Raspberry Pi OS
setup and newer Beta interface are under review in
[PR #1](https://github.com/LESA-RPI/scr.touch_panel/pull/1), on
`experiment/fresh-pi-setup-20261013`. For that setup, start with
[the branch README](https://github.com/LESA-RPI/scr.touch_panel/blob/experiment/fresh-pi-setup-20261013/README.md).
The newer interface calls the original application **Legacy**; this baseline
uses **Original**. Neither branch identifies which commit a cabinet is running.
Check the installed release before maintenance.

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

In this baseline, Settings returns to Original controls. Its touch navigation
strip returns to Beta. Both applications remain separate. Credits are under
**Settings → About panel**. The newer branch has different navigation; use its
guide when operating that version.

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

## Restore or provision hardware

Obtain private recovery archives and the current restore guide from the room
custodian. Check their manifests, scope and read-error records before use; an
incomplete image is not an exact clone. Preserve the OS, custom ROS workspace and
private startup/network settings separately. Git alone is not a system backup.
[Backup and rebuild guidance](WORKFLOWS.md#backup-and-rebuild) covers image checks,
different SD/USB identifiers, new hardware and acceptance tests.

A fresh OS is a separate migration. Keep current Python/Tk/Pillow for new UI
deployments, and validate their room adapter independently. ROS 1 has reached
end of life ([Open Robotics](https://discourse.ros.org/t/ros-noetic-end-of-life-may-31-2025/43160));
do not treat the old cabinet stack as the default for every future device.
Do not change the working fleet during migration trials.

## Maintain and extend

Run `python -m pytest tests` with pytest installed. Checks cover baseline restore,
uncertain operations, external changes, profiles and dynamic input cancellation.
Earlier panel trials covered bounded touch/navigation and connected lighting.
+These do not qualify a different release, replacement boot or prolonged reliability.
The modern preview has been checked with Python 3.11.10, Tk 8.6 and Pillow 12.0.0.

[The interface contract](docs/interface.md) owns profiles, events and the adapter
boundary. Keep experiments independent of room controls. Use one cohesive commit
for a tested change; keep private captures, credentials, temporary tools and
incident timelines outside this public repository. Preserve published release
identities when consolidating later documentation history.

Beta author: **Diyanko Bhowmik**, with Codex assistance. Original contributors
remain in Git history. The supplied LESA logo is retained unchanged; SHA-256:
`ea6224069408b6cc1e3833793ab7f0d627898ff1c6dd71436818dbc83b4ea13b`.
