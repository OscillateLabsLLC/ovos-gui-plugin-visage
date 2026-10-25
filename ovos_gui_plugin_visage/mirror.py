"""Per-session stack mirror and ambient store that serve `snapshot` on hello.

PROTOTYPE SHORTCUT: ovos-gui gives adapters no handle to its query surface, so
the adapter rebuilds the stack from the adapter calls it sees instead of asking
ovos-gui. Ambient data (`gui.ambient.*` status events) is kept the same way:
the last payload per topic, device-wide.
`idle` changes nothing: ovos-gui calls on_idle(session_id) only after the
deactivations that emptied that session, so its mirror is already empty.
Only touched from the server's event loop thread.
"""
from typing import Any, Dict, List, Optional

from ovos_gui_plugin_visage.protocol import Frame

AMBIENT_PREFIX = "gui.ambient."


class _SessionStack:
    def __init__(self):
        self.order: List[str] = []
        self.templates: Dict[str, str] = {}
        self.data: Dict[str, Dict[str, Any]] = {}

    def raise_to_top(self, skill_id: str) -> None:
        if skill_id in self.order:
            self.order.remove(skill_id)
        self.order.insert(0, skill_id)

    def drop(self, skill_id: str) -> None:
        if skill_id in self.order:
            self.order.remove(skill_id)
        self.templates.pop(skill_id, None)
        self.data.pop(skill_id, None)

    def entries(self) -> List[Frame]:
        return [{"skill_id": skill_id,
                 "template": self.templates.get(skill_id),
                 "data": dict(self.data.get(skill_id, {}))}
                for skill_id in self.order]


class StackMirror:
    """Tracks activation order, last template and last data per skill."""

    def __init__(self):
        self._sessions: Dict[str, _SessionStack] = {}
        self._ambient: Dict[str, Dict[str, Any]] = {}

    def _session(self, session_id: str) -> _SessionStack:
        return self._sessions.setdefault(session_id, _SessionStack())

    def apply(self, frame: Frame) -> None:
        kind = frame.get("type")
        if kind == "status":
            self._keep_ambient(frame)
            return
        if kind not in ("template", "session_update", "activated", "deactivated"):
            return
        stack = self._session(frame["session_id"])
        skill_id = frame["skill_id"]
        if kind == "deactivated":
            stack.drop(skill_id)
            return
        if "data" in frame:
            stack.data[skill_id] = dict(frame["data"])
        if kind == "template":
            stack.templates[skill_id] = frame["template"]
            if skill_id not in stack.order:
                stack.raise_to_top(skill_id)
        elif kind == "activated":
            stack.raise_to_top(skill_id)

    def _keep_ambient(self, frame: Frame) -> None:
        topic = frame.get("event_name", "")
        if topic.startswith(AMBIENT_PREFIX):
            self._ambient[topic] = dict(frame.get("data") or {})

    def snapshot(self, session_id: str) -> List[Frame]:
        stack = self._sessions.get(session_id)
        return stack.entries() if stack else []

    def ambient(self) -> Dict[str, Dict[str, Any]]:
        return {topic: dict(data) for topic, data in self._ambient.items()}


class StaticSnapshot:
    """Serves a fixed stack and ambient map and ignores frames (replay server)."""

    def __init__(self, stack: List[Frame], ambient: Optional[Dict[str, Any]] = None):
        self._stack = list(stack)
        self._ambient = dict(ambient or {})

    def apply(self, frame: Frame) -> None:
        return None

    def snapshot(self, session_id: str) -> List[Frame]:
        return [dict(entry) for entry in self._stack]

    def ambient(self) -> Dict[str, Any]:
        return {topic: dict(data) for topic, data in self._ambient.items()}
