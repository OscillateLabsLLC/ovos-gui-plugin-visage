from conftest import join, recv, recv_n

DATE_TIME = "ovos-skill-date-time.openvoiceos"
TIME_DATA = {"time_string": "10:36 AM", "ampm_string": "", "date_string": "25/10/2026"}


def test_legacy_page_goes_out_as_template_frame(adapter):
    conn, _ = join(adapter)
    adapter.on_legacy_page(DATE_TIME, "time", TIME_DATA, "default")
    assert recv(conn) == {"type": "template", "skill_id": DATE_TIME, "template": "time",
                          "data": TIME_DATA, "session_id": "default"}


def test_legacy_page_is_routed_by_session(adapter):
    kitchen, _ = join(adapter, "kitchen")
    hall, _ = join(adapter, "hall")
    adapter.on_legacy_page(DATE_TIME, "time", TIME_DATA, "kitchen")
    adapter.on_status_event("ping", {}, "hall")
    assert recv(kitchen)["template"] == "time"
    assert recv(hall)["type"] == "status"


def test_snapshot_mirrors_legacy_page_as_template(adapter):
    early, _ = join(adapter)
    adapter.on_session_update(DATE_TIME, TIME_DATA, "default")
    adapter.on_legacy_page(DATE_TIME, "time", TIME_DATA, "default")
    adapter.on_namespace_activated(DATE_TIME, "default")
    recv_n(early, 3)
    _, snapshot = join(adapter)
    assert snapshot["stack"] == [{"skill_id": DATE_TIME, "template": "time", "data": TIME_DATA}]
