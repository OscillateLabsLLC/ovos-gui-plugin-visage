from conftest import assert_silent, join, recv


def test_session_frames_reach_only_their_session(adapter):
    kitchen, _ = join(adapter, "kitchen")
    hall, _ = join(adapter, "hall")
    adapter.dispatch_template("SYSTEM_text", "skill.a", {"text": "k"}, "kitchen")
    adapter.on_session_update("skill.a", {"text": "k"}, "kitchen")
    adapter.on_namespace_activated("skill.a", "kitchen")
    adapter.on_namespace_deactivated("skill.a", "kitchen")
    kinds = [recv(kitchen)["type"] for _ in range(4)]
    assert kinds == ["template", "session_update", "activated", "deactivated"]
    assert_silent(hall)


def test_default_is_a_literal_session_not_a_wildcard(adapter):
    default, _ = join(adapter, "default")
    hall, _ = join(adapter, "hall")
    adapter.dispatch_template("SYSTEM_text", "skill.a", {"text": "d"}, "default")
    assert recv(default)["session_id"] == "default"
    assert_silent(hall)


def test_idle_reaches_only_its_session(adapter):
    kitchen, _ = join(adapter, "kitchen")
    hall, _ = join(adapter, "hall")
    adapter.on_idle("kitchen")
    assert recv(kitchen) == {"type": "idle", "session_id": "kitchen"}
    assert_silent(hall)


def test_status_reaches_every_session(adapter):
    kitchen, _ = join(adapter, "kitchen")
    hall, _ = join(adapter, "hall")
    adapter.on_status_event("ovos.listener.wakeword", {"utterance": "hey"}, "kitchen")
    for conn in (kitchen, hall):
        assert recv(conn) == {"type": "status", "event_name": "ovos.listener.wakeword",
                              "data": {"utterance": "hey"}, "session_id": "kitchen"}


def test_two_clients_in_one_session_both_receive(adapter):
    first, _ = join(adapter, "default")
    second, _ = join(adapter, "default")
    adapter.on_namespace_activated("skill.a", "default")
    assert recv(first) == recv(second) == {"type": "activated", "skill_id": "skill.a",
                                           "session_id": "default"}


def test_unknown_template_passes_through(adapter):
    conn, _ = join(adapter)
    adapter.dispatch_template("SYSTEM_hologram", "skill.a", {}, "default")
    adapter.dispatch_template("my_skill_page", "skill.a", {}, "default")
    assert recv(conn)["template"] == "SYSTEM_hologram"
    assert recv(conn)["template"] == "my_skill_page"


def test_unserialisable_data_is_logged_and_later_frames_still_flow(adapter):
    conn, _ = join(adapter)
    adapter.on_session_update("skill.a", {"bad": object()}, "default")
    adapter.on_idle("default")
    assert recv(conn) == {"type": "idle", "session_id": "default"}
