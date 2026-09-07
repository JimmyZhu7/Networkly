"""Relationship and sponsorship facts explain themselves on the Network board."""
import re

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from crm.models import Contact, UserFirm
from directory.models import Firm

pytestmark = pytest.mark.django_db
NETWORK = "/app/contacts/"


def test_the_legend_reads_the_canonical_title_case_labels():
    user = get_user_model().objects.create_user(email="net-legend@example.com", password="x" * 14)
    for index, (warmth, state) in enumerate([("cold", "no_reply"), ("replied", "replied"), ("chatted", "chat_done"), ("advocate", "advocate")]):
        Contact.all_objects.create(user=user, name=f"Person {index}", warmth=warmth, thread_state=state)
    client = Client()
    client.force_login(user)
    response = client.get(NETWORK)
    html = response.content.decode()
    labels = re.findall(r'<span class="warmth-row-label">(.*?)</span>', html)
    expected = [section["label"] for section in response.context["sections"] if section["cards"]]
    assert labels == expected
    assert len(labels) == 4
    assert "Replied" in labels
    assert 'class="net-legend-mini"' not in html


def test_the_key_carries_one_entry_per_mark_a_card_can_wear():
    """Visible full labels replace abbreviations that used to require a key."""
    user = get_user_model().objects.create_user(email="net-legend-marks@example.com", password="x" * 14)
    firm = Firm.objects.create(slug="labeled-firm", name="Labeled Firm", sponsors=True)
    UserFirm.all_objects.create(user=user, firm=firm, tier=1)
    client = Client()
    client.force_login(user)
    html = client.get(NETWORK).content.decode()
    assert '>Visa sponsorship<' in html
    gap = re.search(r'<span class="pill fc-cg"[^>]*>([^<]+)</span>', html)
    assert gap and len(gap.group(1).strip()) > 2
    assert ">SP<" not in html and ">CG<" not in html
    assert 'class="net-legend-mini"' not in html
