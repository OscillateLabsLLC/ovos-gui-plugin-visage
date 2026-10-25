"""GUI-1 websocket server on its own thread and asyncio loop."""
import asyncio
import json
import threading
from http import HTTPStatus
from typing import Callable, Dict, Optional, Set

from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed

from ovos_gui_plugin_visage import protocol
from ovos_gui_plugin_visage.client_link import ClientLink
from ovos_gui_plugin_visage.log import LOG
from ovos_gui_plugin_visage.mirror import StackMirror

DEFAULTS = {"host": "127.0.0.1", "port": 18182, "path": "/gui1",
            "hello_timeout": 5.0, "max_backlog": 256}

ClientFrameHandler = Callable[[protocol.Frame, str], None]


def _ignore_client_frame(frame: protocol.Frame, session_id: str) -> None:
    LOG.info(f"GUI-1 client frame not forwarded (no handler): {frame}")


class GUI1Server:
    """Accepts GUI-1 clients and fans published frames out by session.

    `publish` is safe to call from any thread and never blocks on a client.
    `state` serves snapshots and sees every frame (StackMirror by default).
    `on_client_frame(frame, session_id)` gets each valid `interaction` or
    `focus` frame on the loop thread; it must return at once.

    Threading invariant: `state` and the session map are touched only on the
    server loop thread, so they need no lock. Hook threads (bus executor
    workers, ovos-gui's idle Timer) cross over only via `call_soon_threadsafe`.
    """

    def __init__(self, config: Optional[dict] = None, state=None,
                 on_client_frame: Optional[ClientFrameHandler] = None):
        self.config = {**DEFAULTS, **(config or {})}
        self.state = state or StackMirror()
        self.on_client_frame = on_client_frame or _ignore_client_frame
        self.port: Optional[int] = None
        self.ready = threading.Event()
        self._sessions: Dict[str, Set[ClientLink]] = {}
        self._client_total = 0
        self._loop = asyncio.new_event_loop()
        self._inbox: asyncio.Queue = asyncio.Queue()
        self._stopped: Optional[asyncio.Event] = None
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="gui1-visage-server")

    def start(self) -> "GUI1Server":
        self._thread.start()
        return self

    def publish(self, frame: protocol.Frame) -> None:
        try:
            self._loop.call_soon_threadsafe(self._inbox.put_nowait, frame)
        except RuntimeError:
            LOG.error(f"GUI-1 server loop is closed; frame not sent: {frame}")

    def client_count(self) -> int:
        return self._client_total

    def stop(self, timeout: float = 5.0) -> None:
        if self._stopped is not None and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._stopped.set)
        self._thread.join(timeout)

    def _run(self) -> None:
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._serve())
        except Exception:
            LOG.exception(f"GUI-1 server failed; config: {self.config}")
        finally:
            self.ready.set()
            self._loop.close()

    async def _serve(self) -> None:
        self._stopped = asyncio.Event()
        async with serve(self._handle, self.config["host"], self.config["port"],
                         process_request=self._check_path) as server:
            self.port = server.sockets[0].getsockname()[1]
            LOG.info(f"GUI-1 server listening on ws://{self.config['host']}:"
                     f"{self.port}{self.config['path']}")
            sender = asyncio.create_task(self._send_loop())
            self.ready.set()
            await self._stopped.wait()
            sender.cancel()

    def _check_path(self, connection, request):
        if request.path == self.config["path"]:
            return None
        LOG.warning(f"GUI-1 rejected request for path '{request.path}'")
        return connection.respond(HTTPStatus.NOT_FOUND, "unknown path\n")

    async def _send_loop(self) -> None:
        while True:
            frame = await self._inbox.get()
            try:
                self._route(frame)
            except Exception:
                LOG.exception(f"GUI-1 failed to route frame: {frame}")
            await asyncio.sleep(0)  # let client writers drain between frames of a burst

    def _route(self, frame: protocol.Frame) -> None:
        text = json.dumps(frame)
        self.state.apply(frame)
        for link in self._targets(frame):
            link.offer(text)

    def _targets(self, frame: protocol.Frame):
        if protocol.is_broadcast(frame):
            return [link for links in self._sessions.values() for link in links]
        return list(self._sessions.get(frame.get("session_id"), ()))

    async def _handle(self, websocket) -> None:
        session_id = await self._handshake(websocket)
        if session_id is None:
            return
        link = self._register(websocket, session_id)
        try:
            async for message in websocket:
                self._receive(link, message)
        except ConnectionClosed:
            pass
        finally:
            link.forget()
            LOG.info(f"GUI-1 client {link.peer} left session '{session_id}'")

    def _receive(self, link: ClientLink, message) -> None:
        frame = protocol.parse_client_frame(message)
        if frame is None:
            LOG.info(f"GUI-1 ignored client frame from {link.peer}: {str(message)[:500]}")
            return
        try:
            self.on_client_frame(frame, link.session_id)
        except Exception:
            LOG.exception(f"GUI-1 client frame handler failed for {frame}")

    async def _handshake(self, websocket) -> Optional[str]:
        timeout = float(self.config["hello_timeout"])
        try:
            raw = await asyncio.wait_for(websocket.recv(), timeout)
            return protocol.parse_hello(raw)
        except asyncio.TimeoutError:
            await self._reject(websocket, f"no hello within {timeout:g} s")
        except protocol.HandshakeError as exc:
            await self._reject(websocket, str(exc))
        except ConnectionClosed:
            LOG.info(f"GUI-1 client {websocket.remote_address} left before hello")
        return None

    async def _reject(self, websocket, reason: str) -> None:
        LOG.warning(f"GUI-1 handshake failed for {websocket.remote_address}: {reason}")
        try:
            await websocket.send(json.dumps(protocol.error(reason)))
            await websocket.close(protocol.CLOSE_PROTOCOL_ERROR, reason)
        except ConnectionClosed:
            LOG.info(f"GUI-1 client {websocket.remote_address} closed during reject")

    def _register(self, websocket, session_id: str) -> ClientLink:
        link = ClientLink(websocket, session_id, int(self.config["max_backlog"]),
                          on_drop=self._unregister)
        link.offer(json.dumps(protocol.welcome(session_id)))
        stack = self.state.snapshot(session_id)
        link.offer(json.dumps(protocol.snapshot(session_id, stack)))
        self._sessions.setdefault(session_id, set()).add(link)
        self._client_total += 1
        LOG.info(f"GUI-1 client {link.peer} joined session '{session_id}'")
        return link

    def _unregister(self, link: ClientLink) -> None:
        links = self._sessions.get(link.session_id)
        if links is None:
            return
        if link in links:
            links.discard(link)
            self._client_total -= 1
        if not links:
            del self._sessions[link.session_id]
