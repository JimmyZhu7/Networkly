"""send_weekly_digest: the management command wrapping crm.digest — who it
mails, who it skips, and that --dry-run truly sends nothing.

Uses pytest-django's `mailoutbox` fixture, which forces the locmem email
backend for the test regardless of what EMAIL_URL resolves to in whatever
settings module the suite runs under — the standard Django-testing pattern
the task brief calls for, independent of the console-vs-SMTP backend choice
made at deploy time.
"""

from __future__ import annotations

import io
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone

from analytics.models import UserOpportunity
from directory.models import Firm, Opportunity

pytestmark = pytest.mark.django_db(transaction=True)

User = get_user_model()
_CLOCK: dict = {}


@pytest.fixture(autouse=True)
def _one_clock_per_test():
    """The clock is read on first use inside a test and held for that test.

    Two things were wrong before this. A module-level snapshot was taken at
    collection, so a suite that started before midnight UTC and finished after
    it built its fixtures on yesterday: 39 tests failed by one day on the first
    CI run to cross that line. And a clock read on every call drifts by
    microseconds between two uses in one test, which breaks equality anchors
    (`survivor.first_seen == now - 10 days`) and exact day thresholds. This
    gives each test one instant, read when the test first asks.
    """
    _CLOCK.clear()
    yield
    _CLOCK.clear()


def _today():
    return _CLOCK.setdefault("_today", timezone.localdate())
def _user(email, *, onboarded=True, deleted=False, **kw):
    user = User.objects.create_user(email=email, password="pw12345!", **kw)
    if onboarded:
        user.onboarded_at = timezone.now()
    if deleted:
        user.deleted_at = timezone.now()
    user.save()
    return user


def _closing_opp(user, n=1, *, days=2):
    firm = Firm.objects.create(name=f"Firm {n}", slug=f"firm-{n}")
    o = Opportunity.objects.create(
        firm=firm, url=f"https://x/{n}", title=f"Summer Analyst {n}",
        bucket="internship", status="open", deadline=_today() + timedelta(days=days),
    )
    UserOpportunity.all_objects.create(user=user, opportunity=o, applied_status="saved")
    return o


def _run(*args):
    out = io.StringIO()
    call_command("send_weekly_digest", *args, stdout=out)
    return out.getvalue()


def test_dry_run_sends_nothing(mailoutbox):
    user = _user("dry@example.com")
    _closing_opp(user)

    out = _run("--dry-run")

    assert "dry@example.com" in out
    assert mailoutbox == []


def test_an_onboarded_user_with_something_due_gets_mailed(mailoutbox):
    user = _user("real@example.com")
    _closing_opp(user)

    _run()

    assert len(mailoutbox) == 1
    msg = mailoutbox[0]
    assert msg.to == ["real@example.com"]
    assert "closing" in msg.subject.lower()
    # Both parts of the pair the task brief asks for: plain-text body plus an
    # HTML alternative.
    assert msg.body.strip()
    alt_types = [mimetype for _, mimetype in msg.alternatives]
    assert "text/html" in alt_types


def test_the_plain_text_body_never_html_escapes_an_ampersand(mailoutbox):
    """Regression: Django's template engine autoescapes by default
    REGARDLESS of file extension, so a firm/role name or a mailto: URL's
    '&'-joined query params rendered as literal '&amp;' in the plain-text
    part the first time this was wired up (caught by hand, rendering a real
    dev-DB digest, then pinned here). weekly_digest.txt wraps its body in
    {% autoescape off %} specifically to keep this from regressing."""
    user = _user("amp@example.com")
    firm = Firm.objects.create(name="Smith & Co", slug="smith-and-co")
    o = Opportunity.objects.create(
        firm=firm, url="https://x/amp?a=1&b=2", title="Analyst & Associate",
        bucket="internship", status="open", deadline=_today() + timedelta(days=2),
    )
    UserOpportunity.all_objects.create(user=user, opportunity=o, applied_status="saved")

    _run()

    assert "&amp;" not in mailoutbox[0].body
    assert "Smith & Co" in mailoutbox[0].body
    assert "https://x/amp?a=1&b=2" in mailoutbox[0].body


def test_a_user_with_nothing_due_is_skipped_not_mailed(mailoutbox):
    _user("quiet@example.com")  # onboarded, nothing tracked, nothing due

    out = _run()

    assert mailoutbox == []
    assert "quiet@example.com" in out
    assert "skipped" in out.lower()


def test_a_not_yet_onboarded_user_is_never_mailed_by_default(mailoutbox):
    user = _user("new@example.com", onboarded=False)
    _closing_opp(user)

    _run()

    assert mailoutbox == []


def test_a_deleted_user_is_never_mailed(mailoutbox):
    user = _user("gone@example.com", deleted=True)
    _closing_opp(user)

    _run()

    assert mailoutbox == []


def test_the_user_flag_targets_one_account_bypassing_onboarding(mailoutbox):
    """--user is explicitly for testing a specific account; it must reach
    someone who hasn't finished onboarding yet."""
    user = _user("preview@example.com", onboarded=False)
    _closing_opp(user)

    _run("--user", "preview@example.com")

    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == ["preview@example.com"]


def test_an_unknown_user_flag_raises_rather_than_silently_sending_nothing():
    from django.core.management.base import CommandError

    with pytest.raises(CommandError):
        _run("--user", "nobody@example.com")


def test_the_user_flag_matches_email_case_insensitively(mailoutbox):
    user = _user("Mixed.Case@example.com", onboarded=False)
    _closing_opp(user)

    _run("--user", "mixed.case@example.com")

    assert len(mailoutbox) == 1


def test_two_users_one_quiet_one_due_only_the_due_one_is_mailed(mailoutbox):
    loud = _user("loud@example.com")
    _closing_opp(loud, n=1)
    _user("quiet2@example.com")

    _run()

    assert [m.to[0] for m in mailoutbox] == ["loud@example.com"]


# ---------------------------------------------------------------------------
# THE PROVENANCE MARKER SURVIVES THE INBOX.
#
# `Opportunity.confidence` is the one carrier for where a deadline came from:
# 1.0 means a provider published it as a structured field, anything under it
# means Coverage read the date out of the posting's own prose. Measured on the
# live board, 96% of dated open campus roles are the second kind.
#
# Six web surfaces mark that with a dotted underline plus a `title` holding
# `deadline_provenance`'s `why`. An email has neither hover nor tooltip, and a
# mail client's sanitizer strips the styling anyway — so the digest was
# printing a prose-read date exactly the way it printed a firm-published one.
# The .ics feed hit the same constraint on a phone lock screen and answered it
# by putting the marker in the SUMMARY as words (crm/calendar_views.py); these
# pin the digest to that answer, in BOTH parts of the pair, because some
# clients render only the plain-text half.
# ---------------------------------------------------------------------------
def _parts(msg) -> tuple[str, str]:
    """(plain text, html) — the two halves every one of these checks twice."""
    html = next(body for body, mime in msg.alternatives if mime == "text/html")
    return msg.body, html


def _closing_opp_with_confidence(user, n, confidence, *, days=2):
    o = _closing_opp(user, n=n, days=days)
    o.confidence = confidence
    o.save(update_fields=["confidence"])
    return o


def test_a_prose_read_deadline_is_marked_reported_in_both_parts(mailoutbox):
    user = _user("prose@example.com")
    _closing_opp_with_confidence(user, 1, 0.6)

    _run()

    text, html = _parts(mailoutbox[0])
    # Words, not styling: readable with the stylesheet stripped and with no
    # pointer to hover with.
    assert "(reported)" in text
    assert "(reported)" in html
    # Beside the countdown it qualifies, not floating loose in the row.
    assert "closes in 2 days (reported)" in text


def test_a_deadline_the_board_published_gets_no_marker_in_either_part(mailoutbox):
    """The marker means something because it is not on everything. A
    confidence of 1.0 is the firm's own stated field and is quoted plainly."""
    user = _user("stated@example.com")
    _closing_opp_with_confidence(user, 1, 1.0)

    _run()

    text, html = _parts(mailoutbox[0])
    assert "reported" not in text
    assert "reported" not in html
    assert "closes in 2 days" in text


def test_the_marker_is_explained_once_per_digest_not_once_per_row(mailoutbox):
    """An inbox has nowhere to put the `why` that every web surface hangs off
    a `title`, so the digest spells it out — as a key under the section, once,
    however many rows carry the marker."""
    user = _user("legend@example.com")
    _closing_opp_with_confidence(user, 1, 0.6, days=2)
    _closing_opp_with_confidence(user, 2, 0.6, days=3)
    _closing_opp_with_confidence(user, 3, 1.0, days=4)

    _run()

    text, html = _parts(mailoutbox[0])
    why = "Read from the posting's own text, not a field the board published"
    assert text.count(why) == 1
    # The HTML half escapes the apostrophe; the sentence is the same one.
    assert html.count(why.replace("'", "&#x27;")) == 1
    # Two of the three rows carry the marker, and the third does not. Named
    # by countdown so a failure says WHICH row changed sides.
    assert "closes in 2 days (reported)" in text
    assert "closes in 3 days (reported)" in text
    assert "closes in 4 days (reported)" not in text
    # Two rows plus the key itself, which opens with the marker it explains.
    assert text.count("(reported)") == 3


def test_a_digest_with_no_prose_read_dates_prints_no_key_for_a_missing_marker(
    mailoutbox,
):
    """The key is not boilerplate. Nothing in this digest is our own reading,
    so there is no marker to explain and the section stays clean."""
    user = _user("nokey@example.com")
    _closing_opp_with_confidence(user, 1, 1.0, days=2)
    _closing_opp_with_confidence(user, 2, 1.0, days=3)

    _run()

    text, html = _parts(mailoutbox[0])
    assert "Read from the posting" not in text
    assert "Read from the posting" not in html


# ---------------------------------------------------------------------------
# The rendered email leads with coverage, labels a year-early pick set, and
# prints a pick's date only with its provenance — in BOTH halves.
# ---------------------------------------------------------------------------
def _tier_one(user, name, slug):
    from crm.models import UserFirm

    firm = Firm.objects.create(name=name, slug=slug)
    UserFirm.all_objects.create(user=user, firm=firm, tier=1)
    return firm


def test_the_digest_opens_with_the_coverage_line_in_both_parts(mailoutbox):
    user = _user("coverage@example.com")
    _closing_opp(user)
    _tier_one(user, "Alpha Bank", "alpha")
    _tier_one(user, "Beta Bank", "beta")

    _run()

    text, html = _parts(mailoutbox[0])
    line = "0 advocates across 2 target firms · 2 firms with no contact yet: Alpha Bank and Beta Bank"
    assert line in text
    assert line in html
    # Leads: above this week's deadlines, not below them.
    assert text.index(line) < text.index("CLOSING THIS WEEK")
    assert html.index(line) < html.index("Closing This Week")


def test_a_student_with_nothing_tiered_gets_no_coverage_line(mailoutbox):
    user = _user("untiered@example.com")
    _closing_opp(user)

    _run()

    text, html = _parts(mailoutbox[0])
    assert "advocate" not in text
    assert "advocate" not in html


def test_picks_a_year_early_are_labelled_so_in_both_parts(mailoutbox):
    user = _user("early@example.com", target_cycles=["2028 Summer Internship"])
    _closing_opp(user)
    firm = _tier_one(user, "Alpha Bank", "alpha")
    Opportunity.objects.create(
        firm=firm, url="https://x/alpha/pick", title="Summer Analyst 2027",
        bucket="internship", status="open", cohort="2027",
    )

    _run()

    text, html = _parts(mailoutbox[0])
    note = "Nothing yet for your 2028 Summer Internship cycle; these are a year early."
    assert note in text
    assert note in html
    # Under the section it qualifies, before the first pick.
    assert text.index("NEW FOR YOU") < text.index(note) < text.index("Summer Analyst 2027")


def test_a_picks_prose_read_deadline_is_marked_and_the_key_printed_once(mailoutbox):
    user = _user("pickdate@example.com")
    # A closing row the board PUBLISHED: no marker, no key from that section.
    _closing_opp_with_confidence(user, 1, 1.0, days=2)
    firm = _tier_one(user, "Alpha Bank", "alpha")
    Opportunity.objects.create(
        firm=firm, url="https://x/alpha/pick", title="Summer Analyst 2028",
        bucket="internship", status="open", cohort="2028", confidence=0.6,
        deadline=_today() + timedelta(days=12),
    )

    _run()

    text, html = _parts(mailoutbox[0])
    assert "closes in 12 days (reported)" in text
    assert "closes in 12 days" in html and "(reported)" in html
    why = "Read from the posting's own text, not a field the board published"
    assert text.count(why) == 1
    assert html.count(why.replace("'", "&#x27;")) == 1
    # The key sits with the pick that earned it, since Closing printed none.
    assert text.index("NEW FOR YOU") < text.index(why)


def test_the_key_is_not_printed_twice_when_both_sections_carry_the_marker(mailoutbox):
    user = _user("twice@example.com")
    _closing_opp_with_confidence(user, 1, 0.6, days=2)
    firm = _tier_one(user, "Alpha Bank", "alpha")
    Opportunity.objects.create(
        firm=firm, url="https://x/alpha/pick", title="Summer Analyst 2028",
        bucket="internship", status="open", cohort="2028", confidence=0.6,
        deadline=_today() + timedelta(days=12),
    )

    _run()

    text, html = _parts(mailoutbox[0])
    why = "Read from the posting's own text, not a field the board published"
    assert text.count(why) == 1
    assert html.count(why.replace("'", "&#x27;")) == 1
    assert "closes in 2 days (reported)" in text
    assert "closes in 12 days (reported)" in text


def test_a_picks_board_published_deadline_prints_without_a_marker(mailoutbox):
    user = _user("stateddate@example.com")
    _closing_opp_with_confidence(user, 1, 1.0, days=2)
    firm = _tier_one(user, "Alpha Bank", "alpha")
    Opportunity.objects.create(
        firm=firm, url="https://x/alpha/pick", title="Summer Analyst 2028",
        bucket="internship", status="open", cohort="2028", confidence=1.0,
        deadline=_today() + timedelta(days=12),
    )

    _run()

    text, html = _parts(mailoutbox[0])
    assert "closes in 12 days" in text
    assert "reported" not in text
    assert "reported" not in html


# ---------------------------------------------------------------------------
# The daily mail budget.
#
# The provider's free tier allows 100 messages a day. A 100-student beta
# mailed in one tick spends all of it on the digest, and the confirmation
# or reset somebody is waiting on is refused AFTER the app has told them to
# check their inbox. These two mechanisms are what keeps that from
# happening; both are exercised with the locmem backend, never a relay.
# ---------------------------------------------------------------------------
def test_the_daily_cap_defers_the_rest_instead_of_dropping_them(mailoutbox, settings):
    settings.DIGEST_DAILY_SEND_CAP = 2
    for n in range(4):
        _closing_opp(_user(f"cap{n}@example.com"), n)

    out = _run()

    assert len(mailoutbox) == 2
    assert "daily send cap of 2 reached" in out
    assert "2 recipient(s) deferred" in out
    assert "2 deferred (daily cap 2)" in out


def test_the_cap_admits_the_same_recipients_in_the_same_order_every_run(mailoutbox, settings):
    """Who loses is decided by a stable ordering, not by chance: the same run
    twice admits the same two, so the two below the line stay a known set
    that the next run resumes from rather than a fresh shuffle."""
    settings.DIGEST_DAILY_SEND_CAP = 2
    for n in range(4):
        _closing_opp(_user(f"order{n}@example.com"), n)

    _run()
    first = sorted(m.to[0] for m in mailoutbox)
    mailoutbox.clear()
    _run()

    assert sorted(m.to[0] for m in mailoutbox) == first
    assert first == ["order0@example.com", "order1@example.com"]


def test_the_cap_counts_sends_not_recipients_with_nothing_to_report(mailoutbox, settings):
    """A student the digest skips costs no mail, so they must not consume a
    slot — otherwise a roster of quiet accounts would starve the loud ones."""
    settings.DIGEST_DAILY_SEND_CAP = 2
    _user("aquiet@example.com")  # onboarded, nothing to report
    _user("bquiet@example.com")
    for n in range(2):
        _closing_opp(_user(f"cloud{n}@example.com"), n)

    _run()

    assert sorted(m.to[0] for m in mailoutbox) == ["cloud0@example.com", "cloud1@example.com"]


def test_the_cap_applies_to_a_dry_run_too(mailoutbox, settings):
    """A dry run that reports sends a real run would not make is not a
    rehearsal."""
    settings.DIGEST_DAILY_SEND_CAP = 1
    for n in range(3):
        _closing_opp(_user(f"drycap{n}@example.com"), n)

    out = _run("--dry-run")

    assert mailoutbox == []
    assert out.count("+ ") == 1
    assert "2 recipient(s) deferred" in out


def test_spread_mails_only_todays_seventh_of_the_roster(mailoutbox):
    """The daily cron's flag. Seven accounts spanning every residue of pk % 7
    means exactly one of them is due on any given weekday."""
    users = [_user(f"spread{n}@example.com") for n in range(7)]
    for n, user in enumerate(users):
        _closing_opp(user, n)
    weekday = timezone.now().weekday()
    due = [u.email for u in users if u.pk % 7 == weekday]

    _run("--spread")

    assert [m.to[0] for m in mailoutbox] == due
    assert len(due) == 1


def test_seven_consecutive_spread_runs_reach_everyone_exactly_once(mailoutbox):
    """The cadence promise: one digest per student per seven runs, no more
    and no fewer. Simulated by sweeping the weekday rather than the clock, so
    the assertion does not depend on which day the suite runs."""
    from crm.management.commands.send_weekly_digest import _send_today

    users = [_user(f"week{n}@example.com") for n in range(7)]
    reached = {u.email: 0 for u in users}
    for weekday in range(7):
        for user in users:
            if _send_today(user, weekday=weekday):
                reached[user.email] += 1

    assert set(reached.values()) == {1}


def test_without_spread_the_whole_roster_is_considered(mailoutbox):
    for n in range(3):
        _closing_opp(_user(f"whole{n}@example.com"), n)

    _run()

    assert len(mailoutbox) == 3


def test_a_single_user_run_ignores_the_spread_entirely(mailoutbox):
    """--user already bypasses the onboarded gate and the opt-out; the
    weekday split is the same kind of roster rule and must not silently turn
    a targeted preview into a no-op six days in seven."""
    user = _user("targeted@example.com", onboarded=False)
    _closing_opp(user)

    _run("--user", "targeted@example.com", "--spread")

    assert [m.to[0] for m in mailoutbox] == ["targeted@example.com"]
