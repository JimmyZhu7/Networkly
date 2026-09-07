"""Every column header on the feed names its column on the same baseline.

THE HEADER IS A TWO-ROW GRID (2026-09-02) and that is what keeps the promise
now. Row one is the logo tile and the firm name, centred on each other. Row
two is one line carrying the category, the open count and the tier. A name
cannot move, whatever follows it, because it is in a row of its own.

WHAT CAME BEFORE, and why the grid is the fix rather than a restyle. The head
was a flex row: a 38px tile, then an id COLUMN of three short lines. Two
defects came out of that shape. `align-items: center` centred each id stack,
so where a name LANDED depended on what came after it — Picked-for-you emits
its `.firmcol-stats` row unconditionally and it held nothing until a why-chip
existed, so that column's id block measured 42.2px against a firm's 61.4px and
its name rendered 9.6px lower than Morgan Stanley's beside it (measured live
at 1280px). `align-items: flex-start` fixed that one by declaration. The
second defect survived it: the tile kept its own centring against a three-row
stack, so the logo sat level with the CATEGORY rather than with the firm it
stands for, and the founder's review of the shipped page said so — "the top
part of these widgets look weird ... make it more visually harmonious".

A tile anchoring three lines has nothing to align to. Two rows give it one.
Measured after: the firm head went 126px -> 86px, the Picked head 194px ->
139px, row one computes to exactly the 38px tile, and every column's name
starts at the same y whether its neighbour's name wraps to two lines or not.

The old note about the empty stats div is retired with the flex column that
made it true: `.firmcol-stats` now always carries at least the category and
count, and it is a grid row rather than a flex sibling, so nothing about the
name's position depends on it at all.
"""

from __future__ import annotations

from .presentation_helpers import presentation_css, rule as presentation_rule, rules as presentation_rules, media_blocks

import re

import pytest
from django.test import Client

pytestmark = pytest.mark.django_db

_STYLE_RE = re.compile(r"<style>(.*?)</style>", re.S)


def _feed_css() -> str:
    return presentation_css(Client().get("/opportunities/").content.decode())


def _rule(css: str, selector: str) -> str:
    return presentation_rule(css, selector)


@pytest.fixture
def feed_with_both_columns(db):
    """A profiled student, and picks that share no reason.

    Every piece is load-bearing. The Picked column only renders for a signed-in
    user with a profile; the firm columns it must line up with only exist if
    there are roles; and its stats row is only EMPTY — the state that made the
    centring fail — when no reason is byte-identical across every pick, which
    is why the two firms differ in tier, region and cohort.
    """
    from django.contrib.auth import get_user_model

    from crm.models import UserFirm
    from directory.models import Firm, Opportunity

    alpha = Firm.objects.create(slug="alpha", name="Alpha Partners", tracks=["ib"])
    beta = Firm.objects.create(slug="beta", name="Beta Securities", tracks=["ib"])
    Opportunity.objects.create(
        firm=alpha, url="https://x.test/1", title="2027 Summer Analyst Programme",
        bucket="internship", cohort="2027", status="open", region="us",
        location="New York",
    )
    Opportunity.objects.create(
        firm=beta, url="https://x.test/2", title="2028 Summer Analyst Programme",
        bucket="internship", cohort="2028", status="open", region="hk",
        location="Hong Kong",
    )
    user = get_user_model().objects.create_user(
        email="head@example.com", password="x" * 14
    )
    user.class_year = 2029
    user.target_cycles = ["SA 2028"]
    user.school = "USC Marshall"
    user.regions = ["us", "hk"]
    user.tracks = ["ib"]
    user.save()
    UserFirm.all_objects.create(user=user, firm=alpha, tier=1)
    UserFirm.all_objects.create(user=user, firm=beta, tier=2)

    client = Client()
    client.force_login(user)
    return client


def test_the_header_keeps_name_and_metadata_in_distinct_rows():
    css = _feed_css()
    assert "display: grid" in _rule(css, ".firmcol-head")
    assert "grid-row: 1" in _rule(css, ".firmcol-h")
    assert "grid-row: 2" in _rule(css, ".firmcol-stats")
    assert "grid-template-rows: auto auto" in _rule(css, ".firmcol-head")


def test_the_logo_spans_identity_rows_and_stays_in_its_own_column():
    body = _rule(_feed_css(), ".firmcol-logo")
    assert "grid-column: 1" in body
    assert "grid-row: 1 / 3" in body
    assert "align-self: start" in body


def test_the_logo_image_is_contained_without_distortion():
    css = _feed_css()
    assert "object-fit: contain" in _rule(css, ".firmcol-logo img")
    assert "overflow: hidden" in _rule(css, ".firmcol-logo")


def test_the_heading_carries_no_margin_of_its_own():
    """`.firmcol-h` is an h2 and the shared stylesheet gives an h2 20px of
    vertical margin. Inside the old flex column that collapsed away; inside
    the grid it does not. Measured before the reset: row one computed 58px
    against a 38px tile, so every header on the board ran 20px taller than
    the design and the tile floated in an empty band."""
    assert "margin: 0" in _rule(_feed_css(), ".firmcol-h")


def test_shared_reasons_can_wrap_without_displacing_firm_identity():
    css = _feed_css()
    assert "flex-wrap: wrap" in _rule(css, ".firmcol-stats")
    reasons = _rule(css, ".firmcol-why")
    assert "nowrap" not in reasons and "overflow: hidden" not in reasons
    assert ".why-chip" not in css


def test_the_picked_column_renders_shared_reasons_in_the_firmcol_why_line(db):
    """Two picks that share a cohort AND a bucket AND a tier: the shared
    reasons must land inside `.firmcol-why` (with each full sentence in its
    `title`), never as `.why-chip` pills."""
    from django.contrib.auth import get_user_model

    from crm.models import UserFirm
    from directory.models import Firm, Opportunity

    alpha = Firm.objects.create(slug="alpha", name="Alpha Partners", tracks=["ib"])
    beta = Firm.objects.create(slug="beta", name="Beta Securities", tracks=["ib"])
    for firm, n in ((alpha, 1), (beta, 2)):
        Opportunity.objects.create(
            firm=firm, url=f"https://x.test/{n}", title="2028 Summer Analyst Programme",
            bucket="internship", cohort="2028", status="open", region="us",
            location="New York",
        )
    user = get_user_model().objects.create_user(email="why@example.com", password="x" * 14)
    user.class_year = 2029
    user.target_cycles = ["2028 Summer Internship"]
    user.school = "USC Marshall"
    user.regions = ["us"]
    user.tracks = ["ib"]
    user.save()
    UserFirm.all_objects.create(user=user, firm=alpha, tier=1)
    UserFirm.all_objects.create(user=user, firm=beta, tier=1)

    client = Client()
    client.force_login(user)
    html = _STYLE_RE.sub("", client.get("/opportunities/").content.decode())
    picked = re.search(r'<article class="firmcol firmcol--picked.*?</header>', html, re.S)
    assert picked, "the Picked column should render for a profiled student with picks"
    head = picked.group(0)
    assert 'class="firmcol-why"' in head, head
    assert "why-chip" not in head
    assert "2028 Summer Internship" in head
    assert 'title="' in head, "the full sentences must survive in the tooltip"


def test_both_columns_spend_the_same_two_rows_on_their_identity(feed_with_both_columns):
    """REWRITTEN 2026-09-02, twice over, and the history is the argument.

    It was first written to prove the Picked column's id STACK is shorter
    than a firm's — the condition that made `align-items: center` misalign
    the two — and then rewritten to assert the `fc-eyebrow` span, because
    that word had moved into the stats slot and made the "empty row" premise
    unreachable. Both premises are gone now. The header is a two-row grid, so
    stack height cannot move a name at all; and the eyebrow is deleted,
    because it read "PICKED" directly under a heading reading "Picked for
    you" and the founder's review called that what it was.

    What survives, and is the thing worth pinning: both columns say who they
    are in exactly two rows, and row two is one line in both. The Picked
    column has no tier, so its second row carries its count and whatever the
    picks share; a firm's carries its category, its open count and its tier.
    Different words, same two rows, which is why the headers line up.
    """
    html = feed_with_both_columns.get("/opportunities/").content.decode()
    html = _STYLE_RE.sub("", html)

    stats = re.findall(r'<div class="firmcol-stats">(.*?)</div>', html, re.S)
    assert len(stats) >= 2, f"expected the Picked column and a firm one, got {len(stats)}"
    assert "fc-eyebrow" not in html, (
        "the 'PICKED' eyebrow is back. It repeats the heading directly above "
        "it; the accent star tile and the accent heading are what say this "
        "column is not a firm (see the identity tests below)")
    # Row two, both columns: one `.firmcol-meta` line, and the tier only
    # where a tier exists.
    assert "firmcol-meta" in stats[0], (
        "the Picked column's second row should carry its own count line — "
        "if it moved back out to a row of its own the header grew a third row")
    assert "firmcol-tier" not in stats[0], "the Picked column has no tier"
    assert "firmcol-meta" in stats[1] and "firmcol-tier" in stats[1], (
        "a firm's category, open count and tier belong on ONE line; they were "
        "two stacked rows beside the logo tile until 2026-09-02, which is the "
        "layout the founder called cluttered")
    assert ":empty" not in _feed_css(), (
        "a :empty selector cannot match that row — it holds a whitespace text "
        "node — so a fix resting on one would be silently dead"
    )


# ---------------------------------------------------------------------------
# THE PICKED COLUMN'S IDENTITY (2026-08-31). It used to carry an accent WASH
# (`background: var(--accent-soft)`), and the founder's own dark-mode screen-
# shot is why it does not any more. Measured on the rendered page:
#
#     --accent-soft #232a35 vs --surface #1c201a   1.144:1
#     --accent-soft #232a35 vs --paper   #141712   1.252:1
#
# So the wash separated the column by HUE, not luminance — a blue-grey slab
# on a green-black page. Worse, `.firmcol-scroll` paints `--surface` over the
# whole body, so the wash only ever reached the header: the column rendered
# as a blue lid on a green-black box with that 1.144:1 jump at the seam
# between them, which was the harshest edge in the column and internal to it.
#
# What replaces it must be structural, and these tests pin that it IS
# structural — because with the wash gone there is very little left, and on
# the founder's board there is even less than the stylesheet assumes: all 12
# of his firm columns are `.is-mine`, so the `--accent-line` border the
# Picked column wears is not distinguishing it from anything.
# ---------------------------------------------------------------------------


def test_firm_collections_have_a_bounded_surface_and_natural_height():
    body = _rule(_feed_css(), ".firmcol")
    assert "background: var(--surface)" in body
    assert "height: auto" in body and "overflow: visible" in body
    assert "border: 1px solid var(--line)" in body


def test_picks_have_a_distinct_named_identity_without_a_card_wash():
    css = _feed_css()
    assert "var(--accent-ink)" in _rule(css, ".firmcol--picked .firmcol-name")
    assert "var(--accent-soft)" in _rule(css, ".firmcol-logo.firmcol-logo--picked")


def test_picked_icon_uses_a_more_specific_theme_aware_rule():
    css = _feed_css()
    generic = _rule(css, ".firmcol-logo")
    picked = _rule(css, ".firmcol-logo.firmcol-logo--picked")
    assert "background: var(--surface)" in generic
    assert "background: var(--accent-soft)" in picked
    assert "color: var(--accent-ink)" in picked
