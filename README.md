# SCR room browser interface

A browser companion to the touch panel, with the same Home controls, one Lighting
workspace (White light, Scenes, Programmes and Channels), instruction workflow,
preferences, guide and help. The panel owns
all commands. Diagnostics remain observation-only. Legacy opens the original
application on the cabinet; its original actuator controls stay there.

Browser control is opt-in: pass `--panel-control-socket` to `browser/serve.py`, or
set `SCR_WEB_CONTROL_SOCKET` for `browser/start.sh`, pointing to the panel’s
private socket. Enable its matching `--control-socket` / `SCR_CONTROL_SOCKET`.
Both run as the same user. Keep the explicit bind address and client-subnet
allowlist. Everyone on that configured subnet can use controls; there is no
separate staff login. Without a bridge, controls disable and guide/help remain
available. No browser hardware driver is imported.

Commands use the existing panel queue, require a fresh revision and are never
automatically retried. Confirmed readback alone selects Lights on/off. Pending,
uncertain or disconnected states clear that selection. Running instructions block
lighting from both interfaces. All three original blind actions are visible;
movement has a saved Locked/Unlocked setting, locked by default, and requires a connected
controller. None is installed in the new interface. Gradient, Sun and Circ remain visible with
disconnected Apply/Start controls until their adapters are integrated. Empty Legacy
placeholders and the redundant Enable Sliders gate are omitted. Experiment mode does not
start a recorder. Service-start/restart references are monospace text with Copy,
never executable buttons. Each documented step explains the computer, purpose
and expected result, with its own Copy button and a Copy all option for the topic.
Dark backgrounds stay neutral gray; controls, weather and status use restrained
teal, warm and green/amber accents shared with the panel.
Weather readings use aligned labels and values, with dashes for missing readings.
Earlier forecasts are dated and hide current-day details until fresh data returns.
Screen & controls can preview the touch panel's screen saver. The idle timer and
preview open the same screen; its first touch returns to Home without activating
a control. Date & weather contains clock-format and temperature preferences.
System & help can restart or shut down the touch panel when its power controls
are available. Each request requires a confirmation and an acknowledgement that
recordings and experiments have stopped. The panel validates ownership, restores
lighting and saves its state before the operating-system action. These controls
do not stop other room computers or recorders. A restart or shutdown disconnects
this website; unknown requests are never retried automatically.
Desktop layouts place white-light controls side by side. Landscape tablets keep
large controls; phones put lights first with expandable blinds and a compact
Room tools section selector. Numeric light
values can be typed or adjusted with sliders. Enter or leaving a valid field
applies the selection; Escape cancels. Empty or out-of-range values never dispatch.
Polling preserves an edit, and the panel still validates its original revision.
The website bundles the same Cantarell family used by the panel, so its layout
does not depend on a visitor's installed fonts. Unmodified font files retain
their [SIL Open Font License](browser/fonts/LICENSE).

Run `python -m pytest tests`. HTTP tests use loopback mock services and cover Host,
Origin, nonce, subnet, bounded command bodies, static allowlists and read-only
diagnostics. Browser interaction and native Pi qualification are separate checks.
Do not merge the draft experiment branch without researcher approval.

Panel-owned guide/help, design roles and Lucide paths are exported by
`app/export_room_content.py` in the panel branch to `browser/room-content.json`.
Live controller state supplies the same content and preferences. Preserve source
provenance when rebuilding browser assets. The artwork notices remain in
[browser/icons/LICENSE](browser/icons/LICENSE). Original contributors are retained
in repository history. The interface is maintained by Diyanko Bhowmik.
