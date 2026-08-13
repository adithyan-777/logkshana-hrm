(function () {
  const root = document.documentElement;
  const modeKey = "htmx-template-theme-mode";
  const prefsKey = "htmx-template-ui-prefs";

  const defaults = {
    mode: "system",
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
    const legacyMode = safeGetItem(modeKey);
    if (legacyMode === "system" || legacyMode === "light" || legacyMode === "dark") {
      prefs.mode = legacyMode;
    }
    try {
      const raw = safeGetItem(prefsKey);
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
    if (key === "mode" && !["light", "dark", "system"].includes(value)) return;
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
    const prefs = readPrefs();
    const current = resolveTheme(prefs.mode);
    prefs.mode = current === "dark" ? "light" : "dark";
    applyPrefs(prefs);
  }

  function showStubToast(message) {
    window.dispatchEvent(
      new CustomEvent("showToast", { detail: { message, type: "info" } })
    );
    // Fallback if toast bus expects HX-style detail
    if (typeof window.showToast === "function") {
      window.showToast(message, "info");
    } else {
      const container = document.getElementById("toast-container");
      if (!container) return;
      const el = document.createElement("div");
      el.className = "toast toast--success";
      el.textContent = message;
      container.appendChild(el);
      setTimeout(() => {
        el.classList.add("is-leaving");
        setTimeout(() => el.remove(), 220);
      }, 2200);
    }
  }

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
        return;
      }

      const stub = e.target.closest("[data-toast]");
      if (stub) {
        e.preventDefault();
        showStubToast(stub.getAttribute("data-toast") || "Coming soon");
      }
    });

    // Keep prefs in sync when user collapses via sidebar control
    const collapsed = document.getElementById("sidebar-collapsed");
    if (collapsed) {
      collapsed.addEventListener("change", () => {
        const prefs = readPrefs();
        const nextMode = collapsed.checked ? "icon" : prefs.sidebarMode === "full" ? "full" : "default";
        if (prefs.sidebarMode !== nextMode) {
          prefs.sidebarMode = nextMode;
          applyPrefs(prefs);
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
