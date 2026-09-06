/* Widget behavior enhances native controls; server responses remain authoritative. */
(function () {
  if (window.networklyWidgetsReady) return;
  window.networklyWidgetsReady = true;
  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
  var stage = "all", stagePath = location.pathname, restoreStageFocus = false;
  var pending = new WeakMap();
  var openedByUser = new WeakSet();
  var widgetSelector = ".act-card,.contact-card,.rolerow,.apps-lens-row,.cd-card,.set-card,.as-composer";

  function applyStage(announce) {
    var root = document.getElementById("apps-body");
    if (!root) { stage = "all"; return; }
    if (stagePath !== location.pathname) { stage = "all"; stagePath = location.pathname; }
    var filters = root.querySelectorAll("[data-stage-filter]");
    var chosen = Array.from(filters).find(function (b) { return b.dataset.stageFilter === stage; });
    if (!chosen) stage = "all";
    filters.forEach(function (button) {
      button.disabled = false;
      button.setAttribute("aria-pressed", String(button.dataset.stageFilter === stage));
    });
    var shown = 0;
    root.querySelectorAll("[data-apps-lens]").forEach(function (group) {
      var rows = group.querySelectorAll("[data-app-stage]"), visible = 0;
      rows.forEach(function (row) {
        row.hidden = stage !== "all" && row.dataset.appStage !== stage;
        if (!row.hidden) visible++;
      });
      shown += visible;
      group.hidden = stage !== "all" && visible === 0;
      var count = group.querySelector("[data-apps-lens-count]");
      if (count) {
        if (!count.dataset.original) count.dataset.original = count.textContent;
        count.textContent = stage === "all" ? count.dataset.original : visible + " shown";
      }
    });
    var empty = root.querySelector("[data-apps-filter-empty]");
    if (empty) empty.hidden = stage === "all" || shown > 0;
    var status = root.querySelector("[data-apps-filter-status]");
    if (status) {
      status.hidden = stage === "all" && !announce;
      status.textContent = stage === "all" ? "Showing all " + shown + " roles." :
        "Showing " + shown + " " + (chosen ? chosen.dataset.stageLabel.toLowerCase() : "matching") + " role" + (shown === 1 ? "" : "s") + ". Select All roles to clear.";
    }
    if (restoreStageFocus) {
      var active = root.querySelector('.apps-funnel [data-stage-filter="' + stage + '"]');
      if (active && (document.activeElement === document.body || !document.activeElement)) active.focus({ preventScroll: true });
      restoreStageFocus = false;
    }
  }

  // Preview complete rows, never a pixel slice through a title or action.
  // Nothing is hidden until enhancement runs, so no-JS readers get every row.
  function applyFirmPreview(panel) {
    var list = panel.querySelector(".firmcol-scroll");
    var button = panel.querySelector("[data-widget-expand]");
    if (!list || !button) return;
    var open = panel.classList.contains("is-expanded"), row = 0, remainder = 0, conceal = false;
    var previewCount = panel.classList.contains("firmcol--picked") ? 4 : 3;
    Array.from(list.children).forEach(function (child) {
      if (child.matches(".rolerow,.rolerow-dismissed")) {
        row++;
        conceal = row > previewCount;
        if (conceal) remainder++;
        child.hidden = conceal && !open;
      } else if (child.matches(".variant-fold")) {
        // A programme's other locations travel with their complete lead row.
        if (conceal) remainder += child.querySelectorAll(".rolerow").length;
        child.hidden = conceal && !open;
      }
    });
    button.hidden = remainder === 0;
    button.setAttribute("aria-expanded", String(open));
    if (!button.dataset.originalLabel) button.dataset.originalLabel = button.getAttribute("aria-label");
    button.setAttribute("aria-label", open ? button.dataset.originalLabel.replace(/^Expand/, "Collapse") : button.dataset.originalLabel);
    button.querySelector("span").textContent = open ? "Show fewer roles" : "Show " + remainder + " more role" + (remainder === 1 ? "" : "s");
  }
  function setup() {
    document.querySelectorAll(".firmcol").forEach(applyFirmPreview);
    applyStage(false);
  }
  function reveal(element) {
    if (!element || reduced.matches || !element.animate) return;
    element.animate([{ opacity: .55, transform: "translateY(5px)" }, { opacity: 1, transform: "translateY(0)" }],
      { duration: 200, easing: "cubic-bezier(.16,1,.3,1)" });
  }
  document.addEventListener("click", function (event) {
    // Pointer clicks do not focus summaries in every browser. Track intent
    // directly so keyboard and pointer disclosures receive the same feedback.
    var summary = event.target.closest("summary");
    if (summary && summary.parentElement.tagName === "DETAILS") {
      openedByUser.add(summary.parentElement);
    }
    var disclosureButton = event.target.closest("[data-widget-disclosure]");
    if (disclosureButton) {
      var controlled = document.getElementById(disclosureButton.getAttribute("aria-controls"));
      if (controlled && controlled.tagName === "DETAILS") openedByUser.add(controlled);
    }
    var filter = event.target.closest("[data-stage-filter]");
    if (filter && !filter.disabled) {
      stage = filter.dataset.stageFilter;
      applyStage(true);
      reveal(document.querySelector(".apps-lenses"));
    }
    var expand = event.target.closest("[data-widget-expand]");
    if (expand) {
      var panel = expand.closest(".firmcol");
      if (!panel) return;
      var open = panel.classList.toggle("is-expanded");
      applyFirmPreview(panel);
      reveal(panel.querySelector(".firmcol-scroll"));
      if (!open && panel.getBoundingClientRect().top < 0) panel.scrollIntoView({ block: "start", behavior: "instant" });
    }
  });
  // Run only for user-opened disclosures, never choreograph the initial page.
  document.addEventListener("toggle", function (event) {
    var disclosure = event.target;
    if (!disclosure.matches("details") || !openedByUser.has(disclosure)) return;
    openedByUser.delete(disclosure);
    if (!disclosure.open) return;
    Array.from(disclosure.children).forEach(function (child) {
      if (child.tagName !== "SUMMARY") reveal(child);
    });
  }, true);
  document.addEventListener("htmx:beforeRequest", function (event) {
    var detail = event.detail, source = detail.elt;
    // GET polling and search are not mutations and should not pulse whole panels.
    if (!source || !detail.requestConfig || detail.requestConfig.verb.toLowerCase() !== "post") return;
    var widget = source.closest(widgetSelector);
    if (widget) {
      var count = pending.get(widget) || 0;
      pending.set(widget, count + 1);
      widget.classList.add("widget-pending");
      widget.setAttribute("aria-busy", "true");
      detail.xhr.networklyWidget = widget;
    }
  });
  document.addEventListener("htmx:afterRequest", function (event) {
    var detail = event.detail, widget = detail.xhr && detail.xhr.networklyWidget;
    if (!widget) return;
    var count = Math.max(0, (pending.get(widget) || 1) - 1);
    pending.set(widget, count);
    if (!count) { widget.classList.remove("widget-pending"); widget.removeAttribute("aria-busy"); }
    // A network failure keeps the real content and gets an error state, never success feedback.
    if (detail.failed && widget.isConnected) {
      widget.classList.add("widget-request-error");
      setTimeout(function () { widget.classList.remove("widget-request-error"); }, 1800);
    }
  });
  document.addEventListener("htmx:beforeSwap", function (event) {
    var root = document.getElementById("apps-body");
    if (root && event.detail.target === root) restoreStageFocus = root.contains(document.activeElement);
  });
  document.addEventListener("htmx:afterSwap", function (event) {
    setup();
    var target = event.detail.target;
    if (!target || !target.isConnected) return;
    // Tiny acknowledgments on changed controls; large views retain their existing continuity.
    if (target.matches('[id^="track-"]')) reveal(target);
    var feedback = target.querySelector(".moved-flag:not(.error),.msg.success,.prop-undo");
    if (feedback) reveal(feedback);
  });
  setup();
})();
