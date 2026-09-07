"""Run the local scheduler wrapper with fake commands, never a real job or dump."""
import os
from pathlib import Path
import subprocess

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts/refresh.sh"


@pytest.mark.parametrize(("backup_status", "refresh_status", "expected"), [
    (0, 0, 0),
    (9, 0, 9),
    (0, 7, 7),
    (9, 7, 7),
])
def test_wrapper_preserves_failures_and_runs_refresh_after_backup_failure(
    tmp_path, backup_status, refresh_status, expected,
):
    harness = r'''
    function pg_isready() { return 0; }
    function uv() {
      printf '%s\n' "$*" >> "$CALL_LOG"
      case "$*" in
        *"manage.py backup_db"*) return "$BACKUP_STATUS" ;;
        *"manage.py refresh"*) return "$REFRESH_STATUS" ;;
        *) return 99 ;;
      esac
    }
    export -f pg_isready uv
    bash "$1"
    '''
    calls = tmp_path / "calls.log"
    result = subprocess.run(
        ["bash", "-c", harness, "refresh-test", str(SCRIPT)],
        env={**os.environ, "HOME": str(tmp_path), "CALL_LOG": str(calls),
             "BACKUP_STATUS": str(backup_status), "REFRESH_STATUS": str(refresh_status)},
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == expected, result.stderr
    log = calls.read_text().splitlines()
    assert len(log) == 2
    assert "manage.py backup_db" in log[0]
    assert "--keep 30 --s3-bucket " in log[0]
    assert log[1].endswith("manage.py refresh")
    output = (tmp_path / "Library/Logs/coverage-refresh.log").read_text()
    assert ("backup and refresh finished" in output) is (expected == 0)
    if backup_status:
        assert "BACKUP FAILED" in output
    if refresh_status:
        assert "REFRESH FAILED" in output
