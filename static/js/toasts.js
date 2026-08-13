(function () {
  const container = document.getElementById("toast-container");

  function showToast(detail) {
    if (!container) return;
    const { message = "Done", type = "success" } = detail || {};
    const toast = document.createElement("div");
    toast.className = `toast toast--${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => {
      toast.classList.add("is-leaving");
      setTimeout(() => toast.remove(), 220);
    }, 3200);
  }

  document.body.addEventListener("showToast", (e) => showToast(e.detail));

  document.body.addEventListener("htmx:afterOnLoad", (e) => {
    const trigger = e.detail.xhr.getResponseHeader("HX-Trigger");
    if (!trigger) return;
    try {
      const data = JSON.parse(trigger);
      if (data.showToast) showToast(data.showToast);
      if (data.closeModal) closeModal();
    } catch (_) {}
  });

  function openModal() {
    document.getElementById("app-modal")?.classList.add("is-open");
  }

  function closeModal() {
    document.getElementById("app-modal")?.classList.remove("is-open");
    const body = document.getElementById("modal-body");
    if (body) body.innerHTML = "";
  }

  document.body.addEventListener("closeModal", closeModal);

  document.body.addEventListener("htmx:afterSwap", (e) => {
    if (e.detail.target?.id === "modal-body") openModal();
  });

  document.getElementById("modal-close-btn")?.addEventListener("click", closeModal);
  document.addEventListener("click", (e) => {
    if (e.target.closest("[data-modal-close]")) closeModal();
  });
  document.getElementById("app-modal")?.addEventListener("click", (e) => {
    if (e.target.classList.contains("admin-modal__backdrop")) closeModal();
  });
})();
