"""Journey 4: getting people into the CRM.

Hand-add one, upload a small CSV with the two things a real export always
has — a repeat of somebody already in the book, and a firm the directory has
never heard of — then fix the unmatched firm from the summary page.

Nothing is mocked except one thing, named here rather than hidden: Gmail Live
backfill. `services.import_contacts` calls
`capture.gmail_live.backfill_new_contacts` at the end of an import; it returns
immediately when Gmail is unconfigured (which it is under test settings), so
the tests below neither reach it nor need it. No network call is made and no
provider credential is read.
"""

from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from accounts.models import User
from crm.models import Contact
from directory.models import Firm

pytestmark = pytest.mark.django_db

# Five rows. Row 4 repeats row 1's address with different casing and a
# different name — the shape a re-export from a mail client actually has —
# and row 5 names a firm the directory does not carry.
CSV = (
    "name,email,firm,role,notes,angle\n"
    "Jane Banker,jane@journeypartners.test,Journey Partners,Analyst,met at the info session,rowing\n"
    "Bob Trader,bob@meridian.test,Meridian Capital,Associate,,\n"
    "Priya Analyst,priya@journeypartners.test,Journey Partners,Summer Analyst,,USC\n"
    "Jane B.,JANE@JourneyPartners.test,Journey Partners,Analyst,duplicate row,\n"
    "Casey Buyside,casey@tinyfund.test,Definitely Not A Real Fund LP,Analyst,,\n"
)


@pytest.fixture
def student():
    return User.objects.create_user(email="importer@example.com", password="A-safe-passphrase-123")


@pytest.fixture
def signed_in(client, student):
    client.force_login(student)
    return client


@pytest.fixture
def firms():
    return {
        "journey": Firm.objects.create(name="Journey Partners", slug="journey-partners"),
        "meridian": Firm.objects.create(name="Meridian Capital", slug="meridian-capital"),
        "tiny": Firm.objects.create(name="Tiny Fund", slug="tiny-fund"),
    }


def _upload(client, text=CSV, filename="contacts.csv"):
    return client.post(reverse("accounts:import"), {
        "file": SimpleUploadedFile(filename, text.encode("utf-8"), content_type="text/csv"),
    })


def _names(student):
    return sorted(Contact.objects.for_user(student).values_list("name", flat=True))


# ---------------------------------------------------------------------------


def test_a_contact_can_be_added_by_hand_and_read_back(signed_in, student, firms):
    response = signed_in.post(reverse("crm:contact_new"), {
        "name": "Ada Lovelace",
        "firm": str(firms["journey"].pk),
        "role": "Vice President",
        "email": "ada@journeypartners.test",
        "region": "us",
        "angle": "USC",
    })

    assert response.status_code == 302
    contact = Contact.objects.for_user(student).get()
    assert response.url == reverse("crm:contact_detail", args=[contact.pk])
    assert contact.name == "Ada Lovelace"
    assert contact.firm == firms["journey"]
    assert contact.role == "Vice President"
    assert contact.source == "manual"

    detail = signed_in.get(response.url)
    assert detail.status_code == 200
    assert "Ada Lovelace" in detail.content.decode()

    listing = signed_in.get(reverse("crm:contact_list"))
    assert listing.status_code == 200
    assert "Ada Lovelace" in listing.content.decode()


def test_the_csv_import_skips_the_duplicate_and_flags_the_unknown_firm(signed_in, student, firms):
    response = _upload(signed_in)

    assert response.status_code == 200
    result = response.context["result"]
    assert result.total_rows == 5
    assert result.created == 4
    assert result.skipped_duplicate == 1
    assert result.firm_matched == 3

    assert _names(student) == ["Bob Trader", "Casey Buyside", "Jane Banker", "Priya Analyst"]
    # The duplicate is a duplicate on the ADDRESS, whatever case it arrived in.
    assert Contact.objects.for_user(student).filter(
        email__iexact="jane@journeypartners.test").count() == 1

    # The one firm the directory does not carry is surfaced, not silently
    # dropped and not silently guessed at.
    assert len(result.unmatched_firms) == 1
    group = result.unmatched_firms[0]
    assert group.firm_text == "Definitely Not A Real Fund LP"
    assert group.count == 1
    unmatched = Contact.objects.for_user(student).get(name="Casey Buyside")
    assert unmatched.firm is None
    assert unmatched.firm_text == "Definitely Not A Real Fund LP"
    assert "Definitely Not A Real Fund LP" in response.content.decode()


def test_resolving_the_unmatched_firm_links_it_and_leaves_no_duplicates(signed_in, student, firms):
    group = _upload(signed_in).context["result"].unmatched_firms[0]

    linked = signed_in.post(reverse("accounts:import_link_firm"), {
        "contact_id": [str(cid) for cid in group.contact_ids],
        "firm_id": str(firms["tiny"].pk),
    })

    assert linked.status_code == 302 and linked.url == reverse("accounts:import")
    casey = Contact.objects.for_user(student).get(name="Casey Buyside")
    assert casey.firm == firms["tiny"]
    assert casey.firm_text == ""
    assert Contact.objects.for_user(student).count() == 4
    # And the page no longer asks a question it has an answer to.
    assert signed_in.get(reverse("accounts:import")).status_code == 200


def test_importing_the_same_file_twice_adds_nobody(signed_in, student, firms):
    _upload(signed_in)
    before = _names(student)

    second = _upload(signed_in)

    assert second.context["result"].created == 0
    assert second.context["result"].skipped_duplicate == 5
    assert _names(student) == before


def test_a_file_with_no_recognisable_columns_is_refused_out_loud(signed_in, student):
    response = _upload(signed_in, "alpha,beta,gamma\n1,2,3\n")

    assert response.status_code == 200
    assert response.context["result"].unmatched_columns
    assert response.context["result"].created == 0
    assert not Contact.objects.for_user(student).exists()
    assert "recognizable columns" in response.content.decode().lower()


def test_the_downloadable_template_is_the_format_the_importer_reads(signed_in, student, firms):
    template = signed_in.get(reverse("accounts:import_template"))

    assert template.status_code == 200
    assert template["Content-Type"].startswith("text/csv")
    header = template.content.decode().splitlines()[0]
    assert header == "name,email,linkedin,firm,role,notes,angle"

    # Round trip: a row written under that exact header imports.
    assert _upload(signed_in, header + "\nRound Trip,rt@journeypartners.test,,Journey Partners,Analyst,,\n"
                   ).context["result"].created == 1
    assert Contact.objects.for_user(student).get(name="Round Trip").firm == firms["journey"]


def test_one_students_import_is_invisible_to_another(signed_in, student, firms):
    _upload(signed_in)

    other = User.objects.create_user(email="other@example.com", password="A-safe-passphrase-123")
    signed_in.force_login(other)

    assert not Contact.objects.for_user(other).exists()
    board = signed_in.get(reverse("crm:contact_list"))
    assert "Jane Banker" not in board.content.decode()
    # The same file uploaded by a different student is not a duplicate of
    # anything: the dedupe book is per tenant.
    assert _upload(signed_in).context["result"].created == 4


def test_the_import_surfaces_are_private(client, student):
    assert client.get(reverse("accounts:import")).status_code == 302
    assert client.get(reverse("accounts:import_template")).status_code == 302
    assert client.post(reverse("accounts:import_link_firm"), {}).status_code == 302
    assert not Contact.all_objects.exists()
