"""Contact actions retain native POST semantics when htmx is unavailable."""
import re

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from crm.models import Contact, Touch


@pytest.fixture
def native_contact(client):
    user = get_user_model().objects.create_user(email="native-forms@example.com", password="x")
    contact = Contact.all_objects.create(user=user, name="Alex Example", email="alex@example.com")
    client.force_login(user)
    return user, contact


@pytest.mark.django_db
@pytest.mark.parametrize("endpoint", ["contact_opener", "contact_role", "log_touch"])
def test_contact_action_forms_have_native_post_destinations(client, native_contact, endpoint):
    _, contact = native_contact
    body = client.get(reverse("crm:contact_detail", args=[contact.pk])).content.decode()
    action = reverse(f"crm:{endpoint}", args=[contact.pk])
    forms = re.findall(r"<form\b[^>]*>", body)
    assert any(f'action="{action}"' in form and 'method="post"' in form for form in forms)


@pytest.mark.django_db
@pytest.mark.parametrize("endpoint,field,value", [
    ("contact_opener", "opener", "Private draft: thanks for the introduction."),
    ("contact_role", "role", "Vice President"),
])
def test_native_contact_edits_redirect_without_private_query_parameters(client, native_contact, endpoint, field, value):
    _, contact = native_contact
    response = client.post(reverse(f"crm:{endpoint}", args=[contact.pk]), {field: value})
    assert response.status_code == 302
    assert response.url == reverse("crm:contact_detail", args=[contact.pk])
    assert "?" not in response.url
    contact.refresh_from_db()
    assert getattr(contact, field) == value
    page = client.get(response.url)
    assert b"<!doctype html>" in page.content
    assert b"Networkly" in page.content


@pytest.mark.django_db(transaction=True)
def test_native_interaction_logs_once_and_redirects_to_full_page(client, native_contact):
    user, contact = native_contact
    note = "Private note: follow up after the desk rotation."
    response = client.post(reverse("crm:log_touch", args=[contact.pk]), {
        "kind": "outreach", "channel": "email", "note": note,
    })
    assert response.status_code == 302
    assert response.url == reverse("crm:contact_detail", args=[contact.pk])
    assert "?" not in response.url
    assert Touch.all_objects.filter(user=user, contact=contact, note=note).count() == 1
    page = client.get(response.url)
    assert b"<!doctype html>" in page.content
    assert b"Interaction logged." in page.content
    client.get(response.url)
    assert Touch.all_objects.filter(user=user, contact=contact, note=note).count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize("data,message", [
    ({"kind": "not_real", "channel": "email"}, "Pick an interaction type."),
    ({"kind": "outreach", "channel": "not_real"}, "Pick a channel."),
])
def test_invalid_native_interaction_redirects_with_error_without_writing(client, native_contact, data, message):
    user, contact = native_contact
    response = client.post(reverse("crm:log_touch", args=[contact.pk]), data)
    assert response.status_code == 302
    assert response.url == reverse("crm:contact_detail", args=[contact.pk])
    assert message.encode() in client.get(response.url).content
    assert not Touch.all_objects.filter(user=user, contact=contact).exists()


@pytest.mark.django_db
@pytest.mark.parametrize("endpoint,field", [("contact_role", "role"), ("contact_opener", "opener")])
def test_htmx_edits_still_return_the_live_fragment(client, native_contact, endpoint, field):
    _, contact = native_contact
    response = client.post(reverse(f"crm:{endpoint}", args=[contact.pk]), {field: "Analyst"}, HTTP_HX_REQUEST="true")
    assert response.status_code == 200
    assert b'id="contact-live"' in response.content
    assert b"<!doctype html>" not in response.content


@pytest.mark.django_db
@pytest.mark.parametrize("endpoint,data", [
    ("contact_role", {"role": "Analyst"}),
    ("contact_opener", {"opener": "Private draft"}),
    ("log_touch", {"kind": "outreach", "channel": "email"}),
])
def test_native_contact_actions_keep_tenant_boundary(client, native_contact, endpoint, data):
    _, contact = native_contact
    other = get_user_model().objects.create_user(email="other-native@example.com", password="x")
    client.force_login(other)
    response = client.post(reverse(f"crm:{endpoint}", args=[contact.pk]), data)
    assert response.status_code == 404
    contact.refresh_from_db()
    assert contact.role == ""
    assert contact.opener == ""
    assert not Touch.all_objects.filter(contact=contact).exists()
