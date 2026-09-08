"""Opt-in, disposable-database benchmark; never writes to an application DB.

NETWORKLY_CAPACITY_BENCH=1 NETWORKLY_CAPACITY_CONTACTS=2000 uv run pytest -q -s \
  networkly_web/crm/tests/test_recruiting_capacity.py

Compares the checked-in audit baseline with the current reducers on identical
synthetic records. Results are diagnostic, not a production capacity promise.
"""

import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time
import tracemalloc
import types
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext

from crm import today
from crm.models import Contact, Touch, UserFirm
from directory import views as directory_views
from directory.models import Firm, Opportunity

BASELINE = "3d2c49d"
NOW = datetime(2026, 9, 7, 12, tzinfo=timezone.utc)
pytestmark = [pytest.mark.django_db, pytest.mark.skipif(
    os.environ.get("NETWORKLY_CAPACITY_BENCH") != "1", reason="Opt-in synthetic capacity benchmark",
)]


def _baseline_module(name, path):
    source = subprocess.check_output(["git", "show", f"{BASELINE}:{path}"], text=True)
    module = types.ModuleType(name)
    module.__package__ = name.rpartition(".")[0]
    sys.modules[name] = module
    exec(compile(source, path, "exec"), module.__dict__)
    return module


def _measure(fn):
    # Prime imports/caches separately. Tracemalloc reports Python allocations,
    # not PostgreSQL resident memory or TLS/provider/network latency.
    result = fn()
    times, query_counts = [], []
    for _ in range(3):
        started = time.perf_counter()
        with CaptureQueriesContext(connection) as captured:
            result = fn()
        times.append(time.perf_counter() - started)
        query_counts.append(len(captured))
    # Allocation tracing materially slows these loops, so measure memory in
    # a separate pass rather than labelling traced time as request latency.
    tracemalloc.start()
    fn()
    peak = tracemalloc.get_traced_memory()[1] / 1024**2
    tracemalloc.stop()
    return {"median_seconds": round(statistics.median(times), 4),
            "peak_python_mib": round(peak, 2), "queries": query_counts}, result


def _fingerprint(value):
    return hashlib.sha256(json.dumps(value, default=str, sort_keys=True).encode()).hexdigest()


def test_large_account_reducers_match_baseline_and_report_capacity():
    assert connection.settings_dict["NAME"].startswith("test_")
    contact_count = int(os.environ.get("NETWORKLY_CAPACITY_CONTACTS", "500"))
    touches_per_contact = 100
    role_count = int(os.environ.get("NETWORKLY_CAPACITY_ROLES", "3000"))
    users = [get_user_model().objects.create_user(
        email=f"capacity-{i}@example.test", class_year=2029, target_cycles=["2028 Summer Internship"],
        tracks=["ib"], regions=["us"], study_level="undergrad",
    ) for i in range(100)]
    user = users[0]
    firms = Firm.objects.bulk_create([
        Firm(name=f"Capacity Bank {i}", slug=f"capacity-bank-{i}", tracks=["ib"], regions=["us"])
        for i in range(20)
    ])
    UserFirm.all_objects.bulk_create([UserFirm(user=user, firm=f, tier=1) for f in firms])
    contacts = Contact.all_objects.bulk_create([
        Contact(user=user, name=f"Analyst {i:05d}", firm=firms[i % len(firms)], role="Investment Banking Analyst",
                region="us", school_affiliation=True) for i in range(contact_count)
    ])
    # Other tenants exist in the same tables and must never enter this queue.
    others = Contact.all_objects.bulk_create([
        Contact(user=u, name=f"Other {u.pk}", firm=firms[0], region="us") for u in users[1:]
    ])
    batch = []
    for contact in contacts + others:
        for i in range(touches_per_contact):
            batch.append(Touch(user_id=contact.user_id, contact=contact, kind="outreach",
                               ts=NOW - timedelta(days=60, minutes=i), note="Private history. " * 128))
            if len(batch) >= 2000:
                Touch.all_objects.bulk_create(batch)
                batch = []
    if batch:
        Touch.all_objects.bulk_create(batch)
    # A broad shared board with wide provider bodies, exactly what ranking
    # used to load just to read the facts subtree.
    for start in range(0, role_count, 250):
        Opportunity.objects.bulk_create([
            Opportunity(firm=firms[i % len(firms)], title=f"Investment Banking Summer Analyst Programme {i}",
                        url=f"https://example.test/role/{i}", status="open", bucket="internship", region="us", cohort="2028",
                        raw={"detail_text": "Provider posting details. " * 1000,
                             "facts": {"grad": {"years": ["2029"], "quote": "Class of 2029"}}})
            for i in range(start, min(start + 250, role_count))
        ])
    legacy_cadence = _baseline_module("networkly_domain._capacity_cadence", "networkly_domain/networkly_domain/cadence.py")
    legacy_today = _baseline_module("crm._capacity_today", "networkly_web/crm/today.py")
    legacy_today.cadence = legacy_cadence
    legacy_directory = _baseline_module("directory._capacity_views", "networkly_web/directory/views.py")
    report = {"baseline": BASELINE, "users": 100, "target_contacts": contact_count,
              "touches_per_contact": touches_per_contact, "other_contacts": len(others),
              "shared_roles": role_count, "database": "isolated PostgreSQL test database"}
    with patch("django.utils.timezone.now", return_value=NOW):
        report["history_before"], before = _measure(lambda: legacy_today._build_actions(user)[0])
        report["history_after"], after = _measure(lambda: today._build_actions(user)[0])
        assert _fingerprint(before) == _fingerprint(after)
        report["action_count"] = len(after)
        report["action_fingerprint"] = _fingerprint(after)
        report["ranking_before"], old_picks = _measure(lambda: legacy_directory.picked_roles(user, today=NOW.date()))
        report["ranking_after"], new_picks = _measure(lambda: directory_views.picked_roles(user, today=NOW.date()))
        def picks(result):
            return [(r.candidate.id, r.score, r.why) for r in result[0]], result[1]
        assert picks(old_picks) == picks(new_picks)
        report["pick_count"] = len(new_picks[0])
        assert report["pick_count"] > 0, "A ranking benchmark must actually rank eligible open postings."
    destination = Path(os.environ.get("NETWORKLY_CAPACITY_REPORT", "/tmp/networkly-recruiting-capacity.json"))
    destination.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
