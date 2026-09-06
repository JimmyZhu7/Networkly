"""Product identity must reach private screens and generated communication."""
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from accounts.adapter import CoverageAccountAdapter

pytestmark = pytest.mark.django_db


def visible_copy(html):
    html = re.sub(r'<(script|style)\b[^>]*>.*?</\1>', '', html, flags=re.S)
    return strip_tags(html)


@pytest.mark.parametrize('route', ['/', '/pricing/', '/accounts/login/', '/accounts/signup/', '/welcome/privacy/', '/welcome/terms/'])
def test_public_screens_use_networkly(client, route):
    response = client.get(route)
    assert response.status_code == 200
    text = visible_copy(response.content.decode())
    assert 'Networkly' in text
    head = response.content.decode().split('</head>', 1)[0]
    assert re.search(r'<title>Networkly(?: · |</title>)', head)
    assert 'img/favicon.ico' in head and 'img/favicon-32.png' in head
    assert not re.search(r'\bcoverage\b', text, re.I)


@pytest.mark.parametrize('route', ['/app/', '/app/contacts/', '/app/calendar/', '/opportunities/mine/', '/welcome/settings/', '/assistant/'])
def test_private_screens_use_networkly(client, route):
    user = get_user_model().objects.create_user(email='brand@example.com', password='x')
    client.force_login(user)
    response = client.get(route)
    assert response.status_code == 200
    text = visible_copy(response.content.decode())
    assert 'Networkly' in text
    head = response.content.decode().split('</head>', 1)[0]
    assert re.search(r'<title>Networkly(?: · |</title>)', head)
    assert 'img/favicon.ico' in head and 'img/favicon-32.png' in head
    assert not re.search(r'\bcoverage\b', text, re.I)
    assert 'aria-label="Networkly home"' in response.content.decode()


def test_auth_email_rebrands_stale_site_name_without_changing_links():
    site = SimpleNamespace(name='Coverage', domain='existing.example')
    message = CoverageAccountAdapter().render_mail('account/email/email_confirmation', 'recipient@example.com', {
        'current_site': site, 'activate_url': 'https://existing.example/accounts/confirm-email/token/',
        'user': SimpleNamespace(email='recipient@example.com'), 'key': 'token',
    })
    assert message.subject.startswith('[Networkly] ')
    assert 'Networkly' in message.body and 'Coverage' not in message.body
    assert 'https://existing.example/accounts/confirm-email/token/' in message.body
    assert site.name == 'Coverage'


def test_install_identity_and_icon_geometry_are_updated():
    static = Path(__file__).resolve().parents[2] / 'static'
    manifest = json.loads((static / 'manifest.webmanifest').read_text())
    assert manifest['name'] == manifest['short_name'] == 'Networkly'
    assert manifest['start_url'] == '/app/'
    svg = (static / 'img/favicon.svg').read_text()
    assert svg.count('<circle') == 2
    assert 'M4 16a8' not in svg
    rendered = render_to_string('_logo.html')
    assert rendered.count('<circle') == 2


def test_export_downloads_have_new_names(client):
    user = get_user_model().objects.create_user(email='export-brand@example.com', password='x')
    client.force_login(user)
    response = client.get('/welcome/export/?kind=all')
    assert response.status_code == 200
    assert 'networkly-data.zip' in response['Content-Disposition']
