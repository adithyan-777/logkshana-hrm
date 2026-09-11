(function () {
  const root = document.documentElement;
  const modeKey = "logkshana-theme-mode";
  const prefsKey = "logkshana-ui-prefs";

  const defaults = {
    mode: "light",
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

  function getSystemTheme() {
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }

  function readPrefs() {
    const prefs = { ...defaults };
    const legacyMode = safeGetItem(modeKey) || safeGetItem("htmx-template-theme-mode");
    if (legacyMode === "light") {
      prefs.mode = legacyMode;
    }
    try {
      const raw = safeGetItem(prefsKey) || safeGetItem("htmx-template-ui-prefs");
      if (raw) {
        const parsed = JSON.parse(raw);
        if (parsed && typeof parsed === "object") {
          Object.keys(defaults).forEach((key) => {
            if (parsed[key] != null) prefs[key] = parsed[key];
          });
        }
      }
    } catch (_) {}
    if (prefs.mode !== "light") prefs.mode = "light";
    return prefs;
  }

  function writePrefs(prefs) {
    safeSetItem(modeKey, prefs.mode);
    safeSetItem(prefsKey, JSON.stringify({
      layout: prefs.layout,
      scale: prefs.scale,
      sidebarVariant: prefs.sidebarVariant,
      sidebarMode: prefs.sidebarMode,
    }));
  }

  function resolveTheme(mode) {
    if (mode === "light" || mode === "dark") return mode;
    return getSystemTheme();
  }

  function updateSegButtons(prefs) {
    document.querySelectorAll("[data-ui-set][data-ui-value]").forEach((btn) => {
      const key = btn.dataset.uiSet;
      const value = btn.dataset.uiValue;
      const active = prefs[key] === value;
      btn.classList.toggle("is-active", active);
      btn.setAttribute("aria-checked", active ? "true" : "false");
    });

    document.querySelectorAll(".theme-toggle__btn[data-theme-set]").forEach((btn) => {
      btn.classList.toggle("is-active", btn.dataset.themeSet === prefs.mode);
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
    root.setAttribute("data-theme", resolveTheme(prefs.mode));
    root.setAttribute("data-layout", prefs.layout);
    root.setAttribute("data-scale", prefs.scale);
    root.setAttribute("data-sidebar-variant", prefs.sidebarVariant);
    root.setAttribute("data-sidebar-mode", prefs.sidebarMode);

    applySidebarMode(prefs.sidebarMode);
    updateSegButtons(prefs);
    if (persist) writePrefs(prefs);

    window.dispatchEvent(
      new CustomEvent("themechange", {
        detail: { theme: resolveTheme(prefs.mode), prefs: { ...prefs } },
      })
    );
  }

  function setPref(key, value) {
    const prefs = readPrefs();
    if (!(key in defaults)) return;
    if (key === "mode" && value !== "light") return;
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

  function quickToggleTheme() {
    return;
  }

  window.LogkshanaTheme = {
    defaults,
    readPrefs,
    applyPrefs,
    setPref,
    resetPrefs,
    quickToggleTheme,
    resolveTheme,
  };

  function initTheme() {
    const prefs = readPrefs();
    applyPrefs(prefs, { persist: true });

    window
      .matchMedia("(prefers-color-scheme: dark)")
      .addEventListener("change", () => {
        const current = readPrefs();
        if (current.mode === "system") applyPrefs(current, { persist: false });
      });

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
        return;
      }

      if (e.target.closest("[data-theme-quick]")) {
        e.preventDefault();
        quickToggleTheme();
        return;
      }

      const legacy = e.target.closest(".theme-toggle__btn[data-theme-set]");
      if (legacy) {
        setPref("mode", legacy.dataset.themeSet);
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
