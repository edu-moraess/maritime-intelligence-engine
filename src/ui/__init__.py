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
    """Install a persistent browser controller for free 2D sidebar positioning.

    Streamlit's native sidebar remains the widget host. The controller only
    changes its presentation in the browser: it forces an overlay geometry,
    adds a dedicated drag handle, survives sidebar DOM replacement, and keeps
    the operator's position in localStorage. No Streamlit widget is replaced.
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
  const GLOBAL_KEY = '__mieFloatingSidebarControllerV2';

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
      @media (max-width: 760px) {
        [data-testid="stSidebar"].mie-floating-sidebar {
          width: min(19rem, 92vw) !important;
          height: min(calc(100vh - 16px), 760px) !important;
          max-height: calc(100vh - 16px) !important;
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

  const scan = () => {
    injectStyle();
    const sidebar = root.querySelector(SIDEBAR);
    if (sidebar) bind(sidebar);
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
