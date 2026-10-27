try:
    from ovos_utils.log import LOG
except ImportError:
    import logging

    LOG = logging.getLogger("ovos_gui_plugin_visage")
