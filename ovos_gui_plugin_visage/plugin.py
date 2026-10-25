"""The opm.gui_adapter plugin class."""
from typing import Any, Callable, Dict, Optional

from ovos_plugin_manager.templates.gui import AbstractGUIPlugin

from ovos_gui_plugin_visage import protocol
from ovos_gui_plugin_visage.bus_relay import BusRelay
from ovos_gui_plugin_visage.log import LOG
from ovos_gui_plugin_visage.server import GUI1Server


class VisageGUIPlugin(AbstractGUIPlugin):
    """Every handler builds one frame and hands it to the server thread.

    Client `interaction` and `focus` frames go back out on the bus (BusRelay).
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None, bus=None):
        super().__init__(config or {}, bus=bus)
        self.relay = BusRelay(bus)
        self.server = GUI1Server(self.config, on_client_frame=self.relay.relay).start()

    def _publish(self, build: Callable[..., protocol.Frame], *args) -> None:
        try:
            self.server.publish(build(*args))
        except Exception:
            LOG.exception(f"VisageGUIPlugin failed to publish {build.__name__}{args}")

    def dispatch_template(self, template: str, skill_id: str, data: Dict[str, Any],
                          session_id: str = "default", index: Optional[int] = None,
                          page_count: Optional[int] = None) -> None:
        """`index` and `page_count` default to unknown, not to OPM's 0 and 1: the frame then omits them."""
        self._publish(protocol.template, skill_id, template, data, session_id, index, page_count)

    def on_legacy_page(self, skill_id: str, page: str, data: Dict[str, Any],
                       session_id: str = "default", index: Optional[int] = None,
                       page_count: Optional[int] = None) -> None:
        """GUI-1 4.2 legacy path (prototype only): the skill's own page goes out as a template frame."""
        self._publish(protocol.template, skill_id, page, data, session_id, index, page_count)

    def on_session_update(self, skill_id: str, data: Dict[str, Any],
                          session_id: str = "default") -> None:
        self._publish(protocol.session_update, skill_id, data, session_id)

    def on_namespace_activated(self, skill_id: str, session_id: str = "default") -> None:
        self._publish(protocol.activated, skill_id, session_id)

    def on_namespace_deactivated(self, skill_id: str, session_id: str = "default") -> None:
        self._publish(protocol.deactivated, skill_id, session_id)

    def on_idle(self, session_id: str = "default") -> None:
        self._publish(protocol.idle, session_id)

    def on_status_event(self, event_name: str, data: Dict[str, Any],
                        session_id: str = "default") -> None:
        self._publish(protocol.status, event_name, data, session_id)

    def any_client_connected(self) -> bool:
        return self.server.client_count() > 0

    def shutdown(self) -> None:
        self.server.stop()
        self.relay.shutdown()
