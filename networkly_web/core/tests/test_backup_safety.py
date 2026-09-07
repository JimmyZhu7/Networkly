from pathlib import Path
import subprocess
from unittest.mock import patch

import pytest
from botocore.exceptions import ClientError
from django.core.management import call_command, CommandError
from django.test import override_settings

from core.management.commands.backup_db import Command


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


# ---------------------------------------------------------------------------
# The off-host copy.
#
# Every test here substitutes a fake client for `Command.client`. Nothing in
# this file is allowed near a network, and a backup command whose only
# exercised path needs real object storage is a backup command nobody
# exercises — which is how the deploy image shipped for months with no
# `pg_dump` in it at all.
# ---------------------------------------------------------------------------
class FakeS3:
    """Just enough of boto3's S3 client for the ring: put, list, delete."""

    def __init__(self, existing=(), fail_upload=None, fail_delete=False):
        self.objects = list(existing)
        self.uploaded = []
        self.deleted = []
        self._fail_upload = fail_upload
        self._fail_delete = fail_delete

    def upload_file(self, filename, bucket, key):
        if self._fail_upload is not None:
            raise self._fail_upload
        self.uploaded.append((filename, bucket, key))
        self.objects.append(key)

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        return self

    def paginate(self, Bucket, Prefix):  # noqa: N803 — boto3's own casing
        contents = [{"Key": k} for k in self.objects if k.startswith(Prefix)]
        # Two pages, so a paginated listing is actually walked rather than
        # only ever seeing the first result page.
        yield {"Contents": contents[:1]}
        yield {"Contents": contents[1:]}

    def delete_object(self, Bucket, Key):  # noqa: N803
        if self._fail_delete:
            raise ClientError({"Error": {"Code": "AccessDenied"}}, "DeleteObject")
        self.deleted.append(Key)
        self.objects.remove(Key)


def _dump_writes(payload=b"complete-dump"):
    def dump(cmd, **kwargs):
        Path(cmd[cmd.index("-f") + 1]).write_bytes(payload)
    return dump


def test_require_s3_without_a_bucket_never_touches_the_database(tmp_path):
    """The state the Blueprint's coverage-db-backup cron ships in. It must be
    a complete no-op: not a dump thrown away with the container, and not a
    red cron every night that teaches its one reader to ignore red crons."""
    with patch("core.management.commands.backup_db.subprocess.run") as dump:
        with override_settings(BACKUP_S3_BUCKET=""):
            call_command("backup_db", dest=str(tmp_path), require_s3=True)
    dump.assert_not_called()
    assert not list(tmp_path.iterdir())


def test_a_configured_bucket_receives_the_snapshot_under_its_prefix(tmp_path):
    fake = FakeS3()
    with patch("core.management.commands.backup_db.subprocess.run",
               side_effect=_dump_writes()), \
            patch.object(Command, "client", return_value=fake):
        with override_settings(BACKUP_S3_BUCKET="coverage-backups", BACKUP_S3_PREFIX="db/"):
            call_command("backup_db", dest=str(tmp_path), keep=3, require_s3=True)

    local = list(tmp_path.glob("coverage_*.dump"))
    assert len(local) == 1
    (filename, bucket, key), = fake.uploaded
    assert filename == str(local[0])
    assert bucket == "coverage-backups"
    assert key == f"db/{local[0].name}"


def test_the_ring_is_pruned_in_the_bucket_too_and_never_the_new_object(tmp_path):
    """A ring that prunes the container's throwaway disk and lets the bucket
    grow forever is a bill, not a retention policy."""
    fake = FakeS3(existing=[
        "db/coverage_2026-01-01_000000_000000.dump",
        "db/coverage_2026-01-02_000000_000000.dump",
        "db/coverage_2026-01-03_000000_000000.dump",
        "db/unrelated.txt",
    ])
    with patch("core.management.commands.backup_db.subprocess.run",
               side_effect=_dump_writes()), \
            patch.object(Command, "client", return_value=fake):
        with override_settings(BACKUP_S3_BUCKET="coverage-backups", BACKUP_S3_PREFIX="db/"):
            call_command("backup_db", dest=str(tmp_path), keep=2, require_s3=True)

    new_key = fake.uploaded[0][2]
    # Oldest first, down to `keep`, and the object just written survives.
    assert fake.deleted == [
        "db/coverage_2026-01-01_000000_000000.dump",
        "db/coverage_2026-01-02_000000_000000.dump",
    ]
    assert new_key in fake.objects
    # Nothing that is not one of this command's own snapshots is ever touched.
    assert "db/unrelated.txt" in fake.objects


def test_a_failed_upload_is_loud_and_keeps_the_only_copy_there_is(tmp_path):
    fake = FakeS3(fail_upload=ClientError({"Error": {"Code": "NoSuchBucket"}}, "PutObject"))
    with patch("core.management.commands.backup_db.subprocess.run",
               side_effect=_dump_writes()), \
            patch.object(Command, "client", return_value=fake):
        with override_settings(BACKUP_S3_BUCKET="coverage-backups"):
            with pytest.raises(CommandError, match="upload to coverage-backups failed"):
                call_command("backup_db", dest=str(tmp_path), keep=2, require_s3=True)
    assert len(list(tmp_path.glob("coverage_*.dump"))) == 1


def test_remote_retention_preserves_other_prefixes_and_non_snapshot_objects(tmp_path):
    preserved = [
        "db/other-project/coverage_2026-01-01_000000_000000.dump",
        "db/coverage_2026-01-01_000000_000000.dump.partial",
        "db/coverage_2026-01-01_report.csv",
        "db/coverage_notes.dump",
    ]
    old_snapshot = "db/coverage_2026-01-01_000000_000000.dump"
    fake = FakeS3(existing=[old_snapshot, *preserved])
    with patch("core.management.commands.backup_db.subprocess.run", side_effect=_dump_writes()), \
            patch.object(Command, "client", return_value=fake), \
            override_settings(BACKUP_S3_BUCKET="coverage-backups", BACKUP_S3_PREFIX="db/"):
        call_command("backup_db", dest=str(tmp_path), keep=1, require_s3=True)
    assert fake.deleted == [old_snapshot]
    assert set(preserved).issubset(fake.objects)


def test_local_retention_only_removes_timestamped_snapshot_files(tmp_path):
    old_snapshot = tmp_path / "coverage_2026-01-01_000000_000000.dump"
    old_snapshot.write_bytes(b"old snapshot")
    unrelated = tmp_path / "coverage_notes.dump"
    unrelated.write_bytes(b"user notes")
    with patch("core.management.commands.backup_db.subprocess.run", side_effect=_dump_writes()), \
            override_settings(BACKUP_S3_BUCKET=""):
        call_command("backup_db", dest=str(tmp_path), keep=1)
    assert unrelated.read_bytes() == b"user notes"
    assert not old_snapshot.exists()
    assert len(list(tmp_path.glob("coverage_*.dump"))) == 2


def test_new_backup_survives_a_clock_rollback_locally_and_remotely(tmp_path):
    # A previous host's clock can be ahead. The newly completed dump is
    # still the one this invocation must retain and upload.
    future_name = "coverage_9999-01-01_000000_000000.dump"
    (tmp_path / future_name).write_bytes(b"previous snapshot")
    fake = FakeS3(existing=[f"db/{future_name}"])
    with patch("core.management.commands.backup_db.subprocess.run", side_effect=_dump_writes()), \
            patch.object(Command, "client", return_value=fake), \
            override_settings(BACKUP_S3_BUCKET="coverage-backups", BACKUP_S3_PREFIX="db/"):
        call_command("backup_db", dest=str(tmp_path), keep=1, require_s3=True)
    (filename, _bucket, key), = fake.uploaded
    assert Path(filename).read_bytes() == b"complete-dump"
    assert not (tmp_path / future_name).exists()
    assert fake.objects == [key]


def test_a_bucket_that_cannot_be_pruned_still_reports_a_successful_backup(tmp_path):
    fake = FakeS3(existing=["db/coverage_2026-01-01_000000_000000.dump"], fail_delete=True)
    with patch("core.management.commands.backup_db.subprocess.run",
               side_effect=_dump_writes()), \
            patch.object(Command, "client", return_value=fake):
        with override_settings(BACKUP_S3_BUCKET="coverage-backups", BACKUP_S3_PREFIX="db/"):
            call_command("backup_db", dest=str(tmp_path), keep=1, require_s3=True)
    assert fake.uploaded


def test_missing_storage_credentials_fail_before_the_database_is_read(tmp_path):
    """A bucket named without the credentials to reach it used to mean a full
    read of production, taken and then thrown away."""
    storages = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
    with patch("core.management.commands.backup_db.subprocess.run") as dump:
        with override_settings(BACKUP_S3_BUCKET="coverage-backups", STORAGES=storages):
            with pytest.raises(CommandError, match="MEDIA_S3_ENDPOINT_URL"):
                call_command("backup_db", dest=str(tmp_path), require_s3=True)
    dump.assert_not_called()


def test_no_bucket_and_no_require_flag_still_takes_a_local_snapshot(tmp_path):
    """The laptop path this command was written for is untouched."""
    with patch("core.management.commands.backup_db.subprocess.run",
               side_effect=_dump_writes()):
        with override_settings(BACKUP_S3_BUCKET=""):
            call_command("backup_db", dest=str(tmp_path), keep=2)
    assert len(list(tmp_path.glob("coverage_*.dump"))) == 1
