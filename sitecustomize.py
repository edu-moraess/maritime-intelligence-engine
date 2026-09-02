"""Runtime compatibility hooks for third-party rendering defaults."""
from __future__ import annotations


def _enable_openwaters_maplibre() -> None:
    try:
        import pydeck as pdk
    except Exception:
        return

    deck_cls = pdk.Deck
    if getattr(deck_cls, "_mie_openwaters_patch", False):
        return

    original_init = deck_cls.__init__

    def patched_init(self, *args, **kwargs):
        map_style = kwargs.get("map_style")
        if isinstance(map_style, str) and map_style.startswith("https://tiles.openwaters.io/seamap/"):
            kwargs["map_provider"] = "maplibre"
            kwargs.setdefault("map_projection", "mercator")
        return original_init(self, *args, **kwargs)

    deck_cls.__init__ = patched_init
    deck_cls._mie_openwaters_patch = True


_enable_openwaters_maplibre()
