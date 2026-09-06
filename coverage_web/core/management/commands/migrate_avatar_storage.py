"""Copy local avatars, preserving keys by default or explicitly rekeying."""
import hashlib
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured, SuspiciousFileOperation
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.storage import PrivateMediaStorage, avatar_content_type


def _digest(stream):
    checksum = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        checksum.update(chunk)
    return checksum.hexdigest()


class Command(BaseCommand):
    help = "Preview copying local avatars to private S3; use --apply to upload. Local files are never deleted."

    def add_arguments(self, parser):
        parser.add_argument("--source-root", help="Existing local MEDIA_ROOT; defaults to the current MEDIA_ROOT.")
        parser.add_argument("--apply", action="store_true", help="Copy and verify files; never overwrite remote objects.")
        parser.add_argument("--rekey", action="store_true", help="Use fresh UUID keys and update unchanged avatar references after verification; requires --apply to write.")

    def handle(self, *args, **options):
        if not isinstance(default_storage, PrivateMediaStorage):
            raise CommandError("Configure the private S3 media backend before running this migration.")
        if options.get("rekey"):
            return self._rekey(options)
        if options["apply"]:
            # Reject an unsupported provider before reading rows or copying
            # the first file, rather than failing partway through migration.
            try:
                default_storage.require_conditional_put_support()
            except ImproperlyConfigured as exc:
                raise CommandError(str(exc)) from None
        source_root = Path(options["source_root"] or settings.MEDIA_ROOT).resolve()
        # Operator-only deployment migration across all users. Only actual
        # avatar references are copied; arbitrary files under MEDIA_ROOT are
        # never uploaded and no user row is modified.
        names = list(get_user_model().objects.exclude(avatar="").exclude(avatar__isnull=True)
                     .order_by("avatar").values_list("avatar", flat=True).distinct())
        copied = existing = failed = previewed = 0
        for name in names:
            try:
                avatar_content_type(name)
                source = (source_root / name).resolve()
                if not source.is_relative_to(source_root) or not source.is_file():
                    raise ValueError("missing or unsafe local file")
                if not options["apply"]:
                    previewed += 1
                    continue
                with source.open("rb") as content:
                    expected = _digest(content)
                    content.seek(0)
                    created = default_storage.save_if_absent(name, content, sha256=expected)
                # Verify bytes even when the key already existed. A same-
                # named different object is a conflict, never a reason to
                # overwrite it or point the DB at a silently renamed file.
                with default_storage.open(name, "rb") as remote:
                    if _digest(remote) != expected:
                        raise ValueError("remote content differs")
                if created:
                    copied += 1
                else:
                    existing += 1
            except (OSError, ValueError, SuspiciousFileOperation):
                failed += 1
                self.stderr.write("One avatar is missing, unsafe, or conflicts with remote content; left unchanged.")
            except Exception:  # provider errors must never print credentials/URLs
                failed += 1
                self.stderr.write("One avatar could not be copied or verified; check storage access and retry.")
        if options["apply"]:
            self.stdout.write(f"{copied} copied and verified; {existing} already identical; {failed} failed. Local files retained.")
        else:
            self.stdout.write(f"Dry run: {previewed} local avatar(s) ready; {failed} missing/unsafe. No remote calls or writes. Re-run with --apply.")
        if failed:
            raise CommandError("Avatar migration is incomplete. Resolve failures before switching traffic to remote storage.")

    def _rekey(self, options):
        """Use the ordinary UUID upload path, never the legacy remote key.

        This mode deliberately does not claim conditional PUT support. It
        uses fresh UUID names and storage.save's collision handling, exactly
        as normal avatar uploads do, then compares the original DB reference.
        """
        root = Path(options["source_root"] or settings.MEDIA_ROOT).resolve()
        users = get_user_model().objects
        references = list(users.exclude(avatar="").exclude(avatar__isnull=True)
                          .order_by("pk").values_list("pk", "avatar"))
        copied = failed = previewed = 0
        for user_id, original in references:
            uploaded = None
            committed = False
            try:
                avatar_content_type(original)
                source = (root / original).resolve()
                if not source.is_relative_to(root) or not source.is_file():
                    raise ValueError("missing or unsafe local file")
                if not options["apply"]:
                    previewed += 1
                    continue
                name = f"avatars/{uuid4().hex}{Path(original).suffix.lower()}"
                with source.open("rb") as content:
                    expected = _digest(content)
                    content.seek(0)
                    uploaded = default_storage.save(name, content)
                with default_storage.open(uploaded, "rb") as remote:
                    if _digest(remote) != expected:
                        raise ValueError("remote verification failed")
                with transaction.atomic():
                    changed = users.filter(pk=user_id, avatar=original).update(avatar=uploaded)
                    if changed != 1:
                        raise ValueError("avatar changed concurrently")
                committed = True
                copied += 1
            except Exception:
                failed += 1
                self.stderr.write("One avatar rekey could not be confirmed; its local file was retained.")
            finally:
                if uploaded is not None and not committed:
                    # A commit error can leave an uncertain outcome. Never
                    # remove an object while any user references it; on a DB
                    # outage or ambiguous upload failure, retain the orphan.
                    try:
                        if not users.filter(avatar=uploaded).exists():
                            default_storage.delete(uploaded)
                    except Exception:
                        self.stderr.write("An unconfirmed upload was retained; check storage before retrying.")
        if options["apply"]:
            self.stdout.write(f"{copied} rekeyed and verified; {failed} failed. Local files retained.")
        else:
            self.stdout.write(f"Dry run: {previewed} avatar reference(s) ready for new keys; {failed} missing/unsafe. No remote calls or writes. Re-run with --rekey --apply.")
        if failed:
            raise CommandError("Avatar rekey migration is incomplete. Resolve failures before switching traffic.")
