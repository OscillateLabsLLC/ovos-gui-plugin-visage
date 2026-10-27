import pytest

from conftest import assert_silent, join, recv, recv_n
from scenarios import HELLO_SKILL, SCENARIOS, check_fixture


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_scripted_sequence_matches_fixture(adapter, name):
    script, frame_count = SCENARIOS[name]
    conn, _ = join(adapter)
    script(adapter)
    frames = recv_n(conn, frame_count)
    assert_silent(conn)
    check_fixture(name, frames)


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_late_joiner_snapshot_matches_fixture(adapter, name):
    script, frame_count = SCENARIOS[name]
    early, _ = join(adapter)
    script(adapter)
    recv_n(early, frame_count)
    _, snapshot = join(adapter)
    check_fixture(name, [snapshot], suffix="_snapshot")


def test_text_then_weather_snapshot_is_top_first(adapter):
    early, _ = join(adapter)
    SCENARIOS["text_then_weather"][0](adapter)
    recv_n(early, SCENARIOS["text_then_weather"][1])
    _, snapshot = join(adapter)
    stack = snapshot["stack"]
    assert [entry["template"] for entry in stack] == ["SYSTEM_weather", "SYSTEM_text"]
    assert stack[0]["data"]["current"] == 22


def test_template_before_activation_counts_as_activation(adapter):
    early, _ = join(adapter)
    adapter.dispatch_template("SYSTEM_text", HELLO_SKILL, {"text": "x"}, "default")
    recv(early)
    _, snapshot = join(adapter)
    assert snapshot["stack"] == [{"skill_id": HELLO_SKILL, "template": "SYSTEM_text",
                                  "data": {"text": "x"}}]


def test_data_without_template_snapshots_null_template(adapter):
    early, _ = join(adapter)
    adapter.on_session_update(HELLO_SKILL, {"text": "x"}, "default")
    adapter.on_namespace_activated(HELLO_SKILL, "default")
    recv_n(early, 2)
    _, snapshot = join(adapter)
    assert snapshot["stack"] == [{"skill_id": HELLO_SKILL, "template": None,
                                  "data": {"text": "x"}}]


def test_snapshot_is_per_session(adapter):
    early, _ = join(adapter, "kitchen")
    adapter.on_namespace_activated(HELLO_SKILL, "kitchen")
    recv(early)
    _, other = join(adapter, "hall")
    assert other["stack"] == []


def test_idle_from_one_session_keeps_other_sessions_snapshot(adapter):
    kitchen, _ = join(adapter, "kitchen")
    hall, _ = join(adapter, "hall")
    adapter.on_namespace_activated(HELLO_SKILL, "kitchen")
    adapter.on_namespace_activated(HELLO_SKILL, "hall")
    adapter.on_namespace_deactivated(HELLO_SKILL, "hall")
    adapter.on_idle("hall")
    recv(kitchen)
    recv_n(hall, 3)
    assert_silent(kitchen)
    _, late_kitchen = join(adapter, "kitchen")
    assert [entry["skill_id"] for entry in late_kitchen["stack"]] == [HELLO_SKILL]
    _, late_hall = join(adapter, "hall")
    assert late_hall["stack"] == []


def test_exposed_namespace_returns_to_top(adapter):
    early, _ = join(adapter)
    adapter.on_namespace_activated("skill.low", "default")
    adapter.on_namespace_activated("skill.high", "default")
    adapter.on_namespace_deactivated("skill.high", "default")
    adapter.on_namespace_activated("skill.low", "default")
    recv_n(early, 4)
    _, snapshot = join(adapter)
    assert [entry["skill_id"] for entry in snapshot["stack"]] == ["skill.low"]


def test_snapshot_carries_last_ambient_payload_per_topic(adapter):
    early, _ = join(adapter, "kitchen")
    adapter.on_status_event("gui.ambient.weather", {"temp": 20}, "default")
    adapter.on_status_event("gui.ambient.weather", {"temp": 21}, "default")
    adapter.on_status_event("gui.ambient.notifications", {"count": 3}, "kitchen")
    adapter.on_status_event("ovos.utterance.speak", {"utterance": "hi"}, "default")
    recv_n(early, 4)
    _, snapshot = join(adapter, "hall")
    assert snapshot["ambient"] == {"gui.ambient.weather": {"temp": 21},
                                   "gui.ambient.notifications": {"count": 3}}
