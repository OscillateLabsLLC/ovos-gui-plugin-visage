import json
import time

import pytest
from websockets.exceptions import ConnectionClosed, InvalidStatus
from websockets.sync.client import connect

from conftest import hello, recv, url
from ovos_gui_plugin_visage import __version__


def expect_rejection(conn, reason_part):
    error = recv(conn)
    assert error["type"] == "error"
    assert reason_part in error["reason"]
    with pytest.raises(ConnectionClosed) as closed:
        conn.recv(timeout=2)
    assert closed.value.rcvd.code == 1002


def test_good_hello_gets_welcome_then_snapshot(adapter):
    with connect(url(adapter)) as conn:
        conn.send(json.dumps(hello("kitchen")))
        assert recv(conn) == {"type": "welcome", "protocol": "ovos-gui-1",
                              "version": 1, "session_id": "kitchen",
                              "server": f"ovos-gui-plugin-visage/{__version__}"}
        assert recv(conn) == {"type": "snapshot", "session_id": "kitchen", "stack": []}
        assert adapter.any_client_connected()


@pytest.mark.parametrize("frame, reason", [
    (hello(protocol="x"), "unsupported protocol 'x'"),
    (hello(version=2), "unsupported version"),
    (hello(session_id=""), "missing session_id"),
    ({"type": "hello", "protocol": "ovos-gui-1", "version": 1}, "missing session_id"),
    ({"type": "ping"}, "first frame must be hello"),
])
def test_bad_hello_is_rejected_with_1002(adapter, frame, reason):
    with connect(url(adapter)) as conn:
        conn.send(json.dumps(frame))
        expect_rejection(conn, reason)
    assert not adapter.any_client_connected()


def test_non_json_first_frame_is_rejected(adapter):
    with connect(url(adapter)) as conn:
        conn.send("not json")
        expect_rejection(conn, "not valid JSON")


def test_binary_first_frame_is_rejected(adapter):
    with connect(url(adapter)) as conn:
        conn.send(json.dumps(hello()).encode())
        expect_rejection(conn, "text frame")


def test_no_hello_within_timeout_is_rejected(adapter):
    started = time.monotonic()
    with connect(url(adapter)) as conn:
        expect_rejection(conn, "no hello within 0.5 s")
    assert time.monotonic() - started < 2


def test_wrong_path_is_refused(adapter):
    with pytest.raises(InvalidStatus):
        connect(url(adapter, "/other"))


def test_later_client_frames_are_ignored(adapter):
    with connect(url(adapter)) as conn:
        conn.send(json.dumps(hello()))
        recv(conn)
        recv(conn)
        conn.send(json.dumps({"type": "anything"}))
        adapter.on_idle()
        assert recv(conn) == {"type": "idle"}


def test_disconnect_clears_any_client_connected(adapter):
    with connect(url(adapter)) as conn:
        conn.send(json.dumps(hello()))
        recv(conn)
        recv(conn)
        assert adapter.any_client_connected()
    deadline = time.monotonic() + 2
    while adapter.any_client_connected() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not adapter.any_client_connected()
