# SCR room touch panel

Room controls and an independent interactive panel for the LESA Smart Conference
Room. The original Python/Tk application remains at the repository root. Its
source is unchanged by the new client.

The new client is in [app/](app/scr_touch_panel.py). It provides Room,
Experiment, System and Original controls modes on the installed 1280 × 800 Pi.
It uses Python 2.7 or 3 with installed Tk 8.6 and Pillow. It needs no Project-X
imports, web server, package installation or firmware update.

## Run a bounded trial

From this checkout, with the normal room program already running:

```sh
python -B app/scr_touch_panel.py --duration 600 --theme light \
  --journal /tmp/scr-panel-trial-unique.jsonl
```

Choose a new journal name for each run. Without `--live-lights`, controls are
unavailable and the UI cannot actuate lights. `--windowed` permits local review.
Use `--help` for profiles, an installed font, logo, clock style, timezone and
theme times. Settings changes last for this trial; launch options set defaults.

The supplied LESA JPEG is retained unchanged. The light theme displays its
wordmark in a viewport. Dark mode uses plain LESA text; `--dark-brand original`
selects the original logo on a white plate. Icons identify controls alongside text.
Blue identifies controls; amber identifies practice; channel colours identify
the advanced editor. Advanced lighting is one tap from Room.
Short touch explanations can be switched off with Tips. Author credits stay in
the footer. System can check advertised Lighting, Blinds, Environment and TOF
services through the configured master; this is not sensor or motion health.

## Connected lighting

Use the existing deployment ROS environment. Configure the approved remote
master privately through `SCR_PANEL_MASTER` or `--expected-master`; it must equal
`ROS_MASTER_URI`. The ROS helper uses `/usr/bin/python2.7` by default, independently
of the UI interpreter. [The operating guide](WORKFLOWS.md) describes admission,
restoration and failure handling.

Sliders and presets send changes automatically after 250 ms without movement.
There is one request in flight and one replaceable unsent selection. Leaving a
view or changing its theme cancels unsent selections. Displayed values are
selected controller inputs, not measured brightness or colour.

The ten-fixture adapter requires
a stable, exactly restorable Fid, Sat, Dul or Off baseline. It restores that
baseline before Original controls or exit. An uncertain result disables writes.
The Pi-local lock does not exclude other room controllers. The cabinet beta uses
a persistent touch switcher. Settings returns to Original without removing that
strip. SIGTERM stops the beta after its restoration attempt. The original
application is a separate process and remains available.

For startup, [app/start_panel.sh](app/start_panel.sh) reads a private deployment
file, starts one original application if needed, and opens the beta in Room.
The operating guide describes user autostart, optional autologin and rollback.
Startup does not cure the cabinet's reported undervoltage; replace its supply.

## Experiments and other clients

[The interface contract](docs/interface.md) describes data-only profiles, panel
events and the optional light subprocess. An experiment supplies its instructions
and annotation labels. Project-X is one possible consumer and owns its recorder
integration separately.

Practice buttons never start sensor recording. Each event explicitly records
`recording: false`. Browser/tablet clients and live recorder adapters are future
work; this Tk client does not yet run on an iPad. Reuse the small data contracts
when a second client needs them.

## Validation and provenance

```sh
python -m pytest tests
```

Six focused checks cover exact restore, failed/uncertain operations, external
changes, profile validation and dynamic input cancellation. Display-only checks
on the installed Pi exercised layout bounds, actual Tk slider events, theme/view
changes, Original navigation and stationary two-second wake with both installed
interpreters. The legacy application remained running.

An earlier connected trial verified Sat and 3500 K / 1000 commands against all
ten fixture drive readbacks and exact Fid restoration. The final dynamic UI was
checked with a mocked actuator, not a new hardware write. Persistent switching
also passed three Settings-to-Original-to-Room cycles and timeout/Escape return
on the installed Pi. No eight-hour soak,
touch calibration or optical accuracy claim follows from these checks.

The 2026-10-10 deployment check started one beta and one unchanged original
application. Real screen events verified navigation and fresh Fid admission.
Launching again kept both process identities unchanged. An authorized reboot
then left the cabinet unreachable, with a reported blank screen and blinking
cursor. On 2026-10-13 the original card booted again: SSH confirmed the installed
Ubuntu 16.04.4/Lubuntu and ROS Kinetic, and the researcher saw the new panel.
Undervoltage and earlier SD I/O errors remain; this does not establish reliable
startup or validate a replacement image. Current private application/configuration
backups passed local and cloud verification. A later runtime-file read failed
with SD I/O errors; it is incomplete and must not be used to restore libraries.
No packages, firmware or ROS services were changed.

[Backup and rebuild guidance](WORKFLOWS.md#backup-and-rebuild) separates the panel
source, private deployment, system image and external room-service dependencies.

New panel author: **Diyanko Bhowmik**, with Codex assistance. Independent agent
reviews and a researcher-supplied Claude brief informed the design. Original
contributors and code remain in repository history. The researcher supplied the
LESA logo; SHA-256:
`ea6224069408b6cc1e3833793ab7f0d627898ff1c6dd71436818dbc83b4ea13b`.
