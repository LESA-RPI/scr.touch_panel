# Panel operation

The root `main.py` is the original room application. Keep its installed checkout,
working directory and ROS environment intact. The new `app/` client runs above
it. Do not replace the installed legacy files.

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

Acquire requires two matching scans and one uniform Fid, Sat, Dul or Off preset.
Arbitrary drive words and Standard white baselines are refused because their
exact restore path is not qualified. Use Original controls to establish an
admitted baseline when no other study holds lighting, then re-enter Room.

One Tk process owns display interaction. One helper owns this trial's ROS calls.
The helper checks all fixture words before each write and after its response.
It does not claim optical accuracy. The existing setter accepts integer
percentages, which cannot reproduce arbitrary fractional drive settings.

## Switching and recovery

Room exposes everyday sliders and static presets. Advanced controls opens the
channel editor; Back returns directly. All light controls share one latest
selection queue. Wait for confirmation to distinguish a selection from a result.

Original controls waits for confirmed restoration and helper exit before showing
the legacy program. Its matching navigation strip supports touch-only return.
That strip covers the legacy banner, not its actuator buttons.

The helper has a ten-second parent lease and 30-second operation budget, with
individual service calls bounded to at most twelve seconds. Parent loss triggers
cleanup only when the last confirmed drive state still matches. A lost response
or external change disables further writes and automatic restoration. Never retry
an uncertain write. Inspect the private `.lights-*.jsonl` receipt and coordinate
with staff before controlling again.

Deadlines do not bound filesystem stalls or ROS initialization. The normal UI
waits for restoration; process exit alone does not prove that lights were restored.
`SIGKILL` or host power loss cannot guarantee restoration.

Blank screen displays black pixels. A stationary two-second press returns to the
previous view; movement beyond 40 pixels cancels. The backlight remains powered.
Use qualified display-power control for experiments needing complete darkness.

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
```

Use existing, verified deployment values. Keep this file mode 0600 and outside
Git. The launcher sources the installed ROS setup, sets the same original
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

The launcher uses `--keep-switcher --duration 0`. Settings, Escape and a window
close return to Original after helper cleanup; the touch strip remains. Returning
to Room checks a fresh baseline. If restoration is uncertain, inspect the receipt
before changing lights. Signal shutdown still stops the switcher.

User autostart runs only after login. Where unattended boot is required, back up
the existing LightDM configuration before adding a seat drop-in with
`autologin-user` and `autologin-user-timeout=0`. This grants local desktop access.
Confirm the configured user/session and perform an authorized reboot test.

Rollback: send SIGTERM to the observed beta PID and wait for its helper to exit.
Leave the original process running. Disable only the owned XDG autostart entry,
or repoint `current` to a tested release. Restore the exact previous LightDM
drop-in when undoing autologin; if none existed, remove only the added file.
Preserve the private deployment values and receipts. Do not overwrite legacy code.

Keep journals, host configuration, participant data and screenshots private.
Do not delete logs or disable services merely because they look unused.

Theme times use the panel process's configured timezone. Auto changes wait for
60 seconds without a touch and do not occur in Experiment. Settings use familiar
appearance, date/time, schedule and screen rows. Font and study defaults are launch
configuration; no separate settings service is needed.

## Read-only browser status

The browser status server is independent of Tk, ROS client bindings and Project-X.
It uses Python 3.11's standard library and the existing LESA logo. It imports no
control adapter and exposes no actuator, recorder or maintenance command route.

```sh
# Local-only review; no room queries.
python -B browser/serve.py

# Room host: substitute verified private interface/master addresses.
python -B browser/serve.py --bind PANEL_PRIVATE_IP --port 8768 \
  --label "Cabinet Pi" --master http://ROOM_PRIVATE_IP:11311
```

The server binds one explicit private IPv4 address, not all interfaces. Open the
printed literal-IP URL; Host/Origin checks intentionally refuse other hostnames.
No router forwarding, firewall changes or public hosting are part of this setup.
There is no sign-in: anyone able to reach it can view the limited status payload.
Keep it on the trusted room network. This does not secure existing ROS services.

One sampler refreshes host resources and the ROS master's `getSystemState` graph
every 30 seconds, independent of visitor count. It registers no node, starts no
producer and calls no device services. Omit `--master` for host-only operation.
The graph response is capped at 256 KiB; its subprocess ends after four seconds.
HTTP requests have a four-second absolute deadline and a two-second idle timeout.
Requests serve only an in-memory snapshot and explicitly listed static assets.
No directory listing, arbitrary file access, CORS or write endpoints are provided.

Host readings describe the server computer, not every room computer. The clock
shows Troy's America/New_York time using the viewing device's clock. Service cards
show advertised/partly advertised/not advertised registrations, not physical health
or recording state. After failure, previous observations retain their original
age. Samples older than 90 seconds are labelled stale. Visible pages poll every
30 seconds; hidden tabs pause requests. Snapshot data includes no raw recordings,
participant information, service-provider names, paths or private master address.

For this trial, start the process separately and retain its release commit. Do not
replace panel autostart, install an OS service or restart the room computer. Stop
the foreground process with Ctrl+C, or stop only its verified PID if launched in
the background. No lighting restoration is needed because it owns no lights.
Reboot persistence is deliberately not configured. Validate small screens,
keyboard navigation, failure age and resource use before broader deployment.

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

Restore acceptance requires desktop login, touch alignment, exactly one original
and beta process, touch-only switching, read-only service/status checks, and an
authorized light-control/restoration trial. Verify original blinds and HTTP demo
controls through their existing owners when the room permits those actions.
Confirm power/storage health before an unattended reboot test. Record untested
behavior explicitly.
