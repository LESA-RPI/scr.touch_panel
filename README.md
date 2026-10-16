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
movement is a separate saved setting, disabled by default, and requires a connected
controller. None is installed in Beta. Gradient, Sun and Circ remain visible with
disconnected Apply/Start controls until their adapters are integrated. Empty Legacy
placeholders and the redundant Enable Sliders gate are omitted. Experiment mode does not
start a recorder. Service-start/restart references are monospace text with Copy,
never executable buttons. Each documented step explains the computer, purpose
and expected result, with its own Copy button and a Copy all option for the topic.
Dark backgrounds stay neutral gray; controls, weather and status use restrained
teal, warm and green/amber accents shared with the panel.
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
in repository history. Beta is maintained by Diyanko Bhowmik.
