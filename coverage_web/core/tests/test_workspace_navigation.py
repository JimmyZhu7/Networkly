"""The redesigned shell keeps destinations and page identity unambiguous."""
import re

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from directory.models import Firm


@pytest.fixture
def student(client, db):
    user = get_user_model().objects.create_user(
        email="workspace@example.com", password="test-password",
        onboarded_at=timezone.now(),
    )
    client.force_login(user)
    return user


@pytest.mark.parametrize("path, destination", [
    ("/app/", "/app/"),
    ("/app/contacts/", "/app/contacts/"),
    ("/app/calendar/", "/app/calendar/"),
    ("/opportunities/mine/", "/opportunities/"),
    ("/welcome/settings/", "/welcome/"),
])
def test_workspace_identifies_exactly_one_current_destination(client, student, path, destination):
    response = client.get(path)
    assert response.status_code == 200
    body = response.content.decode()
    nav = re.search(r'<nav class="site-nav".*?</nav>', body, re.S).group()
    current = re.findall(r'<a href="([^"]+)"[^>]*aria-current="page"', nav)
    assert current == [destination]
    assert nav.count("<a href=") == 6
    assert 'aria-label="Search Networkly"' in body
    assert 'aria-controls="workspace-primary"' in body


def test_a_firm_deep_link_stays_in_opportunities(client, student):
    firm = Firm.objects.create(name="Workspace Test Firm", slug="workspace-test-firm")
    response = client.get(f"/firms/{firm.slug}/")
    assert response.status_code == 200
    nav = re.search(r'<nav class="site-nav".*?</nav>', response.content.decode(), re.S).group()
    assert re.findall(r'<a href="([^"]+)"[^>]*aria-current="page"', nav) == ["/opportunities/"]


def test_the_network_starts_with_contacts_and_keeps_the_firm_map_reachable(client, student):
    body = client.get("/app/contacts/").content.decode()
    assert body.index('id="net-contacts"') < body.index('id="net-coverage"')
    assert 'href="#net-coverage"' in body
    assert 'aria-label="Network region"' in body
