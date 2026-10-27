"""Client frames to core bus Messages, emitted off the server loop.

`interaction` becomes `gui.interaction` (GUI-1 amendment A) and `focus`
becomes `gui.page.focus` (amendment B). The session is the connection's own,
never one the client names. Emits run on one worker thread, in arrival order,
so a slow bus never stalls the websocket server.
"""
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from ovos_bus_client import Message

from ovos_gui_plugin_visage.log import LOG
from ovos_gui_plugin_visage.protocol import Frame

SOURCE = "ovos-gui-plugin-visage"
TOPICS = {"interaction": "gui.interaction", "focus": "gui.page.focus"}
PAYLOAD_KEYS = {"interaction": ("namespace", "event", "data"),
                "focus": ("namespace", "page_number")}


def to_message(frame: Frame, session_id: str) -> Message:
    """The bus Message for a parsed client frame, attributed to ``session_id``."""
    kind = frame["type"]
    data = {key: frame[key] for key in PAYLOAD_KEYS[kind]}
    context = {"session": {"session_id": session_id}, "source": SOURCE}
    return Message(TOPICS[kind], data, context)


class BusRelay:
    """Emits client frames on the bus from a single worker thread."""

    def __init__(self, bus):
        self._bus = bus
        self._worker: Optional[ThreadPoolExecutor] = None
        if bus is not None:
            self._worker = ThreadPoolExecutor(max_workers=1,
                                              thread_name_prefix="gui1-visage-bus")

    def relay(self, frame: Frame, session_id: str) -> None:
        if self._worker is None:
            LOG.warning(f"GUI-1 adapter has no bus; client frame dropped: {frame}")
            return
        self._worker.submit(self._emit, to_message(frame, session_id))

    def _emit(self, message: Message) -> None:
        try:
            self._bus.emit(message)
        except Exception:
            LOG.exception(f"GUI-1 failed to emit {message.msg_type} {message.data}")

    def shutdown(self) -> None:
        if self._worker is not None:
            self._worker.shutdown(wait=False)
