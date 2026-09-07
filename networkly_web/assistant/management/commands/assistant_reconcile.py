"""Refund abandoned chat reservations; never touch a live conversation."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from assistant.recovery import DEFAULT_RECOVERY_MINUTES, reconcile_reservations
from ops.tracking import track_job_run


class Command(BaseCommand):
    help = "Inspect abandoned assistant credit reservations; --apply refunds them once."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--user", metavar="EMAIL")
        parser.add_argument("--older-than-minutes", type=int, default=DEFAULT_RECOVERY_MINUTES)
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        if options["older_than_minutes"] < 1 or not 1 <= options["limit"] <= 1000:
            raise CommandError("Age must be positive; limit must be between 1 and 1000.")
        user = None
        if options["user"]:
            user = get_user_model().objects.filter(email__iexact=options["user"]).first()
            if user is None:
                raise CommandError("No user with that email.")
        kwargs = dict(user=user, apply=options["apply"],
                      older_than_minutes=options["older_than_minutes"], limit=options["limit"])
        if options["apply"]:
            with track_job_run("assistant-reconcile"):
                stats = reconcile_reservations(**kwargs)
        else:
            stats = reconcile_reservations(**kwargs)
        mode = "applied" if options["apply"] else "dry run"
        self.stdout.write(
            f"{stats['checked']} checked; {stats['busy']} still running; "
            f"{stats['recoverable']} recoverable; {stats['refunded']} refunded ({mode})."
        )
