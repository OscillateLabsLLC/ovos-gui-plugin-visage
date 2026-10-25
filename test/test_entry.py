"""`index` and `page_count` on template frames and snapshot entries (GUI-1 6.3, amendment B)."""
from conftest import join, recv, recv_n

SKILL = "gui1-focus-probe.oscillatelabs"
DATE_TIME = "ovos-skill-date-time.openvoiceos"
DATA = {"text": "Entry 0 of 2"}


def test_template_frame_carries_entry(adapter):
    conn, _ = join(adapter)
    adapter.dispatch_template("SYSTEM_text", SKILL, DATA, "default", index=0, page_count=2)
    assert recv(conn) == {"type": "template", "skill_id": SKILL, "template": "SYSTEM_text",
                          "data": DATA, "session_id": "default", "index": 0, "page_count": 2}


def test_legacy_page_frame_carries_entry(adapter):
    conn, _ = join(adapter)
    adapter.on_legacy_page(DATE_TIME, "time", {}, "default", index=0, page_count=1)
    frame = recv(conn)
    assert (frame["template"], frame["index"], frame["page_count"]) == ("time", 0, 1)


def test_unknown_entry_is_absent(adapter):
    conn, _ = join(adapter)
    adapter.dispatch_template("SYSTEM_text", SKILL, DATA, "default")
    adapter.on_legacy_page(DATE_TIME, "time", {}, "default", index=0)
    for frame in recv_n(conn, 2):
        assert "index" not in frame and "page_count" not in frame


def test_snapshot_keeps_latest_entry(adapter):
    early, _ = join(adapter)
    adapter.dispatch_template("SYSTEM_text", SKILL, DATA, "default", index=0, page_count=2)
    adapter.on_namespace_activated(SKILL, "default")
    adapter.dispatch_template("SYSTEM_image", SKILL, DATA, "default", index=1, page_count=2)
    recv_n(early, 3)
    _, snapshot = join(adapter)
    assert snapshot["stack"] == [{"skill_id": SKILL, "template": "SYSTEM_image", "data": DATA,
                                  "index": 1, "page_count": 2}]


def test_snapshot_entry_without_template_has_no_entry(adapter):
    early, _ = join(adapter)
    adapter.on_session_update(SKILL, DATA, "default")
    adapter.on_namespace_activated(SKILL, "default")
    recv_n(early, 2)
    _, snapshot = join(adapter)
    assert snapshot["stack"] == [{"skill_id": SKILL, "template": None, "data": DATA}]


def test_template_without_entry_clears_the_mirrored_one(adapter):
    early, _ = join(adapter)
    adapter.dispatch_template("SYSTEM_text", SKILL, DATA, "default", index=0, page_count=2)
    adapter.dispatch_template("SYSTEM_text", SKILL, DATA, "default")
    recv_n(early, 2)
    _, snapshot = join(adapter)
    assert "index" not in snapshot["stack"][0]


def test_deactivation_drops_the_entry(adapter):
    early, _ = join(adapter)
    adapter.dispatch_template("SYSTEM_text", SKILL, DATA, "default", index=0, page_count=2)
    adapter.on_namespace_deactivated(SKILL, "default")
    adapter.on_session_update(SKILL, DATA, "default")
    adapter.on_namespace_activated(SKILL, "default")
    recv_n(early, 4)
    _, snapshot = join(adapter)
    assert snapshot["stack"] == [{"skill_id": SKILL, "template": None, "data": DATA}]
