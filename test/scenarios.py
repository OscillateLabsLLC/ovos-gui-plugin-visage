"""Scripted ovos-gui call sequences, in the order ovos-gui's rework makes them.

handle_show_page dispatches the template, then activates the namespace;
handle_set_value calls on_session_update with the full merged data;
removing the top namespace re-activates the one below it, and on_idle follows
the deactivation that empties a session.
"""
import json
import os
from pathlib import Path

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "gui1"
RECORD_ENV = "GUI1_RECORD_FIXTURES"

HELLO_SKILL = "ovos-skill-hello.openvoiceos"
WEATHER_SKILL = "ovos-skill-weather.openvoiceos"
HELLO_DATA = {"title": "Hi", "text": "Hello"}
WEATHER_DATA = {"current": 21, "min": 14, "max": 25, "condition": "Clear",
                "location": "San Antonio", "unit": "C"}


def text_then_weather(adapter):
    adapter.on_session_update(HELLO_SKILL, HELLO_DATA, "default")
    adapter.dispatch_template("SYSTEM_text", HELLO_SKILL, HELLO_DATA, "default")
    adapter.on_namespace_activated(HELLO_SKILL, "default")
    adapter.on_status_event("speak", {"utterance": "Hello"}, "default")
    adapter.on_session_update(WEATHER_SKILL, WEATHER_DATA, "default")
    adapter.dispatch_template("SYSTEM_weather", WEATHER_SKILL, WEATHER_DATA, "default")
    adapter.on_namespace_activated(WEATHER_SKILL, "default")
    adapter.on_session_update(WEATHER_SKILL, {**WEATHER_DATA, "current": 22}, "default")


def weather_then_clear(adapter):
    text_then_weather(adapter)
    adapter.on_namespace_deactivated(WEATHER_SKILL, "default")
    adapter.on_namespace_activated(HELLO_SKILL, "default")
    adapter.on_namespace_deactivated(HELLO_SKILL, "default")
    adapter.on_idle()


SCENARIOS = {"text_then_weather": (text_then_weather, 8),
             "weather_then_clear": (weather_then_clear, 12)}


def fixture_path(name, suffix=""):
    return FIXTURE_DIR / f"{name}{suffix}.jsonl"


def check_fixture(name, frames, suffix=""):
    """Assert frames equal the recorded fixture; rewrite it when recording."""
    path = fixture_path(name, suffix)
    if os.environ.get(RECORD_ENV):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(f) + "\n" for f in frames))
    recorded = [json.loads(line) for line in path.read_text().splitlines() if line]
    assert frames == recorded
