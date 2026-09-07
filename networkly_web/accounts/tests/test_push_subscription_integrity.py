"""Push subscription ownership must survive concurrent account requests."""

from concurrent.futures import ThreadPoolExecutor
import json
import threading

import pytest
from django.db import connection, connections
from django.db.models.query import QuerySet
from django.test import RequestFactory

from accounts.models import PushSubscription, User
from accounts.views import push_subscribe, push_unsubscribe


ENDPOINT = "https://fcm.googleapis.com/fcm/send/shared-browser"


def _request(user, payload):
    request = RequestFactory().post(
        "/welcome/push/subscribe/",
        data=json.dumps(payload),
        content_type="application/json",
    )
    request.user = user
    return request


@pytest.mark.django_db(transaction=True)
def test_concurrent_accounts_cannot_reassign_the_same_push_endpoint(monkeypatch):
    assert connection.vendor == "postgresql"
    users = [User.objects.create_user(email=f"push-race-{i}@example.com") for i in range(2)]
    barrier = threading.Barrier(2)
    original = QuerySet.get_or_create

    def arrive_together(queryset, *args, **kwargs):
        if queryset.model is PushSubscription:
            barrier.wait(timeout=10)
        return original(queryset, *args, **kwargs)

    monkeypatch.setattr(QuerySet, "get_or_create", arrive_together)

    def subscribe(user):
        try:
            response = push_subscribe(_request(user, {
                "endpoint": ENDPOINT,
                "keys": {"p256dh": f"public-{user.pk}", "auth": f"auth-{user.pk}"},
            }))
            return user.pk, response.status_code
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(subscribe, users))

    assert sorted(status for _, status in results) == [201, 409]
    winner = next(user_id for user_id, status in results if status == 201)
    subscription = PushSubscription.all_objects.get(endpoint=ENDPOINT)
    assert subscription.user_id == winner
    assert subscription.p256dh == f"public-{winner}"
    assert subscription.auth == f"auth-{winner}"


@pytest.mark.django_db
@pytest.mark.parametrize("field", ["endpoint", "p256dh", "auth"])
@pytest.mark.parametrize("value", [True, 123, ["text"], {"value": "text"}])
def test_push_subscribe_rejects_non_string_fields(field, value):
    user = User.objects.create_user(email="push-invalid@example.com")
    payload = {"endpoint": ENDPOINT, "keys": {"p256dh": "public", "auth": "auth"}}
    (payload if field == "endpoint" else payload["keys"])[field] = value
    assert push_subscribe(_request(user, payload)).status_code == 400
    assert not PushSubscription.all_objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize("value", [True, 123, ["text"], {"value": "text"}])
def test_push_unsubscribe_rejects_non_string_endpoint(value):
    user = User.objects.create_user(email="push-invalid@example.com")
    assert push_unsubscribe(_request(user, {"endpoint": value})).status_code == 400


@pytest.mark.django_db
@pytest.mark.parametrize("field", ["p256dh", "auth"])
@pytest.mark.parametrize("value", ["x" * 256, "key\x00value"])
def test_invalid_push_keys_are_rejected_before_the_database(field, value):
    user = User.objects.create_user(email="push-invalid@example.com")
    payload = {"endpoint": ENDPOINT, "keys": {"p256dh": "public", "auth": "auth"}}
    payload["keys"][field] = value
    assert push_subscribe(_request(user, payload)).status_code == 400
    assert not PushSubscription.all_objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize("endpoint", [
    "https://[broken",
    "https://fcm.googleapis.com:not-a-port/push",
    "https://fcm.googleapis.com:444/push",
    "https://user:password@fcm.googleapis.com/push",
    "https://fcm.googleapis.com/push\nextra",
])
def test_malformed_push_urls_are_rejected_cleanly(endpoint):
    user = User.objects.create_user(email="push-invalid@example.com")
    payload = {"endpoint": endpoint, "keys": {"p256dh": "public", "auth": "auth"}}
    assert push_subscribe(_request(user, payload)).status_code == 400
    assert not PushSubscription.all_objects.exists()
