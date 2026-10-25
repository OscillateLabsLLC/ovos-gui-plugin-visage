import importlib.util
import json
import threading
from pathlib import Path

import pytest
from websockets.sync.client import connect

from conftest import hello, recv, recv_n
from ovos_gui_plugin_visage.mirror import StaticSnapshot
from ovos_gui_plugin_visage.server import GUI1Server
from scenarios import fixture_path

TOOL = Path(__file__).parent.parent / "tool" / "replay_server.py"


@pytest.fixture(scope="module")
def replay():
    spec = importlib.util.spec_from_file_location("replay_server", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def start_server(stack):
    server = GUI1Server({"port": 0}, state=StaticSnapshot(stack)).start()
    assert server.ready.wait(5) and server.port
    return server


def test_replay_streams_fixture_after_handshake(replay):
    frames = replay.load_frames(fixture_path("text_then_weather"))
    server = start_server([])
    try:
        with connect(f"ws://127.0.0.1:{server.port}/gui1") as conn:
            conn.send(json.dumps(hello()))
            assert recv(conn)["type"] == "welcome"
            assert recv(conn)["stack"] == []
            threading.Thread(target=replay.stream, args=(server, frames, 0, False),
                             daemon=True).start()
            assert recv_n(conn, len(frames)) == frames
    finally:
        server.stop()


def test_replay_serves_snapshot_fixture(replay):
    stack = replay.load_stack(str(fixture_path("text_then_weather", "_snapshot")))
    server = start_server(stack)
    try:
        with connect(f"ws://127.0.0.1:{server.port}/gui1") as conn:
            conn.send(json.dumps(hello()))
            recv(conn)
            assert recv(conn)["stack"] == stack
            assert stack[0]["template"] == "SYSTEM_weather"
    finally:
        server.stop()


def test_replay_skips_note_lines(replay, tmp_path):
    fixture = tmp_path / "hand.jsonl"
    fixture.write_text('{"_note": "written from WIRE.md, not recorded"}\n{"type": "idle", "session_id": "default"}\n')
    assert replay.load_frames(fixture) == [{"type": "idle", "session_id": "default"}]
