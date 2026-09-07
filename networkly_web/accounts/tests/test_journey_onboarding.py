"""Journey 2: the wizard, and the Settings page the wizard hands over to.

Nothing is mocked here. Every request is the real view, the real form and a
real row in the test database; the only synthetic thing is the student.

The point of the file is the SEAM. `test_onboarding_chrome.py`,
`test_settings_sections.py` and `test_profile_inputs.py` each test one side of
it very well, and the seam itself — what the wizard wrote is what Settings
shows, and what Settings changes the wizard would have accepted — is the part
a fresh account actually walks and nothing walked end to end.
"""

from __future__ import annotations

import pytest
from django.urls import reverse

from accounts.forms import AUTO_TIMEZONE
from accounts.models import User
from crm.models import UserFirm
from directory.models import Firm

pytestmark = pytest.mark.django_db

WIZARD = "/welcome/"


@pytest.fixture
def student():
    return User.objects.create_user(email="fresh@example.com", password="A-safe-passphrase-123")


@pytest.fixture
def signed_in(client, student):
    client.force_login(student)
    return client


@pytest.fixture
def firm():
    return Firm.objects.create(
        name="Journey Partners", slug="journey-partners", regions=["us"], tracks=["ib"],
    )


def _post(client, step, **data):
    return client.post(reverse("accounts:onboarding"), {"step": step, **data})


# ---------------------------------------------------------------------------
# The wizard


def test_a_fresh_account_walks_all_four_steps_and_every_answer_survives(signed_in, student, firm):
    wizard = reverse("accounts:onboarding")

    first = signed_in.get(wizard)
    assert first.status_code == 200
    assert first.context["step"] == "profile"
    assert first.context["step_number"] == 1
    assert first.context["step_total"] == 4

    profile = _post(signed_in, "profile", **{
        "name": "Fresh Student",
        "school": "University of Southern California",
        "class_year": "2028",
        "study_level": "undergrad",
        "regions": ["us", "hk"],
        "tracks": ["ib", "st"],
        "languages": ["english"],
        "timezone": "America/Los_Angeles",
    })
    assert profile.status_code == 302 and "step=work_auth" in profile.url

    work_auth = _post(signed_in, "work_auth", work_auth_us="citizen", work_auth_hk="sponsorship")
    assert work_auth.status_code == 302 and "step=firms" in work_auth.url

    firms = _post(signed_in, "firms", firms=[str(firm.pk)])
    assert firms.status_code == 302 and "step=import" in firms.url

    finish = _post(signed_in, "import")
    assert finish.status_code == 302 and finish.url == "/app/"

    student.refresh_from_db()
    assert student.name == "Fresh Student"
    assert student.school == "University of Southern California"
    assert student.class_year == 2028
    assert student.study_level == "undergrad"
    assert student.regions == ["us", "hk"] or set(student.regions) == {"us", "hk"}
    assert set(student.tracks) == {"ib", "st"}
    assert student.timezone == "America/Los_Angeles"
    assert student.timezone_auto is False
    assert student.work_authorization["us"] == "citizen"
    assert student.work_authorization["hk"] == "sponsorship"
    assert student.onboarded_at is not None
    assert UserFirm.objects.for_user(student).filter(firm=firm).exists()

    # And the surface it dropped them on is real, not a 302 into a loop.
    assert signed_in.get("/app/").status_code == 200


def test_every_step_can_be_skipped_and_the_account_still_opens(signed_in, student):
    """A stranger who answers nothing must still end up with a usable account."""
    for step in ("profile", "work_auth", "firms"):
        assert _post(signed_in, step).status_code == 302
    assert _post(signed_in, "import").url == "/app/"

    student.refresh_from_db()
    assert student.onboarded_at is not None
    assert student.regions == [] and student.tracks == []
    # Nothing was guessed on the student's behalf.
    assert student.work_authorization in ({}, None)
    assert signed_in.get("/app/").status_code == 200


def test_an_invalid_answer_re_renders_its_own_step_without_losing_the_rest(signed_in, student):
    _post(signed_in, "profile", name="Fresh Student", regions=["us"], tracks=["ib"])

    bad = _post(signed_in, "profile", **{
        "name": "Fresh Student",
        "regions": ["us"],
        "tracks": ["ib"],
        "timezone": "Mars/Olympus_Mons",
    })

    assert bad.status_code == 200
    assert bad.context["step"] == "profile"
    assert "timezone" in bad.context["form"].errors
    student.refresh_from_db()
    # The refused save wrote nothing at all, including the fields that were fine.
    assert student.regions == ["us"] and student.name == "Fresh Student"


def test_the_wizard_is_private(client, student):
    assert client.get(reverse("accounts:onboarding")).status_code == 302
    assert client.get(reverse("accounts:settings")).status_code == 302


# ---------------------------------------------------------------------------
# Settings, after the wizard


def test_settings_shows_back_what_the_wizard_wrote(signed_in, student, firm):
    _post(signed_in, "profile", **{
        "name": "Fresh Student", "school": "USC", "class_year": "2028",
        "regions": ["us"], "tracks": ["ib"], "timezone": "Asia/Hong_Kong",
    })
    _post(signed_in, "work_auth", work_auth_us="citizen")
    _post(signed_in, "firms", firms=[str(firm.pk)])
    _post(signed_in, "import")

    page = signed_in.get(reverse("accounts:settings"))

    assert page.status_code == 200
    initial = page.context["form"].initial
    assert initial["name"] == "Fresh Student"
    assert initial["school"] == "USC"
    assert initial["class_year"] == 2028
    assert list(initial["regions"]) == ["us"]
    assert list(initial["tracks"]) == ["ib"]
    assert initial["timezone"] == "Asia/Hong_Kong"
    assert page.context["work_auth_form"].initial["work_auth_us"] == "citizen"
    body = page.content.decode()
    assert "Fresh Student" in body
    assert firm.name in body


def test_changing_the_profile_from_settings_writes_through(signed_in, student):
    _post(signed_in, "profile", name="Fresh Student", regions=["us"], tracks=["ib"])
    _post(signed_in, "import")

    saved = signed_in.post(reverse("accounts:settings"), {
        "section": "profile",
        "name": "Renamed Student",
        "school": "USC",
        "regions": ["us", "eu"],
        "tracks": ["pe"],
        "timezone": "Asia/Hong_Kong",
    })

    assert saved.status_code == 302 and saved.url == reverse("accounts:settings")
    student.refresh_from_db()
    assert student.name == "Renamed Student"
    assert set(student.regions) == {"us", "eu"}
    assert student.tracks == ["pe"]
    assert student.timezone == "Asia/Hong_Kong"


def test_an_unmarked_settings_post_cannot_silently_wipe_the_profile(signed_in, student):
    """The one failure mode this page has had: an empty POST blanking six fields."""
    _post(signed_in, "profile", name="Fresh Student", school="USC",
          regions=["us"], tracks=["ib"])

    response = signed_in.post(reverse("accounts:settings"), {})

    assert response.status_code == 200
    student.refresh_from_db()
    assert student.name == "Fresh Student"
    assert student.school == "USC"
    assert student.regions == ["us"] and student.tracks == ["ib"]


def test_timezone_can_be_handed_back_to_the_browser(signed_in, student):
    _post(signed_in, "profile", timezone="Asia/Hong_Kong")
    student.refresh_from_db()
    assert student.timezone_auto is False

    signed_in.post(reverse("accounts:settings"),
                   {"section": "profile", "timezone": AUTO_TIMEZONE})

    student.refresh_from_db()
    assert student.timezone_auto is True


def test_a_section_save_leaves_the_sections_above_it_alone(signed_in, student):
    _post(signed_in, "profile", name="Fresh Student", regions=["us"], tracks=["ib"])
    signed_in.post(reverse("accounts:settings"),
                   {"section": "work_auth", "work_auth_us": "citizen"})

    bad_cadence = signed_in.post(reverse("accounts:settings"),
                                 {"section": "cadence", "advocate_target": "99"})

    assert bad_cadence.status_code == 200
    assert bad_cadence.context["cadence_form"].errors
    # The failing card is the only one carrying errors; the rest still render
    # the student's stored answers rather than an emptied form.
    assert not bad_cadence.context["work_auth_form"].errors
    assert bad_cadence.context["work_auth_form"].initial["work_auth_us"] == "citizen"
    student.refresh_from_db()
    assert student.name == "Fresh Student"
