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
    """Install persistent browser controllers for the floating operations UI.

    Streamlit's native sidebar remains the widget host. Browser enhancement only
    changes presentation: the mission-controls sidebar is draggable and the
    selected vessel intelligence card becomes a responsive floating inspector.
    No Streamlit widget is replaced and no data is created by this layer.
    """
    global _FLOATING_SIDEBAR_PATCHED
    if _FLOATING_SIDEBAR_PATCHED:
        return

    controller_html = r"""
<script>
(() => {
  const SIDEBAR = '[data-testid="stSidebar"]';
  const CONTENT = '[data-testid="stSidebarContent"]';
  const KEY = 'mie.sidebar.position.v2';
  const HANDLE_CLASS = 'mie-drag-handle';
  const STYLE_ID = 'mie-floating-sidebar-style';
  const GLOBAL_KEY = '__mieFloatingSidebarControllerV3';
  const PANEL_CLASS = 'mie-contact-intelligence-panel';
  const CANVAS_CLASS = 'mie-overview-operational-canvas';

  const root = window.parent && window.parent.document
    ? window.parent.document
    : document;
  const win = root.defaultView || window.parent || window;

  if (win[GLOBAL_KEY]) return;
  win[GLOBAL_KEY] = true;

  const clamp = (value, min, max) => Math.min(Math.max(value, min), max);

  const injectStyle = () => {
    if (root.getElementById(STYLE_ID)) return;
    const style = root.createElement('style');
    style.id = STYLE_ID;
    style.textContent = `
      [data-testid="stSidebar"].mie-floating-sidebar {
        position: fixed !important;
        left: var(--mie-sidebar-left, 12px) !important;
        top: var(--mie-sidebar-top, 12px) !important;
        right: auto !important;
        bottom: auto !important;
        width: min(22rem, 88vw) !important;
        height: min(calc(100vh - 24px), 760px) !important;
        min-height: 0 !important;
        max-height: calc(100vh - 24px) !important;
        margin: 0 !important;
        transform: none !important;
        z-index: 1000000 !important;
        overflow: visible !important;
        will-change: left, top;
      }
      [data-testid="stSidebar"].mie-floating-sidebar[aria-expanded="false"] {
        transform: translateX(-110%) !important;
      }
      [data-testid="stSidebar"].mie-floating-sidebar > div:first-child {
        width: 100% !important;
        height: 100% !important;
        min-height: 0 !important;
      }
      [data-testid="stSidebarContent"].mie-floating-sidebar-content {
        box-sizing: border-box !important;
        height: 100% !important;
        max-height: 100% !important;
        overflow-y: auto !important;
        padding-top: 2.55rem !important;
      }
      [data-testid="stSidebar"] .${HANDLE_CLASS} {
        position: absolute;
        top: 6px;
        left: 8px;
        right: 8px;
        height: 26px;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 7px;
        box-sizing: border-box;
        z-index: 1000002;
        border: 1px solid #1b3640;
        border-radius: 3px;
        background: rgba(13,28,36,.97);
        color: #79939b;
        cursor: grab;
        user-select: none;
        -webkit-user-select: none;
        touch-action: none;
        font: 500 9px 'IBM Plex Mono', monospace;
        letter-spacing: .12em;
      }
      [data-testid="stSidebar"] .${HANDLE_CLASS}:hover {
        color: #35c2c9;
        border-color: #35c2c9;
      }
      [data-testid="stSidebar"] .${HANDLE_CLASS}:active { cursor: grabbing; }
      [data-testid="stSidebar"] .mie-drag-grip { font-size: 16px; line-height: 1; }

      /* P0.3 — selected-contact intelligence inspector. */
      [data-testid="stColumn"].${PANEL_CLASS} {
        position: fixed !important;
        top: 12px !important;
        right: 12px !important;
        bottom: 12px !important;
        width: min(25rem, 31vw) !important;
        max-width: calc(100vw - 24px) !important;
        z-index: 999990 !important;
        overflow: hidden !important;
        box-sizing: border-box !important;
        margin: 0 !important;
        padding: .7rem .75rem !important;
        background: rgba(13,28,36,.97) !important;
        border: 1px solid #1b3640 !important;
        border-radius: 4px !important;
        box-shadow: 0 14px 40px rgba(0,0,0,.35) !important;
      }
      [data-testid="stColumn"].${PANEL_CLASS} > div {
        height: 100% !important;
        min-height: 0 !important;
      }
      [data-testid="stColumn"].${PANEL_CLASS} > div > div {
        height: 100% !important;
        min-height: 0 !important;
        overflow-y: auto !important;
        overflow-x: hidden !important;
        scrollbar-width: thin;
      }
      [data-testid="stColumn"].${PANEL_CLASS} .vessel-id .name {
        font-size: 1.05rem;
      }
      [data-testid="stColumn"].${PANEL_CLASS} .panel-title {
        position: sticky;
        top: 0;
        z-index: 2;
        padding-top: .1rem;
        background: rgba(13,28,36,.97);
      }

      /* P0.4 — make the live map the primary operational canvas. The
         underlying Streamlit layout remains intact; only presentation changes.
         The floating contact inspector is removed from normal flex flow, giving
         the map the dominant working area without changing selection or data. */
      [data-testid="stHorizontalBlock"].${CANVAS_CLASS} {
        width: 100% !important;
        max-width: none !important;
        align-items: flex-start !important;
        gap: .7rem !important;
      }
      [data-testid="stHorizontalBlock"].${CANVAS_CLASS}
        > [data-testid="stColumn"]:nth-child(1) {
        flex: 0 0 11% !important;
        max-width: 11% !important;
      }
      [data-testid="stHorizontalBlock"].${CANVAS_CLASS}
        > [data-testid="stColumn"]:nth-child(2) {
        flex: 1 1 auto !important;
        min-width: 0 !important;
        max-width: none !important;
      }
      [data-testid="stHorizontalBlock"].${CANVAS_CLASS}
        > [data-testid="stColumn"]:nth-child(3) {
        flex: 0 0 0 !important;
        width: 0 !important;
        min-width: 0 !important;
        max-width: 0 !important;
        overflow: visible !important;
      }
      [data-testid="stHorizontalBlock"].${CANVAS_CLASS}
        > [data-testid="stColumn"]:nth-child(2) .stDeckGlJson {
        width: 100% !important;
      }

      @media (max-width: 980px) {
        [data-testid="stColumn"].${PANEL_CLASS} {
          width: min(24rem, 44vw) !important;
        }
        [data-testid="stHorizontalBlock"].${CANVAS_CLASS}
          > [data-testid="stColumn"]:nth-child(1) {
          flex-basis: 17% !important;
          max-width: 17% !important;
        }
      }
      @media (max-width: 760px) {
        [data-testid="stColumn"].${PANEL_CLASS} {
          left: 8px !important;
          right: 8px !important;
          top: auto !important;
          bottom: 8px !important;
          width: auto !important;
          max-width: none !important;
          height: min(58vh, 34rem) !important;
          border-radius: 4px !important;
          padding: .6rem .65rem !important;
        }
        [data-testid="stHorizontalBlock"].${CANVAS_CLASS} {
          flex-wrap: wrap !important;
        }
        [data-testid="stHorizontalBlock"].${CANVAS_CLASS}
          > [data-testid="stColumn"]:nth-child(1),
        [data-testid="stHorizontalBlock"].${CANVAS_CLASS}
          > [data-testid="stColumn"]:nth-child(2) {
          flex: 0 0 100% !important;
          max-width: 100% !important;
        }
      }
    `;
    root.head.appendChild(style);
  };

  const readPosition = () => {
    try {
      const saved = JSON.parse(win.localStorage.getItem(KEY) || 'null');
      if (saved && Number.isFinite(saved.left) && Number.isFinite(saved.top)) {
        return { left: saved.left, top: saved.top };
      }
    } catch (_) {}
    return { left: 12, top: 12 };
  };

  const savePosition = (left, top) => {
    try {
      win.localStorage.setItem(KEY, JSON.stringify({
        left: Math.round(left),
        top: Math.round(top),
      }));
    } catch (_) {}
  };

  const viewport = () => {
    const vv = win.visualViewport;
    return {
      width: Math.max(1, vv ? vv.width : win.innerWidth),
      height: Math.max(1, vv ? vv.height : win.innerHeight),
    };
  };

  const setPosition = (sidebar, left, top, persist = false) => {
    const rect = sidebar.getBoundingClientRect();
    const view = viewport();
    const maxLeft = Math.max(0, view.width - rect.width);
    const maxTop = Math.max(0, view.height - rect.height);
    const nextLeft = clamp(left, 0, maxLeft);
    const nextTop = clamp(top, 0, maxTop);
    sidebar.style.setProperty('--mie-sidebar-left', `${nextLeft}px`, 'important');
    sidebar.style.setProperty('--mie-sidebar-top', `${nextTop}px`, 'important');
    sidebar.style.setProperty('left', `${nextLeft}px`, 'important');
    sidebar.style.setProperty('top', `${nextTop}px`, 'important');
    sidebar.style.setProperty('right', 'auto', 'important');
    sidebar.style.setProperty('bottom', 'auto', 'important');
    if (persist) savePosition(nextLeft, nextTop);
  };

  const clampCurrent = (sidebar, persist = true) => {
    const rect = sidebar.getBoundingClientRect();
    setPosition(sidebar, rect.left, rect.top, persist);
  };

  const bind = (sidebar) => {
    if (!sidebar || sidebar.dataset.mieFloatingBound === '1') return;

    injectStyle();
    sidebar.classList.add('mie-floating-sidebar');

    const saved = readPosition();
    const expanded = sidebar.getAttribute('aria-expanded') !== 'false';
    if (expanded) setPosition(sidebar, saved.left, saved.top, false);

    const content = sidebar.querySelector(CONTENT);
    if (content) content.classList.add('mie-floating-sidebar-content');

    let handle = sidebar.querySelector('.' + HANDLE_CLASS);
    if (!handle) {
      handle = root.createElement('div');
      handle.className = HANDLE_CLASS;
      handle.title = 'Drag to reposition mission controls';
      handle.setAttribute('aria-label', 'Drag sidebar');
      handle.setAttribute('role', 'button');
      handle.innerHTML = '<span class="mie-drag-grip">⠿</span><span>DRAG PANEL</span>';
      sidebar.appendChild(handle);
    }

    sidebar.dataset.mieFloatingBound = '1';

    let dragging = false;
    let pointerId = null;
    let offsetX = 0;
    let offsetY = 0;
    let frame = 0;
    let nextLeft = 0;
    let nextTop = 0;

    const renderDrag = () => {
      frame = 0;
      if (!dragging) return;
      setPosition(sidebar, nextLeft, nextTop, false);
    };

    const move = (event) => {
      if (!dragging || event.pointerId !== pointerId) return;
      const rect = sidebar.getBoundingClientRect();
      nextLeft = event.clientX - offsetX;
      nextTop = event.clientY - offsetY;
      const view = viewport();
      nextLeft = clamp(nextLeft, 0, Math.max(0, view.width - rect.width));
      nextTop = clamp(nextTop, 0, Math.max(0, view.height - rect.height));
      if (!frame) frame = win.requestAnimationFrame(renderDrag);
      event.preventDefault();
    };

    const stop = (event) => {
      if (!dragging || (pointerId !== null && event.pointerId !== pointerId)) return;
      dragging = false;
      try { handle.releasePointerCapture(pointerId); } catch (_) {}
      pointerId = null;
      if (frame) {
        win.cancelAnimationFrame(frame);
        frame = 0;
      }
      setPosition(sidebar, nextLeft, nextTop, true);
      sidebar.style.removeProperty('transition');
    };

    handle.addEventListener('pointerdown', (event) => {
      if (event.button !== undefined && event.button !== 0) return;
      const rect = sidebar.getBoundingClientRect();
      dragging = true;
      pointerId = event.pointerId;
      offsetX = event.clientX - rect.left;
      offsetY = event.clientY - rect.top;
      nextLeft = rect.left;
      nextTop = rect.top;
      sidebar.style.setProperty('transition', 'none', 'important');
      try { handle.setPointerCapture(pointerId); } catch (_) {}
      event.preventDefault();
      event.stopPropagation();
    });

    handle.addEventListener('pointermove', move, { passive: false });
    handle.addEventListener('pointerup', stop);
    handle.addEventListener('pointercancel', stop);
    handle.addEventListener('lostpointercapture', (event) => {
      if (dragging) stop(event);
    });

    win.addEventListener('resize', () => {
      if (sidebar.getAttribute('aria-expanded') !== 'false') clampCurrent(sidebar, true);
    });
    if (win.visualViewport) {
      win.visualViewport.addEventListener('resize', () => {
        if (sidebar.getAttribute('aria-expanded') !== 'false') clampCurrent(sidebar, true);
      });
    }

    clampCurrent(sidebar, false);
  };

  const markContactPanel = () => {
    const selected = root.querySelector('.vessel-id');
    if (!selected) return;
    const column = selected.closest('[data-testid="stColumn"]');
    if (!column) return;
    column.classList.add(PANEL_CLASS);
    column.dataset.mieContactPanelBound = '1';

    const row = column.closest('[data-testid="stHorizontalBlock"]');
    if (row) row.classList.add(CANVAS_CLASS);
  };

  const scan = () => {
    injectStyle();
    const sidebar = root.querySelector(SIDEBAR);
    if (sidebar) bind(sidebar);
    markContactPanel();
  };

  const observer = new MutationObserver(() => scan());
  observer.observe(root.documentElement || root.body, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ['aria-expanded'],
  });

  scan();
})();
</script>
"""

    try:
        html = getattr(st, "html", None)
        if html is not None:
            try:
                html(controller_html, unsafe_allow_javascript=True)
                _FLOATING_SIDEBAR_PATCHED = True
                return
            except TypeError:
                pass

        import streamlit.components.v1 as components

        components.html(controller_html, height=1, scrolling=False)
        _FLOATING_SIDEBAR_PATCHED = True
    except Exception:
        _FLOATING_SIDEBAR_PATCHED = True


_patch_openwaters_pydeck_provider()
_install_floating_sidebar_controller()
