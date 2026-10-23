# Panel interfaces, version 1

These contracts serve the existing Tk client and optional SCR light helper.
They are deliberately small. No registry, plugin loader or recorder
service is implemented.

## Study profile

A JSON object may override `title`, `sensors`, `stages` and `annotations`.
Unknown keys are rejected. No paths, callbacks or executable code are accepted.
The panel loads this file through `--profile` at startup. The browser/API can
operate its instructions and annotations; changing the profile through the API
is not implemented.

```json
{
  "title": "Room activity instructions",
  "sensors": "Study description; not a live sensor connection",
  "stages": ["Please sit still", "Move your hands", "Stand up"],
  "annotations": ["Activity started", "Activity finished", "Unexpected event"]
}
```

The title and description have at most 100 characters. There are 1–20 distinct
instructions, each at most 60 characters, and 1–4 distinct annotation labels,
each at most 20 characters. The client also checks text width at the selected
font. The final instruction pauses instructions; navigation does not wrap.

## Panel journal

`--journal` creates a new mode-0600 JSONL file, never appends to a recording.
Events have `version: 1`, `event`, `panel_run_id`, `sequence`, `boot_id`, UTC,
monotonic elapsed seconds, current mode/instruction and `recording: false`.
The boot identity is null where the operating system does not provide it.

Events include panel open/close, mode/theme/clock changes, practice start/pause,
instruction selection, named annotation, and lighting request/result.
One background writer preserves event order through a bounded 128-event queue.
Ordinary event journal and console writes run outside the Tk thread. Events are flushed
without a per-click fsync; annotation batches and final shutdown are synced.
Annotations show Saving until their flush/fsync acknowledgement arrives; storage
failure or a full queue is reported. Recent ordinary events can be lost on abrupt
power failure. The lighting helper's separate durable recovery receipts are unchanged.
Experiment mode writes a panel journal, not canonical sensor-recording metadata.
The existing `practice_started`, `practice_paused` event names and `panel_practice`
annotation scope remain unchanged for journal consumers.

A future recorder adapter must provide actual recorder state and timestamp
provenance. It must not infer recording from the instruction timer. Project-X or
another experiment owns import, clock association and participant handling.

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

Actions are `acquire`, `cct`, `channels`, `gradient`, `programme`, `blind`,
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
only through the persistent shared owner; an uncertain result disables further
commands until checked.

Replies echo `version` and `request_id`. States are `ready`, `completed`,
`released` or `failed`. Success includes fixture count and relevant baseline,
words or release flags. Persistent `--keep-settings` acquisition admits any stable
snapshot and reports its confirmed `power`; `baseline` is null for a custom mix.
Its release returns `preserved: true, restored: false` without a fixture setter.
Normal Beta/Legacy navigation retains the same helper without any release/acquire
cycle. Preserving release applies to Original fallback, shutdown and parent loss. Bounded trials
omit that flag, require an exactly restorable preset and retain `restored: true`
on successful cleanup. Failure includes detail and whether outcome is unknown.
Unknown extra fields are ignored; unsupported versions are refused.

Only one request is in flight. Requests are capped at 4096 bytes; buffers at
8192 bytes. Requests older than the ten-second lease are refused. Both processes
use the same host monotonic clock. Initialization is the only unsolicited message.
Recovery receipts include baseline and request/result records.

The same helper has a separate `--status-only` command. It reads the ROS master's
service graph through one XML-RPC call, then exits without a ROS node or fixture
queries. The UI bounds that subprocess, refreshes only while System is visible
and labels the result as advertised service availability. It does not query TOF,
blinds, HVAC or acquisition data, and does not assess IRMA recorder health.

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
instruction start/pause/previous/next/known annotations, panel appearance/clock/
weather/idle preferences, blind permission/visibility, Home, Legacy, Original fallback, clock view and
blank display. All inputs are bounded enums or integers. Lighting requires ready
readback, no pending/queued/held touch and no running instructions. Original fallback,
blank and uncertain states block lighting. Ordinary Beta pages, including Guide,
Settings, About and paused Experiment mode, do not restrict lighting availability.
Panel and browser use these same study guards.
Acceptance is not lighting confirmation, annotation persistence or recording.

`legacy` with empty arguments selects `Panel.mode == "classic"`, the familiar
Legacy layout inside the existing Panel/Tk process. It retains the same command
owner, helper PID, ROS initialization and programme state. It is presentation only,
including while instructions run; instruction guards still prevent actuator commands.
`original_fallback` with empty arguments selects `mode == "original"` through the
existing guarded helper-release path. That mode opens the untouched separate
original application, blocks website control, and is identified as Original fallback.
The normal Legacy action never launches or acquires a second controller. This is
an in-process shared view, not a new standalone headless control service.

Blind readiness separates the short user-facing `detail` (Disabled, Busy or Ready)
from a diagnostic `reason`. When no controller is connected, settings show one
unavailable note and omit unlocking. The saved `blinds_enabled` permission and controller
connection remain independent; unlocking never connects a controller or moves blinds.

`blinds_enabled` accepts a boolean `value`; `blind` accepts only a `name` of
`lift`, `open` or `close`. The owner rechecks the saved permission, controller
connection and busy/Original-fallback/experiment guards at dispatch. Visibility does not
grant permission. The existing helper advertises connection when the whole-room
lift/tilt services are present and persistent control owns the resource. Tk
enqueues work without blocking for movement. The browser updates permission
visibility when this connection changes. Window-group addressing and physical
position measurement are not implemented.

Lighting navigation contains White light, Scenes, Programmes and Channels.
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
The owner refuses busy, running-instruction, Original-fallback and uncertain-light states,
then requires confirmed ownership release, helper exit, saved preferences and a durable
power-request record before one fixed OS command. Existing noninteractive
permission and OS inhibitors are respected; no new privilege rule or automatic
retry is installed. These actions affect this Pi and website, not room computers
or recorders. Optional `power`, `app_version` and `build_commit` snapshot fields
describe availability and About information without changing schema version 1.

`app/design_tokens.py` owns theme roles. `app/export_room_content.py` exports the
panel-owned guide/help and Lucide paths for browser fallback and offline demos.
The website reads guide/help only from that export. The live snapshot supplies
current preferences, controls, receipts and experiment state. Normal Beta and
Legacy layouts currently share the owner; Original fallback is the separate app.

`app/help_reference.py` owns each command step's computer, effect, purpose,
expected result and exact copy text. A help topic exports its `reference` object
alongside the complete `commands` text for older clients. The complete text joins
step commands with blank lines; highlighting never changes that text. These are
display/copy references, not executable gateway actions.

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
