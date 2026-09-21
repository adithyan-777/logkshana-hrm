(function () {
  const SECTION_PREFIXES = {
    dashboard: { exact: "/" },
    employees: { prefix: "/employees/" },
    attendance: { prefix: "/attendance/" },
    leave: { prefix: "/leave/" },
    schedule: { prefix: "/schedule/" },
    reports: { prefix: "/reports/" },
  };

  function pathMatches(path, rule) {
    if (rule.exact) return path === rule.exact;
    if (rule.prefix) return path === rule.prefix.slice(0, -1) || path.startsWith(rule.prefix);
    return false;
  }

  function readCommands() {
    const el = document.getElementById("command-palette-data");
    if (!el) return [];
    try {
      const data = JSON.parse(el.textContent);
      return Array.isArray(data) ? data : [];
    } catch (_) {
      return [];
    }
  }

  function titleFromXhr(xhr) {
    const html = xhr && xhr.responseText;
    if (!html) return "";
    const match = html.match(/<title[^>]*>([^<]*)<\/title>/i);
    return match ? match[1].trim() : "";
  }

  function isSpaTarget(detail) {
    const target = detail && (detail.target || detail.elt);
    return Boolean(target && target.id === "spa-view");
  }

  function isBoosted(detail) {
    return Boolean(
      detail &&
        (detail.boosted || (detail.requestConfig && detail.requestConfig.boosted))
    );
  }

  function isSpaNav(detail) {
    return isBoosted(detail) || isSpaTarget(detail);
  }

  function spaEl() {
    return document.getElementById("spa-view");
  }

  function configureBoostedNav(detail) {
    if (!isBoosted(detail)) return;
    const spa = spaEl();
    if (!spa) return;
    detail.target = spa;
    const config = detail.requestConfig;
    if (!config) return;
    config.target = spa;
    config.select = "#spa-view";
    config.swapStyle = "outerHTML";
    config.swapOverride = "outerHTML show:none settle:120ms";
  }

  function extractSpaView(html) {
    if (!html || html.indexOf("spa-view") === -1) return null;
    try {
      const doc = new DOMParser().parseFromString(html, "text/html");
      const next = doc.getElementById("spa-view");
      return next ? next.outerHTML : null;
    } catch (_) {
      return null;
    }
  }

  function closeMobileSidebar() {
    const mobile = document.getElementById("sidebar-mobile");
    if (mobile) mobile.checked = false;
  }

  function syncNavActive(path) {
    document.querySelectorAll("[data-nav-match]").forEach((el) => {
      const key = el.getAttribute("data-nav-match");
      const rule = SECTION_PREFIXES[key];
      el.classList.toggle("is-active", Boolean(rule && pathMatches(path, rule)));
    });
  }

  function themeApi() {
    return window.IttisalTheme || null;
  }

  document.addEventListener("alpine:init", () => {
    const Alpine = window.Alpine;

    Alpine.store("spa", {
      path: window.location.pathname,
      loading: false,
      commands: readCommands(),
      sync() {
        this.path = window.location.pathname;
        this.commands = readCommands();
        syncNavActive(this.path);
      },
      isSection(name) {
        const rule = SECTION_PREFIXES[name];
        return Boolean(rule && pathMatches(this.path, rule));
      },
    });

    Alpine.store("ui", {
      menu: null,
      commandOpen: false,
      toasts: [],
      modalOpen: false,
      modalTitle: "Dialog",
      modalSize: "default",
      toggleMenu(name) {
        this.menu = this.menu === name ? null : name;
      },
      closeMenus() {
        this.menu = null;
      },
      openCommand() {
        this.closeMenus();
        this.commandOpen = true;
      },
      closeCommand() {
        this.commandOpen = false;
      },
      toast(message, type) {
        const id = Date.now() + Math.random();
        this.toasts.push({ id, message: message || "Done", type: type || "success" });
        window.setTimeout(() => this.dismiss(id), 3200);
      },
      dismiss(id) {
        this.toasts = this.toasts.filter((item) => item.id !== id);
      },
      openModal(title, size) {
        if (title) this.modalTitle = title;
        if (size) this.modalSize = size;
        this.modalOpen = true;
      },
      closeModal() {
        this.modalOpen = false;
        this.modalSize = "default";
        const body = document.getElementById("modal-body");
        if (body) body.innerHTML = "";
      },
    });

    Alpine.store("theme", {
      prefs: themeApi() ? themeApi().readPrefs() : { mode: "system", layout: "compact", scale: "md", sidebarVariant: "inset", sidebarMode: "default" },
      get resolved() {
        const api = themeApi();
        if (api && api.resolveTheme) return api.resolveTheme(this.prefs.mode);
        if (typeof window !== "undefined" && window.matchMedia) {
          try {
            if (this.prefs.mode === "dark") return "dark";
            if (this.prefs.mode === "light") return "light";
            return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
          } catch (_) {}
        }
        return this.prefs.mode === "dark" ? "dark" : "light";
      },
      set(key, value) {
        const api = themeApi();
        if (api) {
          api.setPref(key, value);
          this.prefs = api.readPrefs();
          return;
        }
        this.prefs = { ...this.prefs, [key]: value };
      },
      reset() {
        const api = themeApi();
        if (api) {
          api.resetPrefs();
          this.prefs = api.readPrefs();
        }
      },
      toggle() {
        const api = themeApi();
        if (api && api.quickToggleTheme) {
          api.quickToggleTheme();
          this.prefs = api.readPrefs();
          return;
        }
        this.prefs = { ...this.prefs, mode: this.resolved === "dark" ? "light" : "dark" };
      },
      refresh() {
        const api = themeApi();
        if (api) this.prefs = api.readPrefs();
      },
    });

    Alpine.data("commandPalette", () => ({
      query: "",
      index: 0,
      get items() {
        const q = this.query.trim().toLowerCase();
        const all = Alpine.store("spa").commands;
        if (!q) return all;
        return all.filter((item) => {
          const haystack = [item.title, item.subtitle, item.group, item.url]
            .filter(Boolean)
            .join(" ")
            .toLowerCase();
          return haystack.includes(q);
        });
      },
      get grouped() {
        const groups = [];
        const seen = new Map();
        this.items.forEach((item) => {
          const name = item.group || "Pages";
          if (!seen.has(name)) {
            const group = { name, items: [] };
            seen.set(name, group);
            groups.push(group);
          }
          seen.get(name).items.push(item);
        });
        return groups;
      },
      open() {
        this.query = "";
        this.index = 0;
        Alpine.store("ui").openCommand();
        this.$nextTick(() => this.$refs.query && this.$refs.query.focus());
      },
      close() {
        Alpine.store("ui").closeCommand();
        this.query = "";
        this.index = 0;
      },
      move(delta) {
        const count = this.items.length;
        if (!count) {
          this.index = 0;
          return;
        }
        this.index = (this.index + delta + count) % count;
        this.$nextTick(() => {
          const active = this.$refs.list && this.$refs.list.querySelector("[data-active='true']");
          if (active) active.scrollIntoView({ block: "nearest" });
        });
      },
      choose(item) {
        if (!item) item = this.items[this.index];
        if (!item || !item.url) return;
        this.close();
        const anchor = document.createElement("a");
        anchor.href = item.url;
        document.body.appendChild(anchor);
        if (window.htmx) window.htmx.process(anchor);
        anchor.click();
        anchor.remove();
      },
    }));
  });

  document.addEventListener("keydown", (event) => {
    const ui = window.Alpine && window.Alpine.store("ui");
    if (!ui) return;

    const metaK = (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k";
    if (metaK) {
      event.preventDefault();
      document.dispatchEvent(new CustomEvent("open-command-palette", { bubbles: true }));
      return;
    }

    if (event.key === "Escape") {
      if (ui.commandOpen) {
        ui.closeCommand();
        return;
      }
      if (ui.modalOpen) {
        ui.closeModal();
        return;
      }
      ui.closeMenus();
    }
  });

  document.body.addEventListener("showToast", (event) => {
    const detail = event.detail || {};
    if (window.Alpine) window.Alpine.store("ui").toast(detail.message, detail.type);
  });

  document.body.addEventListener("closeModal", () => {
    if (window.Alpine) window.Alpine.store("ui").closeModal();
  });

  document.body.addEventListener("htmx:beforeRequest", (event) => {
    configureBoostedNav(event.detail);
    if (!isSpaNav(event.detail) || !window.Alpine) return;
    const spa = window.Alpine.store("spa");
    const ui = window.Alpine.store("ui");
    spa.loading = true;
    ui.closeMenus();
    ui.closeCommand();
    closeMobileSidebar();
  });

  document.body.addEventListener("htmx:afterOnLoad", (event) => {
    const xhr = event.detail && event.detail.xhr;
    if (!xhr) return;
    const trigger = xhr.getResponseHeader("HX-Trigger");
    if (!trigger || !window.Alpine) return;
    // htmx already dispatches HX-Trigger events (caught by the showToast /
    // closeModal listeners above); only handle legacy payloads it cannot
    // express, e.g. a bare "closeModal" string header.
    if (trigger === "closeModal") {
      window.Alpine.store("ui").closeModal();
    }
  });

  document.body.addEventListener("htmx:beforeSwap", (event) => {
    const detail = event.detail;
    if (isBoosted(detail)) {
      const spa = spaEl();
      if (spa) detail.target = spa;
      const extracted = extractSpaView(detail.serverResponse);
      if (extracted) {
        detail.serverResponse = extracted;
        if (detail.requestConfig) detail.requestConfig.select = "";
      }
      if (window.Alpine && spa && typeof window.Alpine.destroyTree === "function") {
        window.Alpine.destroyTree(spa);
      }
      return;
    }

    const target = detail && detail.target;
    if (window.Alpine && target && target.id === "spa-view" && typeof window.Alpine.destroyTree === "function") {
      window.Alpine.destroyTree(target);
    }
  });

  document.body.addEventListener("htmx:afterSwap", (event) => {
    const elt = event.detail && event.detail.elt;
    if (window.Alpine && elt) {
      window.Alpine.initTree(elt);
    }
    if (elt && elt.id === "modal-body" && window.Alpine) {
      window.Alpine.store("ui").openModal();
    }
  });

  document.body.addEventListener("htmx:afterSettle", (event) => {
    if (!window.Alpine) return;
    const spa = window.Alpine.store("spa");
    if (isSpaNav(event.detail)) {
      spa.loading = false;
      spa.sync();
      const title = titleFromXhr(event.detail.xhr);
      if (title) document.title = title;
      window.Alpine.store("theme").refresh();
    }
  });

  document.body.addEventListener("htmx:responseError", (event) => {
    if (!window.Alpine) return;
    window.Alpine.store("spa").loading = false;
    if (isSpaNav(event.detail)) {
      window.Alpine.store("ui").toast("Could not load that page", "error");
    }
  });

  document.body.addEventListener("htmx:historyRestore", (event) => {
    if (!window.Alpine) return;
    window.Alpine.store("spa").loading = false;
    window.Alpine.store("spa").sync();
    const elt = event.detail && event.detail.elt;
    if (elt) window.Alpine.initTree(elt);
  });

  document.body.addEventListener("htmx:pushedIntoHistory", () => {
    if (window.Alpine) window.Alpine.store("spa").sync();
  });

  function openDrawerFromQuery() {
    const params = new URLSearchParams(window.location.search);
    const url = params.get("drawer");
    if (!url || !window.htmx || !window.Alpine) return;

    const title = params.get("drawer_title") || "Dialog";
    const size = params.get("drawer_size") || "default";
    params.delete("drawer");
    params.delete("drawer_title");
    params.delete("drawer_size");
    const qs = params.toString();
    const clean = `${window.location.pathname}${qs ? `?${qs}` : ""}${window.location.hash || ""}`;
    window.history.replaceState(window.history.state, "", clean);

    window.Alpine.store("ui").openModal(title, size);
    window.htmx.ajax("GET", url, { target: "#modal-body", swap: "innerHTML" });
  }

  document.addEventListener("alpine:initialized", () => {
    openDrawerFromQuery();
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      if (window.Alpine) window.Alpine.store("spa").sync();
    });
  } else if (window.Alpine) {
    window.Alpine.store("spa").sync();
  }
})();
