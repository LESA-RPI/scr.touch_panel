# Panel interfaces, version 1

These contracts serve the existing Tk client and optional SCR light helper.
They are deliberately small. No registry, plugin loader or recorder
service is implemented.

## Study profile

A JSON object may override `title`, `sensors`, `stages` and `annotations`.
Unknown keys are rejected. No paths, callbacks or executable code are accepted.

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
the trial. It ignores duplicate initialization messages. Pipes carry JSON lines.
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

Actions are `acquire`, `cct`, `channels`, `release` and `heartbeat`.
Channels takes eight integer percentages in installed channel order:
Blue 1, Blue 2, Blue 3, Lime, Amber, Orange, Red 1, Red 2.
CCT permits 1600–10000 K; intensity permits 0–1900 lookup units.
Heartbeat needs no request ID and produces no response.

Replies echo `version` and `request_id`. States are `ready`, `completed`,
`released` or `failed`. Success includes fixture count and relevant baseline,
words or restoration flag. Failure includes detail and whether outcome is unknown.
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
No new hardware adapter, shell executor or recording adapter exists.

A command has exactly `id`, `revision`, `action`, `arguments`. IDs are unique,
16–80 alphanumeric/hyphen characters. The revision identifies the panel session,
journal sequence and view generation. A stale revision returns409 without executing.
Duplicate IDs return their original receipt; differing payloads with a reused ID
are refused. Queued requests expire after two seconds. Lost acceptance is uncertain:
clients query receipts and never automatically repeat commands.

The shared actions cover on/off, CCT/level, eight channels, admitted presets,
instruction start/pause/previous/next/known annotations, panel appearance/clock/
weather/idle preferences, blind permission/visibility, Home, Legacy, clock view and
blank display. All inputs are bounded enums or integers. Lighting requires ready
readback, no pending/queued/held touch and no running instructions. Legacy and
uncertain states block lighting. Panel and browser use these same study guards.
Acceptance is not lighting confirmation, annotation persistence or recording.

Blind readiness separates the short user-facing `detail` (Disabled, Busy or Ready)
from a diagnostic `reason`. The saved `blinds_enabled` permission and controller
connection remain independent; unlocking never connects a controller or moves blinds.

`blinds_enabled` accepts a boolean `value`; `blind` accepts only a `name` of
`lift`, `open` or `close`. The owner rechecks the saved permission, controller
connection and busy/Legacy/experiment guards at dispatch. Visibility does not
grant permission. No blind adapter is installed, so commands are rejected even
when the preference is enabled. A future adapter must own its resource and
enqueue through `submit(name)` without blocking Tk; this is not a qualified
hardware implementation. Window-group addressing is not implemented.

Lighting navigation contains White light, Scenes, Programmes and Channels.
`app/room_controls.py` owns their shared labels and descriptions. Gradient, Sun
and Circ are represented with disconnected controls, not exposed as executable
actions. No HTTP script launcher or independent programme runner is added.

The opt-in HTTP gateway exposes `/api/controller` and `/api/command`. Commands
require the exact configured Host, matching Origin, a per-service nonce and bounded
JSON. The existing source-subnet allowlist applies to every request. Everyone in
that subnet can control the room; there is no separate user identity system.
`/api/status` and diagnostics remain observation-only. Service-start and restart
references are display/copy text, never command actions.

`app/design_tokens.py` owns theme roles. `app/export_room_content.py` exports the
panel-owned guide/help and Lucide paths for browser fallback and offline demos.
The live snapshot supplies current preferences, controls, receipts, guide/help and
experiment state. Original Legacy controls are external to this common Beta API.

`app/help_reference.py` owns each command step's computer, effect, purpose,
expected result and exact copy text. A help topic exports its `reference` object
alongside the complete `commands` text for older clients. The complete text joins
step commands with blank lines; highlighting never changes that text. These are
display/copy references, not executable gateway actions.

## Planned individual device controls

The legacy room clients expose coordinate-based light `cct`/`sources` operations
and named-blind `lift`/`tilt` operations in addition to whole-room commands.
This is source-level capability evidence, not qualification of installed services.
Beta's current light helper only admits whole-room commands, and its blind
adapter is not implemented. No individual target picker is exposed yet.

The intended extension keeps All as the default. An optional individual-controls
setting would reveal only verified device names/groups reported by the owning
adapter. Selecting a target must not send a command. Home's power shortcuts must
always address All, and opening a new session must not inherit a previous narrow
target. Window groups need an explicit mapping; client list order is not a room map.

Every queued intent and receipt must include its immutable target. Invalid or
missing target identities must be rejected rather than falling back to All.
Per-fixture writes must verify unaffected fixtures, preserve the owner's expected
state and retain exact starting-state restoration. Blind ownership, naming,
response/readback and completion semantics need qualification before wiring its
controller; a setting alone cannot establish those capabilities.
