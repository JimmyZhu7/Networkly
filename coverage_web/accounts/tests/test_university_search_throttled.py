"""`university_search` is public by design but must share the per-IP search window."""
from __future__ import annotations

import pytest
from django.core.cache import cache
from django.test import Client
from django.urls import reverse

from core import views as core_views


@pytest.mark.django_db
def test_a_burst_from_one_address_is_throttled():
    cache.clear()
    url = reverse("accounts:university_search")
    client = Client(REMOTE_ADDR="203.0.113.9")
    limit = core_views._SEARCH_WINDOW_LIMIT
    codes = [client.get(url, {"school": "univ"}).status_code for _ in range(limit + 1)]
    assert codes[0] == 200
    assert 429 in codes, f"no 429 within {limit + 1} requests: {codes[-3:]}"
    cache.clear()
