// Show/hide password fields paired with [data-password-toggle] buttons.
// Rebinds on Turbo:load/Turbolinks:load if present, and on DOMContentLoaded otherwise.
(function () {
  function bind(button) {
    if (button.dataset.passwordToggleBound) return;
    button.dataset.passwordToggleBound = "true";

    var wrapper = button.closest(".password-wrapper");
    var input = wrapper ? wrapper.querySelector("input") : null;
    if (!input) return;
    var icon = button.querySelector("i");

    function show() {
      input.type = "text";
      button.setAttribute("aria-pressed", "true");
      button.setAttribute("aria-label", "Hide password");
      if (icon) icon.classList.replace("bx-eye", "bx-eye-slash");
    }

    function hide() {
      input.type = "password";
      button.setAttribute("aria-pressed", "false");
      button.setAttribute("aria-label", "Show password");
      if (icon) icon.classList.replace("bx-eye-slash", "bx-eye");
    }

    button.addEventListener("click", function () {
      if (input.type === "password") {
        show();
        input.focus();
      } else {
        hide();
        input.focus();
      }
    });
  }

  function init() {
    document.querySelectorAll("[data-password-toggle]").forEach(bind);
  }

  if (window.Turbo || window.Turbolinks) {
    document.addEventListener(
      (window.Turbo ? "turbo:load" : "turbolinks:load"),
      init
    );
  } else {
    document.addEventListener("DOMContentLoaded", init);
    init();
  }
})();
