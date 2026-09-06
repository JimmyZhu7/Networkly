"""Guard: the two disclosures the privacy page cannot lose.

Most of `templates/legal/privacy.html` is prose, and prose gets edited. Two
paragraphs in it are not prose in that sense — they are the things an outside
reviewer checks for, and losing either one in a copy pass is a silent
regression that only surfaces months later as a rejected verification.

1. Google's Limited Use representation. Coverage asks for `gmail.readonly`
   (settings/base.py's GMAIL_LIVE_SCOPES), a restricted scope, and Google's
   API Services User Data Policy requires the near-exact sentence asserted
   below to appear in the published privacy policy. Reworded, it does not
   count.

2. The Gmail-to-Anthropic flow. capture/gmail_residue.py sends a message's
   subject line and Gmail preview snippet to a third party during a "Scan
   Now" rescan. An onward transfer of Gmail-derived data that the policy
   does not name is exactly the finding that stalls a review.

These assert on the rendered page, not the file, so a template that stops
rendering fails them too.
"""

from __future__ import annotations

import pytest
from django.urls import reverse
from django.utils.html import strip_tags

pytestmark = pytest.mark.django_db

# Google's required wording. The subject may name the app; the rest is
# theirs. "and transfer to any other app of" is not optional filler -- it is
# part of the mandated sentence (Google's own published wording, verified
# 2026-08-30 against Google for Developers' Limited Use disclosure guidance
# and matched verbatim by every third-party Google-API disclosure page
# checked). A prior version of both this page and this constant dropped that
# clause, which is exactly the kind of silent trim a copy pass makes without
# realizing the sentence is not ours to shorten.
LIMITED_USE = (
    "use and transfer to any other app of information received from Google "
    "APIs will adhere to the Google API Services User Data Policy"
)


@pytest.fixture
def page(client):
    """The rendered page as running text.

    Tags are stripped and whitespace collapsed because the sentences below
    are read by a human reviewer, not a parser. Google's required wording has
    a link in the middle of it, so a raw-HTML match would fail on markup while
    the page reads exactly right.
    """
    resp = client.get(reverse("accounts:privacy"))
    assert resp.status_code == 200
    return " ".join(strip_tags(resp.content.decode()).split())


def test_the_policy_carries_googles_limited_use_wording(page):
    assert LIMITED_USE in page
    assert "including the Limited Use requirements" in page


def test_the_limited_use_statement_links_to_the_policy_it_names(client):
    resp = client.get(reverse("accounts:privacy"))
    assert "developers.google.com/terms/api-services-user-data-policy" in resp.content.decode()


def test_the_policy_says_gmail_subjects_and_snippets_go_to_anthropic(page):
    """Named provider, named data, named trigger. All three, or a reader
    cannot tell what they are agreeing to."""
    assert "Anthropic" in page
    assert "Scan Now" in page
    assert "subject line" in page and "snippet" in page


def test_the_ai_sharing_section_counts_scan_now_among_the_triggers(page):
    """The section used to list three AI triggers, then four (2026-08-30:
    Autopilot, capture/autopilot.py, makes it five -- it is a real,
    user-triggered Anthropic call the founder's own account has 53 decisions
    from, and it was missing from this list entirely). The list and the code
    have to stay in step."""
    section = page.split("Who We Share Data With", 1)[1]
    section = section.split("Cookies and Sessions", 1)[0]
    for trigger in (
        "the assistant",
        "coffee-chat brief",
        "relationship summary",
        "Scan Now",
        "Autopilot",
    ):
        assert trigger.lower() in section.lower(), f"{trigger} is an AI trigger and must be listed"


def test_the_ai_sharing_section_discloses_autopilot_sends_the_email_address(page):
    """Autopilot's evidence_text() sends `PERSON: {name} <{email}>` to
    Anthropic (capture/autopilot.py) -- unlike the advisor, which is told
    only whether a contact has an email on file. The blanket "email
    addresses are deliberately excluded" line only covers the advisor's
    three triggers; Autopilot needs its own, separate, honest sentence."""
    section = page.split("Who We Share Data With", 1)[1]
    section = section.split("Cookies and Sessions", 1)[0]
    assert "Autopilot" in section and "email address" in section


def test_the_policy_admits_the_whole_message_is_read(page):
    """It used to say the opposite by omission.

    `capture/gmail_live.py` fetches every message with `format="full"` and
    `_decode_body` walks every text part, because a bounce's routing address
    is legible in the decoded body and mangled in Gmail's snippet. The page
    described only "headers, an .ics attachment, a short snippet" — narrower
    than what runs. A student who reads this has to be able to tell that
    Coverage sees the body, even though it does not keep it.
    """
    section = page.split("Optional Mail Access", 1)[1]
    section = section.split("Google API Limited Use", 1)[0]
    assert "reads the whole message" in section
    assert "in memory" in section


def test_the_policy_admits_one_sentence_of_body_text_is_stored(page):
    """`capture.models.MailFact.quote` is a 500-character CharField holding
    a verbatim sentence from a message, and no fact is acted on without one.
    The page said "we do not store your messages" and left it there, which
    read as "no body text at all". Naming it is also the honest thing: the
    quote exists so the student can audit an automated action, and a
    justification nobody is told about cannot do that job."""
    section = page.split("Optional Mail Access", 1)[1]
    section = section.split("Google API Limited Use", 1)[0]
    assert "one verbatim sentence" in section
    assert "500 characters" in section


def test_the_gmail_scope_comment_and_the_page_do_not_disagree():
    """settings/base.py carried the same understated sentence next to
    GMAIL_LIVE_SCOPES. Two places describing one behaviour is two places to
    drift, so the comment now points at this page and says so."""
    from pathlib import Path

    from django.conf import settings

    source = Path(settings.BASE_DIR) / "coverage_web" / "settings" / "base.py"
    text = source.read_text()
    assert "a short snippet for bounce-pattern matching" not in text
    assert "templates/legal/privacy.html" in text


def test_the_page_is_still_marked_a_draft():
    """The disclosure gaps are filled; the lawyer review is not done. The
    banner comes off when counsel says so, not when a test stops caring."""
    from pathlib import Path

    from django.conf import settings

    source = Path(settings.BASE_DIR) / "templates" / "legal" / "privacy.html"
    assert "DRAFT. NOT REVIEWED BY A LAWYER." in source.read_text()


def test_calendar_connection_scope_and_retained_imports_are_disclosed(page):
    section = page.split("Optional Calendar Access", 1)[1].split("Google API Limited Use", 1)[0]
    for fact in ("separate read-only permission", "encrypted connection token", "descriptions", "locations", "start and end times", "event identifiers"):
        assert fact in section
    assert "does not create, edit, delete, or RSVP" in section
    assert "Imported events remain" in section
    assert "AI feature" in section


def test_export_and_deletion_scope_do_not_overpromise(page):
    assert "original uploaded files are not part of this record export" in page
    assert "private database records from the active service" in page
    assert "[BACKUP RETENTION PERIOD]" in page
    assert "[HOSTING REGION]" in page
    assert "[LEGAL ENTITY NAME]" in page


# ---------------------------------------------------------------------------
# 2026-09-06 security review. Four more claims that trace to a call site, and
# one honest omission, each of which a copy pass would otherwise smooth away.
# ---------------------------------------------------------------------------


def test_ai_classification_is_not_described_as_scan_now_only(page):
    """`capture/gmail.py` calls `appmail.consider_finding` and
    `mailfacts.consider_finding` without passing `allow_ai`, and both default
    it to True — so the ORDINARY background sync already sends a subject and
    Gmail snippet to Anthropic whenever the deterministic rules come up
    empty. The page framed that transfer as something that happens only when
    the student presses Scan Now, which is the narrower and friendlier claim
    and not the one the code makes. Both paths, or neither."""
    section = page.split("Optional Mail Access", 1)[1]
    section = section.split("Optional Calendar Access", 1)[0]
    assert "During ordinary sync" in section
    assert "Scan Now" in section


def test_the_provider_list_names_the_object_store_holding_the_avatar(page):
    """With MEDIA_S3_* set, `core/storage.py::media_storage_config` swaps
    STORAGES["default"] to PrivateMediaStorage and the profile picture leaves
    Render for a third-party bucket. The provider list named only Render, so
    a reader would have concluded their photo sits where their database rows
    sit. It does not."""
    section = page.split("Who We Share Data With", 1)[1]
    section = section.split("Cookies and Sessions", 1)[0]
    assert "object storage provider" in section
    assert "profile picture" in section


def test_the_provider_list_names_the_shared_cache(page):
    """`settings/base.py`'s REDIS_URL branch moves allauth's brute-force
    counters and axes' lockout records into a third-party cache, and those
    counters are keyed by the email address typed at sign-in. Small, short
    lived, and still someone else's server holding an address."""
    section = page.split("Who We Share Data With", 1)[1]
    section = section.split("Cookies and Sessions", 1)[0]
    assert "shared cache provider" in section
    assert "email address typed at sign-in" in section


def test_the_advisor_bullet_admits_mail_subject_lines_go_with_it(page):
    """`assistant/tools.py` puts "recent_subjects" — real Gmail subject
    lines, three per contact — into the advisor's contact payload. The bullet
    listed CRM fields only, so Google-derived data was travelling to Anthropic
    through a route the page did not name. It correctly said contact EMAIL
    ADDRESSES stay out of that path (`tools.py` sends `has_email` as a bool);
    that sentence stays true and stays put."""
    section = page.split("Who We Share Data With", 1)[1]
    section = section.split("Cookies and Sessions", 1)[0]
    assert "recent mail subject lines" in section
    assert "excludes contact email addresses" in section


def test_the_google_bullet_admits_addresses_travel_to_google_as_search_terms(page):
    """`capture/gmail_live.py` builds `(from:<address> OR to:<address>)`
    Gmail queries per contact. Every read of the mailbox is also a WRITE of a
    third party's address into Google's query log, which is the direction of
    flow the page described only one way round."""
    section = page.split("Who We Share Data With", 1)[1]
    section = section.split("Cookies and Sessions", 1)[0]
    assert "search term" in section


def test_deletion_does_not_claim_to_end_sessions_it_does_not_end(page):
    """`accounts/views.py::delete_account` calls `logout(request)`, which
    flushes the REQUESTING session and nothing else; `sign_out_other_sessions`
    is a separate control the deletion path never calls, and Django's session
    rows carry no FK for `user.delete()` to cascade. The rows are harmless —
    the account they name is gone — but "removes your account and associated
    private database records" said more than that."""
    # "Retention" is also an entry in the on-this-page nav, so anchor on the
    # section's own opening sentence rather than on its heading.
    section = page.split("Your recruiting records are retained", 1)[1]
    section = section.split("Security", 1)[0]
    assert "Sign-in sessions on your other devices are not removed" in section
