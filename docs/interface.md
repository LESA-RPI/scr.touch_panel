# Panel interfaces, version 1

These contracts serve the existing Tk client and optional SCR light helper.
They are deliberately small. No registry, plugin loader or recorder
service is implemented.

## Panel journal

`--journal` creates a new mode-0600 JSONL file, never appends to a recording.
Events have `version: 1`, `event`, `panel_run_id`, `sequence`, `boot_id`, UTC,
monotonic elapsed seconds, current mode and `recording: false`.
The boot identity is null where the operating system does not provide it.

Events include panel open/close, mode/theme/clock changes and lighting request/result.
One background writer preserves event order through a bounded 128-event queue.
Ordinary event journal and console writes run outside the Tk thread. Events are flushed
without a per-click fsync; power-request records and final shutdown are synced.
Storage failure or a full queue is reported. Recent ordinary events can be lost on abrupt
power failure. The lighting helper's separate durable recovery receipts are unchanged.

## Local light helper

The UI launches one subprocess using inherited, validated deployment ROS settings.
After initialization, the helper sends `{"version": 1, "state": "initialized"}`.
The UI then sends a fresh acquire request, or release if navigation already ended
the session. It ignores duplicate initialization messages. Pipes carry JSON lines.
Requests have:

```json
{
  "version": 1,
  "request_id": "panel-run:1",
  "action": "cct",
  "arguments": {"cct": 3500, "intensity": 1000},
  "sent_monotonic_s": 12345.6
}
```

Actions are `acquire`, `check`, `return_legacy`, `cct`, `channels`, `gradient`, `programme`, `blind`,
`release` and `heartbeat`.
Channels takes eight integer percentages in installed channel order:
Blue 1, Blue 2, Blue 3, Lime, Amber, Orange, Red 1, Red 2.
CCT permits 1600–10000 K; intensity permits 0–1900 lookup units.
Heartbeat needs no request ID and produces no response.

`gradient` has empty arguments and applies the fixed original ten-fixture spatial
pattern, verifying the complete fixture-word map. Its reply identifies
`scene: "Gradient"`, confirmed `power`, and `fixture_words`; it does not invent
uniform channel words. `programme` accepts only `name: "Sun"`, `"Circ"` or
`"Stop"`. In persistent control it relays fixed Run/Kill requests to the existing
Status service supplied by private `SCR_STATUS_URL`/`--status-url` configuration.
HTTP acceptance is not process-running or completion confirmation. Before an
explicit manual lighting action, the helper requests both programmes stop and
requires two stable drive snapshots. Navigation and ownership release do not
start, stop or restore a programme.

`blind` accepts `name: "lift"`, `"open"` or `"close"` and uses the original
whole-room service sequence. Lift requests lift 100; Open requests tilt 50;
Close requests tilt 100 followed after two seconds by lift 0. Returned values
acknowledge service acceptance, not measured physical position. This is available
only through the persistent shared owner; a failed result ends the helper and
the panel reconnects with a fresh read.

Replies echo `version` and `request_id`. States are `ready`, `checked`, `completed`,
`released` or `failed`. Success includes fixture count and relevant baseline,
words or release flags. Persistent `--keep-settings` acquisition admits any stable
snapshot and reports its confirmed `power`; `baseline` is null for a custom mix.
Its release returns `preserved: true, restored: false` without a fixture setter.
Ordinary Beta navigation retains the same helper. Preserving release applies to
Legacy, shutdown and parent loss. Bounded trials
omit that flag, require an exactly restorable preset and retain `restored: true`
on successful cleanup. Failure includes detail and whether outcome is unknown.
Unknown extra fields are ignored; unsupported versions are refused.

Only one request is in flight. Requests are capped at 4096 bytes; buffers at
8192 bytes. Requests older than the ten-second lease are refused. Both processes
use the same host monotonic clock. Initialization is the only unsolicited message.
Recovery receipts include baseline and request/result records.
Handoff checkpoints (Legacy entry and return) are saved by
one background writer in FIFO order and wait for those saves. Everyday commands are
tracked in memory only. Helper input uses bounded nonblocking writes on Linux, failing closed
when its pipe is full. Power execution waits for recovery storage as well.

The same helper has a separate `--status-only` command. It reads the ROS master's
service graph through one XML-RPC call, then exits without a ROS node or fixture
queries. The UI bounds that subprocess, refreshes only while System is visible
and labels the result as advertised service availability. It does not query TOF,
blinds, HVAC or acquisition data, and does not assess IRMA recorder health.

`check` has empty arguments and returns `checked` after stable read-only scans of
all ten lights. In room control a stable check adopts the current settings.

## Lighting ownership and recovery

Handoffs persist before they proceed. An interrupted handoff and storage errors
block writes across restart; an interrupted everyday command does not.

The public `lighting_recovery` snapshot contains `status`, `title`, `detail`,
`can_check`, `needs_staff` and `write_blocked`.
States are `normal`, `writing`, `checking`, `returning`,
`needs_staff`, `offline`, `legacy`. Public `check_connection` takes no arguments,
reads only and cannot clear uncertainty or override ownership. The website retains
unknown receipts until a matching receipt or new owner session; it never resends.

## Optional weather details

The bounded weather helper may add `feels_like_f`, `high_f`, `low_f` and
`rain_chance`. Valid temperatures also include corresponding `_c` values. Missing
fields are omitted so older samples remain readable; probabilities must be finite
and within 0..100, and a daily low cannot exceed its high. Home labels rain as
today's maximum forecast probability. Daily details are hidden for older readings.
Attribution and model time remain in Date & weather and website Weather details.


## Optional browser gateway, version 1

The panel remains the only lighting command owner. `--control-socket` enables a
private mode-0600 Unix socket; a same-user browser service may relay requests.
Socket threads only read immutable snapshots or enqueue bounded requests. The Tk
thread validates current ownership/state and calls the existing panel methods.
The gateway adds no hardware driver, shell executor or recording adapter; the
existing helper owns the qualified room-service calls.

A command has exactly `id`, `revision`, `action`, `arguments`. IDs are unique,
16–80 alphanumeric/hyphen characters. The revision identifies the panel session,
journal sequence and view generation. A stale revision returns 409 without executing.
Duplicate IDs return their original receipt; differing payloads with a reused ID
are refused. Queued requests expire after two seconds. Lost acceptance is uncertain:
clients query receipts and never automatically repeat commands.

The shared actions cover on/off, CCT/level, eight channels, admitted presets, Gradient,
original programme requests, permitted whole-room blinds,
panel appearance/clock/
weather/idle preferences, blind permission/visibility, Home, Legacy, Check connection, clock view and
blank display. Inputs use bounded enums or numbers. Lighting requires ready
readback, no pending/queued/held touch. Legacy,
blank and uncertain states block lighting. Ordinary Beta pages, including Guide,
Settings and About, do not restrict lighting availability.
Panel and browser use these same guards.
`on` applies the Fid preset. White light's Warm white uses `cct` with 3500 K
and intensity 1000; Fid remains a separately selectable scene.
Acceptance is not lighting confirmation or recording.
During a requested Sun/Circ programme, a read-only check verifies the ten fixture
identities without querying changing drive values or confirming running status.
Stop performs the full stable-drive check. Read failures and pre-existing
uncertainty still block writes; an identity check never clears them.

`legacy` (alias `original_fallback`) takes no arguments and opens `mode: "original"`
after preserving release and successful helper exit. The unchanged original app
sits behind a 144-pixel navigation strip; Beta/website actuators pause. Uncertainty guards still apply.
Home covers original input, probes its exact Tk PID and checks the entry log:
same readable file, bounded new output and no new callback/service errors.
Failed checks retain `legacy` ownership and allow reopening the same app. Otherwise
a durable writing marker precedes bounded `return_legacy`: stop Sun/Circ and read
all ten fixtures twice. Stable success automatically enables Ready with current
drive preserved. Failed stop, moving readback or lost result blocks both control
paths across restart until local staff reconciliation. Original callbacks remain
unchanged; no old scene is restored and no ROS/Status restart occurs.

Blind readiness separates the short user-facing `detail` (Disabled, Busy or Ready)
from a diagnostic `reason`. When no controller is connected, settings show one
unavailable note and omit unlocking. The saved `blinds_enabled` permission and controller
connection remain independent; unlocking never connects a controller or moves blinds.

`blinds_enabled` accepts a boolean `value`; `blind` accepts only a `name` of
`lift`, `open` or `close`. The owner rechecks the saved permission, controller
connection and busy/Legacy guards at dispatch. Visibility does not
grant permission. The existing helper advertises connection when the whole-room
lift/tilt services are present and persistent control owns the resource. Tk
enqueues work without blocking for movement. The browser updates permission
visibility when this connection changes. Window-group addressing and physical
position measurement are not implemented.

Lighting navigation contains White light, Scenes, Programmes and Channels.
`lights.confirmed_power` retains the last readback alongside `recent` and its age,
including while a command is pending or uncertain. It is historical display data,
never a readiness signal; guarded `power`, `scene` and `can_control` retain their
existing semantics. Lighting action buttons use explicit confirmation text instead
of pressed-state styling.
`app/room_controls.py` owns their shared labels and descriptions. The gateway
accepts `gradient` with empty arguments and `programme` with exactly the fixed
`name` enum above. `lights.capabilities.gradient` and `.programmes` advertise
available controls; absent capabilities keep those controls hidden. Scenes adds
Gradient separately from the admitted uniform presets. Programmes provides
original Sun/Circ Start and Stop controls. Stop does not require lighting-ready
state, but ownership, busy and uncertain-result guards still apply.
`lights.programme` is the last selected name or null, and
`lights.programme_confirmed` is false: the UI reports requests, never confirmed
running status. There is no general HTTP script launcher or second programme owner.

The opt-in HTTP gateway exposes `/api/controller` and `/api/command`. Commands
require the exact configured Host, matching Origin, a per-service nonce and bounded
JSON. The existing source-subnet allowlist applies to every request. Everyone in
that subnet can control the room; there is no separate user identity system.
`/api/status` and diagnostics remain observation-only. Service-start and restart
references are display/copy text, never command actions.

Pi power actions use `power` with exactly `operation` (`reboot` or `shutdown`)
and `confirmed: true`. They share the existing network and revision checks.
The owner refuses busy, Legacy and uncertain-light states,
then requires confirmed ownership release, helper exit, saved preferences and a durable
power-request record before one fixed OS command. Existing noninteractive
permission and OS inhibitors are respected; no new privilege rule or automatic
retry is installed. These actions affect this Pi and website, not room computers
or recorders. Optional `power`, `app_version` and `build_commit` snapshot fields
describe availability and About information without changing schema version 1.

`app/design_tokens.py` owns theme roles. `app/export_room_content.py` exports the
panel-owned guide/help and Lucide paths for browser fallback and offline demos.
The website reads guide/help only from that export. The live snapshot supplies
current preferences, controls and receipts. Beta and the website
share the owner; Legacy hands control to the unchanged separate original app.

`app/help_reference.py` owns each command step's computer, effect, purpose,
expected result and exact copy text. A help topic exports its `reference` object
alongside the complete `commands` text for older clients. The complete text joins
step commands with blank lines; highlighting never changes that text. These are
display/copy references, not executable gateway actions.

Guide metadata owns the room/control sections, captions and safe destinations.
The ceiling map is a static derived snapshot of Project-X-Ceiling's registered
grid cells, with source date and hash. It carries no device endpoint or health
state and makes no network request. Channel/grid diagrams are static schematics.
Explicit guide scene buttons use existing owner actions; navigation is passive.
No new poller or background service is used by guides.
The nested ceiling-map schema is version 2. Each family position has `cell`
([R index, C index]), `reference_id`, and lower-left-normalized `u`/`v` offsets.
These are dated source annotations and logical references, not live device IDs
or surveyed positions. Family colours come from the same reference layout.
Optional `fixtures` groups use the same position fields for quiet troffer,
HVAC and sprinkler symbols. `fixtures_source` records their provenance;
these annotations add no controls, measured footprints or live status.

`room_diagnostics` contains `state`, copied `services` rows (`name`,
`listed`/`missing` state), `observed_at`, monotonic `age_s`, `checking`, `can_check`
and explanatory `detail`. Successful metadata probes replace the observation;
failures retain its data/time. `refresh_status` takes no arguments and requests
the same bounded worker. It is read-only, does not alter held-touch or uncertain
lighting state, and does not replay a device command. Gateway `/api/status`
reuses this owner cache, preserving age; it does not fall back to a separate ROS
query if the configured owner is unavailable. Standalone mode remains independent.

`network_name` identifies the configured visitor Wi-Fi. Its confirmed default is
panel-owned shared content; deployment may override it. The optional private
Wi-Fi key is shown only by the physical panel QR component and never included
in snapshots, exports or journals.

## Planned individual device controls

The legacy room clients expose coordinate-based light `cct`/`sources` operations
and named-blind `lift`/`tilt` operations in addition to whole-room commands.
This is source-level capability evidence, not qualification of installed services.
Beta exposes whole-room manual controls, the fixed per-fixture Gradient and
whole-room blind actions. No arbitrary individual target picker is exposed yet.

The intended extension keeps All as the default. An optional individual-controls
setting would reveal only verified device names/groups reported by the owning
adapter. Selecting a target must not send a command. Home's lighting shortcuts must
always address All, and opening a new session must not inherit a previous narrow
target. Window groups need an explicit mapping; client list order is not a room map.

Every queued intent and receipt must include its immutable target. Invalid or
missing target identities must be rejected rather than falling back to All.
Per-fixture writes must verify unaffected fixtures, preserve the owner's expected
state and preserve current settings during view changes. Exact restoration remains
a separate bounded-trial requirement. Blind ownership, naming,
response/readback and completion semantics need qualification before wiring its
controller; a setting alone cannot establish those capabilities.

Presentation is split into `app/panel_views.py` (room, lighting and preferences),
`app/panel_screensaver.py` (clock/weather) and `app/panel_guidance.py` (guide/help).
They use the same `Panel` instance; `app/scr_touch_panel.py` retains command,
recovery and lifecycle ownership. `app/panel_common.py` owns shared presentation
values and pure helpers. Preset mixtures remain in `app/scr_touch_panel_lights.py`;
shared control metadata and the browser export derive their available scene IDs
from those mixtures. `browser/room-content.json` is generated fallback data and is
checked against its exporter in tests, including the plain About version.
