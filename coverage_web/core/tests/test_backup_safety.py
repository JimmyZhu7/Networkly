from pathlib import Path
import subprocess
from unittest.mock import patch

import pytest
from django.core.management import call_command, CommandError


def test_backup_is_private_and_only_complete_snapshots_are_published(tmp_path):
    def dump(cmd, **kwargs):
        output = Path(cmd[cmd.index('-f') + 1])
        assert output.suffix == '.partial'
        assert output.stat().st_mode & 0o777 == 0o600
        output.write_bytes(b'complete-dump')
    with patch('core.management.commands.backup_db.subprocess.run', side_effect=dump):
        call_command('backup_db', dest=str(tmp_path), keep=2)
    snapshots = list(tmp_path.glob('*.dump'))
    assert len(snapshots) == 1
    assert snapshots[0].read_bytes() == b'complete-dump'
    assert snapshots[0].stat().st_mode & 0o777 == 0o600
    assert not list(tmp_path.glob('*.partial'))


def test_timed_out_backup_does_not_replace_or_prune_good_backup(tmp_path):
    good = tmp_path / 'coverage_2026-01-01.dump'
    good.write_bytes(b'keep me')
    with patch('core.management.commands.backup_db.subprocess.run', side_effect=subprocess.TimeoutExpired('pg_dump',600)):
        with pytest.raises(CommandError, match='timed out'):
            call_command('backup_db', dest=str(tmp_path), keep=1)
    assert good.read_bytes() == b'keep me'
    assert not list(tmp_path.glob('*.partial'))


@pytest.mark.parametrize('keep',[0,-1])
def test_invalid_retention_refuses_before_dump_or_delete(tmp_path,keep):
    with patch('core.management.commands.backup_db.subprocess.run') as dump:
        with pytest.raises(CommandError, match='at least 1'):
            call_command('backup_db', dest=str(tmp_path),keep=keep)
    dump.assert_not_called()
