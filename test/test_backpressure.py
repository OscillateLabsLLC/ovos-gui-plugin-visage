import base64
import json
import os
import socket
import statistics
import struct
import time

from conftest import TEST_CONFIG, hello, join, recv

FRAME_DATA = {"blob": "x" * 8192}
CALLS = 400
CALL_SPACING = 0.001


def masked_text_frame(text):
    payload = text.encode()
    mask = os.urandom(4)
    if len(payload) < 126:
        header = bytes([0x81, 0x80 | len(payload)])
    else:
        header = bytes([0x81, 0x80 | 126]) + struct.pack("!H", len(payload))
    body = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    return header + mask + body


def stalled_client(port):
    """Completes the HTTP upgrade and hello, then never reads again."""
    sock = socket.socket()
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
    sock.connect(("127.0.0.1", port))
    key = base64.b64encode(os.urandom(16)).decode()
    sock.sendall((f"GET /gui1 HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
                  "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                  f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
    response = b""
    while b"\r\n\r\n" not in response:
        response += sock.recv(1)
    assert b" 101 " in response
    sock.sendall(masked_text_frame(json.dumps(hello())))
    return sock


def wait_for(predicate, timeout=10.0):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        time.sleep(0.01)
    return predicate()


def test_stalled_client_never_delays_handlers_and_is_dropped(adapter):
    stalled = stalled_client(adapter.server.port)
    healthy, _ = join(adapter)
    assert wait_for(lambda: adapter.server.client_count() == 2)
    durations = []
    for _ in range(CALLS):
        started = time.perf_counter()
        adapter.on_session_update("skill.a", FRAME_DATA, "default")
        durations.append(time.perf_counter() - started)
        time.sleep(CALL_SPACING)
    assert statistics.median(durations) < 100e-6
    assert max(durations) < 20e-3, "bounded by the GIL switch interval, not the client"
    assert wait_for(lambda: adapter.server.client_count() == 1)
    assert TEST_CONFIG["max_backlog"] < CALLS
    adapter.on_idle()
    while recv(healthy)["type"] != "idle":
        pass
    stalled.close()
