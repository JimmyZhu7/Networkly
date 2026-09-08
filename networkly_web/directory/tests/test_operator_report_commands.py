"""Operator command contracts, using isolated rows and no provider requests."""

from datetime import date
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import OperationalError, connection
from django.utils import timezone

from directory import health
from directory.boards import board_key
from directory.models import Firm, FirmDate, Opportunity, ScrapeRun
from networkly_connectors import GreenhouseBoard


pytestmark = pytest.mark.django_db


def report(command, *args):
    """These operator reports must never quietly repair or persist data."""
    output, errors = StringIO(), StringIO()

    def reads_only(execute, sql, params, many, context):
        assert sql.lstrip().split(None, 1)[0].upper() in {"SELECT", "SHOW"}, sql
        return execute(sql, params, many, context)

    with connection.execute_wrapper(reads_only):
        call_command(command, *args, stdout=output, stderr=errors, no_color=True)
    assert errors.getvalue() == ""
    return output.getvalue()


@pytest.fixture
def recorded_boards(monkeypatch):
    boards, entries = [], []
    # Catalog order deliberately differs from the operator's severity order.
    for slug, fetched, ok, open_rows, error in [
        ("quiet", 0, True, 0, ""),
        ("wiped", 0, True, 1, ""),
        ("working", 1, True, 1, ""),
        ("broken", 0, False, 1, "HTTP 404: board no longer exists"),
    ]:
        firm = Firm.objects.create(slug=slug, name=slug.title())
        board = GreenhouseBoard(firm=firm.name, token=f"{slug}-jobs")
        boards.append((slug, board))
        if open_rows:
            Opportunity.objects.create(
                firm=firm, title="Summer Analyst", source="greenhouse",
                status="open", url=f"https://example.test/{slug}/1",
            )
        entries.append({"firm": firm.name, "provider": "greenhouse",
                        "board": board_key(board), "ok": ok, "rows": fetched,
                        "error": error})
    monkeypatch.setattr(health, "BOARDS", boards)
    return ScrapeRun.objects.create(
        connector="all", started=timezone.now(), status="partial",
        stats={"boards": entries},
    )


def test_board_report_defaults_to_complete_read_only_table(recorded_boards):
    output = report("board_health")
    assert output.splitlines()[0].split() == [
        "slug", "provider", "board", "state", "rows", "open", "ever", "error",
    ]
    assert [line.split()[0] for line in output.splitlines()[1:]] == [
        "broken", "wiped", "quiet", "working",
    ]
    assert "HTTP 404: board no longer exists" in output
    assert "greenhouse" in output
    assert report("board_health") == output


def test_board_alarming_flag_keeps_actionable_rows_and_failure_reason(recorded_boards):
    output = report("board_health", "--alarming")
    lines = output.splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("failed") and "broken/broken-jobs (greenhouse)" in lines[0]
    assert "1 open rows: HTTP 404: board no longer exists" in lines[0]
    assert lines[1].startswith("wiped") and "wiped/wiped-jobs (greenhouse)" in lines[1]
    assert "1 open rows: fetched clean, zero rows" in lines[1]
    assert "quiet" not in output and "working" not in output


def test_board_alarming_flag_reports_clean_recorded_boards(recorded_boards):
    stats = recorded_boards.stats
    stats["boards"] = [row for row in stats["boards"] if row["firm"] in {"Quiet", "Working"}]
    recorded_boards.save(update_fields=["stats"])
    assert report("board_health", "--alarming").strip() == (
        "No board is failing or silently wiped."
    )


def test_board_default_distinguishes_missing_scrape_history():
    assert report("board_health").strip() == "no full scrape recorded yet"


@pytest.fixture
def recruiting_dates():
    alpha = Firm.objects.create(slug="alpha", name="Alpha")
    beta = Firm.objects.create(slug="beta", name="Beta")
    missing = FirmDate.objects.create(
        firm=beta, cycle="", event_kind="app_close", date=None, confidence=0.6,
        history=[{"was_cycle": "old label"}, None, "legacy note",
                 {"was_cycle": "latest unrecognized cycle"}, {"note": "reviewed"}],
    )
    dated = FirmDate.objects.create(
        firm=alpha, cycle="", event_kind="app_open", date=date(2027, 3, 1),
        confidence=1.0,
    )
    for firm, cycle, track, event_kind in [
        (alpha, "sa2028", "ib", "app_open"),
        (alpha, "sa2028", "ib", "app_close"),
        (beta, "sa2028", "ib", "app_open"),
        (beta, "sa2028", "", "app_open"),
        (alpha, "ft2027", "", "app_open"),
    ]:
        FirmDate.objects.create(firm=firm, cycle=cycle, track=track, event_kind=event_kind)
    return dated, missing


def test_cycle_report_lists_only_unfiled_rows_with_latest_provenance(recruiting_dates):
    dated, missing = recruiting_dates
    output = report("review_firm_date_cycles")
    assert "2 of 7 firm_dates rows have no cycle on file" in output
    assert "can never match a student's stated cycle" in output
    rows = [line for line in output.splitlines() if line.startswith("  #")]
    assert len(rows) == 2
    assert rows[0].startswith(f"  #{dated.pk}") and "2027-03-01" in rows[0]
    assert rows[1].startswith(f"  #{missing.pk}") and "(no date)" in rows[1]
    assert "was 'latest unrecognized cycle'" in rows[1]
    assert "old label" not in output and "legacy note" not in output
    assert "Rows by cycle:" not in output
    assert "To file one:" in output
    assert report("review_firm_date_cycles") == output


def test_cycle_all_flag_groups_tracks_and_counts_distinct_firms(recruiting_dates):
    output = report("review_firm_date_cycles", "--all")
    groups = [line.split() for line in output.split("Rows by cycle:\n", 1)[1].splitlines()]
    assert groups == [
        ["ft2027", "1", "rows", "across", "1", "firms"],
        ["sa2028", "1", "rows", "across", "1", "firms"],
        ["sa2028/ib", "3", "rows", "across", "2", "firms"],
    ]
    assert "2 of 7" in output


def test_cycle_empty_report_is_explicit_and_read_only():
    assert report("review_firm_date_cycles").strip() == (
        "Every one of the 0 firm_dates rows names a cycle."
    )


@pytest.mark.parametrize("command", ["board_health", "review_firm_date_cycles"])
def test_unknown_report_arguments_fail_before_querying(command):
    def no_queries(*args):
        raise AssertionError("Invalid command arguments reached the database")

    with connection.execute_wrapper(no_queries), pytest.raises(CommandError, match="unrecognized arguments"):
        call_command(command, "--does-not-exist", stdout=StringIO(), stderr=StringIO())


@pytest.mark.parametrize("command,args", [
    ("board_health", []), ("board_health", ["--alarming"]),
    ("review_firm_date_cycles", []), ("review_firm_date_cycles", ["--all"]),
])
def test_database_failure_is_not_reported_as_a_healthy_or_empty_result(command, args):
    output = StringIO()

    def unavailable(*unused):
        raise OperationalError("simulated reporting database outage")

    with connection.execute_wrapper(unavailable), pytest.raises(OperationalError, match="simulated reporting"):
        call_command(command, *args, stdout=output, stderr=StringIO())
    assert output.getvalue() == ""
