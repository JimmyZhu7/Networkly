/* Responsive navigation. Without JavaScript every destination stays visible. */
(function () {
  if (window.networklyWorkspaceReady) return;
  window.networklyWorkspaceReady = true;
  document.documentElement.classList.add("workspace-ready");

  var phoneSettings = window.matchMedia("(max-width: 820px)");
  function setupSettings() {
    var index = document.querySelector(".settings-index");
    if (index && !index.dataset.ready) {
      index.dataset.ready = "true";
      index.open = !phoneSettings.matches;
    }
  }
  setupSettings();
  phoneSettings.addEventListener("change", function () {
    var index = document.querySelector(".settings-index");
    if (index) index.open = !phoneSettings.matches;
  });

  function closeNavigation(returnFocus) {
    var header = document.querySelector(".workspace-nav");
    var button = document.querySelector("[data-workspace-menu]");
    if (!header || !button) return;
    header.classList.remove("is-open");
    button.setAttribute("aria-expanded", "false");
    button.setAttribute("aria-label", "Open navigation");
    if (returnFocus) button.focus();
  }

  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-workspace-menu]");
    if (button) {
      var header = button.closest(".workspace-nav");
      var expanded = header.classList.toggle("is-open");
      button.setAttribute("aria-expanded", String(expanded));
      button.setAttribute("aria-label", expanded ? "Close navigation" : "Open navigation");
    } else if (!event.target.closest(".workspace-nav")) {
      closeNavigation(false);
    }
  });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && document.querySelector(".workspace-nav.is-open")) {
      closeNavigation(true);
    }
  });
  document.addEventListener("focusin", function (event) {
    if (!event.target.closest(".workspace-nav")) closeNavigation(false);
  });
  document.addEventListener("htmx:afterSettle", function () {
    closeNavigation(false);
    setupSettings();
  });
})();
