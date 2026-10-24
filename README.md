# ovos-gui-plugin-visage

This plugin is an OVOS GUI adapter. It connects `ovos-gui` to the Visage GUI client.

`ovos-gui` calls the adapter for each GUI event. The adapter changes each call into one JSON frame.
It sends the frame to the Visage clients over a websocket. The protocol is GUI-1, version 1.
The protocol is in [docs/WIRE.md](docs/WIRE.md).

Status: working prototype.

## Install

The adapter needs the `gui` branch of `ovos-plugin-manager`. Install that branch first:

```sh
pip install "git+https://github.com/OpenVoiceOS/ovos-plugin-manager@gui"
pip install "git+https://github.com/OscillateLabsLLC/ovos-gui-plugin-visage"
```

The plugin registers in the entry-point group `opm.gui_adapter` with the name
`ovos-gui-plugin-visage`. `ovos-gui` loads all installed adapters when it starts.

## Configure

Put this block in `mycroft.conf`. All keys are optional. The values below are the defaults.

```json
{
  "gui": {
    "adapters": {
      "ovos-gui-plugin-visage": {
        "host": "127.0.0.1",
        "port": 18182,
        "path": "/gui1",
        "hello_timeout": 5,
        "max_backlog": 256
      }
    }
  }
}
```

| Key | Meaning |
|---|---|
| `host` | Address that the websocket server listens on. Use `0.0.0.0` for clients on other hosts. |
| `port` | TCP port of the websocket server. |
| `path` | URL path of the endpoint. The server refuses other paths with HTTP 404. |
| `hello_timeout` | Seconds that a client has to send `hello`. After this time, the server closes the socket. |
| `max_backlog` | Number of frames that can wait for one client. If a client is slower, the server closes it with code 1013. |

## How it works

1. The adapter starts the websocket server on its own thread. `__init__` does not wait.
2. Each adapter call makes one frame and puts it on a queue. The call does not wait for a client.
3. The server thread sends the frame to the clients of its `session_id`.
   It sends `idle` and `status` frames to all clients.
4. A new client sends `hello`. The server replies with `welcome` and then one `snapshot`.

## Replay server (no ovos-gui)

Use the replay server to develop Visage without ovos-gui. It uses the same server code as the
adapter. It needs only the `websockets` package.

```sh
python tool/replay_server.py --port 28182 test/fixtures/gui1/text_then_weather.jsonl
```

| Option | Meaning |
|---|---|
| `--interval 1.0` | Seconds between frames. |
| `--loop` | Send the fixture again and again. |
| `--snapshot FILE` | Send the `snapshot` frame from `FILE` on `hello`. If you do not set it, the stack is empty. |
| `--host`, `--path` | Endpoint address and path. |

The server sends the next frame only when one or more clients are connected.

To see the frames from a live adapter or from the replay server, use the dump client:

```sh
python tool/dump_client.py ws://127.0.0.1:28182/gui1 --session default
```

## Fixtures

`test/fixtures/gui1/*.jsonl` holds frames that the tests recorded from the real adapter.
There is one frame on each line. A `<scenario>_snapshot.jsonl` file holds the `snapshot` that a
client gets when it connects after the scenario.

To record the fixtures again, run:

```sh
GUI1_RECORD_FIXTURES=1 pytest
```

## Test

```sh
pip install -e ".[test]"
pytest
```

## PROTOTYPE SHORTCUT list

These items are temporary. They are not the final design.

- **Snapshot from a local mirror.** `ovos-gui` has no query surface yet. The adapter keeps a copy
  of the stack for each session. It builds the copy from the calls it sees: activation order, last
  template, and last data for each `skill_id`. `deactivated` removes an entry. `idle` does not
  change the copy, because `ovos-gui` sends it after the deactivations that empty one session.
  The plan wants a stateless adapter that reads the stack from `ovos-gui`.
- **No authentication.** Any client that can reach the port can connect. The default host is
  `127.0.0.1` for this reason.
- **No reply leg.** The server logs and ignores all client frames after `hello` (GUI-1 version 1).

## License

Apache-2.0
