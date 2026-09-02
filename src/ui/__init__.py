"""UI package runtime compatibility hooks."""
from __future__ import annotations


def _patch_openwaters_pydeck_provider() -> None:
    """Force Open Waters Seamap styles through PyDeck's MapLibre provider.

    PyDeck defaults to Carto. Open Waters publishes a MapLibre style, so the
    provider must be explicit or the style URL is not rendered as intended.
    The patch is intentionally limited to the Open Waters Seamap URL family.
    """
    try:
        import pydeck as pdk
    except Exception:
        return

    deck_cls = pdk.Deck
    if getattr(deck_cls, "_mie_openwaters_maplibre", False):
        return

    original_init = deck_cls.__init__

    def patched_init(self, *args, **kwargs):
        map_style = kwargs.get("map_style")
        if isinstance(map_style, str) and map_style.startswith(
            "https://tiles.openwaters.io/seamap/"
        ):
            kwargs["map_provider"] = "maplibre"
            kwargs.setdefault("map_projection", "mercator")
        return original_init(self, *args, **kwargs)

    deck_cls.__init__ = patched_init
    deck_cls._mie_openwaters_maplibre = True


_patch_openwaters_pydeck_provider()
