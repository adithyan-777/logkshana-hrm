(function () {
  // Light theme only — there are no color modes. This file persists UI prefs
  // (layout / scale / sidebar) and reflects them as data-* attributes.
  const root = document.documentElement;
  const prefsKey = "ittisal-ui-prefs";

  const defaults = {
    layout: "compact",
    scale: "md",
    sidebarVariant: "inset",
    sidebarMode: "default",
  };

  function safeGetItem(key) {
    try {
      return window.localStorage.getItem(key);
    } catch (_) {
      return null;
    }
  }

  function safeSetItem(key, value) {
    try {
      window.localStorage.setItem(key, value);
    } catch (_) {}
  }

  function safeRemoveItem(key) {
    try {
      window.localStorage.removeItem(key);
    } catch (_) {}
  }

  function readPrefs() {
    const prefs = { ...defaults };
    try {
      const raw = safeGetItem(prefsKey) || safeGetItem("logkshana-ui-prefs") || safeGetItem("htmx-template-ui-prefs");
      if (raw) {
        const parsed = JSON.parse(raw);
        if (parsed && typeof parsed === "object") {
          Object.keys(defaults).forEach((key) => {
            if (parsed[key] != null) prefs[key] = parsed[key];
          });
        }
      }
    } catch (_) {}
    return prefs;
  }

  function writePrefs(prefs) {
    safeSetItem(prefsKey, JSON.stringify({
      layout: prefs.layout,
      scale: prefs.scale,
      sidebarVariant: prefs.sidebarVariant,
      sidebarMode: prefs.sidebarMode,
    }));
  }

  function updateSegButtons(prefs) {
    document.querySelectorAll("[data-ui-set][data-ui-value]").forEach((btn) => {
      const key = btn.dataset.uiSet;
      const value = btn.dataset.uiValue;
      const active = prefs[key] === value;
      btn.classList.toggle("is-active", active);
      btn.setAttribute("aria-checked", active ? "true" : "false");
    });
  }

  function applySidebarMode(mode) {
    const collapsed = document.getElementById("sidebar-collapsed");
    if (!collapsed) return;
    if (mode === "icon") {
      collapsed.checked = true;
    } else {
      collapsed.checked = false;
    }
  }

  function applyPrefs(prefs, { persist = true } = {}) {
    root.setAttribute("data-layout", prefs.layout);
    root.setAttribute("data-scale", prefs.scale);
    root.setAttribute("data-sidebar-variant", prefs.sidebarVariant);
    root.setAttribute("data-sidebar-mode", prefs.sidebarMode);

    applySidebarMode(prefs.sidebarMode);
    updateSegButtons(prefs);
    if (persist) writePrefs(prefs);
  }

  function setPref(key, value) {
    const prefs = readPrefs();
    if (!(key in defaults)) return;
    if (key === "layout" && !["compact", "full"].includes(value)) return;
    if (key === "scale" && !["sm", "md", "lg"].includes(value)) return;
    if (key === "sidebarVariant" && !["default", "inset"].includes(value)) return;
    if (key === "sidebarMode" && !["default", "icon", "full"].includes(value)) return;
    prefs[key] = value;
    applyPrefs(prefs);
  }

  function resetPrefs() {
    applyPrefs({ ...defaults });
  }

  window.IttisalTheme = {
    defaults,
    readPrefs,
    applyPrefs,
    setPref,
    resetPrefs,
  };

  function initTheme() {
    // Drop retired color-mode keys left by older versions.
    safeRemoveItem("logkshana-theme-mode");
    safeRemoveItem("htmx-template-theme-mode");

    const prefs = readPrefs();
    applyPrefs(prefs, { persist: true });

    document.addEventListener("click", (e) => {
      if (window.Alpine) return;

      const setBtn = e.target.closest("[data-ui-set][data-ui-value]");
      if (setBtn) {
        e.preventDefault();
        setPref(setBtn.dataset.uiSet, setBtn.dataset.uiValue);
        return;
      }

      if (e.target.closest("[data-ui-reset]")) {
        e.preventDefault();
        resetPrefs();
      }
    });

    const collapsed = document.getElementById("sidebar-collapsed");
    if (collapsed) {
      collapsed.addEventListener("change", () => {
        const prefs = readPrefs();
        const nextMode = collapsed.checked ? "icon" : prefs.sidebarMode === "full" ? "full" : "default";
        if (prefs.sidebarMode !== nextMode) {
          prefs.sidebarMode = nextMode;
          applyPrefs(prefs);
          if (window.Alpine) window.Alpine.store("theme").refresh();
        }
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initTheme);
  } else {
    initTheme();
  }
})();
