"""One connected, handshaken client: a bounded outbox and its writer task."""
import asyncio
from typing import Callable

from websockets.exceptions import ConnectionClosed

from ovos_gui_plugin_visage.log import LOG
from ovos_gui_plugin_visage.protocol import CLOSE_TRY_AGAIN_LATER

SLOW_CLIENT_REASON = "client too slow"


class ClientLink:
    """Queues encoded frames for one socket; a full outbox drops the client."""

    def __init__(self, websocket, session_id: str, max_backlog: int,
                 on_drop: Callable[["ClientLink"], None]):
        self.websocket = websocket
        self.session_id = session_id
        self._outbox: asyncio.Queue = asyncio.Queue(maxsize=max_backlog)
        self._on_drop = on_drop
        self._writer = asyncio.create_task(self._drain())
        self.dropped = False

    @property
    def peer(self) -> str:
        return str(self.websocket.remote_address)

    def offer(self, text: str) -> None:
        if self.dropped:
            return
        try:
            self._outbox.put_nowait(text)
        except asyncio.QueueFull:
            LOG.warning(f"GUI-1 client {self.peer} (session '{self.session_id}') "
                        f"exceeded backlog of {self._outbox.maxsize} frames; "
                        f"dropping it. Undelivered frame: {text[:500]}")
            self.drop(CLOSE_TRY_AGAIN_LATER, SLOW_CLIENT_REASON)

    def drop(self, code: int, reason: str) -> None:
        if self.dropped:
            return
        self.forget()
        asyncio.create_task(self._close(code, reason))

    async def _close(self, code: int, reason: str) -> None:
        try:
            await self.websocket.close(code, reason)
        except Exception:
            LOG.exception(f"GUI-1 close of {self.peer} failed")

    async def _drain(self) -> None:
        try:
            while True:
                text = await self._outbox.get()
                await self.websocket.send(text)
        except ConnectionClosed:
            LOG.info(f"GUI-1 client {self.peer} closed while sending")
        except asyncio.CancelledError:
            raise
        except Exception:
            LOG.exception(f"GUI-1 writer for {self.peer} failed")
        self.forget()

    def forget(self) -> None:
        """Stop routing to this client without closing the socket again."""
        if self.dropped:
            return
        self.dropped = True
        self._writer.cancel()
        self._on_drop(self)
