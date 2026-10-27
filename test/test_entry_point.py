import socket
import time
from importlib.metadata import entry_points

from ovos_plugin_manager.gui import OVOSGUIAdapterFactory, find_gui_adapter_plugins

from ovos_gui_plugin_visage import VisageGUIPlugin

PLUGIN_NAME = "ovos-gui-plugin-visage"


def test_entry_point_is_registered():
    names = {ep.name: ep for ep in entry_points(group="opm.gui_adapter")}
    assert names[PLUGIN_NAME].load() is VisageGUIPlugin


def test_opm_finds_plugin():
    assert find_gui_adapter_plugins()[PLUGIN_NAME] is VisageGUIPlugin


def test_factory_builds_plugin_with_its_config_section():
    config = {PLUGIN_NAME: {"port": 0, "path": "/custom"}}
    adapters = OVOSGUIAdapterFactory.create_all(config=config)
    ours = [a for a in adapters if isinstance(a, VisageGUIPlugin)]
    try:
        assert len(ours) == 1
        assert ours[0].server.ready.wait(5)
        assert ours[0].server.config["path"] == "/custom"
        assert ours[0].server.config["host"] == "127.0.0.1"
        assert ours[0].server.port
        assert not ours[0].any_client_connected()
    finally:
        for adapter in adapters:
            getattr(adapter, "shutdown", lambda: None)()


def test_init_returns_at_once():
    started = time.perf_counter()
    plugin = VisageGUIPlugin({"port": 0})
    elapsed = time.perf_counter() - started
    try:
        assert elapsed < 0.05
        assert plugin.server.ready.wait(5)
    finally:
        plugin.shutdown()


def test_port_in_use_is_logged_and_handlers_keep_working():
    with socket.socket() as blocker:
        blocker.bind(("127.0.0.1", 0))
        blocker.listen()
        plugin = VisageGUIPlugin({"port": blocker.getsockname()[1]})
        try:
            assert plugin.server.ready.wait(5)
            assert plugin.server.port is None
            plugin.on_idle()
            plugin.dispatch_template("SYSTEM_text", "skill.a", {}, "default")
            assert not plugin.any_client_connected()
        finally:
            plugin.shutdown()
