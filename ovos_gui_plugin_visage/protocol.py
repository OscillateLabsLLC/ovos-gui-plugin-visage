"""GUI-1 wire protocol frames and handshake validation (see docs/WIRE.md)."""
import json
from typing import Any, Dict, List, Optional

from ovos_gui_plugin_visage.version import __version__

PROTOCOL = "ovos-gui-1"
VERSION = 1
SERVER_NAME = f"ovos-gui-plugin-visage/{__version__}"
CLOSE_PROTOCOL_ERROR = 1002
CLOSE_TRY_AGAIN_LATER = 1013

Frame = Dict[str, Any]


class HandshakeError(Exception):
    """The first client frame is not a valid GUI-1 hello."""


def parse_hello(raw: Any) -> str:
    """Validate a hello frame and return its session_id."""
    if not isinstance(raw, str):
        raise HandshakeError("first frame must be a text frame")
    try:
        hello = json.loads(raw)
    except ValueError:
        raise HandshakeError("first frame is not valid JSON")
    if not isinstance(hello, dict) or hello.get("type") != "hello":
        raise HandshakeError("first frame must be hello")
    if hello.get("protocol") != PROTOCOL:
        raise HandshakeError(f"unsupported protocol '{hello.get('protocol')}'")
    if hello.get("version") != VERSION:
        raise HandshakeError(f"unsupported version '{hello.get('version')}'")
    session_id = hello.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        raise HandshakeError("missing session_id")
    return session_id


def welcome(session_id: str) -> Frame:
    return {"type": "welcome", "protocol": PROTOCOL, "version": VERSION,
            "session_id": session_id, "server": SERVER_NAME}


def error(reason: str) -> Frame:
    return {"type": "error", "reason": reason}


def snapshot(session_id: str, stack: List[Frame], ambient: Dict[str, Any]) -> Frame:
    return {"type": "snapshot", "session_id": session_id, "stack": stack, "ambient": ambient}


def template(skill_id: str, template_name: str, data: Dict[str, Any],
             session_id: str) -> Frame:
    return {"type": "template", "skill_id": skill_id, "template": template_name,
            "data": dict(data or {}), "session_id": session_id}


def session_update(skill_id: str, data: Dict[str, Any], session_id: str) -> Frame:
    return {"type": "session_update", "skill_id": skill_id,
            "data": dict(data or {}), "session_id": session_id}


def activated(skill_id: str, session_id: str) -> Frame:
    return {"type": "activated", "skill_id": skill_id, "session_id": session_id}


def deactivated(skill_id: str, session_id: str) -> Frame:
    return {"type": "deactivated", "skill_id": skill_id, "session_id": session_id}


def idle(session_id: str) -> Frame:
    return {"type": "idle", "session_id": session_id}


def status(event_name: str, data: Optional[Dict[str, Any]], session_id: str) -> Frame:
    return {"type": "status", "event_name": event_name,
            "data": dict(data or {}), "session_id": session_id}


def is_broadcast(frame: Frame) -> bool:
    """Only status goes to every client regardless of session; idle is per session."""
    return frame.get("type") == "status"


def parse_client_frame(raw: Any) -> Optional[Frame]:
    """A valid interaction or focus frame after hello, normalised; None for anything else."""
    try:
        frame = json.loads(raw) if isinstance(raw, str) else None
    except ValueError:
        return None
    if not isinstance(frame, dict) or not _is_name(frame.get("namespace")):
        return None
    if frame.get("type") == "interaction":
        return _interaction(frame)
    if frame.get("type") == "focus":
        return _focus(frame)
    return None


def _is_name(value: Any) -> bool:
    return isinstance(value, str) and bool(value)


def _interaction(frame: Frame) -> Optional[Frame]:
    data = frame.get("data", {})
    if not _is_name(frame.get("event")) or not isinstance(data, dict):
        return None
    return {"type": "interaction", "namespace": frame["namespace"],
            "event": frame["event"], "data": data}


def _focus(frame: Frame) -> Optional[Frame]:
    page_number = frame.get("page_number")
    if not isinstance(page_number, int) or isinstance(page_number, bool) or page_number < 0:
        return None
    return {"type": "focus", "namespace": frame["namespace"], "page_number": page_number}
