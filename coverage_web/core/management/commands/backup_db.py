"""One consistent snapshot of the database, kept on a small ring.

    python manage.py backup_db                # ~/Backups/coverage/
    python manage.py backup_db --dest /path --keep 14

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
"""

from __future__ import annotations

import os
import subprocess
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "pg_dump the app database to a timestamped file, keeping the newest N."

    def add_arguments(self, parser):
        parser.add_argument("--dest", default=str(Path.home() / "Backups" / "coverage"))
        parser.add_argument("--keep", type=int, default=14,
                            help="How many snapshots to retain (default 14).")

    def handle(self, *args, **opts):
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
        snapshots = sorted(dest.glob("coverage_*.dump"))
        for old in snapshots[:-opts["keep"]]:
            old.unlink()

        self.stdout.write(self.style.SUCCESS(
            f"{out.name} written ({size_mb:.1f} MB) — "
            f"{min(len(snapshots), opts['keep'])} snapshot(s) on the ring"))
