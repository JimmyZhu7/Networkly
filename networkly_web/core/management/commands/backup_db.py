"""One consistent snapshot of the database, kept on a small ring.

    python manage.py backup_db                # ~/Backups/coverage/
    python manage.py backup_db --dest /path --keep 14
    python manage.py backup_db --require-s3   # the deploy's cron: off-host or nothing

pg_dump in custom format (-Fc): compressed, and restorable table-by-table with
pg_restore rather than all-or-nothing psql. The ring keeps the newest N and
deletes older ones so an unattended schedule cannot quietly fill a disk.

This command is the free half of the backup story; wiring it to a schedule is
a deploy-time decision (cron, launchd, or the host's own snapshots). It exists
now because the first real user's data deserves a restore path from day one —
"the database is local" is an availability statement, not a durability one.

RESTORE, verified 2026-08-08 against a live 3.0 MB dump. A backup that has
never been restored is hope, not a backup, so the exact commands are here
rather than left to be improvised during the emergency:

    createdb coverage_restore_drill
    pg_restore -d coverage_restore_drill --no-owner ~/Backups/coverage/<dump>
    psql -d coverage_restore_drill -c "SELECT count(*) FROM contacts"
    dropdb coverage_restore_drill        # when only drilling

`--no-owner` matters: the dump records the role that made it, and without
this pg_restore fails on any machine where that role does not exist — which
is exactly the machine you are restoring onto after losing the first one.

To restore FOR REAL, target a fresh database and repoint DATABASE_URL at it.
Never pg_restore over the live database: the dump has no DROP statements
without --clean, so it merges into whatever is already there and leaves a
silent half-old, half-new mixture. Restore beside, verify counts, then swap.

The drill compared all seven tables live-versus-restored (users 4, contacts
170, touches 195, firms 119, opportunities 9,012, user_opportunities 16,
product_events 116) — every one matched, and row contents survived intact.

OFF-HOST COPY (--s3-bucket / --require-s3). A dump written inside a Render
container is not a backup: the filesystem goes away with the container, so a
scheduled `backup_db` on that host would dump the database, print a
reassuring size, and delete the result. The bucket is what makes the
schedule mean anything.

  - The bucket NAME comes from `settings.BACKUP_S3_BUCKET` (or --s3-bucket)
    and is deliberately its own setting, separate from the avatar bucket:
    one file here is every row in the app, and it does not belong in the
    same listing as media a request path can reach. The ENDPOINT, REGION and
    CREDENTIALS are the existing MEDIA_S3_* values, because there is one
    object store account and re-entering the same key under a second name is
    how key rotation starts missing a copy.
  - BLANK IS THE OFF SWITCH, everywhere. No bucket and no --require-s3: the
    local dump happens and nothing is uploaded, exactly as before. No bucket
    WITH --require-s3 (what the cron passes): the command does nothing at
    all — no pg_dump, no connection, no file — and says so. That is what
    lets the backup cron exist in render.yaml before anyone has paid for
    storage, in the same dark-by-default posture as every other optional
    integration in this app.
  - The --keep ring is applied to the bucket too, oldest first, over the
    objects under this prefix only. A ring that pruned the container's
    throwaway disk but let the bucket grow forever is a bill, not a policy.
"""

from __future__ import annotations

import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


_SNAPSHOT_NAME = re.compile(
    r"coverage_\d{4}-\d{2}-\d{2}(?:_\d{6}(?:_\d{6})?)?\.dump"
)


class Command(BaseCommand):
    help = "pg_dump the app database to a timestamped file, keeping the newest N."

    def add_arguments(self, parser):
        parser.add_argument("--dest", default=str(Path.home() / "Backups" / "coverage"))
        parser.add_argument("--keep", type=int, default=14,
                            help="How many snapshots to retain (default 14).")
        parser.add_argument(
            "--s3-bucket", default=None,
            help="Object-storage bucket for the off-host copy. Defaults to "
                 "settings.BACKUP_S3_BUCKET; blank means no upload.")
        parser.add_argument(
            "--s3-prefix", default=None,
            help="Key prefix inside that bucket. Defaults to "
                 "settings.BACKUP_S3_PREFIX.")
        parser.add_argument(
            "--require-s3", action="store_true",
            help="Do nothing at all unless a bucket is configured. What the "
                 "deploy's cron passes: a dump that stays on an ephemeral "
                 "container is not a backup, so it is better not taken.")

    def handle(self, *args, **opts):
        bucket = opts["s3_bucket"]
        if bucket is None:
            bucket = getattr(settings, "BACKUP_S3_BUCKET", "")
        bucket = (bucket or "").strip()
        prefix = opts["s3_prefix"]
        if prefix is None:
            prefix = getattr(settings, "BACKUP_S3_PREFIX", "")
        prefix = (prefix or "").strip().strip("/")

        if not bucket and opts["require_s3"]:
            # Deliberately exit 0. This is the configured-off state, not a
            # failure: the cron is defined in render.yaml before the storage
            # it needs has been bought, and a red cron every night would
            # train the one person watching to ignore red crons.
            self.stdout.write(self.style.WARNING(
                "BACKUP_S3_BUCKET is not set — no snapshot taken. A dump held "
                "only on this host would not survive it."))
            return

        # Built BEFORE pg_dump, deliberately. A bucket named without the
        # credentials to reach it used to be discovered after the dump had
        # already been taken — a full read of production, held for a moment
        # on a disk that is about to disappear, for nothing. Fail on the
        # configuration first; the database is the expensive part.
        client = self.client() if bucket else None

        db = settings.DATABASES["default"]
        if "postgresql" not in db["ENGINE"]:
            raise CommandError(f"backup_db only knows PostgreSQL, not {db['ENGINE']}")

        if opts["keep"] < 1:
            raise CommandError("--keep must be at least 1")
        dest = Path(opts["dest"]).expanduser()
        dest.mkdir(mode=0o700, parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S_%f")
        out = dest / f"coverage_{stamp}.dump"

        partial = out.with_suffix(".dump.partial")
        # Create privately before pg_dump opens it; never expose a partial as a backup.
        fd = os.open(partial, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        cmd = ["pg_dump", "-Fc", "-f", str(partial), "-d", db["NAME"]]
        for flag, key in (("-h", "HOST"), ("-p", "PORT"), ("-U", "USER")):
            if db.get(key):
                cmd += [flag, str(db[key])]
        # Layered over the inherited environment, never replacing it: a bare
        # {"PGPASSWORD": ...} dict wipes PATH and turns "wrong password" into
        # the far more misleading "pg_dump not found".
        env = {**os.environ}
        if db.get("PASSWORD"):
            env["PGPASSWORD"] = db["PASSWORD"]
        for option in ("sslmode", "sslrootcert", "sslcert", "sslkey"):
            if db.get("OPTIONS", {}).get(option):
                env["PG" + option.upper()] = str(db["OPTIONS"][option])

        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True,
                           env=env, timeout=600)
        except FileNotFoundError:
            partial.unlink(missing_ok=True)
            raise CommandError("pg_dump not on PATH — install the Postgres client tools")
        except subprocess.CalledProcessError as exc:
            # A failed dump must not leave a half-written file that a restore
            # later mistakes for a snapshot.
            partial.unlink(missing_ok=True)
            raise CommandError(f"pg_dump failed: {exc.stderr.strip()[:400]}")

        except subprocess.TimeoutExpired as exc:
            partial.unlink(missing_ok=True)
            raise CommandError("pg_dump timed out; the incomplete snapshot was removed") from exc
        if not partial.stat().st_size:
            partial.unlink()
            raise CommandError("pg_dump produced an empty snapshot")
        os.replace(partial, out)

        size_mb = out.stat().st_size / 1_048_576
        # Prune beyond the ring, oldest first, and never the file just written.
        snapshots = sorted(
            path for path in dest.iterdir()
            if path.is_file() and _SNAPSHOT_NAME.fullmatch(path.name)
        )
        previous = [path for path in snapshots if path != out]
        for old in previous[:max(0, len(previous) - (opts["keep"] - 1))]:
            old.unlink()

        self.stdout.write(self.style.SUCCESS(
            f"{out.name} written ({size_mb:.1f} MB) — "
            f"{min(len(snapshots), opts['keep'])} snapshot(s) on the ring"))

        if client is not None:
            kept = self.upload(client, out, bucket=bucket, prefix=prefix,
                               keep=opts["keep"])
            self.stdout.write(self.style.SUCCESS(
                f"{out.name} uploaded to {bucket} — {kept} object(s) on the "
                f"remote ring"))

    # -- the off-host copy -------------------------------------------------

    def client(self):
        """The S3 client, built from the endpoint and credentials the avatar
        storage was already configured with.

        Read out of `settings.STORAGES["default"]` rather than out of the
        environment a second time. `core.storage.media_storage_config` has
        already resolved and validated those four MEDIA_S3_* values (all
        present or none, HTTPS endpoint, no credentials in the URL); reading
        the raw env vars here would duplicate that validation badly and let
        the two halves of one account drift apart. The bucket is the one
        thing NOT taken from there, which is the whole point.

        A method rather than an inline call so a test can substitute a fake
        client: nothing in this command's tests is allowed near a network,
        and a backup command that can only be exercised against real object
        storage is a backup command nobody exercises.

        boto3 is imported here, not at module scope, so every other path
        through this command still works on a checkout without it.
        """
        import boto3

        options = (settings.STORAGES.get("default", {}) or {}).get("OPTIONS", {}) or {}
        endpoint = str(options.get("endpoint_url", "") or "").strip()
        region = str(options.get("region_name", "") or "").strip()
        key_id = str(options.get("access_key", "") or "").strip()
        secret = str(options.get("secret_key", "") or "").strip()
        if not all((endpoint, region, key_id, secret)):
            raise CommandError(
                "A backup bucket is configured but the object-storage "
                "credentials are not. Set MEDIA_S3_ENDPOINT_URL, "
                "MEDIA_S3_REGION_NAME, MEDIA_S3_ACCESS_KEY_ID and "
                "MEDIA_S3_SECRET_ACCESS_KEY on this service.")
        return boto3.client(
            "s3", endpoint_url=endpoint, region_name=region,
            aws_access_key_id=key_id, aws_secret_access_key=secret,
        )

    def upload(self, client, path: Path, *, bucket: str, prefix: str, keep: int) -> int:
        """Put the snapshot in the bucket, then hold the same ring there.

        The remote ring is pruned by KEY NAME, not by the object's own
        LastModified: the key carries this command's own timestamp, so a
        clock skew on the storage provider cannot reorder a ring whose
        ordering the restore procedure depends on. Same lexicographic sort
        the local ring uses, for the same reason.
        """
        key = f"{prefix}/{path.name}" if prefix else path.name
        try:
            client.upload_file(str(path), bucket, key)
        except (BotoCoreError, ClientError) as exc:
            # Loud, and non-zero: unlike the unconfigured case above, this is
            # a bucket that was asked for and did not take the file. The
            # local dump is left in place — it is the only copy there is.
            raise CommandError(f"upload to {bucket} failed: {str(exc)[:400]}") from exc

        listing = client.get_paginator("list_objects_v2")
        listing_prefix = f"{prefix}/" if prefix else ""
        keys = []
        for page in listing.paginate(Bucket=bucket, Prefix=listing_prefix):
            for obj in page.get("Contents", []):
                # A recursive prefix listing can include another project's
                # snapshots, partial uploads, and unrelated coverage_* files.
                # Only exact snapshot names directly in this ring are ours.
                relative = obj["Key"][len(listing_prefix):]
                if _SNAPSHOT_NAME.fullmatch(relative):
                    keys.append(obj["Key"])
        keys.sort()
        previous = [old for old in keys if old != key]
        for old in previous[:max(0, len(previous) - (keep - 1))]:
            try:
                client.delete_object(Bucket=bucket, Key=old)
            except (BotoCoreError, ClientError) as exc:
                # A ring that cannot be pruned is a bill, not a lost backup.
                # Say so and keep the exit code the upload earned.
                self.stderr.write(f"could not prune {old}: {str(exc)[:200]}")
        return min(len(keys), keep)
