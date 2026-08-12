(function () {
    const toggle = document.getElementById("sidebar-toggle");
    const overlay = document.getElementById("sidebar-overlay");
    const layout = document.querySelector(".app-layout");

    if (!toggle || !overlay || !layout) {
        return;
    }

    function closeSidebar() {
        layout.classList.remove("sidebar-open");
        overlay.hidden = true;
        toggle.setAttribute("aria-expanded", "false");
    }

    function openSidebar() {
        layout.classList.add("sidebar-open");
        overlay.hidden = false;
        toggle.setAttribute("aria-expanded", "true");
    }

    toggle.addEventListener("click", function () {
        if (layout.classList.contains("sidebar-open")) {
            closeSidebar();
        } else {
            openSidebar();
        }
    });

    overlay.addEventListener("click", closeSidebar);
})();
