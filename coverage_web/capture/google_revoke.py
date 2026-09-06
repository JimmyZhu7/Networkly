"""Hand a Google grant back to Google when the user is done with it.

Gmail and Calendar request separate scopes, but Google revokes the user's
authorization for the whole Cloud project, including its other clients.
`include_granted_scopes=false` does not isolate revocation. A confirmed
revoke therefore also invalidates the matching local sibling connection.
Official source, checked 2026-09-06:
https://developers.google.com/identity/protocols/oauth2/web-server#tokenrevoke


WHY THIS EXISTS. Disconnecting Gmail, and deleting a Coverage account
outright, both used to delete the encrypted refresh-token row and stop
there. `capture/views.py`'s own docstring argued the case: Google already
gives the user a better place to revoke (myaccount.google.com/permissions),
and a second call is a second thing that can silently fail. That reasoning
holds for a button in a settings page. It does not hold for what the two
actions PROMISE. "Disconnect" reads as "the grant is gone", and account
deletion is documented in the privacy policy as a hard delete with nothing
kept — while the OAuth grant stayed live at Google, indefinitely, for an
account that no longer exists on this side. A grant nobody can see and
nobody can use is exactly the kind of thing that surfaces years later.

BEST-EFFORT, DELIBERATELY. Provider failures return rather than raise.
The stored row is being deleted either way, and a network blip at Google
must not be able to leave a student unable to disconnect or unable to
delete their account. A failed revoke is logged and the user's own
myaccount.google.com control remains the backstop it always was — the
difference is that it is now the backstop rather than the only path.

NOTHING HERE LOGS A TOKEN. The revoke endpoint takes the token as a POST
body parameter, not a query string, so it does not reach an access log
either; the log lines below name the connection's id and the HTTP status
and nothing else.
"""

from __future__ import annotations

import logging

import requests

logger = logging.getLogger(__name__)

# Google's revocation endpoint invalidates project-wide authorization for
# the associated Google account, even across distinct OAuth clients.
REVOKE_URL = "https://oauth2.googleapis.com/revoke"

# Short on purpose. This runs inline in a request that the user is waiting
# on (a disconnect POST, an account deletion), and the work it guards is
# already done by the time it matters.
TIMEOUT_SECONDS = 5


def revoke_token(raw_token: str) -> bool:
    """POST one refresh token to Google's revoke endpoint. Never raises.

    Only HTTP 200 confirms this request revoked the project authorization.
    A 400 may describe an expired/invalid old token while another integration
    has since reconnected; it must never invalidate that newer grant locally.
    """
    if not raw_token:
        return False
    try:
        resp = requests.post(
            REVOKE_URL,
            data={"token": raw_token},
            timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        logger.warning("Gmail token revoke failed to reach Google: %s", exc)
        return False
    if resp.status_code == 200:
        return True
    logger.warning("Gmail token revoke returned HTTP %s", resp.status_code)
    return False


def _related_connections(connection):
    """Snapshot the same user's other service on the same Google account.

    Both integrations currently use GMAIL_LIVE_CLIENT_ID, hence the same
    project. Account addresses come from Google's profile/primary calendar,
    not the Coverage login email. A different Google account is unaffected.
    """
    from capture.models import GmailConnection, GoogleCalendarConnection

    if isinstance(connection, GmailConnection):
        model, field, address, label = (GoogleCalendarConnection, "google_email", connection.gmail_address, "Google Calendar")
    elif isinstance(connection, GoogleCalendarConnection):
        model, field, address, label = (GmailConnection, "gmail_address", connection.google_email, "Gmail")
    else:
        return []
    if not address or not connection.user_id:
        return []
    return [(model, label, row) for row in model.all_objects.filter(user_id=connection.user_id,
        status="active", **{f"{field}__iexact": address.strip()},
    ).values("pk", "refresh_token_encrypted")]


def revoke_connection(connection, *, related_services=None) -> bool:
    """Revoke the grant behind one `capture.models.GmailConnection`.

    Decryption is `gmail_live`'s, not a second implementation of it — but
    it is imported here rather than at module scope so that importing this
    module costs nothing on a deploy with Gmail Live switched off, and so a
    malformed `GMAIL_LIVE_TOKEN_KEY` (which `decrypt_token` raises
    `GmailLiveError` for, loudly and correctly) cannot turn "disconnect" or
    "delete my account" into a 500.
    """
    ciphertext = getattr(connection, "refresh_token_encrypted", "") or ""
    if not ciphertext:
        return False
    from capture import gmail_live

    try:
        raw = gmail_live.decrypt_token(ciphertext)
    except Exception as exc:  # noqa: BLE001 — see the docstring: never fatal here
        logger.warning(
            "Gmail token revoke skipped for connection %s: token unreadable (%s)",
            getattr(connection, "pk", "?"),
            exc,
        )
        return False
    related = _related_connections(connection)
    confirmed = revoke_token(raw)
    if confirmed:
        for model, label, row in related:
            # Never let an old request clear a credential replaced while
            # Google's response was in flight. Passive refresh errors do not
            # enter this explicit-disconnect path at all.
            changed = model.all_objects.filter(user_id=connection.user_id,
                pk=row["pk"], status="active",
                refresh_token_encrypted=row["refresh_token_encrypted"],
            ).update(status="revoked", refresh_token_encrypted="")
            if changed and related_services is not None:
                related_services.add(label)
    return confirmed


def disconnect_connections(user, model):
    """Remove the requested stored connection and report related revocation.

    The token comparison also preserves a concurrent reconnect to the service
    being disconnected. Provider failure never keeps the old local token.
    """
    related_services = set()
    removed = 0
    unconfirmed = False
    replaced = False
    for connection in list(model.all_objects.filter(user=user)):
        if not revoke_connection(connection, related_services=related_services):
            unconfirmed = True
        count, _ = model.all_objects.filter(user=user,
            pk=connection.pk,
            refresh_token_encrypted=connection.refresh_token_encrypted,
        ).delete()
        removed += count
        replaced = replaced or count == 0
    return {"removed": removed, "related_services": sorted(related_services),
            "unconfirmed": unconfirmed, "replaced": replaced}


def revoke_all_for_user(user) -> int:
    """Revoke every Google grant this user holds. Returns how many succeeded.

    BOTH GRANTS, not just the mailbox. Account deletion is documented in the
    privacy policy as a hard delete with nothing kept, and a calendar grant
    that outlives the account is the same thing this module was written to
    stop — a live permission nobody can see and nobody can use, surfacing
    years later. `GoogleCalendarConnection` names its ciphertext field
    `refresh_token_encrypted` for exactly this reason: `revoke_connection`
    reads that field off whatever it is handed, so one implementation covers
    both and a third grant would cost one line here.

    `all_objects` with an explicit `user=` filter, the same shape every
    other worker-side read of these tables uses: both are private-zone
    models and this is called from paths (account deletion) where the caller
    already holds the user object.
    """
    from capture.models import GmailConnection, GoogleCalendarConnection

    revoked = 0
    for model in (GmailConnection, GoogleCalendarConnection):
        for connection in model.all_objects.filter(user=user):
            if revoke_connection(connection):
                revoked += 1
    return revoked
