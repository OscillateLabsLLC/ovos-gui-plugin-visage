import contextlib
import json
import sys
from pathlib import Path

import pytest
from websockets.sync.client import connect

sys.path.insert(0, str(Path(__file__).parent))

from ovos_gui_plugin_visage import VisageGUIPlugin  # noqa: E402

TEST_CONFIG = {"port": 0, "hello_timeout": 0.5, "max_backlog": 16}
RECV_TIMEOUT = 2.0
_open_clients = contextlib.ExitStack()


def hello(session_id="default", **overrides):
    frame = {"type": "hello", "protocol": "ovos-gui-1", "version": 1,
             "session_id": session_id, "client": "pytest/0"}
    frame.update(overrides)
    return frame


def url(adapter, path="/gui1"):
    return f"ws://127.0.0.1:{adapter.server.port}{path}"


def recv(conn, timeout=RECV_TIMEOUT):
    return json.loads(conn.recv(timeout=timeout))


def join(adapter, session_id="default"):
    """Connect, hello, and consume welcome + snapshot; returns (conn, snapshot)."""
    conn = _open_clients.enter_context(connect(url(adapter)))
    conn.send(json.dumps(hello(session_id)))
    assert recv(conn)["type"] == "welcome"
    snapshot = recv(conn)
    assert snapshot["type"] == "snapshot"
    return conn, snapshot


def recv_n(conn, count):
    return [recv(conn) for _ in range(count)]


def assert_silent(conn, wait=0.3):
    with pytest.raises(TimeoutError):
        conn.recv(timeout=wait)


@pytest.fixture
def adapter():
    plugin = VisageGUIPlugin(dict(TEST_CONFIG))
    assert plugin.server.ready.wait(5)
    assert plugin.server.port, "server failed to bind"
    yield plugin
    _open_clients.close()
    plugin.shutdown()
