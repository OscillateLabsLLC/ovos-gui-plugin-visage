"""OVOS GUI-1 adapter that relays ovos-gui adapter calls to Visage clients.

VisageGUIPlugin loads lazily so the server and tools run with only
`websockets` installed (no ovos-plugin-manager needed for the replay server).
"""
from ovos_gui_plugin_visage.version import __version__

__all__ = ["VisageGUIPlugin", "__version__"]


def __getattr__(name):
    if name == "VisageGUIPlugin":
        from ovos_gui_plugin_visage.plugin import VisageGUIPlugin
        return VisageGUIPlugin
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
