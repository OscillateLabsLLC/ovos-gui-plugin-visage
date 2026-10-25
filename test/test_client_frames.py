"""Client interaction and focus frames become gui.interaction and gui.page.focus on the bus."""
import importlib.util
import json
import queue
import threading
from pathlib import Path

import pytest

from conftest import TEST_CONFIG, join, recv
from ovos_gui_plugin_visage import VisageGUIPlugin, protocol

BUS_WAIT = 2.0
SKILL = "ovos-skill-gui1-demo.oscillatelabs"
CONTEXT = {"session": {"session_id": "kitchen"}, "source": "ovos-gui-plugin-visage"}


class RecordingBus:
    def __init__(self, gate=None):
        self.emitted = queue.Queue()
        self._gate = gate

    def emit(self, message):
        if self._gate is not None:
            self._gate.wait(BUS_WAIT)
        self.emitted.put(message)

    def next(self):
        return self.emitted.get(timeout=BUS_WAIT)


def load_tool(name):
    path = Path(__file__).parent.parent / "tool" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def start(bus):
    plugin = VisageGUIPlugin(dict(TEST_CONFIG), bus=bus)
    assert plugin.server.ready.wait(5) and plugin.server.port
    return plugin


@pytest.fixture
def bus_adapter():
    bus = RecordingBus()
    plugin = start(bus)
    yield plugin, bus
    plugin.shutdown()


def test_interaction_becomes_gui_interaction_in_the_client_session(bus_adapter):
    adapter, bus = bus_adapter
    conn, _ = join(adapter, "kitchen")
    conn.send(json.dumps({"type": "interaction", "namespace": SKILL, "event": "confirm",
                          "data": {"answer": True}, "session_id": "hall"}))
    message = bus.next()
    assert message.msg_type == "gui.interaction"
    assert message.data == {"namespace": SKILL, "event": "confirm", "data": {"answer": True}}
    assert message.context == CONTEXT


def test_focus_becomes_gui_page_focus_in_the_client_session(bus_adapter):
    adapter, bus = bus_adapter
    conn, _ = join(adapter, "kitchen")
    conn.send(json.dumps({"type": "focus", "namespace": SKILL, "page_number": 1}))
    message = bus.next()
    assert message.msg_type == "gui.page.focus"
    assert message.data == {"namespace": SKILL, "page_number": 1}
    assert message.context == CONTEXT


@pytest.mark.parametrize("frame", [
    {"type": "focus", "namespace": SKILL, "page_number": -1},
    {"type": "focus", "namespace": SKILL, "page_number": True},
    {"type": "focus", "namespace": "", "page_number": 0},
    {"type": "interaction", "namespace": SKILL, "event": "", "data": {}},
    {"type": "interaction", "namespace": SKILL, "event": "x", "data": [1]},
    {"type": "anything", "namespace": SKILL},
])
def test_malformed_or_unknown_frames_are_not_relayed(frame):
    assert protocol.parse_client_frame(json.dumps(frame)) is None


def test_interaction_data_defaults_to_empty_object():
    frame = {"type": "interaction", "namespace": SKILL, "event": "tap"}
    assert protocol.parse_client_frame(json.dumps(frame))["data"] == {}


def test_slow_bus_does_not_stall_server_frames():
    gate = threading.Event()
    bus = RecordingBus(gate)
    adapter = start(bus)
    try:
        conn, _ = join(adapter, "default")
        conn.send(json.dumps({"type": "focus", "namespace": SKILL, "page_number": 0}))
        conn.send(json.dumps({"type": "focus", "namespace": SKILL, "page_number": 1}))
        adapter.on_namespace_activated(SKILL, "default")
        assert recv(conn)["type"] == "activated"
        gate.set()
        assert [bus.next().data["page_number"] for _ in range(2)] == [0, 1]
    finally:
        adapter.shutdown()


def test_without_a_bus_client_frames_are_dropped_and_server_keeps_working(adapter):
    conn, _ = join(adapter, "default")
    conn.send(json.dumps({"type": "focus", "namespace": SKILL, "page_number": 0}))
    adapter.on_idle("default")
    assert recv(conn) == {"type": "idle", "session_id": "default"}


def test_dump_client_sends_its_frames_after_the_snapshot(bus_adapter, capsys):
    adapter, bus = bus_adapter
    dump_client = load_tool("dump_client")
    focus = {"type": "focus", "namespace": SKILL, "page_number": 2}
    argv = [f"ws://127.0.0.1:{adapter.server.port}/gui1", "--session", "kitchen",
            "--send", json.dumps(focus)]
    threading.Thread(target=dump_client.main, args=(argv,), daemon=True).start()
    message = bus.next()
    assert (message.msg_type, message.data) == ("gui.page.focus", {"namespace": SKILL,
                                                                    "page_number": 2})
    assert message.context["session"] == {"session_id": "kitchen"}
