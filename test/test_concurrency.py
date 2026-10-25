"""Hooks arrive on ovos-bus-client ThreadPoolExecutor workers and a Timer thread."""
import random
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from conftest import join, recv
from ovos_gui_plugin_visage import client_link, plugin, server
from ovos_gui_plugin_visage.mirror import StackMirror

SESSIONS = ("kitchen", "hall")
SKILLS = tuple(f"skill.{n}" for n in range(5))
CALLS = 400
WORKERS = 8
SEED = 1024


def random_call(adapter, rng):
    session, skill = rng.choice(SESSIONS), rng.choice(SKILLS)
    data = {"n": rng.randint(0, 999), "session": session}
    calls = [
        lambda: adapter.on_session_update(skill, data, session),
        lambda: adapter.dispatch_template("SYSTEM_text", skill, data, session),
        lambda: adapter.on_namespace_activated(skill, session),
        lambda: adapter.on_namespace_deactivated(skill, session),
        lambda: adapter.on_status_event("ovos.utterance.speak", data, session),
        lambda: adapter.on_idle(session),
    ]
    return rng.choice(calls)


@pytest.fixture
def logged_failures(monkeypatch):
    failures = []
    for module in (server, plugin, client_link):
        log = module.LOG
        monkeypatch.setattr(module, "LOG", _RecordingLog(log, failures))
    return failures


class _RecordingLog:
    def __init__(self, log, failures):
        self._log, self._failures = log, failures

    def __getattr__(self, name):
        return getattr(self._log, name)

    def exception(self, msg, *args, **kwargs):
        self._failures.append(msg)
        self._log.exception(msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        self._failures.append(msg)
        self._log.error(msg, *args, **kwargs)


def record_mirror_threads(adapter):
    threads = set()
    mirror = adapter.server.state
    for name in ("apply", "snapshot"):
        original = getattr(mirror, name)

        def traced(*args, _original=original):
            threads.add(threading.current_thread().name)
            return _original(*args)
        setattr(mirror, name, traced)
    return threads


def drain_until_marker(conn, marker_session):
    frames = []
    while True:
        frame = recv(conn)
        if frame.get("event_name") == "test.marker" and frame["session_id"] == marker_session:
            return frames
        frames.append(frame)


def test_concurrent_hooks_keep_mirror_consistent(adapter, logged_failures):
    threads = record_mirror_threads(adapter)
    clients = {session: join(adapter, session)[0] for session in SESSIONS}
    rng = random.Random(SEED)
    calls = [random_call(adapter, rng) for _ in range(CALLS)]
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for future in [pool.submit(call) for call in calls]:
            future.result()
    adapter.on_status_event("test.marker", {}, "end")
    for session, conn in clients.items():
        replayed = StackMirror()
        for frame in drain_until_marker(conn, "end"):
            replayed.apply(frame)
        _, snapshot = join(adapter, session)
        assert snapshot["stack"] == replayed.snapshot(session)
        skill_ids = [entry["skill_id"] for entry in snapshot["stack"]]
        assert len(skill_ids) == len(set(skill_ids))
    assert threads == {"gui1-visage-server"}
    assert logged_failures == []
