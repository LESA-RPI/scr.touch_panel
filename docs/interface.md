# Panel interfaces, version 1

These contracts serve the existing Tk client and optional SCR light helper.
They are deliberately small. No registry, plugin loader, network API or recorder
service is implemented.

## Study profile

A JSON object may override `title`, `sensors`, `stages` and `annotations`.
Unknown keys are rejected. No paths, callbacks or executable code are accepted.

```json
{
  "title": "Seated activity practice",
  "sensors": "Study description; not a live sensor connection",
  "stages": ["Please sit still", "Move your hands", "Stand up"],
  "annotations": ["Activity started", "Activity finished", "Unexpected event"]
}
```

The title and description have at most 100 characters. There are 1–20 distinct
instructions, each at most 60 characters, and 1–4 distinct annotation labels,
each at most 20 characters. The client also checks text width at the selected
font. The final instruction pauses practice; navigation does not wrap.

## Panel journal

`--journal` creates a new mode-0600 JSONL file, never appends to a recording.
Events have `version: 1`, `event`, `panel_run_id`, `sequence`, `boot_id`, UTC,
monotonic elapsed seconds, current mode/instruction and `recording: false`.
The boot identity is null where the operating system does not provide it.

Events include panel open/close, mode/theme/clock changes, practice start/pause,
instruction selection, named annotation, and lighting request/result.
Annotations are acknowledged after flush and fsync; storage failure is reported.
This is a panel practice journal, not canonical sensor-recording metadata.

A future recorder adapter must provide actual recorder state and timestamp
provenance. It must not infer recording from the practice timer. Project-X or
another experiment owns import, clock association and participant handling.

## Local light helper

The UI launches one subprocess using inherited, validated deployment ROS settings.
Pipes carry JSON lines. Requests have:

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
use the same host monotonic clock. There are no unsolicited status messages in
this version. Recovery receipts include baseline and request/result records.

The same helper has a separate `--status-only` command. It reads the ROS master's
service graph through one XML-RPC call, then exits without a ROS node or fixture
queries. The UI bounds that subprocess, refreshes only while System is visible
and labels the result as advertised service availability. It does not query TOF,
blinds, HVAC or acquisition data, and does not assess IRMA recorder health.
