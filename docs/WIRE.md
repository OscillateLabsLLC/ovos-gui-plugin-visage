# GUI-1 adapter ⇄ Visage wire protocol, version 1 (prototype)

Source of truth for the prototype. Both `ovos-gui-plugin-visage` (server) and Visage (client)
implement exactly this. Origin: `ovos-gui-visage/docs/GUI1_PLAN.md`, section 2.2. Changes go
here first. Where the spec text is a pending amendment, this file follows the proposed text
(amendments A, B and D on the `gui1/*` branches of the architecture clone).

Spec: [gui-1.md](https://github.com/OpenVoiceOS/architecture/blob/b6c1583/gui-1.md) at `b6c1583`.

## Transport

- One websocket per client. Default endpoint `ws://<host>:18182/gui1`. The prototype stack uses
  port **28182**.
- Adapter config keys (all optional, under `gui.adapters.ovos-gui-plugin-visage`):

  | Key | Default | Meaning |
  |---|---|---|
  | `host` | `127.0.0.1` | Listen address. |
  | `port` | `18182` | TCP port. |
  | `path` | `/gui1` | URL path. A request for any other path gets HTTP **404** and no websocket. |
  | `hello_timeout` | `5` | Seconds a client has to send `hello`. |
  | `max_backlog` | `256` | Frames that may wait for one client. A client that falls further behind is closed with code **1013** (try again later), reason `client too slow`. |

- Every message is one websocket **text** frame holding one JSON object with a string `type`.
- The server never blocks ovos-gui on a slow client: handlers enqueue, a sender thread writes.
- The server accepts any number of clients. Each connection belongs to exactly one `session_id`,
  the one its `hello` names.

## Handshake (client speaks first)

Client → server, first frame, within `hello_timeout` (5 s) of connecting (else the server sends
`error` and closes):

```json
{"type": "hello", "protocol": "ovos-gui-1", "version": 1, "session_id": "default", "client": "visage/2.4.0"}
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

then the server closes the socket with code 1002.

## Server → client frames

Every frame below carries `session_id`. `status` carries the session that raised it; every other
frame carries the session it is addressed to. `data` is always the namespace's **full merged**
session data as ovos-gui holds it after the change (never a delta), with `__` keys already
stripped by ovos-gui and `null` values already removed.

| `type` | Fields | Source | Sent to |
|---|---|---|---|
| `template` | `skill_id`, `template`, `data`, `session_id`, optional `index` and `page_count` | `dispatch_template` (a `SYSTEM_*` name) or `on_legacy_page` (a skill page name) | clients of `session_id` |
| `session_update` | `skill_id`, `data`, `session_id` | `on_session_update` | clients of `session_id` |
| `activated` | `skill_id`, `session_id` | `on_namespace_activated` | clients of `session_id` |
| `deactivated` | `skill_id`, `session_id` | `on_namespace_deactivated` | clients of `session_id` |
| `idle` | `session_id` | `on_idle(session_id)` | clients of `session_id` |
| `status` | `event_name`, `data`, `session_id` | `on_status_event` | all clients |
| `snapshot` | `session_id`, `stack`, `ambient` | the adapter's mirror, on `hello` | the connecting client |

- `template` is a **spec name** (`SYSTEM_text`, `SYSTEM_weather`, `SYSTEM_media_player`, …) or,
  from the legacy hook, a skill's own page name. It is never a handler method name and never a
  QML file. Unknown `SYSTEM_*` names pass through unchanged; the client degrades them
  ([gui-1.md 6.5](https://github.com/OpenVoiceOS/architecture/blob/b6c1583/gui-1.md#65-capability-and-graceful-degradation)).
- `index` and `page_count` (proposed amendment B,
  [gui-1.md 6.3](https://github.com/OpenVoiceOS/architecture/blob/b6c1583/gui-1.md#63-events-received)): `index` is the active
  entry's zero-based position in the namespace's `page_names`, and `page_count` is the length
  of `page_names`. The server sends both or neither, with `0 <= index < page_count`. They are
  optional on the wire; absent means unknown, and a client then never sends `focus` for that
  namespace. The adapter sends them when ovos-gui passes them to `dispatch_template` or
  `on_legacy_page`, which it does on every show and on the dispatch after a valid `focus`.
  That dispatch, with the new `index`, is how a client learns that its `focus` took effect.
  A legacy page carries them the same way.
- **Legacy pages (prototype only).** A skill that shows its own page name (`time`,
  `CurrentWeather`, `Timer`) is never dispatched as a template; ovos-gui hands it to the
  adapter's `on_legacy_page(skill_id, page, data, session_id)` instead. This is the
  deployment-specific legacy path that
  [gui-1.md 4.2](https://github.com/OpenVoiceOS/architecture/blob/b6c1583/gui-1.md#42-messages)
  allows (proposed amendment E names it); the hook also gets `index` and `page_count`.
  ovos-gui takes this path when the **first**
  `page_names` entry is not a `SYSTEM_*` name, and sends the **active** entry. The adapter sends
  it as an ordinary `template` frame whose `template` is the page name exactly as the skill sent
  it, with the same `data` and `session_id` rules, and the snapshot mirror records it as that
  namespace's template. A client routes a non-`SYSTEM_` `template` to the skill's own page
  (Visage: `<skill_id>/<page>` in `router.dart` `routes`). ovos-gui calls the hook after
  `on_session_update` and before `on_namespace_activated`, as for a template. Legacy frame names
  with a spec alias (`SYSTEM_TextFrame`) still arrive as spec templates. The spec has no such
  frame; it lasts only until skills emit catalogue templates.
- `activated` means the namespace is now the top of the stack for that session. `deactivated`
  means it left the stack; the client drops its state.
- `idle` means the stack of that session just emptied (proposed amendment D: the idle hook is
  per session). A client empties its state for its own session and shows its resting display.
  The `deactivated` frames that emptied the session arrive before it. A client never gets the
  `idle` of another session.
- `status.event_name` is the bus topic (`ovos.*` per
  [gui-1.md 5.3](https://github.com/OpenVoiceOS/architecture/blob/b6c1583/gui-1.md#53-system-wide-signals),
  `gui.ambient.*` per [6.9.1](https://github.com/OpenVoiceOS/architecture/blob/b6c1583/gui-1.md#691-ambient-data),
  or whatever legacy topic ovos-gui forwards); `status.data` is the message payload unchanged.
- `snapshot.stack` is an array, **index 0 = active/top**, each entry
  `{"skill_id": "...", "template": "<spec name or legacy page name>" | null, "data": {...}}`,
  plus `"index"` and `"page_count"` as the last `template` frame for that namespace carried
  them (both or neither, same meaning). `template` is `null` when the namespace has data but
  no template yet, and such an entry has neither field. An empty array means idle.
- `snapshot.ambient` is an object `{"<topic>": {...}}`: the last payload the adapter saw for each
  `gui.ambient.*` status event, unchanged, device-wide. `{}` when none was seen.
- **PROTOTYPE SHORTCUT:** ovos-gui has a state query surface
  ([gui-1.md 6.7](https://github.com/OpenVoiceOS/architecture/blob/b6c1583/gui-1.md#67-state-query-recovery)),
  but it gives an adapter no handle to it. The adapter builds `snapshot` from a per-session
  mirror of the adapter calls it saw: activation order, last template with its `index` and
  `page_count`, and last data per `skill_id`, plus the ambient map. `deactivated` removes the entry. `idle` does not change the
  mirror, because ovos-gui sends it after the deactivations that empty its session. The plan
  wants a stateless adapter that reads the stack from ovos-gui instead.

Example sequence after a skill shows text (the order ovos-gui calls the hooks):

```json
{"type": "session_update", "skill_id": "ovos-skill-hello.openvoiceos", "data": {"title": "Hi", "text": "Hello"}, "session_id": "default"}
{"type": "template", "skill_id": "ovos-skill-hello.openvoiceos", "template": "SYSTEM_text", "data": {"title": "Hi", "text": "Hello"}, "session_id": "default", "index": 0, "page_count": 1}
{"type": "activated", "skill_id": "ovos-skill-hello.openvoiceos", "session_id": "default"}
```

Order is whatever ovos-gui calls; the client must cope with `template` before any `activated`
(treat it as activation of that namespace too) and with `session_update` for a namespace it
has never seen.

## Client → server frames

After `hello`, a client **may** send these two frames. Both are optional. Neither carries a
session: the adapter uses the session of the connection. The adapter never waits on the bus to
read the next frame.

| `type` | Fields | Bus Message the adapter emits |
|---|---|---|
| `interaction` | `namespace` (string), `event` (string), `data` (object, default `{}`) | `gui.interaction`, data `{"namespace", "event", "data"}` |
| `focus` | `namespace` (string), `page_number` (integer ≥ 0) | `gui.page.focus`, data `{"namespace", "page_number"}` |

Both Messages have the context
`{"session": {"session_id": "<the connection's session>"}, "source": "ovos-gui-plugin-visage"}`.

```json
{"type": "interaction", "namespace": "ovos-skill-gui1-demo.oscillatelabs", "event": "confirm", "data": {"answer": true}}
{"type": "focus", "namespace": "ovos-skill-gui1-demo.oscillatelabs", "page_number": 1}
```

- `interaction` carries an event back to the namespace that showed the page, such as a reply of
  an interactive companion (proposed amendment A: `gui.interaction`,
  [gui-1.md 7](https://github.com/OpenVoiceOS/architecture/blob/b6c1583/gui-1.md#7-interaction-render-backend--application)).
  The application treats it as a shortcut for the spoken path.
- `focus` asks ovos-gui to make another held entry of the namespace's `page_names` active
  (proposed amendment B: `gui.page.focus`). ovos-gui acts only when the namespace is on top of
  that session's stack and `page_number` is in range; it then dispatches the newly active entry,
  so the client gets a new `template` frame with `index` equal to `page_number`. A client sends
  `focus` for a namespace only after a `template` frame or snapshot entry for it carried both
  `index` and `page_count`. Every valid `focus` restarts the namespace's
  removal timer, as a touch. A `focus` that names the current entry does only that: it
  dispatches nothing. A `focus` for a namespace that is not on top, or with `page_number` out
  of range, is ignored, and ovos-gui logs one diagnostic for it.
- A client that sends neither frame still conforms. Visage no longer needs to emit
  `gui.page_gained_focus` or `<namespace>.<event>` on the core bus for a GUI-1 connection.
- A frame with another `type`, or with a missing or wrongly typed field, is logged and ignored.

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
