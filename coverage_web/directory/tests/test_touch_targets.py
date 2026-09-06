"""No control may be invisible and tappable at the same time.

`opacity: 0` hides a control from the eye. It does not hide it from a finger:
the box still occupies layout, still hit-tests, and still fires its handler.
On a device with a mouse that is fine, because the pointer reveals the control
before it can reach it. On a phone there is no hover — the reveal never
happens, and the first thing a tap does is fire the action.

That shipped. Every untracked role card on /opportunities/ drew a "Not for me"
button at `opacity: 0` with `pointer-events: auto`, 61.6x19, flush against the
right edge of the Save pill, with no `@media (hover: hover)` guard anywhere in
the repo. Measured in a touch context at 390x844, `elementFromPoint` at the
region's centre returned `.track-hide`, and a blind `touchscreen.tap()` there
fired `POST /opportunities/<id>/track/` with `status=dismiss` — the label only
faded in AFTER the role had been dismissed. 490 of 493 feed cards carried one.

These tests assert the rendered stylesheet, because that is the artifact the
browser actually gets.
"""

from __future__ import annotations

from .presentation_helpers import presentation_css, rule as presentation_rule, rules as presentation_rules, media_blocks

import re

import pytest
from django.test import Client

pytestmark = pytest.mark.django_db

# Controls that are deliberately hidden until a pointer reveals them. Add a
# class here only alongside the guard the tests below require.
REVEAL_ON_HOVER = ["track-hide"]

_STYLE_RE = re.compile(r"<style>(.*?)</style>", re.S)
# The body of an `@media (hover: hover)` block, brace-counted so a nested rule
# inside it does not truncate the match.
_HOVER_BLOCK_RE = re.compile(r"@media\s*\(\s*hover:\s*hover\s*\)\s*\{")


def _feed_css() -> str:
    return presentation_css(Client().get("/opportunities/").content.decode())


def _blocks(css: str, opener: re.Pattern[str]) -> list[str]:
    """Every `@media ... { ... }` body whose prelude `opener` matches, brace
    counted so a nested rule inside it does not truncate the match."""
    out = []
    for m in opener.finditer(css):
        depth, i = 1, m.end()
        while depth and i < len(css):
            depth += (css[i] == "{") - (css[i] == "}")
            i += 1
        out.append(css[m.end():i - 1])
    return out


def _hover_guarded_blocks(css: str) -> list[str]:
    """Every `@media (hover: hover) { ... }` body in the stylesheet."""
    return _blocks(css, _HOVER_BLOCK_RE)


def _rules(css: str) -> list[tuple[str, str]]:
    """(selector, declarations) for every flat rule in the stylesheet."""
    return [
        (m.group(1).strip(), m.group(2))
        for m in re.finditer(r"([^{}@]+)\{([^{}]*)\}", css)
    ]


@pytest.mark.parametrize("cls", REVEAL_ON_HOVER)
def test_dismiss_is_visible_without_requiring_hover(cls):
    body = presentation_rule(_feed_css(), "." + cls)
    assert "opacity: 1" in body
    assert "opacity: 0" not in body


@pytest.mark.parametrize("cls", REVEAL_ON_HOVER)
def test_visible_dismiss_control_accepts_pointer_interaction(cls):
    body = presentation_rule(_feed_css(), "." + cls)
    assert "pointer-events: auto" in body
    assert "pointer-events: none" not in body


def test_role_actions_do_not_need_pointer_or_keyboard_reveal():
    css = _feed_css()
    actions = presentation_rule(css, ".rr-act")
    assert "position: static" in actions
    assert "opacity: 1" in actions and "pointer-events: auto" in actions
    focus = presentation_rule(css, "button:focus-visible")
    assert "outline:" in focus and "var(--accent)" in focus


def test_save_and_dismiss_have_separate_targets_with_spacing():
    body = presentation_rule(_feed_css(), ".track")
    gap = re.search(r"(?<!-)gap:\s*(\d+(?:\.\d+)?)px", body)
    assert gap and float(gap.group(1)) >= 4
    assert "flex-wrap: wrap" in body


# ---------------------------------------------------------------------------
# Size, not just visibility. The tests above stop a control being invisible
# and tappable; these stop it being visible and untappable.
#
# Measured at 375x812 with `(pointer: coarse)` and `(hover: none)` both true,
# the feed's three per-card controls were .track-btn 60.7x19, .track-hide
# 61.6x19 and .meta-read 42x16, while /app/ on the same run measured its own
# buttons at 44px because crm/_styles.html floors them there. A fingertip
# covers ~44px; 19px is a control you aim at and miss, and for "Not for me"
# the thing you hit on the way past is Save.
# ---------------------------------------------------------------------------

_COARSE_BLOCK_RE = re.compile(r"@media\s*\(\s*pointer:\s*coarse\s*\)\s*\{")

# Every control drawn on a role card, and where its rule lives. .meta-read is
# a shared component in the static sheet — the feed, the firm page and My
# Applications all draw it — so a fix made only in the feed's inline styles
# would leave two of the three pages at 16px.
CARD_CONTROLS = ["track-btn", "track-hide", "track-chip", "meta-read"]

TOUCH_FLOOR = 44


def _shared_css() -> str:
    """The static stylesheet as shipped, comments stripped."""
    from django.contrib.staticfiles import finders

    path = finders.find("css/networkly.css")
    assert path, "css/networkly.css is not on the static path"
    with open(path, encoding="utf-8") as fh:
        return re.sub(r"/\*.*?\*/", "", fh.read(), flags=re.S)


def _all_feed_css() -> str:
    """Everything the browser applies to a role card: the page's inline
    styles plus the shared stylesheet it links."""
    return _feed_css() + "\n" + _shared_css()


def _coarse_rules(css: str) -> list[tuple[str, str]]:
    return [r for block in _blocks(css, _COARSE_BLOCK_RE) for r in _rules(block)]


def _declared_px(rules, selector: str, prop: str) -> float | None:
    for sel, body in rules:
        if selector not in {s.strip() for s in sel.split(",")}:
            continue
        # `contain-intrinsic-size` carries an `auto` keyword before its length.
        m = re.search(rf"(?<!-){prop}:\s*(?:auto\s+)?(-?\d+(?:\.\d+)?)px", body)
        if m:
            return float(m.group(1))
    return None


@pytest.mark.parametrize("cls", CARD_CONTROLS)
def test_phone_role_controls_clear_the_touch_floor(cls):
    compact = media_blocks(_feed_css(), r"max-width:\s*640px")
    body = presentation_rule(compact, ".rr-act ." + cls)
    height = re.search(r"min-height:\s*(\d+(?:\.\d+)?)px", body)
    assert height and float(height.group(1)) >= TOUCH_FLOOR


def test_larger_controls_have_wrapping_actions_and_content_sized_rows():
    css = _feed_css()
    assert "flex-wrap: wrap" in presentation_rule(css, ".rr-act")
    row = presentation_rule(css, ".rolerow")
    assert not re.search(r"(?:^|;)\s*(?:height|max-height):\s*\d", row)
    assert "contain-intrinsic-size:" not in row


def test_opposite_actions_remain_separately_named_native_buttons():
    from pathlib import Path
    template = Path(__file__).resolve().parents[2] / "templates/directory/_track_control.html"
    text = template.read_text()
    assert 'class="track-btn"' in text and 'class="track-hide"' in text
    assert '>Not for me</button>' in text
    assert '"status": "saved"' in text and '"status": "dismiss"' in text
    assert "flex-wrap: wrap" in presentation_rule(_feed_css(), ".track")

