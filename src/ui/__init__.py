"""UI package runtime compatibility hooks."""
from __future__ import annotations

import streamlit as st


_OPENWATERS_PATCHED = False
_FLOATING_SIDEBAR_PATCHED = False


def _patch_openwaters_pydeck_provider() -> None:
    """Force Open Waters Seamap styles through PyDeck's MapLibre provider."""
    global _OPENWATERS_PATCHED
    if _OPENWATERS_PATCHED:
        return
    try:
        import pydeck as pdk
    except Exception:
        return

    deck_cls = pdk.Deck
    if getattr(deck_cls, "_mie_openwaters_maplibre", False):
        _OPENWATERS_PATCHED = True
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
    _OPENWATERS_PATCHED = True


def _install_floating_sidebar_controller() -> None:
    """Inject a browser-side controller for free 2D sidebar positioning.

    The app keeps Streamlit's native sidebar as the widget host. A tiny
    components.v1 iframe is used only as a same-origin JavaScript bridge so
    the browser can attach pointer events to that native DOM node. The
    operator's position is stored in localStorage and restored after reruns.
    """
    global _FLOATING_SIDEBAR_PATCHED
    if _FLOATING_SIDEBAR_PATCHED:
        return

    original_markdown = st.markdown

    def patched_markdown(body, *args, **kwargs):
        result = original_markdown(body, *args, **kwargs)
        if (
            isinstance(body, str)
            and ".stApp {" in body
            and '[data-testid="stSidebar"]' in body
        ):
            try:
                import streamlit.components.v1 as components

                components.html(
                    """
                    <script>
                    (() => {
                      const SIDEBAR = '[data-testid="stSidebar"]';
                      const KEY = 'mie.sidebar.position.v1';
                      const HANDLE_CLASS = 'mie-drag-handle';
                      const STYLE_ID = 'mie-floating-sidebar-style';
                      const clamp = (v, min, max) => Math.min(Math.max(v, min), max);

                      const controller = () => {
                        const doc = window.parent.document;
                        const sidebar = doc.querySelector(SIDEBAR);
                        if (!sidebar) return false;

                        if (!sidebar.querySelector('.' + HANDLE_CLASS)) {
                          const handle = doc.createElement('div');
                          handle.className = HANDLE_CLASS;
                          handle.title = 'Drag to reposition mission controls';
                          handle.setAttribute('aria-label', 'Drag sidebar');
                          handle.innerHTML = '<span class="mie-drag-grip">⠿</span><span>DRAG PANEL</span>';
                          sidebar.appendChild(handle);
                        }

                        if (!doc.getElementById(STYLE_ID)) {
                          const style = doc.createElement('style');
                          style.id = STYLE_ID;
                          style.textContent = `
                            [data-testid="stSidebar"] { will-change: left, top; }
                            [data-testid="stSidebar"] .${HANDLE_CLASS} {
                              position:absolute; top:6px; left:8px; right:8px; height:26px;
                              display:flex; align-items:center; justify-content:center; gap:7px;
                              box-sizing:border-box; z-index:1000002;
                              border:1px solid #1b3640; border-radius:3px;
                              background:rgba(13,28,36,.97); color:#79939b;
                              cursor:grab; user-select:none; touch-action:none;
                              font:500 9px 'IBM Plex Mono',monospace; letter-spacing:.12em;
                            }
                            [data-testid="stSidebar"] .${HANDLE_CLASS}:hover {
                              color:#35c2c9; border-color:#35c2c9;
                            }
                            [data-testid="stSidebar"] .${HANDLE_CLASS}:active { cursor:grabbing; }
                            [data-testid="stSidebar"] .mie-drag-grip { font-size:16px; line-height:1; }
                            [data-testid="stSidebarContent"] { padding-top:2.35rem !important; }
                          `;
                          doc.head.appendChild(style);
                        }

                        if (sidebar.dataset.mieDragBound === '1') return true;
                        sidebar.dataset.mieDragBound = '1';
                        sidebar.style.position = 'fixed';
                        sidebar.style.zIndex = '1000000';
                        sidebar.style.bottom = 'auto';

                        try {
                          const saved = JSON.parse(
                            doc.defaultView.localStorage.getItem(KEY) || 'null'
                          );
                          if (saved && Number.isFinite(saved.left) && Number.isFinite(saved.top)) {
                            sidebar.style.left = `${saved.left}px`;
                            sidebar.style.top = `${saved.top}px`;
                          }
                        } catch (_) {}

                        const handle = sidebar.querySelector('.' + HANDLE_CLASS);
                        const save = () => {
                          const rect = sidebar.getBoundingClientRect();
                          try {
                            doc.defaultView.localStorage.setItem(
                              KEY,
                              JSON.stringify({
                                left: Math.round(rect.left),
                                top: Math.round(rect.top)
                              })
                            );
                          } catch (_) {}
                        };

                        const clampToViewport = () => {
                          const rect = sidebar.getBoundingClientRect();
                          const maxLeft = Math.max(0, doc.defaultView.innerWidth - rect.width);
                          const maxTop = Math.max(0, doc.defaultView.innerHeight - rect.height);
                          sidebar.style.left = `${clamp(rect.left, 0, maxLeft)}px`;
                          sidebar.style.top = `${clamp(rect.top, 0, maxTop)}px`;
                          save();
                        };

                        let dragging = false;
                        let offsetX = 0;
                        let offsetY = 0;

                        handle.addEventListener('pointerdown', (event) => {
                          if (event.button !== 0) return;
                          const rect = sidebar.getBoundingClientRect();
                          dragging = true;
                          offsetX = event.clientX - rect.left;
                          offsetY = event.clientY - rect.top;
                          handle.setPointerCapture?.(event.pointerId);
                          sidebar.style.transition = 'none';
                          event.preventDefault();
                          event.stopPropagation();
                        });

                        handle.addEventListener('pointermove', (event) => {
                          if (!dragging) return;
                          const rect = sidebar.getBoundingClientRect();
                          const maxLeft = Math.max(0, doc.defaultView.innerWidth - rect.width);
                          const maxTop = Math.max(0, doc.defaultView.innerHeight - rect.height);
                          sidebar.style.left = `${clamp(event.clientX - offsetX, 0, maxLeft)}px`;
                          sidebar.style.top = `${clamp(event.clientY - offsetY, 0, maxTop)}px`;
                          event.preventDefault();
                        });

                        const stop = (event) => {
                          if (!dragging) return;
                          dragging = false;
                          try { handle.releasePointerCapture?.(event.pointerId); } catch (_) {}
                          sidebar.style.transition = 'box-shadow .18s ease, opacity .18s ease';
                          save();
                        };

                        handle.addEventListener('pointerup', stop);
                        handle.addEventListener('pointercancel', stop);
                        doc.defaultView.addEventListener('resize', clampToViewport);
                        clampToViewport();
                        return true;
                      };

                      let attempts = 0;
                      const boot = () => {
                        if (controller() || attempts++ >= 50) return;
                        doc.defaultView.setTimeout(boot, 120);
                      };
                      boot();
                    })();
                    </script>
                    """,
                    height=0,
                    scrolling=False,
                )
            except Exception:
                pass
        return result

    st.markdown = patched_markdown
    _FLOATING_SIDEBAR_PATCHED = True


_patch_openwaters_pydeck_provider()
_install_floating_sidebar_controller()
