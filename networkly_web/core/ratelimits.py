"""Fixed request windows shared by public search and waitlist endpoints."""

from django.core.cache import cache


def window_exceeded(key: str, *, limit: int, seconds: int) -> bool:
    # add() claims a fresh window; incr() assigns each remaining request its
    # own place. Checking a preceding get() admits an entire concurrent burst
    # into the same final place. Neither operation extends an existing TTL.
    for _ in range(2):
        if cache.add(key, 1, timeout=seconds):
            return False
        try:
            return cache.incr(key) > limit
        except ValueError:
            # The window expired or was evicted between add and increment.
            # Compete for the replacement instead of overwriting its count.
            continue
    return True
