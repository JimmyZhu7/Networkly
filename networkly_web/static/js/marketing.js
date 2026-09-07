/* Public, illustrative interaction only. No requests and no account mutations. */
(function () {
  'use strict';
  var root = document.querySelector('.networkly-marketing');
  if (!root) return;
  var demo = root.querySelector('[data-product-demo]');
  if (demo) {
    var tabs = Array.from(demo.querySelectorAll('[data-demo-tab]'));
    var panels = Array.from(demo.querySelectorAll('.mk-demo-panel'));
    function select(tab) {
      tabs.forEach(function (item) { item.setAttribute('aria-pressed', String(item === tab)); });
      panels.forEach(function (panel) {
        var active = panel.id === tab.getAttribute('aria-controls');
        panel.hidden = !active;
        panel.classList.toggle('mk-switched', active);
      });
    }
    tabs.forEach(function (tab, index) {
      tab.addEventListener('click', function () { select(tab); });
      tab.addEventListener('keydown', function (event) {
        var next = null;
        if (event.key === 'ArrowRight') next = tabs[(index + 1) % tabs.length];
        if (event.key === 'ArrowLeft') next = tabs[(index + tabs.length - 1) % tabs.length];
        if (event.key === 'Home') next = tabs[0];
        if (event.key === 'End') next = tabs[tabs.length - 1];
        if (next) { event.preventDefault(); next.focus(); select(next); }
      });
    });
    select(tabs[0]);
    demo.classList.add('mk-demo-ready');
  }
  var reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  if ('IntersectionObserver' in window && !reduced.matches) {
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('mk-revealed');
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.15 });
    root.querySelectorAll('[data-mk-reveal]').forEach(function (item) { observer.observe(item); });
  }
}());
