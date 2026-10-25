#!/usr/bin/env python3
"""Serve a recorded GUI-1 fixture to Visage without ovos-gui.

Speaks the real handshake (same GUI1Server as the adapter), then streams the
fixture's frames to connected clients, waiting for a client before each frame.

    python tool/replay_server.py --port 28182 test/fixtures/gui1/text_then_weather.jsonl
"""
import argparse
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ovos_gui_plugin_visage.log import LOG  # noqa: E402
from ovos_gui_plugin_visage.mirror import StaticSnapshot  # noqa: E402
from ovos_gui_plugin_visage.server import DEFAULTS, GUI1Server  # noqa: E402

CLIENT_POLL = 0.1


def load_frames(path: Path):
    frames = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return [frame for frame in frames if "_note" not in frame]


def load_snapshot(path):
    """The first snapshot frame in `path`; an empty one when `path` is None."""
    if path is None:
        return {"stack": [], "ambient": {}}
    snapshots = [f for f in load_frames(Path(path)) if f.get("type") == "snapshot"]
    if not snapshots:
        raise SystemExit(f"{path} holds no snapshot frame")
    return snapshots[0]


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("fixture", type=Path, help="GUI-1 .jsonl fixture to stream")
    parser.add_argument("--host", default=DEFAULTS["host"])
    parser.add_argument("--port", type=int, default=28182)
    parser.add_argument("--path", default=DEFAULTS["path"])
    parser.add_argument("--interval", type=float, default=1.0, help="seconds between frames")
    parser.add_argument("--loop", action="store_true", help="replay the fixture forever")
    parser.add_argument("--snapshot", help=".jsonl holding the snapshot frame served on hello")
    return parser.parse_args(argv)


def wait_for_client(server: GUI1Server) -> None:
    while server.client_count() == 0:
        time.sleep(CLIENT_POLL)


def stream(server: GUI1Server, frames, interval: float, loop: bool) -> None:
    while True:
        for frame in frames:
            wait_for_client(server)
            LOG.info(f"replay -> {json.dumps(frame)[:200]}")
            server.publish(frame)
            time.sleep(interval)
        if not loop:
            return


def main(argv=None) -> int:
    args = parse_args(argv)
    if isinstance(LOG, logging.Logger):
        logging.basicConfig(level=logging.INFO)
    frames = load_frames(args.fixture)
    config = {"host": args.host, "port": args.port, "path": args.path}
    snapshot = load_snapshot(args.snapshot)
    state = StaticSnapshot(snapshot["stack"], snapshot.get("ambient"))
    server = GUI1Server(config, state=state).start()
    if not server.ready.wait(5) or server.port is None:
        LOG.error(f"replay server could not listen with {config}")
        return 1
    try:
        stream(server, frames, args.interval, args.loop)
        LOG.info("fixture done; still serving handshakes, Ctrl-C to stop")
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        return 0
    finally:
        server.stop()


if __name__ == "__main__":
    sys.exit(main())
