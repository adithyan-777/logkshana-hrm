(function () {
  // Flatpickr-enhanced date / time / datetime fields.
  // Replaces native browser calendars so UI matches ITTISAL tokens + Done closes.

  const SELECTOR =
    'input[type="date"], input[type="datetime-local"], input[type="time"], input.has-flatpickr';

  function addFooter(fp) {
    if (fp.calendarContainer.querySelector(".flatpickr-footer")) return;

    const footer = document.createElement("div");
    footer.className = "flatpickr-footer";
    footer.innerHTML =
      '<button type="button" class="flatpickr-footer__btn flatpickr-footer__btn--muted" data-fp-action="clear">Clear</button>' +
      '<button type="button" class="flatpickr-footer__btn flatpickr-footer__btn--muted" data-fp-action="today">Today</button>' +
      '<span class="flatpickr-footer__spacer"></span>' +
      '<button type="button" class="flatpickr-footer__btn flatpickr-footer__btn--primary" data-fp-action="done">Done</button>';

    footer.addEventListener("click", function (event) {
      const btn = event.target.closest("[data-fp-action]");
      if (!btn) return;
      const action = btn.getAttribute("data-fp-action");
      if (action === "clear") {
        fp.clear();
        fp.input.dispatchEvent(new Event("input", { bubbles: true }));
        fp.input.dispatchEvent(new Event("change", { bubbles: true }));
      } else if (action === "today") {
        const now = new Date();
        if (fp.config.noCalendar && fp.config.enableTime) {
          fp.setDate(now, true);
        } else if (fp.config.enableTime) {
          fp.setDate(now, true);
        } else {
          fp.setDate(new Date(now.getFullYear(), now.getMonth(), now.getDate()), true);
        }
      } else if (action === "done") {
        fp.close();
      }
    });

    fp.calendarContainer.appendChild(footer);
  }

  // Prefer left-edge alignment with the input. Flatpickr's default "auto"
  // flips to right-align near the viewport edge (common in the right drawer),
  // which looks like a mid-field offset.
  function positionCalendar(fp) {
    const cal = fp.calendarContainer;
    const anchor = fp._positionElement || fp._input;
    if (!cal || !anchor) return;

    const rect = anchor.getBoundingClientRect();
    const gap = 4;
    const margin = 8;
    const calW = cal.offsetWidth || 308;
    const calH = cal.offsetHeight || 0;

    let left = rect.left;
    let top = rect.bottom + gap;

    if (top + calH > window.innerHeight - margin && rect.top - calH - gap >= margin) {
      top = rect.top - calH - gap;
      cal.classList.add("arrowBottom");
      cal.classList.remove("arrowTop");
    } else {
      cal.classList.add("arrowTop");
      cal.classList.remove("arrowBottom");
    }

    if (left + calW > window.innerWidth - margin) {
      left = Math.max(margin, window.innerWidth - calW - margin);
    }
    if (left < margin) left = margin;

    cal.style.position = "fixed";
    cal.style.left = left + "px";
    cal.style.top = top + "px";
    cal.style.right = "auto";
    cal.classList.remove("rightMost", "centerMost", "arrowLeft", "arrowCenter", "arrowRight");
  }

  function optionsFor(input) {
    const originalType = input.dataset.fpType || input.getAttribute("type") || "date";
    const isTime = originalType === "time";
    const isDateTime = originalType === "datetime-local";

    const opts = {
      allowInput: true,
      disableMobile: true,
      animate: false,
      clickOpens: true,
      appendTo: document.body,
      position: positionCalendar,
      onReady: function (_dates, _str, fp) {
        addFooter(fp);
      },
      onOpen: function (_dates, _str, fp) {
        addFooter(fp);
        // Footer changes height — re-measure after layout.
        window.requestAnimationFrame(function () {
          positionCalendar(fp);
        });
      },
    };

    if (isDateTime) {
      opts.enableTime = true;
      opts.time_24hr = true;
      opts.dateFormat = "Y-m-d\\TH:i";
      opts.defaultHour = 9;
      opts.defaultMinute = 0;
    } else if (isTime) {
      opts.enableTime = true;
      opts.noCalendar = true;
      opts.time_24hr = true;
      opts.dateFormat = "H:i";
    } else {
      opts.dateFormat = "Y-m-d";
    }

    return opts;
  }

  function enhanceInput(input) {
    if (!input || input.disabled || input.readOnly) return;
    if (input._flatpickr) return;
    if (input.closest(".flatpickr-calendar")) return;

    const type = input.getAttribute("type") || "text";
    if (!["date", "datetime-local", "time", "text"].includes(type) && !input.classList.contains("has-flatpickr")) {
      return;
    }
    if (type === "text" && !input.classList.contains("has-flatpickr") && !input.dataset.fpType) {
      return;
    }

    if (!input.dataset.fpType && (type === "date" || type === "datetime-local" || type === "time")) {
      input.dataset.fpType = type;
    }

    // Avoid native picker chrome; keep submitted value format.
    input.setAttribute("type", "text");
    input.setAttribute("autocomplete", "off");
    input.classList.add("has-flatpickr");

    window.flatpickr(input, optionsFor(input));
  }

  function initDatePickers(root) {
    if (!window.flatpickr) return;
    const scope = root && root.querySelectorAll ? root : document;
    const nodes = scope.querySelectorAll
      ? scope.querySelectorAll(SELECTOR)
      : [];
    nodes.forEach(enhanceInput);

    // If root itself is an input
    if (root && root.matches && root.matches(SELECTOR)) {
      enhanceInput(root);
    }
  }

  window.initDatePickers = initDatePickers;

  function boot() {
    initDatePickers(document);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }

  document.body.addEventListener("htmx:afterSettle", function (event) {
    const target = event && event.detail && event.detail.target;
    initDatePickers(target || document);
  });

  document.body.addEventListener("htmx:afterSwap", function (event) {
    const target = event && event.detail && event.detail.target;
    initDatePickers(target || document);
  });
})();
