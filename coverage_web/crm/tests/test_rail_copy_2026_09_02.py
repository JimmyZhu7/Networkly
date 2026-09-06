"""Today rail contracts: keep exact facts, explicit timing, accessible labels,
and actionable market assignment across presentation changes.

The September 5 workspace separates progress from contact cleanup. Browser
checks own responsive geometry; these assertions protect meaning and actions.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from crm.models import Contact, Touch
from crm.today import _next_deadlines, _recent_activity
from directory.models import Firm, FirmDate

pytestmark = pytest.mark.django_db

User = get_user_model()

STYLES = Path(__file__).resolve().parents[2] / "templates" / "crm" / "_styles.html"
COCKPIT = Path(__file__).resolve().parents[2] / "templates" / "crm" / "_cockpit.html"


def _user(email="rail@example.com", tracks=("st",)):
    return User.objects.create_user(
        email=email, password="pw12345!", regions=["us", "hk"],
        tracks=list(tracks),
    )


def _page(user) -> str:
    from django.test import Client
    client = Client()
    client.force_login(user)
    res = client.get(reverse("crm:week"))
    assert res.status_code == 200
    return res.content.decode()


def _styles_of(html: str, *, strip_comments: bool = False) -> str:
    """EVERY <style> block on the page, joined.

    Not the first. The page carries more than one and which block holds a
    given rule is the base template's business, not this file's — reading
    only the first is how four guards broke on the night of 2026-09-01.

    `strip_comments` for the assertions that say a rule is GONE: this
    stylesheet explains itself at length directly above each rule, and the
    comment explaining why `.pace-ring` was deleted contains the string
    `.pace-ring`. Same class of trap as `_rules` in
    `directory/tests/test_styles_block.py` — the file's own prose is inside
    the string under test.
    """
    blocks = re.findall(r"<style[^>]*>(.*?)</style>", html, re.S)
    assert blocks, "the page no longer renders a <style> block"
    css = "\n".join(blocks)
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S) if strip_comments else css


def _face(markup: str) -> str:
    """The plain text of a slice of markup, tags stripped.

    Needed from 2026-09-02: the word "good" moved OFF the send-window row
    and INTO its `title`, so `"good " in card` now passes on the strength of
    the attribute that replaced it. Same trap `_styles_of(strip_comments=)`
    guards against one function up, one attribute over. Any assertion about
    what a student READS goes through here; assertions about a `title` read
    the markup directly and say so.
    """
    return " ".join(re.sub(r"<[^>]+>", " ", markup).split())


def _card(html: str, heading: str) -> str:
    """One rail card, so an assertion about it cannot be satisfied by the
    rest of a large page."""
    # Decorative heading icons do not change the widget's visible name.
    title = next((m for m in re.finditer(r'<h3 class="rail-title"[^>]*>(.*?)</h3>', html, re.S)
                  if _face(m.group(1)).startswith(heading)), None)
    assert title is not None, f"missing widget heading: {heading}"
    start = title.start()
    return html[start:html.index("</div>", start)]


def _rail_widget(html: str, class_name: str) -> str:
    """Read one named widget, including its nested markup."""
    match = re.search(r'<(?P<tag>div|section) class="[^"]*\b' + re.escape(class_name) + r'\b[^"]*"[^>]*>', html)
    assert match, f"missing widget: {class_name}"
    tag = match.group("tag")
    depth = 0
    for token in re.finditer(r'</?' + tag + r'\b[^>]*>', html[match.start():]):
        depth += -1 if token.group(0).startswith("</") else 1
        if not depth:
            return html[match.start():match.start() + token.end()]
    raise AssertionError(f"unclosed widget: {class_name}")


def _pace_card(html: str) -> str:
    return _rail_widget(html, "pace-card")


def _css_rule(css: str, selector: str) -> str:
    flat = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    m = re.search(r"^\s*" + re.escape(selector) + r"\s*\{(.*?)\}", flat, re.S | re.M)
    assert m, f"no rule found for {selector}"
    return m.group(1)


# ---------------------------------------------------------------------------
# 1. Schedule — the send-window hints.
# ---------------------------------------------------------------------------
def _st_user_with_two_markets(email="rail@example.com"):
    """An S&T student with contacts in both markets AND something on the
    schedule.

    The second half is not decoration: the hints render inside the Schedule
    card, which is gated on a non-empty `schedule`, so a fixture with only
    contacts renders no card and no hint to assert about.
    """
    user = _user(email=email)
    for i, region in enumerate(["hk", "us"]):
        Contact.all_objects.create(
            user=user, name=f"Desk {region} {i}", region=region)
    booked = Contact.all_objects.create(
        user=user, name="Lily Liu", thread_state="chat_scheduled")
    Touch.all_objects.create(
        user=user, contact=booked, kind="reply_received", channel="email",
        ts=timezone.now() - dt.timedelta(days=1),
    )
    return user


def test_a_market_gets_one_row_and_not_a_sentence():
    """BEFORE: "HK desk good 9p to 10:30p, avoid 12:30a to 1:30a around the
    close", twice, wrapping to four rendered lines above a card whose subject
    is the day's schedule — most of the card, before a single scheduled thing
    appeared.

    A row per market, structurally: the hints are a list now, so "one idea per
    line" is enforced by the markup rather than by however wide the card
    happens to be.
    """
    card = _card(_page(_st_user_with_two_markets("row@example.com")), "Schedule")
    assert '<ul class="daybar-hint">' in card, (
        "the hints are a list of rows, not a wrapping paragraph of clauses"
    )
    assert card.count('<li class="dbh"') == 2, (
        "one row per market the student actually has contacts in"
    )


def test_the_close_is_no_longer_explained_in_the_copy():
    """"around the close" told the reader WHY that half hour is bad. It adds
    no time to avoid — `avoid` already carries a window of its own — so it was
    the sentence explaining the fact rather than the fact. It moved to the
    row's `title`, which is where a provenance fact lives on this page."""
    card = _card(_page(_st_user_with_two_markets("close@example.com")), "Schedule")
    assert "around the close" not in card
    assert "either side of that market's close" in card, (
        "the reason the window is bad is still available, in the row's title"
    )


def test_both_windows_survive_the_diet():
    """The good window and the avoid window are two different facts, and a
    good window with no avoid window is a smaller claim, not a shorter one.
    Nothing here trades a fact for a line.

    REWRITTEN 2026-09-02, fourth pass. It read `"good " in hk`, and "good"
    moved into the row's `title` that night, so the old assertion would now
    pass on the strength of the attribute that replaced the word it was
    guarding. Read off the FACE instead, which is the only place a window
    the student can act on counts.
    """
    card = _card(_page(_st_user_with_two_markets("both@example.com")), "Schedule")
    hk = _face(re.search(r'<li class="dbh"[^>]*>(.*?)</li>', card, re.S).group(1))
    assert "send " in hk.lower() and "avoid " in hk.lower(), (
        "two windows, still two: a send window and an avoid window"
    )
    # A pair of clock times on each side. Matched rather than spelled out:
    # `_local_clock` renders on the READER's timezone, so the digits differ
    # with the test user's, and the claim here is that both windows still
    # print two hours and not that they print any particular two.
    pairs = re.findall(r"\d{1,2}(?::\d\d)?[AP]M to \d{1,2}(?::\d\d)?[AP]M", hk)
    assert len(pairs) == 2, f"expected a send window and an avoid window; got {hk!r}"
    assert "desk" in hk, "the row still says whose day this is a fact about"


def test_the_send_window_leads_with_a_verb_and_says_what_it_is_for():
    """"HK desk good 9PM to 10:30PM" led its clause with a bare adjective, so
    the first three words parse as a verdict on the desk until the time
    arrives to correct them. It also never said what the window was FOR: this
    row is `crm.today._send_windows`, the answer to "when is it worth
    writing", and the card above it is titled Schedule, so nothing on screen
    connected the hours to an email.

    "send" is the verb the function is named for and the same four characters
    "good" was, so the pair now reads as two imperatives in one register --
    send then, avoid then. Measured: one line at 1280 and at 375, both
    schemes, unchanged.
    """
    card = _card(_page(_st_user_with_two_markets("verb@example.com")), "Schedule")
    # The WHOLE <li>, opening tag included: the word this test says has moved
    # into the `title` is in the attribute, not in the element's children.
    row = re.search(r'<li class="dbh".*?</li>', card, re.S).group(0)
    face = _face(row)
    assert " send " in f" {face.lower()} ", "the window states the action it is a window for"
    assert "good" not in face, (
        "an adjective is leading the clause again; the word belongs in the "
        "title, where the reason the window is good lives"
    )
    assert "good window" in row, (
        "the fact that this half hour is the GOOD one is still stated, in "
        "the title"
    )


def test_the_windows_say_whose_clock_they_are_on():
    """THE FACT THIS PASS ADDED, and the only one it did.

    `crm.today._local_clock` converts every one of these hours into the
    reader's own timezone -- that conversion is the whole feature -- and the
    card said so nowhere. "HK desk send 9PM" with no such note reads as 9PM
    in Hong Kong, which is the one misreading on these three cards that costs
    a student a real send at a real wrong hour.

    In the `title` and not on the face, because it is provenance and not a
    thing to act on, and because the row measured full at both widths. The
    words are the Deadlines card's own, which already says "your own clock"
    about the same idea one card down.
    """
    card = _card(_page(_st_user_with_two_markets("clock@example.com")), "Schedule")
    assert "your own clock" in card


def test_send_and_avoid_windows_have_visible_labels():
    card = _card(_page(_st_user_with_two_markets("shape@example.com")), "Schedule")
    assert card.count('<span class="dbh-label">Send</span>') == 2
    assert card.count('<span class="dbh-label">Avoid</span>') == 2
    assert "your timezone" in _face(card)


def test_an_ib_only_student_still_gets_no_hint_at_all():
    """P1 and the scoping in `_send_windows`: the source is a trading floor's
    day. Reshaping the copy must not widen who it is shown to."""
    user = _user(email="ib@example.com", tracks=("ib",))
    Contact.all_objects.create(user=user, name="Banker", region="hk")
    booked = Contact.all_objects.create(
        user=user, name="Booked", thread_state="chat_scheduled")
    Touch.all_objects.create(
        user=user, contact=booked, kind="reply_received", channel="email",
        ts=timezone.now() - dt.timedelta(days=1),
    )
    # The Schedule card itself renders; the hint block inside it does not.
    # Asserted on the MARKUP, not on the page text: `.daybar-hint` is styled
    # in the shared block whether or not any student sees it.
    card = _card(_page(user), "Schedule")
    assert '<ul class="daybar-hint">' not in card


def test_a_chat_with_no_time_is_agreed_and_does_not_claim_to_be_booked():
    """"Lily Liu · chat set up" sat beside "no time yet" and contradicted it
    inside five words: a chat that is SET UP is a chat with a time on it, and
    this branch of `crm.today._schedule` exists precisely because no time is
    known. The stored value's own display label over-claims the same way
    ("Chat scheduled", `crm.utils`) -- right for a booked chat, wrong for
    every row this branch builds.

    "agreed" is what the state actually asserts and nothing further:
    `thread_state="chat_scheduled"` is reached off a reply saying yes
    (`crm.relevance.INBOUND_TOUCH_KINDS`) or off the student logging that it
    was agreed, and neither of those events knows a time.

    Nothing about the row's shape moved, and the person is still named.
    """
    card = _card(_page(_st_user_with_two_markets("chat@example.com")), "Schedule")
    face = _face(card)
    assert "Lily Liu · chat agreed" in face
    assert "set up" not in face, (
        "the row claims a chat is arranged on a card that says it has no time"
    )


def test_the_time_column_still_says_the_time_is_missing():
    """"no time yet" is UNCHANGED and this pins that it stays that way.

    It sits in `.activity-when`, the column holding "2p today", "Fri" and
    "in 58d" on every other row of this rail, and the honest occupant of a
    time column is the absence of a time. Rewriting it as an ask ("needs a
    time") was considered in the same pass and rejected: it would be the only
    imperative in that column anywhere on the page, and the row already has
    a verb -- the chat was agreed and the time is what is outstanding.
    """
    card = _card(_page(_st_user_with_two_markets("when@example.com")), "Schedule")
    when = re.findall(r'<span class="activity-when[^"]*">(.*?)</span>', card, re.S)
    assert "no time yet" in [w.strip() for w in when], (
        "the row no longer says a time is missing; it is the only thing in "
        "the product that does"
    )


# ---------------------------------------------------------------------------
# 2. Deadlines — three fields, and two day counts that pointed opposite ways.
# ---------------------------------------------------------------------------
def _deadline_user():
    user = _user(email="dl@example.com", tracks=("ib",))
    firm = Firm.objects.create(slug="hsbc", name="HSBC")
    FirmDate.objects.create(
        firm=firm, cycle="sa2028", event_kind="applications_close",
        date=timezone.localdate() + dt.timedelta(days=58),
        confidence=1.0, precision="day", region="hk",
    )
    return user


def test_the_market_is_a_chip_and_not_a_third_word_in_a_phrase():
    """BEFORE: the market and the event label were both plain
    `.activity-kind` spans separated by a space, so the row read "HSBC HK
    Applications close" — a firm, a market and an event with no seam, which
    parses as one confusing phrase and not as three fields.

    The market is the shortest and most categorical of the three, so it is the
    one that becomes the chip."""
    card = _card(_page(_deadline_user()), "Deadlines")
    assert '<span class="dl-market">HK</span>' in card
    assert "HSBC" in card and "applications close" in card.lower(), (
        "all three fields survive the separation"
    )


def test_the_market_chip_is_styled():
    """A chip whose class is styled nowhere renders as bare text in the middle
    of a designed page, and no markup assertion would notice."""
    css = _css_rule(_styles_of(_page(_deadline_user())), ".dl-market")
    assert "border" in css, "a chip needs an edge or it is not a seam"


def test_a_countdown_says_which_direction_it_points():
    """THE DEFECT, in the founder's own screenshot: "58d" on the right of a
    row and "24d" an inch under it, two identical-looking day counts pointing
    in OPPOSITE directions of time. 58 days until an application close; 24
    days a posting has ALREADY been open, an elapsed figure that
    `directory.open_runs` argues at length is explicitly not a forecast.

    This is a presentation fix and not a data change: `days` is untouched, no
    number moved, nothing was dropped. The rail's rule is now stated on both
    sides — a bare "Nd" is time already spent, and a future distance says
    "in".
    """
    user = _deadline_user()
    row = _next_deadlines(user, timezone.localdate())[0]
    assert row["when"] == "in 58d"
    assert row["days"] == 58, "the number itself did not move"


def test_today_is_still_today_and_not_in_0d():
    """Zero days away is not a distance, and "in 0d" would be the kind of
    mechanical phrasing that reads as a bug."""
    user = _user(email="dl0@example.com", tracks=("ib",))
    firm = Firm.objects.create(slug="ms", name="Morgan Stanley")
    FirmDate.objects.create(
        firm=firm, cycle="sa2028", event_kind="applications_close",
        date=timezone.localdate(), confidence=1.0, precision="day", region="us",
    )
    assert _next_deadlines(user, timezone.localdate())[0]["when"] == "today"


def test_the_two_day_counts_on_one_card_can_no_longer_read_alike():
    """The pair, checked together on the rendered card rather than one at a
    time — the defect only existed because they shared a card."""
    from directory.models import Opportunity
    user = _deadline_user()
    firm = Firm.objects.get(slug="hsbc")
    today = timezone.localdate()
    for i, age in enumerate([70, 24, 20, 9]):
        o = Opportunity.objects.create(
            firm=firm, title=f"SA {i}", bucket="internship", status="open",
            url=f"https://x.test/hsbc/{i}",
        )
        Opportunity.objects.filter(pk=o.pk).update(
            first_seen=timezone.make_aware(
                dt.datetime.combine(today - dt.timedelta(days=age), dt.time(9)),
                dt.timezone.utc,
            )
        )
    card = _card(_page(user), "Deadlines")
    assert "in 58d" in card, "the countdown carries its direction"
    assert "oldest 24d" in card, "the elapsed figure is still stated"
    assert ">58d<" not in card, "a bare countdown is what caused the confusion"


def test_the_open_run_line_names_its_noun_and_points_backwards():
    """"18 open, longest 24d" was the most cryptic line on the rail: four
    words carrying a census, a subject and an age, and stating one of them.

    TWO FIXES, NEITHER OF THEM A CUT.

    "18 open" named no noun, so the reader supplied one from the row above
    it, where the only candidates were applications and deadlines -- neither
    of which is what this counts. "roles" is the word the Opportunities feed
    and every firm page already use for exactly these rows ("See open roles",
    "No campus roles open right now"), so the line joins the vocabulary a
    student meets everywhere else. No `pluralize`: `firm_open_runs` drops any
    firm under `CYCLE_OBSERVATION_MIN_SAMPLE`, so the count is three or more
    or the line does not render.

    "longest" was the half of the 2026-09-02 direction bug that the "in 58d"
    fix did not reach. A countdown an inch above now states its direction,
    but "longest 24d" still reads forward -- "open longest", "lasts longest"
    -- which is the exact confusion this card was rewritten to end.
    "oldest" is a superlative of age and cannot point forward, so the elapsed
    reading is the only one available and the rail's bare-Nd rule is restated
    on the line rather than relied on from elsewhere.

    Measured at the widest values this line holds (236 roles open, oldest
    124d): one line at 1280 and at 375, both schemes, as before.
    """
    from directory.models import Opportunity
    user = _deadline_user()
    firm = Firm.objects.get(slug="hsbc")
    today = timezone.localdate()
    for i, age in enumerate([70, 24, 20, 9]):
        o = Opportunity.objects.create(
            firm=firm, title=f"SA {i}", bucket="internship", status="open",
            url=f"https://x.test/hsbc/{i}",
        )
        Opportunity.objects.filter(pk=o.pk).update(
            first_seen=timezone.make_aware(
                dt.datetime.combine(today - dt.timedelta(days=age), dt.time(9)),
                dt.timezone.utc,
            )
        )
    card = _card(_page(user), "Deadlines")
    face = _face(card)
    # Three, not four: the 70-day row predates this firm's onboarding cutoff,
    # so `open_run_days` returns None for it and it is not counted at all.
    assert "3 roles open, oldest 24d" in face
    assert "longest" not in face, (
        "the forward-reading superlative is back on a backward-reading figure"
    )
    # And the fact the noun is short for is where it already was.
    assert "Campus postings" in card, (
        "the title still says these are campus postings Coverage watched open"
    )


# ---------------------------------------------------------------------------
# 3. Contacts to place — the heading, the count and the verb.
# ---------------------------------------------------------------------------
def _unplaced_user():
    user = _user(email="unpl@example.com", tracks=("ib",))
    for i in range(3):
        Contact.all_objects.create(user=user, name=f"Arrival {i}", region="")
    return user


def test_market_assignment_names_the_missing_field_and_links_to_its_tool():
    card = _rail_widget(_page(_unplaced_user()), "unplaced-card")
    assert "No market · new this week" in _face(card)
    assert ">Assign markets</a>" in card
    assert f'href="{reverse("crm:contact_list")}?scope=unplaced"' in card


def test_market_assignment_count_keeps_its_period_and_missing_fact():
    card = _rail_widget(_page(_unplaced_user()), "unplaced-card")
    line = re.search(r'<p class="unplaced-count"[^>]*>(.*?)</p>', card, re.S).group(1)
    assert _face(line) == "3 contacts"
    assert "No market · new this week" in _face(card)
    assert "Arrival 0" not in card, "this summary should not repeat the full roster"


def test_market_assignment_explains_matching_without_claiming_inference():
    card = _rail_widget(_page(_unplaced_user()), "unplaced-card")
    assert "matches firm deadlines to contacts by market" in card
    assert "does not infer one" in card


# ---------------------------------------------------------------------------
# 4. Recent Activity — a label that repeated the heading, six times.
# ---------------------------------------------------------------------------
def test_the_activity_rail_does_not_say_ago_under_a_heading_that_says_recent():
    """Six rows each ending "ago" under a card titled Recent Activity. "ago"
    is grammar, not a fact — the heading already places every row in the
    past — and it is exactly the "no label that repeats the heading directly
    above it" rule.

    It also settles the rail's one shared reading rule from the other side:
    a bare "Nd" anywhere in this rail is elapsed time, and a future distance
    carries "in" (see the Deadlines tests above)."""
    user = _user(email="act@example.com", tracks=("ib",))
    contact = Contact.all_objects.create(user=user, name="Ada Lovelace")
    Touch.all_objects.create(
        user=user, contact=contact, kind="outreach", channel="email",
        ts=timezone.now() - dt.timedelta(days=10),
    )
    rows = _recent_activity(user, as_of=timezone.now())
    assert rows[0]["ago"] == "10d"
    card = _card(_page(user), "Recent Activity")
    assert "ago" not in card


def test_a_touch_logged_today_still_says_today():
    """"0d" is not how anyone says it, and the zero case was never the
    complaint."""
    user = _user(email="act0@example.com", tracks=("ib",))
    contact = Contact.all_objects.create(user=user, name="Grace Hopper")
    Touch.all_objects.create(
        user=user, contact=contact, kind="outreach", channel="email",
        ts=timezone.now(),
    )
    assert _recent_activity(user, as_of=timezone.now())[0]["ago"] == "today"


# ---------------------------------------------------------------------------
# 5. Pace — one week, stated once.
# ---------------------------------------------------------------------------
def test_the_pace_ring_is_gone_and_took_its_css_with_it():
    """THE COMPLAINT: "too complicated, refine with opus." The card stated one
    week four times — the ring's arc, the figure, the note, and the last bar
    of the sparkline. On the founder's own screenshot the week was 39 against
    a goal of 14, so `pace.pct` clamped to 100, the arc closed into a full
    circle, and the ring rendered as a plain outline indistinguishable from
    its own empty track. A meter that looks the same at 100% as at 0% is not
    a meter.

    Deleted rather than left as dead rules, which is the other half of the
    same cleanup.

    THE SPARKLINE FOLLOWED IT the same day (see
    `test_the_pace_card_carries_no_picture_at_all`), so the slice below can
    no longer end at `pace-spark` and ends at the card's own closing tag
    instead. `pace-grow` stays on the dead list and `mrail-grow` joins it:
    the sparkline's bars were the only thing in this stylesheet using it.
    """
    html = _page(_user(email="pace@example.com", tracks=("ib",)))
    # 'class="rail-card pace-card"' stopped matching once D-13's panel
    # primitive appended "panel" to the same attribute (2026-09-02).
    card = _pace_card(html)
    assert "pace-ring" not in card
    css = _styles_of(html, strip_comments=True)
    for dead in (".pace-ring", ".pace-track", ".pace-fill", "pace-grow",
                 ".pace-spark", "mrail-grow"):
        assert dead not in css, f"{dead} is dead CSS now that the ring is gone"


def test_weekly_outreach_preserves_the_exact_count_and_goal():
    user = _user(email="pace2@example.com", tracks=("ib",))
    contact = Contact.all_objects.create(user=user, name="Katherine Johnson")
    Touch.all_objects.create(user=user, contact=contact, kind="outreach", channel="email", ts=timezone.now())
    from crm.today import _cockpit_context
    pace = _cockpit_context(user)["pace"]
    card = _pace_card(_page(user))
    assert '<dd class="pace-done">1</dd>' in card
    assert f'<dd class="pace-goal">{pace["goal"]}</dd>' in card
    assert f'aria-valuetext="1 completed; weekly goal {pace["goal"]}"' in card
    assert "Last 8 weeks:" not in card


def test_weekly_count_and_goal_have_distinct_accessible_labels():
    card = _pace_card(_page(_user(email="pace3@example.com", tracks=("ib",))))
    assert 'aria-labelledby="weekly-outreach-title"' in card
    assert 'id="weekly-outreach-title">Weekly Outreach</h3>' in card
    assert re.search(r'<dt>Completed</dt>\s*<dd class="pace-done">\d+</dd>', card)
    assert re.search(r'<dt>Weekly goal</dt>\s*<dd class="pace-goal">\d+</dd>', card)


def test_weekly_progress_has_a_literal_accessible_value_without_fake_history():
    user = _user(email="pace4@example.com", tracks=("ib",))
    card = _pace_card(_page(user))
    assert card.count("<progress") == 1
    assert 'aria-label="Weekly outreach goal"' in card
    assert 'aria-valuetext="0 completed; weekly goal ' in card
    for drawing in ("<canvas", "pace-spark", "pace-ring"):
        assert drawing not in card


# ---------------------------------------------------------------------------
# 5b. Weekly progress and contact-market cleanup retain independent meanings.
# ---------------------------------------------------------------------------
def _merged_user(email="merge@example.com"):
    """Both halves at once: a pace figure and something unplaced under it.

    Deliberately NOT `_unplaced_user` from section 3 — that one is shared by
    the copy tests above and a rename there would be a second edit to guards
    this change has no business touching.
    """
    user = _user(email=email, tracks=("ib",))
    Contact.all_objects.create(user=user, name="Ada Lovelace", region="us")
    Contact.all_objects.create(user=user, name="Jude Yoon", source="capture")
    return user


def test_weekly_progress_and_market_assignment_are_distinct_tasks(client):
    html = _page(_merged_user())
    pace = _pace_card(html)
    markets = _rail_widget(html, "unplaced-card")
    assert "Weekly Outreach" in pace
    assert "No market · new this week" in _face(markets)
    assert "unplaced-card" not in pace
    assert "pace-card" not in markets


def test_market_summary_counts_only_new_contacts_without_a_market(client):
    user = _merged_user(email="merge2@example.com")
    card = _rail_widget(_page(user), "unplaced-card")
    assert "1 contact No market · new this week" in _face(card)
    assert "2 contacts" not in _face(card)


def test_market_assignment_has_one_action_and_progress_is_a_readout(client):
    html = _page(_merged_user(email="merge3@example.com"))
    assert "<a " not in _pace_card(html)
    markets = _rail_widget(html, "unplaced-card")
    links = re.findall(r'<a\b[^>]*>.*?</a>', markets, re.S)
    assert len(links) == 1
    assert _face(links[0]) == "Assign markets"


def test_the_two_widgets_have_distinct_landmark_names(client):
    html = _page(_merged_user(email="merge4@example.com"))
    for name, title in (("pace-card", "weekly-outreach-title"), ("unplaced-card", "set-markets-title")):
        card = _rail_widget(html, name)
        assert card.startswith("<section")
        assert f'aria-labelledby="{title}"' in card
        assert f'id="{title}"' in card


def test_no_market_task_is_shown_when_every_new_contact_has_a_market(client):
    user = _user(email="merge5@example.com", tracks=("ib",))
    Contact.all_objects.create(user=user, name="Ada Lovelace", region="us")
    html = _page(user)
    assert "Weekly Outreach" in _pace_card(html)
    assert not re.search(r'<section[^>]*class="[^"]*unplaced-card', html)
    assert 'id="set-markets-title"' not in html


def test_unmet_outreach_goal_does_not_hide_the_market_task(client):
    user = _merged_user(email="merge6@example.com")
    from crm.today import _cockpit_context
    ctx = _cockpit_context(user)
    assert not ctx["pace"]["hit"]
    html = _page(user)
    card = _pace_card(html)
    assert "Weekly goal reached." not in card
    if ctx["blackout"]:
        assert "Outreach is paused today." in card
    else:
        assert "more to reach your goal." in card
    assert "Assign markets" in _rail_widget(html, "unplaced-card")


# ---------------------------------------------------------------------------
# 6. The rule this whole pass was working to, checked across the rail at once.
# ---------------------------------------------------------------------------
def test_no_rail_card_states_a_direction_of_time_inconsistently():
    """The rail's one shared reading rule, asserted where it is easiest to
    break: a bare "Nd" is elapsed, and a future distance says "in". Two cards
    print day counts and this is the seam between them."""
    user = _deadline_user()
    contact = Contact.all_objects.create(user=user, name="Ada Lovelace")
    Touch.all_objects.create(
        user=user, contact=contact, kind="outreach", channel="email",
        ts=timezone.now() - dt.timedelta(days=3),
    )
    html = _page(user)
    assert "in 58d" in _card(html, "Deadlines")
    activity = _rail_widget(html, "activity-card")
    assert ">3d<" in activity and "in 3d" not in activity
