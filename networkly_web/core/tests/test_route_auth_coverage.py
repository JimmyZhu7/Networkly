"""Every first-party route is login-gated, staff-gated, or on this page's list.

THE GAP THIS CLOSES. `settings/base.py`'s MIDDLEWARE has no login-enforcing
entry and no public allowlist, so authentication in this app is one hundred
percent per-view decorator: ninety-four hand-applied `@login_required`s across
eight modules, plus four `@staff_member_required`s. That is a working design —
Django's own — but it fails open. A view added without a decorator is public,
it looks exactly like a view that is public on purpose, and nothing anywhere
notices. The 2026-09-06 security review found one route already in that state
(`accounts.views.university_search`, below), and found it by reading all 116
routes by hand, which is not a control anyone will repeat before every deploy.

So this is the backstop the middleware doesn't provide. It walks the resolved
URLconf, reads each first-party callback's own source, and requires one of:

  * `@login_required` or `@staff_member_required` in its decorator lines, or
  * an entry in PUBLIC below, with a stated reason.

Adding a public route stays a one-line change. What it stops being is a
*silent* one: the line has to be written down next to the reason it is public,
in a file whose whole subject is that question.

WHY SOURCE INSPECTION RATHER THAN INTROSPECTION. `login_required` returns a
`functools.wraps`-decorated closure, which copies `__module__`, `__name__` and
`__doc__` off the wrapped function — so a wrapped and an unwrapped view are
almost indistinguishable as objects, and the parts that do differ (closure cell
layout) are Django internals that a version bump may reshape. `getsource` reads
the decorator lines that are actually written in the file, which is the thing
being asserted and the thing a reviewer would look at.

SCOPE. First-party modules only. django-allauth's own account views, Django's
admin and `django.views.static` are third-party code with their own gating; a
source scan of them would assert on a dependency's style rather than on this
codebase's discipline, and would break on upgrade. Allauth's mount is covered
instead by `accounts/tests/test_security.py`, which walks its routes through
the test client as an anonymous caller.
"""

from __future__ import annotations

import inspect

import pytest
from django.urls import get_resolver

# Modules this repo owns. Everything else on the URLconf is a dependency.
FIRST_PARTY = (
    "accounts.", "analytics.", "assistant.", "billing.", "capture.",
    "core.", "crm.", "directory.", "ops.",
)

# A decorator line carrying any of these is the gate. `staff_member_required`
# implies authentication (it redirects an anonymous caller to the admin login),
# so it counts here for the same reason `login_required` does.
GATES = ("login_required", "staff_member_required", "user_passes_test", "permission_required")

# Routes that answer an unauthenticated caller ON PURPOSE, each with the reason
# it is allowed to. Keyed by "module.qualname" so a route rename does not
# quietly re-key an entry onto a different view.
PUBLIC: dict[str, str] = {
    # Marketing and legal surface. Nothing per-tenant is read.
    "core.views.home": "the landing page; shared-zone counts only",
    "core.views.pricing": "the pricing page",
    "core.views.favicon": "a static asset behind the pushstate fallback",
    "core.views.healthz": "the PaaS liveness probe; reads nothing, writes nothing",
    "accounts.views.privacy": "the published privacy policy, which must be readable before signup",
    "accounts.views.terms": "the published terms, same reason",
    # Public directory. The shared opportunity/firm zone is the same for
    # everyone; the per-user slices inside these views are gated inline on
    # `request.user.is_authenticated` (directory/views.py).
    "directory.views.opportunities": "the shared opportunity feed",
    "directory.views.role_description": "a shared posting's own text; the contacts slice is gated inline",
    "directory.views.firm_detail": "a shared firm page",
    # Signed or bearer credentials rather than a session.
    "accounts.views.digest_unsubscribe": "a signed digest token identifies the recipient",
    "crm.calendar_views.calendar_ics": "a per-user secret token in the path is the credential; rotatable in Settings",
    "billing.views.webhook": "Stripe's HMAC signature is the authentication; csrf_exempt is correct here",
    # Deliberately reachable signed out, with its own per-IP burst guard.
    "billing.views.waitlist_join": "the pricing page's notify-me form, IP-throttled",
    # Signup needs the static university list before authentication. The
    # shared per-IP search window is covered by test_university_search_throttled.
    "accounts.views.university_search": "signup autocomplete; static data only and per-IP throttled",
    # Anonymous by design, and already throttled: the contacts branch inside it
    # is gated on `request.user.is_authenticated` and scoped with `for_user`.
    "core.views.search": "the marketing search box; per-IP throttled, tenant branch gated inline",
}

# Not public, and not decorated either: these check the caller in the function
# body because the check they need is stronger than "is signed in". Kept in
# their own list so that reading PUBLIC never has to mean "anyone can see
# this" — a route dropped in here is asserting that the named line does the
# work a decorator would, and the named test is what holds it to that.
GATED_IN_BODY: dict[str, str] = {
    "core.media.avatar": (
        "core/media.py's first statement requires an authenticated, active, "
        "undeleted user whose own `avatar.name` equals the requested path, "
        "which is ownership AND traversal defence in one comparison. "
        "@login_required would be strictly weaker: it would admit any signed-in "
        "user to any other user's avatar key. Covered by "
        "core/tests/test_private_media.py."
    ),
}


def _first_party_views():
    """(dotted name, callable) for every distinct view this repo owns."""
    seen: dict[str, object] = {}

    def walk(resolver):
        for pattern in resolver.url_patterns:
            nested = getattr(pattern, "url_patterns", None)
            if nested is not None:
                walk(pattern)
                continue
            view = pattern.callback
            # A CBV's `as_view()` result carries the class on `view_class`.
            target = getattr(view, "view_class", view)
            module = getattr(target, "__module__", "") or ""
            if not module.startswith(FIRST_PARTY):
                continue
            name = f"{module}.{getattr(target, '__qualname__', target)}"
            seen.setdefault(name, view)

    walk(get_resolver())
    return seen


def test_the_urlconf_still_resolves_to_first_party_views():
    """Guard the guard: a walk that silently found nothing would pass below."""
    views = _first_party_views()
    assert len(views) > 80, f"only {len(views)} first-party views found; the walk is broken"


@pytest.mark.parametrize("name", sorted(_first_party_views()))
def test_every_first_party_route_is_gated_or_declared_public(name):
    view = _first_party_views()[name]
    if name in PUBLIC or name in GATED_IN_BODY:
        return
    try:
        source = inspect.getsource(view)
    except (OSError, TypeError) as exc:  # pragma: no cover - a view with no file
        pytest.fail(f"{name}: cannot read source to check its gate ({exc})")
    # Only the decorator lines, so a `login_required` mentioned in a docstring
    # or imported inside the body cannot vouch for the view.
    decorators = []
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("def ") or stripped.startswith("class "):
            break
        if stripped.startswith("@"):
            decorators.append(stripped)
    joined = " ".join(decorators)
    assert any(gate in joined for gate in GATES), (
        f"{name} has no authentication decorator and is not listed in PUBLIC.\n"
        f"Decorators found: {decorators or 'none'}.\n"
        "Either add @login_required (or @staff_member_required), or add it to "
        "PUBLIC in this file with the reason it answers anonymous callers."
    )


def test_the_exemption_lists_have_no_stale_entries():
    """An entry for a route that no longer exists hides the next one that
    lands on that name — which is exactly how a dead exemption becomes a live
    one after a rename."""
    live = set(_first_party_views())
    stale = sorted((set(PUBLIC) | set(GATED_IN_BODY)) - live)
    assert not stale, f"exemptions name routes that no longer exist: {stale}"


def test_the_two_exemption_lists_do_not_overlap():
    """One route, one reason. A name in both lists means nobody decided."""
    both = sorted(set(PUBLIC) & set(GATED_IN_BODY))
    assert not both, f"listed as both public and body-gated: {both}"
