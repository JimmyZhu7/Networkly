"""Simultaneous public requests must share the final place in a window."""

from concurrent.futures import ThreadPoolExecutor
import threading

import pytest
from django.core.cache import cache
from django.core.cache.backends.locmem import LocMemCache
from django.test import RequestFactory

from billing.views import _waitlist_throttled, _WAITLIST_WINDOW_LIMIT
from core.views import _search_throttled, _SEARCH_WINDOW_LIMIT


@pytest.mark.parametrize("throttle,key,limit", [
    (_search_throttled, "search-rate:127.0.0.1", _SEARCH_WINDOW_LIMIT),
    (_waitlist_throttled, "waitlist-rate:127.0.0.1", _WAITLIST_WINDOW_LIMIT),
])
def test_concurrent_requests_share_the_final_place(monkeypatch, throttle, key, limit):
    cache.set(key, limit - 1, timeout=60)
    barrier = threading.Barrier(6)
    original = LocMemCache.incr

    def arrive_together(backend, counter_key, *args, **kwargs):
        if counter_key == key:
            barrier.wait(timeout=10)
        return original(backend, counter_key, *args, **kwargs)

    monkeypatch.setattr(LocMemCache, "incr", arrive_together)
    try:
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(lambda _: throttle(RequestFactory().get("/")), range(6)))
        assert results.count(False) == 1
        assert results.count(True) == 5
    finally:
        cache.delete(key)
