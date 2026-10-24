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
