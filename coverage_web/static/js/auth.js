/* Optional visibility control. Native password fields remain usable without JS. */
document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('.auth-form input[type="password"]').forEach(function (input) {
    if (input.closest('.auth-password')) return;
    var wrap = document.createElement('div');
    wrap.className = 'auth-password';
    input.before(wrap);
    wrap.appendChild(input);
    var toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'auth-password-toggle';
    toggle.setAttribute('aria-controls', input.id);
    toggle.setAttribute('aria-label', 'Show password');
    toggle.setAttribute('aria-pressed', 'false');
    toggle.textContent = 'Show';
    toggle.addEventListener('click', function () {
      var reveal = input.type === 'password';
      input.type = reveal ? 'text' : 'password';
      toggle.textContent = reveal ? 'Hide' : 'Show';
      toggle.setAttribute('aria-label', reveal ? 'Hide password' : 'Show password');
      toggle.setAttribute('aria-pressed', String(reveal));
    });
    wrap.appendChild(toggle);
  });
});
