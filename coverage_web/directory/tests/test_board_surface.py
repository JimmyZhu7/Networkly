"""The Opportunities board's own surface: what its counts promise, what shape
its controls are, what colour its figures are, and what is allowed to move.

Every test here pins a defect measured on the live dev board on 2026-09-01
(the read-only UI audit, `scratchpad/audit-ui.md` §3), and every one of them
asserts the RENDERED artifact — the stylesheet the browser is served and the
HTML it is served with it — because each defect was invisible to every test
in this suite while being plainly visible on the page:

  * two totals disagreed by 127 with nothing explaining the difference,
  * four pressable controls were 999px capsules under a filter bar that had
    just been squared, on a page whose own `.btn` rule states the law,
  * the "6d" on every role closing this week rendered at 3.98:1 (light) and
    3.12:1 (dark) because it was painted with a BAR token,
  * ten infinite pulse rings ran on the first viewport for a state that never
    changes,
  * the dark board's scroll affordance was invisible and its logo tiles glowed,
  * eight rules and two keyframes styled markup no template has emitted since
    the 2026-08-30 row redesign.

Colour is asserted by TOKEN NAME rather than by measuring a ratio in Python:
the tokens' own values live in `static/css/networkly.css` and are another
workstream's to move, and the promise this file can keep is "this figure is
painted with the tier built to be read", not "this hex is 4.5:1". The measured
ratios are in the docstrings so the next reader knows what was checked and how.
"""

from __future__ import annotations

from .presentation_helpers import presentation_css, rule as presentation_rule, rules as presentation_rules, media_blocks

import pathlib
import re

import pytest
from django.test import Client
from django.urls import reverse

from directory.models import Firm, Opportunity

pytestmark = pytest.mark.django_db

_STYLE_RE = re.compile(r"<style>(.*?)</style>", re.S)


def _css(path: str = "/opportunities/") -> str:
    return presentation_css(Client().get(path).content.decode())


def _rule(css: str, selector: str) -> str:
    return presentation_rule(css, selector)


# ---------------------------------------------------------------------------
# 1. TWO TOTALS ON ONE SCREEN.
#
# The segmented control said "All Campus (2723)" and the stat strip eight
# pixels below said "2596 Open Roles". filter-bar-redesign.md §3, principle 2:
# counts are a promise. Both numbers were right and they count different
# things, and nothing on the page said so, which makes at least one of them
# read as wrong.
# ---------------------------------------------------------------------------


@pytest.fixture
def dupes(db):
    """A board with a Class-B duplicate on it: one firm filing one job as two
    requisitions, which is what `fold_duplicates` collapses at DISPLAY time.

    Same title, same location, same deadline, different URLs — SIG posts every
    2027 internship under two iCIMS job numbers, which is the live case
    `directory.dupes` was written for.
    """
    f = Firm.objects.create(slug="sig", name="Susquehanna")
    common = dict(firm=f, title="2027 Quantitative Trading Intern", bucket="internship",
                  status="open", location="Dublin", region="eu")
    Opportunity.objects.create(url="https://x/jobs/1/a/job", **common)
    Opportunity.objects.create(url="https://x/jobs/2/b/job", **common)
    Opportunity.objects.create(url="https://x/jobs/3/c/job",
                               **{**common, "title": "2027 Summer Analyst"})
    return f


def test_the_board_count_and_the_strip_total_reconcile(client, dupes):
    """`board_count - hidden_fit == total`, exactly — and with the fit
    filter off, the two are simply the same number.

    REWRITTEN 2026-09-02, and the premise it used to pin is retired rather
    than weakened. The old identity was `board_count - hidden_dupes -
    hidden_fit == total`, because the segmented control counted board ROWS
    while the strip counted the rows a student is shown, and the page paid
    for that gap with a footnote explaining 137 folded listings. The segment
    counts fold before they count now (`views._folded_count`), so
    `hidden_dupes` is no longer a term: the fold happens on both sides of the
    equation or on neither. That is a strictly stronger promise — three
    numbers reduced to two, and the two agree wherever the student has not
    switched a personal filter on.

    Measured on the founder's live board when this shipped: segment 2,958,
    strip 2,958, 137 rows folded and nothing left to say about them.
    """
    ctx = client.get(reverse("opportunities")).context
    assert ctx["board_count"] - ctx["hidden_fit"] == ctx["total"]
    # And the fixture really does fold something, so this is not holding
    # vacuously on a board with no duplicate on it.
    assert ctx["hidden_dupes"] == 1
    assert ctx["board_count"] == ctx["total"] == 2


def test_the_segment_pill_is_the_only_surface_stating_the_board_total(client, dupes):
    response = client.get(reverse("opportunities"))
    body = response.content.decode()
    label = re.search(r'<label[^>]*for="seg-campus"[^>]*>(.*?)</label>', body, re.S)
    if label is None:
        label = next((m for m in re.finditer(r'<label[^>]*>(.*?)</label>', body, re.S)
                      if 'id="cnt-role-campus"' in m.group(1)), None)
    assert label, "The campus count belongs to its native radio label"
    text = re.sub(r'<[^>]+>', '', label.group(1))
    assert "All Campus" in text
    assert re.search(r'id="cnt-role-campus">\d+</span>', label.group(1))
    assert 'class="stat-strip"' not in body
    assert 'Open Role' not in re.sub(r'<style[^>]*>.*?</style>', '', body, flags=re.S)



# `test_the_strip_states_the_board_total_once_and_quietly` stood here. It
# pinned how the STRIP said the board total — demoted into a coverage clause
# at the strip's own text size rather than as a headline figure. The strip was
# removed on 2026-09-03, so there is no second statement left to keep quiet;
# the test above now asserts the stronger thing, that there is only one.



# `test_every_strip_tier_settles_on_the_colour_it_declares` stood here,
# parametrized over the strip's warn/fresh tiers. It pinned that a tier
# declaring a colour must name a keyframe landing on it, because `ss-settle`
# ran with `animation-fill-mode: both` and repainted a tier neutral 380ms in.
# The strip, its tiers and all three `ss-settle*` keyframes were removed on
# 2026-09-03; there is no tier left to declare a colour.


def test_the_fold_is_silent_because_there_is_nothing_left_to_say(client, dupes):
    """No footnote on a board whose only cut is the duplicate fold.

    This is the 2026-08-28 decision restored, not a regression of the
    2026-09-01 one. `opportunities.html` records it: repeat listings fold
    silently, no toggle, no count, no route back, because a firm re-filing
    one job as several requisitions is noise on every reading of this page
    and never a role anyone was trying to reach. The footnote had reopened
    that purely to account for a gap in the counts; with the counts agreeing,
    printing "1 folded as repeat listing" would be telling a student about a
    difference the page no longer has.
    """
    body = client.get(reverse("opportunities")).content.decode()
    # The class ATTRIBUTE, not the bare word: the rule that styles this line
    # ships in the page's own <style> block on every render, footnote or not.
    assert 'class="scope-line scope-foot"' not in body
    assert "folded as repeat listing" not in body


def test_no_footnote_when_the_two_counts_agree(client):
    """A board with nothing folded and nothing hidden says nothing. The line
    is a footnote to a difference; with no difference it is noise, and this
    is the state of most filtered views."""
    f = Firm.objects.create(slug="ms", name="Morgan Stanley")
    Opportunity.objects.create(firm=f, url="https://x/1", title="Summer Analyst",
                               bucket="internship", status="open", region="us")
    body = client.get(reverse("opportunities")).content.decode()
    assert 'class="scope-line scope-foot"' not in body
    ctx = client.get(reverse("opportunities")).context
    assert ctx["board_count"] == ctx["total"] == 1


def test_turning_the_fold_off_moves_both_counts_together(client, dupes):
    """`?dupes=1` unfolds the board, and the segment count unfolds with it.

    The escape hatch is the one place a folded count could quietly become a
    lie in the other direction: the render stops folding, and a pill still
    quoting the folded number would put the same two-totals defect back on
    the page wearing the URL fallback as a disguise. Both sides move.

    It stays unadvertised (the "Show repeat listings" checkbox was cut on
    2026-08-28), so nothing on the page links it.
    """
    ctx = client.get(reverse("opportunities"), {"dupes": "1"}).context
    assert ctx["hidden_dupes"] == 0
    assert ctx["board_count"] == ctx["total"] == 3
    body = client.get(reverse("opportunities"), {"dupes": "1"}).content.decode()
    assert 'class="scope-line scope-foot"' not in body
    assert "dupes=1" not in body, (
        "the fold's URL fallback stays unadvertised; see _results.html")


def test_the_segment_count_does_not_depend_on_who_is_asking(dupes):
    """The fold's tie-break may not move a shared count, and it cannot.

    `fold_duplicates` reads `sticky_ids` only in `_survivor_rank`, which
    decides WHICH copy of a cluster the student sees. The number of survivors
    is the same either way — and that is the whole licence for the segmented
    control to fold before it counts while staying a figure about the board
    rather than about one reader. If this ever stops holding, the pill and
    the strip stop being one number and the footnote has to come back.
    """
    from directory.dupes import fold_duplicates

    rows = list(Opportunity.objects.filter(status="open"))
    plain, folded_plain = fold_duplicates(rows)
    for sticky in ([], [rows[0].id], [r.id for r in rows]):
        kept, folded = fold_duplicates(rows, sticky_ids=sticky)
        assert (len(kept), folded) == (len(plain), folded_plain)


def test_every_segment_states_what_clicking_it_shows(client, dupes):
    """Each pill's count is that segment's own rendered total, not the
    board's row count — checked by clicking through every one of them.

    The pills are cross-filtered facets, so each is folded over its OWN
    scope: `Everything` over the whole board, `All Campus` over the three
    campus buckets together, a single bucket over itself. Summing folded
    buckets to get the wider scopes would be exact only while no duplicate
    cluster straddles a bucket boundary, which is data rather than an
    invariant.
    """
    segments = {s["value"]: s["count"]
                for s in client.get(reverse("opportunities")).context["role_segments"]}
    assert segments  # the control is drawn at all
    for value, count in segments.items():
        params = {"role": value} if value else {}
        assert client.get(reverse("opportunities"), params).context["total"] == count, (
            f"segment {value!r} promises {count} roles")


def test_the_out_of_band_refresh_ships_the_folded_counts(client, dupes):
    """The counts that survive an htmx swap are the folded ones too.

    The filter bar sits outside `#cov-results`, so its numbers are re-sent as
    out-of-band spans (`_filter_counts.html`). That fragment reads
    `role_segments`, the same list the initial render draws from, which is
    what stops the bar drifting back to unfolded numbers after the first
    keystroke — the exact failure mode that fragment exists to prevent.
    """
    body = client.get(reverse("opportunities"),
                      HTTP_HX_REQUEST="true").content.decode()
    oob = re.search(r'<span id="cnt-role-campus" hx-swap-oob="innerHTML">(\d+)</span>',
                    body)
    assert oob, "the campus segment's count must ship in the out-of-band swap"
    assert oob.group(1) == "2"


# ---------------------------------------------------------------------------
# 2. ONE CONTROL SHAPE.
#
# networkly.css's `.btn` rule (L1089-1093) states it: "Status chips keep the
# pill; controls don't." The board was the last page ignoring it — Save, Read,
# "Save them all" and Undo were all 999px under a filter bar squared to
# `--r-ctl` in the same pass, so a student met both shapes on one screen.
# ---------------------------------------------------------------------------

SQUARED = [
    (".track-btn", "Save / Saved — writes a row"),
    # `.scope-act` until 2026-09-02, when the blue banner it belonged to was
    # folded into the Picked column. Same control, same argument: the button
    # writes rows, so it is squared. It now commits to at most the six cards
    # rendered under it (`DEFAULT_LIMIT`), which is why the cap this line used
    # to name is gone rather than restated.
    (".pickcol-save", "Save all — writes the column's unsaved picks"),
    (".rcd-undo", "Undo — reverses a dismissal"),
    # 2026-09-03. The last 999px pressable in the filter bar. It survived the
    # 2026-08-22 squaring because the segments beside it were pills too, so it
    # did not look out of place; with the round shape moved onto the segmented
    # control's own track (where it is the GROUP's capsule) a stadium-shaped
    # "Clear" was the one button in the bar still wearing a badge shape.
    (".filters-clear", "Clear — drops every active filter"),
]

# Kept as capsules, each for a stated reason.
PILLED = [
    (".track-chip", "read-only funnel status: Applied, Interviewing, Offer"),
]


@pytest.mark.parametrize("selector,why", SQUARED)
def test_mutating_and_filter_controls_have_usable_shapes_and_target_sizes(selector, why):
    body = _rule(_css(), selector)
    assert "border-radius:" in body and "999px" not in body, why
    height = re.search(r"min-height:\s*(\d+(?:\.\d+)?)px", body)
    assert height and float(height.group(1)) >= 40, why


@pytest.mark.parametrize("selector,why", PILLED)
def test_application_state_links_are_named_and_semantically_distinct(selector, why):
    css = _css()
    assert "var(--accent-ink)" in _rule(css, selector), why
    assert "var(--ok)" in _rule(css, selector + ".track-offer")
    assert "var(--stale-t)" in _rule(css, selector + ".track-interview")
    assert "var(--ink-2)" in _rule(css, selector + ".track-closed")


def test_role_type_controls_wrap_as_coherent_label_count_pairs():
    css = _css()
    group = _rule(css, ".seg-list")
    control = _rule(css, ".filters .seg-pill")
    assert "flex-wrap: wrap" in group
    assert "flex-direction: row" in control
    assert "white-space: nowrap" in control
    assert "box-shadow: none" in control
    assert "font-variant-numeric: tabular-nums" in _rule(css, ".seg-count")


def test_the_shared_reading_presentation_loads_on_every_directory_page():
    from .test_tracking import _user
    Firm.objects.get_or_create(slug="sig", defaults={"name": "Susquehanna"})
    anonymous, signed_in = Client(), Client()
    signed_in.force_login(_user())
    for client_, path in ((anonymous, "/opportunities/"), (anonymous, "/firms/sig/"),
                          (signed_in, reverse("my_applications"))):
        html = client_.get(path).content.decode()
        css = presentation_css(html)
        assert "directory-page" in html and "directory-drawer" in html
        assert "min-height:" in _rule(css, ".meta-read")
        assert "position: sticky" in _rule(css, ".drawer-apply")


# ---------------------------------------------------------------------------
# 3. THE DUE FIGURE'S COLOUR.
# ---------------------------------------------------------------------------


def test_the_closing_soon_figure_uses_the_text_tier_not_the_bar_tier():
    """`.rr-due-n.meta-soon` is the "6d" on every role closing inside a week —
    the one figure on a board of 649 rows that is supposed to shout.

    It was painted `--w-chatted-bar`, which is a FILL colour for the warmth
    meter's 4px band and was never a text value. Measured on the rendered
    page: 3.98:1 in light and 3.12:1 in dark at 12px, both under AA's 4.5.
    `--w-chatted-t` is the same warmth family's text tier: 6.89:1 light and
    6.63:1 dark, measured the same way after the change.
    """
    body = _rule(_css(), ".rr-due-n.meta-soon")
    assert "var(--w-chatted-t)" in body
    assert "--w-chatted-bar" not in body


# ---------------------------------------------------------------------------
# 4 + 11. WHAT IS ALLOWED TO MOVE.
#
# Two rules, both from the audit's motion inventory: an infinite animation is
# earned only by a live state, and a number may not animate through values it
# does not hold.
# ---------------------------------------------------------------------------


def test_the_rolling_dot_does_not_pulse_forever():
    """"Rolling" is a state, not an event. `.rolling-dot::after` ran
    `pulse-ring` on an infinite loop on every rolling role — ten on the first
    viewport, sixty-odd down one scrolled column. networkly.css's own
    `.live-dot` (L2125-2137) already made this argument and removed its own
    ring. The colour carries the signal; nothing needs to move."""
    css = _css()
    assert ".rolling-dot::after" not in css
    assert "pulse-ring" not in css


def test_no_looping_animation_survives_on_the_board():
    """The general form of the rule above, so the next ring cannot be added
    without a state to bind it to.

    `.cols-loading::after` is the one exception and is named rather than
    pattern-matched, so adding a second means editing this list and writing
    down why. It earns the loop: it is the lazy-load sentinel's own spinner,
    on screen only while more columns are actually in flight, which is
    precisely the "bound to a live state" test the rule states.
    """
    css = _css()
    looping = {
        " ".join(prelude.split())
        for prelude, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css)
        if re.search(r"\banimation(?:-name)?:[^;}]*\binfinite\b", body)
    }
    assert looping <= {".cols-loading::after"}, looping


def test_the_strip_figures_do_not_animate_through_false_values():
    """`ss-pop` scaled every figure 0.6 -> 1.08 -> 1 over 620ms on load.

    A number that GROWS reads as a number resolving, so for half a second
    "2596 Open Roles" was a smaller figure at a smaller size and a reader
    could not tell a render from a count. Nothing had changed; the page had
    merely loaded. The settle is opacity and colour now — the figure is at
    its final size and its final value from the first frame it is legible.
    """
    css = _css()
    assert "ss-pop" not in css
    for _name, body in re.findall(r"@keyframes\s+(ss-settle\w*)\s*\{(.*?)\}\s*\n", css, re.S):
        assert "scale" not in body
        assert "transform" not in body


def test_board_mutations_keep_busy_error_and_reversal_feedback():
    root = pathlib.Path(__file__).resolve().parents[2]
    code = (root / "static/js/widgets.js").read_text()
    assert '"aria-busy"' in code and '"widget-pending"' in code
    assert "htmx:afterRequest" in code and "widget-request-error" in code
    track = (root / "templates/directory/_track_control.html").read_text()
    dismissed = (root / "templates/directory/_rolecard_dismissed.html").read_text()
    assert 'class="track-btn is-saved"' in track
    assert 'role="status"' in dismissed and '>Undo</button>' in dismissed
    assert '"status": "undismiss"' in dismissed


def test_directory_motion_respects_reduced_motion():
    css = _css()
    guarded = media_blocks(css, r"prefers-reduced-motion:\s*reduce")
    for scope in (".directory-page *", ".directory-drawer *"):
        body = _rule(guarded, scope)
        assert "animation: none" in body
        assert "transition-duration: 0s" in body
    code = (pathlib.Path(__file__).resolve().parents[2] / "static/js/widgets.js").read_text()
    assert "prefers-reduced-motion: reduce" in code and "reduced.matches" in code


# ---------------------------------------------------------------------------
# 5 + 6. THE DARK BOARD.
# ---------------------------------------------------------------------------


def test_long_firm_lists_show_complete_rows_with_expansion_controls():
    css = _css()
    body = _rule(css, ".firmcol-scroll")
    assert "overflow: visible" in body
    assert "max-height: none" in body
    assert "max-height: none" in _rule(css, ".firmcol.is-expanded .firmcol-scroll")
    template = (pathlib.Path(__file__).resolve().parents[2] / "templates/directory/_columns.html").read_text()
    assert "data-widget-expand" in template
    assert 'aria-expanded="false"' in template and 'aria-controls="firm-roles-' in template


def test_monogram_and_picked_tiles_inherit_the_active_theme():
    css = _css()
    mono = _rule(css, ".firmcol-logo")
    picked = _rule(css, ".firmcol-logo.firmcol-logo--picked")
    assert "background: var(--surface)" in mono and "color: var(--ink-2)" in mono
    assert "background: var(--accent-soft)" in picked and "color: var(--accent-ink)" in picked
    assert "hsl(" not in mono
    assert "object-fit: contain" in _rule(css, ".firmcol-logo img")


# ---------------------------------------------------------------------------
# 8 + 10. ONE ROW SHAPE PER PAGE, AND NO RULES FOR MARKUP NOBODY EMITS.
# ---------------------------------------------------------------------------


@pytest.fixture
def firm_page(db):
    f = Firm.objects.create(slug="td", name="TD Securities")
    for i in range(20):
        Opportunity.objects.create(
            firm=f, url=f"https://td/{i}", title=f"2027 Summer Analyst {i}",
            bucket="internship", status="open", region="us")
    return f


def test_firm_roles_and_observed_activity_are_open_ruled_lists(firm_page):
    css = _css("/firms/td/")
    for selector in (".frow", ".cyc-obs-row"):
        body = _rule(css, selector)
        assert "border-bottom: 1px solid var(--line)" in body, selector
        assert "var(--shadow" not in body, selector
    role = _rule(css, ".frow")
    assert "border-radius: 0" in role and "background: transparent" in role
    assert "grid-template-columns:" in role and "minmax(0, 1fr)" in role


def test_the_retired_fuse_bar_leaves_no_rules_behind(firm_page):
    """The fuse was the depleting countdown bar the 2026-08-30 row redesign
    replaced. Eight rules and two keyframes outlived the markup: no template
    has emitted `.fuse-fill` since, and `core/home.html`'s `.v-fuse-fill` is
    a different rule in a different file for the landing mock.

    Deleting it also removes the last hardcoded light-mode colour in this
    stylesheet (`#c1652f`, the light `--w-chatted-bar`), which would have
    painted a light-mode bar on a dark board had anything drawn it.
    """
    for path in ("/opportunities/", "/firms/td/"):
        css = _css(path)
        for dead in ("fuse-fill", "fuse-burn", "fuse-today", "fuse-soon",
                     "fuse-upcoming", "fuse-passed", "pulse-red"):
            assert dead not in css, f"{dead} still styles on {path}"


def test_a_capped_group_says_how_many_it_left_out(firm_page):
    """The cap is 12 rows per KIND group (`ROLE_ROWS_PER_GROUP`), and a
    capped group hands the remainder to the feed rather than dropping it.

    Pinned here because the row restyle above changes what a long group looks
    like and not how long it is: an uncapped group is how one firm's page
    became 74 screens of scroll, and a page that just got quieter is a page
    where a regression here would be harder to notice, not easier.
    """
    html = Client().get("/firms/td/").content.decode()
    assert html.count('<article class="frow">') == 12
    assert "Show the other 8 in Opportunities" in html


# ---------------------------------------------------------------------------
# 7. THE DRAWER'S BODY.
# ---------------------------------------------------------------------------


def _drawer(text: str) -> str:
    """The drawer fragment for one posting whose text `enrich_postings` has
    fetched. `raw["detail_text"]` is the field the view reads (see
    `role_description`); `facts.paragraphs()` turns it into `blocks`."""
    f, _ = Firm.objects.get_or_create(slug="gs", defaults={"name": "Goldman Sachs"})
    o = Opportunity.objects.create(
        firm=f, url=f"https://gs/{len(text)}", title="Summer Analyst",
        bucket="internship", status="open", region="us",
        raw={"detail_text": text})
    return Client().get(reverse("role_description", args=[o.pk])).content.decode()


def test_a_long_posting_is_folded_and_a_short_one_is_not():
    """The median fetched posting is one unbroken block: `facts.paragraphs()`
    splits on the posting's own section headings and most scrapes have none.
    Measured on the founder's first row, the drawer opened onto 2,741
    characters in two blocks — 651px of solid text with the provenance note
    and the apply link pushed under it. A student opens this to DECIDE, and
    the deciding happens in the first screen.

    The threshold reads the WHOLE description, not one block, so three short
    paragraphs adding up to 400 characters get no fold and one 3,800-character
    paragraph does.

    Nothing is cut: the fold is a CSS clamp (see `_drawer.html`), so the full
    text stays in the DOM for find-in-page and for a screen reader, and where
    `:has()` is missing the drawer renders exactly as it did before.
    """
    long_body = "The programme runs ten weeks. " * 40      # ~1,200 chars
    html = _drawer(long_body)
    assert 'class="drawer-fold"' in html
    assert 'class="drawer-prose"' in html
    # The whole text is still there. The fold is a clamp, not a cut.
    assert html.count("The programme runs ten weeks.") == 40


def test_a_short_posting_gets_no_fold():
    short = "We are hiring a summer analyst in New York. Apply by October."
    html = _drawer(short)
    assert 'class="drawer-fold"' not in html
    assert 'class="drawer-prose"' not in html
    assert short.split(".")[0] in html


# ---------------------------------------------------------------------------
# The two remaining audit enhancements, both of which turned out to be one
# line of markup and are pinned so they stay.
# ---------------------------------------------------------------------------


def test_picked_identity_is_distinct_without_repeated_eyebrow_copy():
    css = _css()
    assert ".fc-eyebrow" not in css
    tile = _rule(css, ".firmcol-logo.firmcol-logo--picked")
    assert "var(--accent-soft)" in tile and "var(--accent-ink)" in tile
    assert "var(--accent-ink)" in _rule(css, ".firmcol--picked .firmcol-name")


def test_the_picked_columns_header_spends_the_same_two_rows_a_firms_does():
    """REWRITTEN 2026-09-02. Its premise was the eyebrow's POSITION: the word
    had to ride `.firmcol-stats` rather than take a line of its own above the
    name, because a line of its own measured 141px of header against every
    firm column's 126 and dropped this column's first role row 15px below the
    row it belongs to.

    There is no eyebrow to place any more. The invariant it was protecting —
    this header must not grow a row its neighbours do not have — is now
    structural, and stronger: the head is a two-row grid, the name is row one
    and `.firmcol-stats` is row two, in both columns.

    Asserted against the TEMPLATES, not a rendered page, for the reason the
    original gave: the Picked column only draws for a student whose profile
    scores picks, so a rendered assertion would silently skip on most
    fixtures, and this test exists precisely because the defect it guards was
    invisible until measured.
    """
    here = pathlib.Path(__file__).resolve().parents[2] / "templates" / "directory"
    # `_pickcol.html` since 2026-09-02: the column moved into its own partial
    # so a dismissal on a card elsewhere can swap it out of band. Same markup,
    # same invariant, one file along.
    picked = (here / "_pickcol.html").read_text()
    assert "fc-eyebrow" not in picked
    heading = picked.index('id="pickcol-h"')
    stats = picked.index('<div class="firmcol-stats">')
    meta = picked.index('class="firmcol-meta"')
    assert heading < stats < meta, (
        "the Picked column's count line moved out of the stats row; that is a "
        "third row in a header whose neighbours have two")
    # "Save all" is the header's own control and belongs BELOW both rows, on
    # its own auto-placed line. Inside `.firmcol-stats` it would be competing
    # with the count line it acts on; above the name it would be a row this
    # header has and its neighbours do not.
    assert meta < picked.index("pickcol-save")

    firms = (here / "_columns.html").read_text()
    fstats = firms.index('<div class="firmcol-stats">')
    fmeta = firms.index('class="firmcol-meta"')
    ftier = firms.index('class="firmcol-tier')
    assert fstats < fmeta < ftier, (
        "a firm column's category, open count and tier belong on ONE line "
        "inside .firmcol-stats — stacked, they are the three-row block beside "
        "a square tile that the founder's review called cluttered")
    assert firms.index('class="firmcol-h"') < fstats


def test_the_mobile_filter_disclosure_carries_its_active_count(client, db):
    """filter-bar-redesign.md §F: the 375px summary reads "Filters · n".

    The count comes from `filters_more_active`, computed server-side and also
    frozen into the script that decides whether the disclosure may close — so
    a summary that stopped naming it would mean a deep-linked filter could be
    both invisible and unannounced.
    """
    f = Firm.objects.create(slug="ms", name="Morgan Stanley", tracks=["ib"])
    Opportunity.objects.create(firm=f, url="https://x/1", title="Summer Analyst",
                               bucket="internship", status="open", region="us")
    plain = client.get(reverse("opportunities")).content.decode()
    assert ">Filters</summary>" in plain

    two = client.get(reverse("opportunities"), {"region": "us", "track": "ib"})
    assert two.context["filters_more_active"] == 2
    assert "Filters · 2</summary>" in two.content.decode()


# ---------------------------------------------------------------------------
# THE ONE STRING ON THE ROW THAT COULD BE CUT WITH NO WAY TO READ IT
# (2026-09-02).
#
# `.rr-title a` is `-webkit-line-clamp: 2`. Measured on the founder's own
# board with `content-visibility` forced off so off-screen rows reported real
# geometry rather than their placeholder: 25 of 311 rows overflowed that clamp
# at 1280px and 64 of 311 at 375px, and all but one of them carried no `title`
# attribute at all — the attribute was emitted only on the ~3% of rows with an
# `unconfirmed` note. So "Central Relationship Management Corporate and
# Institutional Banking Interns…" ended there, and the only way to read the
# rest was to open the posting.
#
# Every other truncating part of this row already does the opposite. `.rr-loc`
# is capped at 205px and its own comment states the rule: "the full string has
# to survive the cut somewhere". `.rr-why` ellipsises at the row's edge and
# keeps every sentence in `pick_why_title`. The title, which is the row's most
# important string, was the exception.
# ---------------------------------------------------------------------------

_LONG_TITLE = ("Central Relationship Management Corporate and Institutional "
               "Banking Internship Hong")


@pytest.fixture
def long_titled_row(db):
    """One role whose title outruns two clamped lines, which is the case the
    `title` attribute exists for. The string is a real one off the founder's
    board (HSBC, and truncated at the source — see `enrich_postings`)."""
    f = Firm.objects.create(slug="hsbc", name="HSBC", tracks=["ib"])
    Opportunity.objects.create(
        firm=f, url="https://x/1", title=_LONG_TITLE, bucket="internship",
        status="open", location="Hong Kong", region="apac")
    return f


def _title_anchor(body: str) -> str:
    return body[body.index('class="rr-title"'):][:900]


def test_every_role_row_carries_its_whole_title_in_the_hover(client, long_titled_row):
    """The clamp may cut the face; it may not cut the record.

    ON EVERY ROW, not only the ones that overflow. Whether two lines are
    enough depends on the rendered width, the viewport and the reader's font,
    none of which the template can know — the same argument `.rr-loc` makes
    for always carrying its own text. Repeating a short title in its tooltip
    adds no claim: it is the same string the anchor already holds.
    """
    anchor = _title_anchor(client.get(reverse("opportunities")).content.decode())
    assert f'title="{_LONG_TITLE}"' in anchor, (
        "the row's own title must survive the two-line clamp in the hover; "
        f"got: {anchor[:400]}")
    # And it is still the link's visible text, not only its tooltip.
    assert f">{_LONG_TITLE}<" in anchor


def test_a_stale_rows_note_joins_the_title_in_the_hover_instead_of_evicting_it(
        client, long_titled_row):
    """`unconfirmed` used to own this attribute alone, which made the ~3% of
    rows carrying a staleness note the ONLY rows whose full title could be
    recovered — and on exactly those rows the note had displaced the title
    rather than joined it.

    Both facts share one hover now, in the parentheses the `.vh` span beside
    it already uses for the same note, so one pointer answers "what is this
    role called" and "why is it greyed out" together.
    """
    from datetime import timedelta

    from django.utils import timezone

    o = Opportunity.objects.get(firm=long_titled_row)
    o.last_verified = timezone.now() - timedelta(days=40)
    o.last_checked = timezone.now()
    o.save(update_fields=["last_verified", "last_checked"])

    anchor = _title_anchor(client.get(reverse("opportunities")).content.decode())
    assert "is-unconfirmed" in anchor, (
        "fixture no longer trips the staleness threshold, so this test is no "
        "longer exercising the two-facts-one-attribute case it exists for")
    start = anchor.index('title="') + len('title="')
    attr = anchor[start:anchor.index('"', start)]
    assert attr.startswith(_LONG_TITLE), (
        f"the title must lead its own hover, not be evicted by the note: {attr}")
    assert len(attr) > len(_LONG_TITLE) and attr.rstrip().endswith(")"), (
        f"the staleness sentence rides in parentheses after it: {attr}")
