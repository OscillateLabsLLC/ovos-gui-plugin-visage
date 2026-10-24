# GUI-1 adapter ⇄ Visage wire protocol, version 1 (prototype)

Source of truth for the prototype. Both `ovos-gui-plugin-visage` (server) and Visage (client)
implement exactly this. Origin: `ovos-gui-visage/docs/GUI1_PLAN.md` §2.2. Changes go here first.

## Transport

- One websocket per client. Default endpoint `ws://<host>:18182/gui1`. The prototype stack uses
  port **28182**. Adapter config keys: `host` (default `127.0.0.1`), `port` (default `18182`),
  `path` (default `/gui1`).
- Every message is one websocket **text** frame holding one JSON object with a string `type`.
- The server never blocks ovos-gui on a slow client: handlers enqueue, a sender thread writes.
- The server accepts any number of clients. Each connection belongs to exactly one `session_id`.

## Handshake (client speaks first)

Client → server, first frame, within 5 s of connecting (else the server closes):

```json
{"type": "hello", "protocol": "ovos-gui-1", "version": 1, "session_id": "default", "client": "visage/2.5.0"}
```

Server → client:

```json
{"type": "welcome", "protocol": "ovos-gui-1", "version": 1, "session_id": "default", "server": "ovos-gui-plugin-visage/0.1.0"}
```

followed at once by one `snapshot` frame for that session (below). Unknown `protocol`, unsupported
`version`, missing `session_id`, or a first frame that is not `hello`:

```json
{"type": "error", "reason": "unsupported protocol 'x'"}
```

then the server closes the socket with code 1002. Any later client → server frame in version 1 is
ignored and logged; GUI-1 has no reply leg (spec §7.2). Visage keeps sending interaction messages
on the core bus as today.

## Server → client frames

Every frame below except `idle` carries `session_id` (`status` carries the session that raised it). `data` is always the namespace's
**full merged** session data as ovos-gui holds it after the change (never a delta), with `__` keys
already stripped by ovos-gui and `null` values already removed.

| `type` | Fields | Mirrors adapter call | Sent to |
|---|---|---|---|
| `template` | `skill_id`, `template`, `data`, `session_id` | `dispatch_template` → `handle_show_<x>` | clients of `session_id` |
| `session_update` | `skill_id`, `data`, `session_id` | `on_session_update` | clients of `session_id` |
| `activated` | `skill_id`, `session_id` | `on_namespace_activated` | clients of `session_id` |
| `deactivated` | `skill_id`, `session_id` | `on_namespace_deactivated` | clients of `session_id` |
| `idle` | (none) | `on_idle` | all clients |
| `status` | `event_name`, `data`, `session_id` | `on_status_event` | all clients |
| `snapshot` | `session_id`, `stack` | query on `hello` | the connecting client |

- `template` is the **spec name** (`SYSTEM_text`, `SYSTEM_weather`, `SYSTEM_media_player`, …),
  never a handler method name and never a QML file. Unknown `SYSTEM_*` names pass through
  unchanged; the client degrades them (spec §6.5). A skill's own non-`SYSTEM_` template name also
  passes through.
- `activated` means the namespace is now the top of the stack for that session. `deactivated`
  means it left the stack; the client drops its state.
- `idle` means the stack is empty on the device; the client shows its resting display.
- `status.event_name` is the bus topic (`ovos.*` per spec §5.3, or whatever ovos-gui forwards);
  `status.data` is the message payload unchanged.
- `snapshot.stack` is an array, **index 0 = active/top**, each entry
  `{"skill_id": "...", "template": "SYSTEM_text" | null, "data": {...}}`. `template` is `null`
  when the namespace has data but no template yet. An empty array means idle.
- **PROTOTYPE SHORTCUT:** ovos-gui has no query surface yet. The adapter builds `snapshot` from
  a per-session mirror of the adapter calls it saw: activation order, last template and last
  data per `skill_id`. `deactivated` removes the entry. `idle` does not change the mirror,
  because ovos-gui sends it after the deactivations that empty one session. The plan wants a
  stateless adapter that reads the stack from ovos-gui instead.

Example sequence after a skill shows text:

```json
{"type": "activated", "skill_id": "ovos-skill-hello.openvoiceos", "session_id": "default"}
{"type": "session_update", "skill_id": "ovos-skill-hello.openvoiceos", "data": {"title": "Hi", "text": "Hello"}, "session_id": "default"}
{"type": "template", "skill_id": "ovos-skill-hello.openvoiceos", "template": "SYSTEM_text", "data": {"title": "Hi", "text": "Hello"}, "session_id": "default"}
```

Order is whatever ovos-gui calls; the client must cope with `template` before any `activated`
(treat it as activation of that namespace too) and with `session_update` for a namespace it
has never seen.

## Client behaviour (Visage)

- Config `protocol`: `auto` (default) | `gui1` | `legacy`; env `VISAGE_PROTOCOL` overrides.
  Env `VISAGE_GUI1_URL` overrides the endpoint (default: bus host, port 18182, path `/gui1`).
- `auto`: connect to the GUI-1 endpoint and send `hello`. `welcome` within **3 s** selects GUI-1
  for this run. Refused connection, timeout or `error` selects legacy (`mycroft.gui.connected`
  negotiation on 18181). Log the choice. Do not switch mid-run; a reconnect probes again.
- `gui1`: GUI-1 only, keep retrying the endpoint. `legacy`: today's behaviour, no probe.

## Fixtures

Record server frames as `.jsonl`, one frame per line, named `<scenario>.jsonl`. Hand-written
fixtures say so in a first line `{"_note": "written from WIRE.md, not recorded"}`.
