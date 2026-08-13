(function () {
  function closeAll(except) {
    document.querySelectorAll(".dropdown-menu.is-open").forEach((menu) => {
      if (menu !== except) menu.classList.remove("is-open");
    });
  }

  function closeDetails(selector, except) {
    document.querySelectorAll(selector).forEach((menu) => {
      if (menu !== except) menu.removeAttribute("open");
    });
  }

  const DETAILS = "details.profile-menu[open], details.theme-customizer[open], details.notify-menu[open]";

  document.addEventListener("click", (e) => {
    const toggle = e.target.closest("[data-dropdown-toggle]");
    if (toggle) {
      e.stopPropagation();
      const menu = toggle.closest(".dropdown")?.querySelector(".dropdown-menu");
      if (menu) {
        const willOpen = !menu.classList.contains("is-open");
        closeAll(menu);
        menu.classList.toggle("is-open", willOpen);
      }
      return;
    }

    const profile = e.target.closest("details.profile-menu");
    const customizer = e.target.closest("details.theme-customizer");
    const notify = e.target.closest("details.notify-menu");

    if (profile) {
      closeDetails(DETAILS, profile);
      return;
    }
    if (customizer) {
      closeDetails(DETAILS, customizer);
      return;
    }
    if (notify) {
      closeDetails(DETAILS, notify);
      return;
    }

    if (!e.target.closest(".dropdown-menu")) closeAll(null);
    closeDetails(DETAILS, null);
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      closeAll(null);
      closeDetails(DETAILS, null);
    }
  });
})();
