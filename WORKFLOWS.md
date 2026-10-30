# Panel operation

The root `main.py` is the unchanged Legacy application; `app/` provides Beta and
its website bridge. Keep the installed original checkout, working directory and ROS
environment intact. README owns the user overview; this guide owns operating
procedures. `docs/interface.md` owns data and adapter contracts.

## Before connected control

1. Check power, free memory and storage on the panel.
2. Verify the native fixture server and its ten connections.
3. Verify that no recording, demo or other lighting controller owns the lights.
4. Source the already installed ROS workspace.
5. Set `SCR_PANEL_MASTER` to the approved remote `ROS_MASTER_URI`.
6. Run a bounded trial with a new private journal and `--live-lights`.

No automatic discovery or second fixture server is used. Do not launch old demo
scripts to qualify ownership. Stability reads and a Pi-local file lock cannot
prove global exclusivity; coordinate with the other room users.

```sh
# Deployment-specific ROS variables and approved master are set externally.
python -B app/scr_touch_panel.py --duration 600 --live-lights \
  --journal /tmp/scr-panel-connected-unique.jsonl
```

The bounded trial above requires two matching scans and one uniform Fid, Sat, Dul
or Off preset, because it restores that preset when finished. Arbitrary drive
words cannot be restored exactly by the existing integer-percent setter.
The installed persistent launcher uses `--keep-switcher`; its helper uses
`--keep-settings` instead. It accepts any stable ten-fixture snapshot, including
Gradient, and never restores lighting on navigation, shutdown or parent loss.

One Tk process owns display interaction. One helper owns Beta's ROS calls.
The helper checks all fixture words before each write and after its response.
It does not claim optical accuracy. The existing setter accepts integer
percentages, which cannot reproduce arbitrary fractional drive settings.

## Switching and recovery

Home combines stacked Lights on/off with time and outdoor weather. Blind
callbacks check the saved permission and controller connection; movement defaults
to Locked. The helper exposes whole-room blinds when the existing lift/tilt
services are advertised. Room tools → Lighting groups
white-light adjustments, scenes, programmes and the channel editor. Home returns to everyday
controls. All light controls share one latest selection queue. Wait for
confirmation to distinguish a selection from a result.

Scenes includes the original ten-fixture Gradient when the coordinate service is
available. Programmes exposes the original Sun/Circ requests through the existing
Status service when configured below. Start/Stop acceptance is not programme
running or completion confirmation. Before an explicit manual lighting action,
the helper requests both programmes stop and qualifies stable drive readback;
uncertain results block further changes. Opening Beta pages does not stop
programmes or send lighting setters. Blind commands use the same
helper, with service acknowledgements rather than measured physical positions.

System & help explains each reference command's computer, purpose and expected
result. The panel shows one command step at a time; the browser can copy each
step or the complete topic and provides documentation links. Neither interface
executes these references. Service-start commands use `cd ... && python ...` so
a failed directory change cannot launch the script from another directory.

Legacy opens the unchanged original app after preserving helper release and
confirmed exit; website lighting pauses. Home checks the original interface,
stops Sun/Circ and reads stable settings before automatically returning to Ready.
No old scene is restored. A failed interface/log check lets the same Legacy owner
reopen. Uncertainty after programme stopping or readback blocks both control paths
until staff recovery. The [interface contract](docs/interface.md#optional-browser-gateway-version-1)
defines these checks.

The helper has a ten-second parent lease and 30-second operation budget, with
individual service calls bounded to at most twelve seconds. Persistent control
releases without setters; bounded trials restore only while the last confirmed
drive state still matches. A lost response or external change disables further
writes and automatic trial restoration. Never retry
an uncertain write. Inspect the private `.lights-*.jsonl` receipt and coordinate
with staff before controlling again.

Deadlines do not bound filesystem stalls.

Recovery checkpoints use one ordered background writer. The UI remains responsive
while saving; a command is not dispatched until its checkpoint is durable, and
Legacy input remains covered until its handoff is saved. A save taking more than
ten seconds before dispatch or Legacy handoff blocks that action without a later
retry. Confirmations and experiment ownership remain unavailable until saved.
Power actions also wait for recovery saves. Never remove durability checks to
improve speed. The private journal records widget-update time as `render_ms` and
rate-limited callback delays over 200 ms; these are not physical touch latency.

An initializing helper is cancelled after 30 seconds without sending a lighting
command. The normal UI
waits for ownership release for Legacy, experiment handoff, shutdown and power actions;
a process exit alone cannot confirm an in-flight
lighting result. A helper still initializing can be cancelled without a write.
`SIGKILL` or host power loss cannot guarantee bounded-trial restoration.

### Experiments and returning everyday control

Run the CLI as the panel user with its configured private control socket. Use a
fresh private token and a generic label. Reserve before starting an external
lighting worker; wait for success, then send heartbeats while it owns lighting.

```sh
TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
python3 app/lighting_handoff.py --socket "$SCR_CONTROL_SOCKET" reserve --token "$TOKEN" --label Experiment
python3 app/lighting_handoff.py --socket "$SCR_CONTROL_SOCKET" heartbeat --token "$TOKEN"
```

After stopping the worker and verifying no remote lighting request remains pending:

```sh
python3 app/lighting_handoff.py --socket "$SCR_CONTROL_SOCKET" finish --token "$TOKEN" --owner-closed --pending-clear
```

Successful finish means verified Ready controls with the current scene preserved.
A failed or timed-out finish is incomplete cleanup: do not start another worker or
repeat the request. Crashes, expired heartbeats and restarts never reclaim lighting.

### When controls are unavailable

Staff check the deployed version, current owner and private receipts. Stop previous
workers/programmes and verify no remote lighting handler remains pending; a stable
read alone cannot prove that. Keep Legacy covered on Home during recovery.

```sh
python3 app/lighting_handoff.py --socket "$SCR_CONTROL_SOCKET" status
python3 app/lighting_handoff.py --socket "$SCR_CONTROL_SOCKET" recover --owner-closed --pending-clear
```

The flags acknowledge those completed checks. The website cannot make them.
Never restart ROS/Status, delete ownership state or retry an uncertain setter to
clear a block. Record deployment/recovery results in the private `.local/README.md`.

Blank screen displays black pixels. A stationary two-second press returns to the
previous view; movement beyond 40 pixels cancels. The backlight remains powered.
Use qualified display-power control for experiments needing complete darkness.

## Appearance and weather

The launcher uses `~/.config/scr-panel/appearance.json` for theme, clock style,
weather temperature units, help tips and light/dark schedule. Set `SCR_PANEL_PREFERENCES` to change its
location. Saved appearance choices override CLI appearance defaults. Writes
are atomic and use one background worker with one pending snapshot. Invalid
files fall back to defaults and show a warning; they cannot start recordings
or restore light settings. Remove this private file to reset appearance.
A direct preview saves preferences only when `--preferences PATH` is supplied.
`blinds_enabled` is a strict boolean, defaults to false and is saved separately
from Home visibility. Changing this setting never sends a blind command.
Screen & controls omits unlocking until the helper reports a connected controller.
Its permission controls update when connection state changes, including while the
page remains open. Unlocking changes permission only; explicit Home buttons move blinds.
Room tools → Date & weather selects Celsius or Fahrenheit. Old preference files
default to Fahrenheit. Direct previews can use `--temperature-unit c` or `f`.
Switching units converts cached data; it does not fetch again or change room controls.
Screen settings save `idle_timeout` as 0, 60, 300 or 900 seconds, defaulting to
300 seconds. `blinds_display` defaults to `disabled`; `hidden` removes the blind section
from Home. This is a display choice only and cannot enable blind commands.
`--idle-timeout` selects the preview default. Idle reuses
the screen saver and its existing weather cache/cadence. The Preview screen saver
button opens this same view. Every wake opens Home so visitors
can find Lights on/off. The first wake touch is intercepted before button bindings;
controls need a subsequent touch. Experiment mode, Legacy, blank screen, active touches,
pending/queued commands, restoration and uncertain lighting block idle entry.
Lighting failures leave idle automatically. Confirmation age uses monotonic time
from matching successful acquire/apply replies; failures never refresh it. It is
historical feedback, not continuous measurement. No preference saves light state.

Weather is optional. Set these private values in `deployment.env`:

```sh
SCR_WEATHER_LATITUDE=42.7284
SCR_WEATHER_LONGITUDE=-73.6918
SCR_WEATHER_NAME="Troy, NY"
```

These example coordinates represent the Troy city area, not the panel's exact
position. Other installations must choose their own location. Without both
coordinates, the screen saver shows weather as unconfigured. Direct previews accept
`--weather-latitude`, `--weather-longitude` and `--weather-name`.

The [Open-Meteo forecast API](https://open-meteo.com/en/docs) provides temperature,
feels-like temperature, today's high/low and maximum rain probability, condition,
sunrise and sunset in the panel timezone. The public endpoint needs
no API key for its free non-commercial use; review its terms for other uses.
Date & weather displays attribution and model time. Home keeps these details
out of the everyday view. It starts one helper at most
every 15 minutes while Home or the clock view is open, bounds its response to 32 KiB and kills
the helper after eight seconds. Requests never use the Tk thread. A failed
refresh labels the last available data; data older than 30 minutes has an age
warning. Weather never drives lights, screen themes or experiment timing.

The weather helper and UI ship together: its JSON contains numeric temperatures,
optional feels-like/high/low/rain fields,
condition/code and dated sunrise, sunset and model timestamps. The UI validates
these fields before displaying them. Daylight progress is clamped before sunrise
and after sunset; it is hidden when the timestamps refer to another date.
After sunset, the card says night rather than calculating tomorrow from old data.
Cantarell is already installed on
the qualified Raspberry Pi OS image; other hosts may select another family with
`--font`. A requested font name alone does not establish what Tk rendered.

## Room guide and troubleshooting

Demo & guide is a four-page introduction. It shares the existing navigation,
icons and text layout. No demo script or recorder starts when pages change.
The fixed header badge reflects the existing lighting adapter state, with no extra
network polling. Its icons and labels distinguish Ready, Sending, Checking,
Uncertain and Offline. Preview never reports Ready; Legacy shows its own mode.

Room tools → System & help offers read-only Check connection alongside panel
controls and reference instructions. Reference commands are never executed by the interface.
[app/panel_guides.py](app/panel_guides.py) owns the concise displayed guidance.
The room's installed `startROS.py` and `startStatus.py` were inspected on
2026-10-14: each destroys its existing named tmux session before rebuilding it.
The Status launcher starts its server before waiting and launching clients.
These launch paths were not executed or qualified as whole-system recovery.
Use them only from their installed directories after stopping experiments and
coordinating shared room ownership. Service autostart on the Ubuntu room computer
is unverified. A restart can interrupt controls and passive/acquisition consumers.
Keep the panel's own autostart separate from room-server maintenance.

## Startup and rollback

The client does not install or change OS services. The deployment launcher
uses a private `~/.config/scr-panel/deployment.env` file:

```sh
SCR_CLASSIC_DIR=/absolute/path/to/installed/original
SCR_ROS_SETUP=/absolute/path/to/installed/workspace/devel/setup.bash
SCR_PANEL_MASTER=http://approved-room-master:11311
ROS_IP=panel-address
ROS_HOSTNAME=panel-hostname
DISPLAY=:0
SCR_START_DELAY=8
SCR_PANEL_PYTHON=/usr/bin/python3
# Optional: existing approved programme service; omit to hide Sun/Circ controls.
SCR_STATUS_URL=http://approved-status-service:5000
```

Use existing, verified deployment values. Keep this file mode 0600 and outside
Git. Beta requires Python 3.11+, Tk and Pillow; the launcher checks these before
sourcing ROS or starting Legacy. `SCR_PANEL_PYTHON` defaults to `/usr/bin/python3`.
`SCR_STATUS_URL` is the private base URL of the existing Status owner, not a new
service to install or restart. The launcher passes it as `--status-url` to Beta
and its helper. Direct launches can use the same option. Use an approved HTTP(S)
address without embedded credentials, query or fragment; keep real addresses out
of Git. Only the fixed original `sun`/`circ` Run/Kill requests are admitted.
Omitting it leaves programme controls unavailable while ordinary lighting remains
usable. Automatic return from Legacy also requires this existing programme service
to stop Sun/Circ; without it, the return stays blocked. Capability advertisement identifies configured services, not their health;
qualify request acceptance and stable readback before a live change.
Legacy and the light adapter use independent interpreter settings. The launcher
sources the installed ROS setup, sets the same original
environment, and checks process working directories before starting `main.py`.
Its file lock prevents two switchers. Journals and logs stay under
`~/.cache/scr-panel`; retain them for investigation and manage their disk use.

Deploy each published commit to a separate release directory. Point a `current`
symlink to that release. An XDG user autostart entry runs:

```ini
[Desktop Entry]
Type=Application
Name=LESA room panel
Exec=/bin/bash /absolute/path/to/current/app/start_panel.sh
Terminal=false
```

The launcher uses `--keep-switcher --duration 0`. Legacy, Escape and window close
use the guarded original-application path described above. Signal shutdown stops
the switcher and leaves confirmed light settings in place.

User autostart runs only after desktop login. Check the actual display manager
and session before enabling autologin; use that OS's supported configuration.
On older LightDM deployments, back up the configuration before adding a seat
drop-in with `autologin-user` and `autologin-user-timeout=0`. These settings do
not configure a different display manager. Autologin grants local desktop access.
Confirm the configured user/session and perform an authorized reboot test.

Rollback: send SIGTERM to the observed beta PID and wait for its helper to exit.
Leave the original process running. Disable only the owned XDG autostart entry,
or repoint `current` to a tested release. Restore the exact previous LightDM
drop-in when undoing autologin; if none existed, remove only the added file.
Preserve the private deployment values and receipts. Do not overwrite legacy code.

Keep journals, host configuration, participant data and screenshots private.
Do not delete logs or disable services merely because they look unused.

Panel event logging uses one background thread and a bounded queue. Annotations
show Saving before Saved; do not interpret Saving as persistence confirmation.
Close drains the writer asynchronously after lighting cleanup. Ordinary navigation
does not wait for SD-card fsync. Hardware-command recovery receipts remain synced
in the separate light helper.

Theme times use the panel process's configured timezone. Auto changes wait for
60 seconds without a touch and do not occur in Experiment mode. Settings use familiar
appearance, date/time, schedule and screen rows. Font and study defaults are launch
configuration; no separate settings service is needed.

## Reliable operation and maintenance

Coordinate with other room users before maintenance or power actions, including
recordings started on other computers. The website shares the panel's command
owner; it does not own ROS devices independently. Keep room-server maintenance
separate from restarting this Pi or its website.

Desktop autostart starts the panel after login, and the launcher lock rejects a
duplicate instance. This is not automatic recovery from a panel crash. The website's
separate user service restarts on failure after 15 seconds; a missing panel leaves
room controls unavailable. Before manually relaunching a crashed panel, inspect
its last receipt and verify the current owner. Do not repeat uncertain commands.

Restart and shut-down controls require explicit confirmation that the room is ready.
They use the same panel owner from touch and the trusted-network website. Only
fixed OS actions authorized by [existing system policy](https://github.com/systemd/systemd/blob/v252/man/org.freedesktop.login1.xml) are eligible; the panel does
not install privilege rules or execute arbitrary commands. An authentication
challenge alone is insufficient for unattended execution. Existing narrowly
authorized noninteractive operator commands may supply an alternative. An unavailable
action requires the operator's normal desktop or administration workflow.

Before requesting OS power changes, finish lighting operations, confirm ownership release
and helper exit, and wait for saved preferences and the event journal to finish.
An uncertain lighting result or a persistence error blocks the action. Do not use forced
shutdown or a direct power cut as the normal procedure. An accepted restart is
not proof of a successful boot: check desktop autostart, one panel/controller,
website availability and the new release identity afterward.

Use a [suitable power supply and cable](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#power-supply)
and keep a verified backup off the Pi.
File and directory synchronization improves saved-preference durability, but
sudden power loss can still damage storage or interrupt an unconfirmed hardware
operation. After an outage, preserve receipts, establish a fresh baseline and
verify room state before controlling again. A real power-cycle and recovery test
requires an available operator and a maintenance window.

Keep SSH keys and the explicit trusted-network allowlist; do not expose room control
through public port forwarding. Review OS/security updates in planned maintenance
windows and recheck Python/Tk, startup, fonts and room connectivity afterward.
Enabled APT timers alone do not establish that security upgrades are installed;
[Debian's update guidance](https://wiki.debian.org/PeriodicUpdates) explains the
separate configuration. Retain recovery receipts before managing log growth;
the append-only panel logs need an explicit retention or rotation policy.

## Fresh Raspberry Pi OS

The fresh-install profile uses Raspberry Pi OS Legacy 32-bit (Bookworm) on Pi 3.
Both applications use distribution Python 3.11, Tk 8.6 and Pillow 9.4. The modern
preview requirements are a separate optional environment; do not replace system
packages with pip. The room server remains unchanged.

1. Flash the OS, configure the user, hostname and SSH key, and boot the desktop.
2. Check power, storage and connectivity. Let any OS installation finish first.
3. Install the small client dependency set; no local ROS master is required:

   ```sh
   sudo apt-get install --no-install-recommends python3-tk python3-pil.imagetk \
     python3-requests python3-rospy python3-genpy
   ```

4. Obtain the verified custom client bundle from the room custodian. It contains
   `scr_control` generated Python bindings and the existing lights/blinds clients.
   The recovery capture also retains their `.srv` definitions and original source.
   Do not rebuild the old workspace's Python 2 native components on the new OS.
5. Extract the bundle under `~/.local/share/scr-panel/ros-clients`. Add its
   `bindings`, `scripts/lights` and `scripts/blinds` directories to `PYTHONPATH`
   in a private `ros-client.env` shell file. The captured utility client needs
   `except rospy.ServiceException as e` for Python 3; service definitions stay unchanged.
6. Verify client imports, request/response serialization, and live service type/MD5
   agreement. Read `/get_lights` and `/get_sources` before enabling setters.
7. Deploy a published checkout and create the private deployment file described
   above. Use the approved room address and the panel's reachable address. Add:

   ```sh
   SCR_ROS_SETUP="$HOME/.config/scr-panel/ros-client.env"
   SCR_CLASSIC_PYTHON=/usr/bin/python3
   SCR_PANEL_PYTHON=/usr/bin/python3
   SCR_ADAPTER_PYTHON=/usr/bin/python3
   SCR_START_MODE=room
   ```

8. Start `app/start_panel.sh` from the desktop session. The compatibility entrypoint
   `app/run_original.py` supplies Tk/Pillow aliases without modifying original code.
9. Add the owned XDG autostart entry shown above. Bookworm's labwc desktop calls
   `lxsession-xdg-autostart`; existing desktop autologin must also be enabled.
10. Check Beta → Legacy → Beta without lighting changes, settings and dynamic lighting.
    Confirm one process of each application and test duplicate launcher rejection.
    An unattended reboot is a separate final acceptance check.

The light helper announces initialization before receiving its first request.
Slow imports therefore do not age a queued lighting command beyond its ten-second
freshness limit. Heartbeats and operation deadlines remain enforced.

This is a room-specific client migration, not a complete server installation.
The external ROS master, fixture server and legacy HTTP demo runner are separate
dependencies. Do not infer working demos or physical blind motion from UI startup.

## Additional surfaces — agreed direction

Tk owns connected commands. The optional browser gateway already provides the
shared controls, preferences and guidance on the configured trusted room network,
with responsive tablet, desktop and phone layouts. Navigation, units, feedback and
theme semantics are shared; screen geometry can differ. Finer access roles below
remain a proposed direction; the current website admits everyone on its configured
trusted subnet.

| Role | Intended access |
|---|---|
| Visitor | Room introduction and non-personal status; no device writes |
| Room user | Everyday lighting when no experiment owns it |
| Staff | Advanced controls, experiment integration and configuration |

Enforce roles in the backend, not only by hiding buttons. Do not expose personal
experiment metadata to visitors. These proposed roles do not secure the existing
legacy ROS services or change the original application's access policy.

Use one shared, documented command/state contract and one command owner. Multiple
clients may observe; independent browser ROS owners must not compete with Tk.
Reuse the existing adapter and confirmed-readback rules. Migrate ownership only
after qualifying the new transport and updating its consumers together. Report
requested, pending, confirmed and uncertain results with age; do not infer physical
brightness or sensor health from service presence. Connection loss must not cause
automatic command retries or silent takeover of an experiment.

Prefer standard semantic HTML/CSS, large touch targets and visible keyboard focus.
Keep weather/help usable when room control is unavailable. Describe capabilities
and experiment profiles as data; keep Project-X's recorder integration in its own
repository. The implemented version 1 gateway schema is in docs/interface.md.
Choose packages for that tested workflow; no framework or room-server upgrade is
required for the current client. README owns setup, WORKFLOWS owns operation,
and tests/adapter contracts provide the starting point for human and agent changes.

## Backup and rebuild

The Git repository preserves panel source. It does not preserve the installed
operating system, private configuration or the room's custom ROS workspace.
Keep private recovery archives outside Git, with capture dates, source identity,
scope, read errors, archive size and SHA-256. Verify the downloaded backup too.

Preserve these layers before changing a working deployment:

1. Original application and assets, beta release and launcher.
2. Custom catkin source and generated workspace, including service definitions,
   clients, launch files and fixture lookup data.
3. User startup/settings, private deployment environment, SSH configuration,
   LightDM configuration, networking and display/touch settings.
4. Boot files, partition layout/identifiers, kernel/modules and installed package
   versions. Old package lists alone do not guarantee old binaries remain available.
5. A full-device image with its read-error map, repair provenance and checksums.

A live archive captures files at different times. A live image of a writable root
is not a consistent clone. Preserve any warnings and unreadable ranges. For a
consistent new device image, use clean shutdown and offline read-only acquisition
after the essential files are secured. Repair a separate copy; preserve the source.
Do not overlay an incomplete runtime archive, even if its transfer hash matches.

The fastest legacy restore uses a verified system image on known-good replacement
media. Check written bytes before booting. Match the saved root/boot identifiers
to the chosen SD or USB medium. Keep the original card disconnected during the
replacement test. Restore the current private application/configuration layer
only after comparing it with the image's files and installed versions.

A fresh OS is a migration. The original UI uses Python 2/Tkinter, Pillow and
custom ROS 1 clients. Preserve their service definitions and wire MD5s before
porting. Rebuild generated bindings for the chosen interpreter; verify service
types and wire MD5s before enabling writes. The ROS master, native light/blind
servers and HTTP demo/status endpoints are external dependencies. A Pi image
does not back them up. Use the room's existing deployment owner and contracts.

Restore acceptance requires desktop login, touch alignment, one Beta panel
process and the retained separate original Legacy process, touch-only switching,
read-only service/status checks, and an
authorized light-control/restoration trial. Verify original blinds and HTTP demo
controls through their existing owners when the room permits those actions.
Confirm power/storage health before an unattended reboot test. Record untested
behavior explicitly.


## Trusted-network browser controls

The browser release must include the gateway and the panel must include its local
bridge. Set `SCR_CONTROL_SOCKET` in the private panel deployment file and
`SCR_WEB_CONTROL_SOCKET` in the browser service’s private EnvironmentFile to the
same absolute socket path under the panel user’s private cache. Both processes run
as that user. The launchers pass their explicit socket options; omitting them keeps
browser control disabled. The fixed bind address and trusted-client subnet still
determine who can access the site. No separate staff login is implemented.

Deploy and qualify both compatible releases. Keep the original application and
room servers running. Legacy waits for safe release and helper exit, then pauses
website controls. Preserve its receipts. Restart only the owned browser service after
selecting its release. Check controller availability and receipt handling with a
same-value display preference, not an actuator command. If the panel bridge is
unavailable, web controls disable while the panel and guide/help remain usable.

Common actions and their rejection rules are owned by
[the interface contract](docs/interface.md#optional-browser-gateway-version-1).
Changing a website page does not move room devices. Explicit Legacy/display
controls affect the cabinet. A running instruction session blocks lighting on
both interfaces until paused. Pause instructions before opening Legacy, Blank or
clock view on either interface. Home keeps the instruction session running; use
Room tools → Experiment mode to pause it. Ordinary Beta pages and paused
instructions leave lighting available through the other interface. The gateway
also relays Gradient, original programme requests and permitted whole-room blind
actions through the same owner; it does not add independent hardware drivers.
Individual fixture/window selectors remain unimplemented. Reference commands may be copied,
never executed.
