"""The Stripe webhook must not echo provider error text to an unauthenticated caller.

The checkout view already keeps provider messages out of responses; the
webhook handler returned `str(exc)`, which can carry account or signature
details, to whoever posted the request.
"""
from __future__ import annotations

import pytest
from django.test import Client

from billing import stripe_gateway


@pytest.mark.django_db
def test_gateway_error_text_stays_out_of_the_response(monkeypatch):
    monkeypatch.setattr(stripe_gateway, "is_configured", lambda: True)

    def reject(body, sig):
        raise stripe_gateway.StripeGatewayError("signature mismatch for acct_1234 using whsec_zzz")

    monkeypatch.setattr(stripe_gateway, "handle_webhook_event", reject)
    response = Client().post("/billing/webhook/", data=b"{}", content_type="application/json")
    assert response.status_code == 400
    body = response.content.decode()
    assert "acct_1234" not in body and "whsec_zzz" not in body
