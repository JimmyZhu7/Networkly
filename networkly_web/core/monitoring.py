"""Keep private CRM and mailbox payloads out of error monitoring."""

from urllib.parse import urlsplit, urlunsplit
import re


def scrub_sentry_event(event, hint):
    """Retain error locations and types, excluding untrusted free-text data.

    Provider exception messages and logging arguments can contain mailbox
    content, so a denylist of credential names is insufficient here.
    """
    for key in ("breadcrumbs", "user", "extra", "message", "logentry"):
        event.pop(key, None)

    request = event.get("request")
    if isinstance(request, dict):
        for key in ("headers", "cookies", "data", "query_string", "env"):
            request.pop(key, None)
        if "url" in request:
            try:
                parsed = urlsplit(request["url"])
                hostname = parsed.hostname or ""
                # Preserve IPv6 literals and a non-default service port.
                if ":" in hostname:
                    hostname = f"[{hostname}]"
                authority = hostname
                if parsed.port is not None:
                    authority = f"{authority}:{parsed.port}"
                # Calendar feeds and email opt-outs carry bearer tokens in
                # the path, not the query string. Monitoring needs the route,
                # never a reusable private subscription URL.
                path = re.sub(r"(/(?:calendar/feed|unsubscribe)/)[^/]+", r"\1[Filtered]", parsed.path)
                request["url"] = urlunsplit(
                    (parsed.scheme, authority, path, "", "")
                )
            except (TypeError, ValueError, AttributeError):
                request.pop("url", None)

    exception = event.get("exception")
    if isinstance(exception, dict):
        for value in exception.get("values", []):
            if isinstance(value, dict) and "value" in value:
                value["value"] = "[Filtered]"

    return event
