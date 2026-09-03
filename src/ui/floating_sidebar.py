"""Browser controller for the draggable operational sidebar."""

from __future__ import annotations

import streamlit.components.v1 as components


_CONTROLLER = r'''<script>
(() => {
  const KEY = "mie-floating-sidebar-position-v1";
  const HANDLE_ID = "mie-floating-sidebar-handle";
  const doc = window.parent.document;

  function install() {
    const sidebar = doc.querySelector('[data-testid="stSidebar"]');
    if (!sidebar) return false;

    sidebar.style.setProperty("position", "fixed", "important");
    sidebar.style.setProperty("bottom", "auto", "important");
    sidebar.style.setProperty("margin", "0", "important");
    sidebar.style.setProperty("z-index", "1000000", "important");
    sidebar.style.setProperty("width", "min(22rem, 88vw)", "important");

    if (!sidebar.dataset.miePositionLoaded) {
      let saved = null;
      try { saved = JSON.parse(window.localStorage.getItem(KEY) || "null"); } catch (_) {}
      const left = saved && Number.isFinite(saved.left) ? saved.left : 18;
      const top = saved && Number.isFinite(saved.top) ? saved.top : 72;
      sidebar.dataset.mieLeft = `${Math.max(0, left)}px`;
      sidebar.dataset.mieTop = `${Math.max(8, top)}px`;
      sidebar.dataset.miePositionLoaded = "1";
    }
    sidebar.style.setProperty("left", sidebar.dataset.mieLeft, "important");
    sidebar.style.setProperty("top", sidebar.dataset.mieTop, "important");

    let handle = sidebar.querySelector(`#${HANDLE_ID}`);
    if (handle) return true;

    handle = doc.createElement("div");
    handle.id = HANDLE_ID;
    handle.setAttribute("aria-label", "Drag operational sidebar");
    handle.title = "Drag to reposition";
    handle.innerHTML = "<span>⠿</span><span class='mie-drag-label'>DRAG PANEL</span>";
    sidebar.insertBefore(handle, sidebar.firstChild);

    if (!doc.getElementById("mie-floating-sidebar-style")) {
      const style = doc.createElement("style");
      style.id = "mie-floating-sidebar-style";
      style.textContent = `
        #${HANDLE_ID} { position:absolute; top:6px; left:8px; right:8px; height:24px; display:flex; align-items:center; justify-content:center; gap:6px; color:#79939b; background:rgba(13,28,36,.96); border:1px solid #1b3640; border-radius:3px; cursor:grab; user-select:none; z-index:1000002; box-sizing:border-box; font:500 10px 'IBM Plex Mono',monospace; letter-spacing:.12em; }
        #${HANDLE_ID}:hover { color:#35c2c9; border-color:#35c2c9; }
        #${HANDLE_ID}:active { cursor:grabbing; }
        #${HANDLE_ID} span:first-child { font-size:16px; line-height:1; }
        #${HANDLE_ID} .mie-drag-label { font-size:9px; }
        [data-testid="stSidebarContent"] { padding-top:2.25rem !important; }
      `;
      doc.head.appendChild(style);
    }

    let dragging = false, offsetX = 0, offsetY = 0;
    const point = (event) => { const s = event.touches ? event.touches[0] : event; return {x:s.clientX,y:s.clientY}; };
    const move = (event) => {
      if (!dragging) return;
      const p = point(event);
      const maxLeft = Math.max(0, window.parent.innerWidth - sidebar.offsetWidth - 8);
      const maxTop = Math.max(8, window.parent.innerHeight - 48);
      const left = Math.min(Math.max(0, p.x - offsetX), maxLeft);
      const top = Math.min(Math.max(8, p.y - offsetY), maxTop);
      sidebar.style.setProperty("left", `${left}px`, "important");
      sidebar.style.setProperty("top", `${top}px`, "important");
      sidebar.dataset.mieLeft = `${left}px`;
      sidebar.dataset.mieTop = `${top}px`;
      event.preventDefault();
    };
    const stop = () => {
      if (!dragging) return;
      dragging = false;
      handle.style.cursor = "grab";
      try { window.localStorage.setItem(KEY, JSON.stringify({left:parseFloat(sidebar.dataset.mieLeft),top:parseFloat(sidebar.dataset.mieTop)})); } catch (_) {}
    };
    handle.addEventListener("mousedown", (event) => { const r=sidebar.getBoundingClientRect(); dragging=true; offsetX=event.clientX-r.left; offsetY=event.clientY-r.top; handle.style.cursor="grabbing"; event.preventDefault(); });
    handle.addEventListener("touchstart", (event) => { const p=point(event), r=sidebar.getBoundingClientRect(); dragging=true; offsetX=p.x-r.left; offsetY=p.y-r.top; handle.style.cursor="grabbing"; event.preventDefault(); }, {passive:false});
    doc.addEventListener("mousemove", move, {passive:false});
    doc.addEventListener("mouseup", stop);
    doc.addEventListener("touchmove", move, {passive:false});
    doc.addEventListener("touchend", stop);
    return true;
  }

  install();
  const observer = new MutationObserver(install);
  observer.observe(doc.body, {childList:true, subtree:true});
  setTimeout(install,100);
  setTimeout(install,500);
})();
</script>'''


def mount_floating_sidebar() -> None:
    """Attach the draggable controller after the native sidebar is rendered."""
    components.html(_CONTROLLER, height=0, scrolling=False)
