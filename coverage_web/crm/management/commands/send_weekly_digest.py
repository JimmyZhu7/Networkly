"""send_weekly_digest — Coverage's retention loop: what closes this week, who
to ping, and (when there's a real fit) what's new, mailed once a week to
every onboarded student who has something to act on.

    python manage.py send_weekly_digest --dry-run            # render every recipient, send nothing
    python manage.py send_weekly_digest --user a@b.com       # one account, real send (testing)
    python manage.py send_weekly_digest                      # every onboarded, opted-in-by-default user

WHY THIS SHIPS COMPLETE WITH ZERO PAID SETUP. Outbound email already has one
point of configuration, in settings/production.py:
`vars().update(env.email_url("EMAIL_URL", default="consolemail://"))`. Unset,
mail is printed to the service logs instead of actually sent — so this
command is safe to point a cron/scheduler at in production today, before
anyone has bought an SMTP relay: nothing breaks, nothing bounces, nothing
costs money, and the rendered digest is inspectable in the logs exactly like
a password-reset email is today. Buying a real provider later is a one-line
env var change (`EMAIL_URL=smtp+tls://...`, see .env.example); it requires no
change to this command, `crm/digest.py`, or the templates.

WHO GETS ONE. Every `User` with `onboarded_at` set (accounts/models.py),
`deleted_at` unset, `weekly_digest_opt_out` False, AND something to report
this week — `crm.digest.assemble_digest` returns `None` for everyone else,
and that skip is logged by email so a dry run reads as a full roster, not a
silent partial one. See that module's docstring for the exact "nothing to
report" rule.

OPT-OUT. `User.weekly_digest_opt_out` (default False — opted IN by default,
same posture as the rest of this docstring's title) is set from the
Notifications card on Settings (accounts/forms.NotificationsForm), the same
card the Push Alerts toggle lives on. `--user` bypasses this gate along with
`onboarded_at`, since it exists for previewing/testing a specific account
regardless of their live preference.

TIMEZONE. Every other "today" boundary in this app activates the user's own
`User.timezone` per request (`accounts.middleware.TimezoneMiddleware`) so a
Hong Kong student's week rolls over on Hong Kong midnight, not UTC's. A
management command has no request for that middleware to run against, so
`_local_today` below replicates its exact activate/fallback/deactivate
contract for each user in turn — see that function's docstring.

HOW MUCH MAIL THIS COSTS IN A DAY, WHICH IS THE THING THAT NEARLY BROKE IT.
The cron ran `0 13 * * 1`: every eligible account, mailed inside one minute,
once a week. At the invited beta's cap of 100 students that is up to 100
messages on one calendar day, and the free mail tier this deploy is sized
for allows 100 a day in TOTAL. The digest would have spent the whole day's
allowance on itself and left nothing for the mail somebody is actually
waiting on — the email confirmation, the password reset, the invitation.
Nobody would have seen an error either: those sends fail at the provider,
after the app has already told the student to check their inbox.

Two mechanisms, and they do different jobs.

`--spread` (what render.yaml's now-DAILY cron passes) sends only the seventh
of the roster whose `pk % 7` matches the run's UTC weekday — see
`_send_today`. Every student still gets exactly one digest every seven days,
on the same weekday every week; the day's bill is a seventh of what it was.
Without the flag the whole roster is considered, which is what a founder
running this by hand means, and what every test in this suite assumes.

`settings.DIGEST_DAILY_SEND_CAP` (default 60) is the hard ceiling, and it
applies either way. Recipients past it are DEFERRED, not dropped, and
deterministically so: the roster is ordered by `email` and, under --spread,
fixed by `pk % 7`, so the students below the line are the same students in
the same order next time their slot comes round rather than a fresh shuffle
of who loses. The count is printed. It applies to `--dry-run` too, because a
dry run that reports sends a real run would not make is not a rehearsal.
"""

from __future__ import annotations

from datetime import date
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMultiAlternatives
from django.core.management.base import BaseCommand, CommandError
from django.template.loader import render_to_string
from django.utils import timezone

from crm.digest import assemble_digest
from ops.tracking import track_job_run


def _local_today(user) -> date:
    """This user's `timezone.localdate()`, activated exactly the way
    `accounts.middleware.TimezoneMiddleware` would for a request: a blank or
    unrecognized zone falls back to the project default rather than raising,
    the same "validated on write is not trustworthy on read" posture that
    middleware documents. Caller is responsible for `timezone.deactivate()`
    afterward — this loop runs many users on one thread/process, and a stuck
    activation would leak one student's zone into the next student's
    "today", exactly the bug the middleware's own `finally` exists to
    prevent."""
    name = (getattr(user, "timezone", "") or "").strip()
    if name:
        try:
            timezone.activate(ZoneInfo(name))
        except (ZoneInfoNotFoundError, ValueError):
            timezone.deactivate()
    else:
        timezone.deactivate()
    return timezone.localdate()


#: How many runs one full pass over the roster takes. Seven, because the
#: digest is weekly per student and the cron now ticks daily: a student's
#: slot repeats every seven runs, which is the cadence the email's own copy
#: ("closing this week") promises.
SPREAD_DAYS = 7


def _send_today(user, *, weekday: int) -> bool:
    """Is this user's slot today?

    `pk % 7` rather than a hash of the email: primary keys are sequential, so
    the modulus spreads a roster into seven groups of near-equal size, which
    is the whole point — a hash spreads *randomly*, and a random split of 100
    students has visibly uneven days. It is stable for the life of the
    account (the pk never changes), needs no stored state and no migration,
    and is the same answer in every process, which `hash()` is not.

    `weekday` is the RUN's UTC weekday, not the student's local one, because
    the budget this protects is the mail provider's daily quota and the
    provider counts days on its own clock, not on each recipient's.
    """
    return user.pk % SPREAD_DAYS == weekday


def _subject(digest: dict) -> str:
    """No em dash (house copy style): a comma-joined clause list instead."""
    n_closing = len(digest["closing"])
    n_actions = len(digest["actions"])
    parts = []
    if n_closing:
        parts.append(f"{n_closing} closing this week")
    if n_actions:
        parts.append(f"{n_actions} to ping")
    # assemble_digest only ever returns a digest when at least one of these
    # is non-empty, so `parts` is never empty here — the fallback exists so a
    # future third section can't silently produce a blank subject.
    return "Coverage: " + ", ".join(parts) if parts else "Coverage: your weekly digest"


class Command(BaseCommand):
    help = "Send the weekly digest email to onboarded users who have something to act on."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Render every recipient's digest and report it. Sends nothing.")
        parser.add_argument(
            "--user", metavar="EMAIL", default="",
            help="Restrict to one account by email, bypassing the onboarded_at "
                 "gate and the weekly_digest_opt_out preference — for "
                 "previewing or testing a specific user's digest.")
        parser.add_argument(
            "--spread", action="store_true",
            help="Send only the seventh of the roster whose weekly slot is "
                 "today (pk %% 7 == this run's UTC weekday). What the daily "
                 "cron passes. Without it the whole roster is considered, "
                 "still under the daily send cap.")

    def handle(self, *args, **opts):
        # "weekly-digest" matches render.yaml's coverage-weekly-digest cron —
        # see ops/tracking.py.
        with track_job_run("weekly-digest"):
            dry = opts["dry_run"]
            tag = "[dry-run] " if dry else ""
            User = get_user_model()

            if opts["user"]:
                try:
                    users = [User.objects.get(
                        email__iexact=opts["user"], is_active=True, deleted_at__isnull=True,
                    )]
                except User.DoesNotExist as exc:
                    raise CommandError(f"no user with email {opts['user']!r}") from exc
            else:
                users = list(
                    User.objects.filter(
                        is_active=True, onboarded_at__isnull=False, deleted_at__isnull=True,
                        weekly_digest_opt_out=False,
                    )
                    .order_by("email")
                )
                if opts["spread"]:
                    weekday = timezone.now().weekday()
                    users = [u for u in users if _send_today(u, weekday=weekday)]

            if not users:
                self.stdout.write("No eligible users (onboarded, not deleted, not opted out).")
                return

            # Clamped, not trusted: a cap above the provider's own daily
            # allowance is the one value that cannot be right, and a cap
            # below one would mail nobody forever. base.py rejects < 1 at
            # boot; this is the second half of the same guard for a value
            # overridden in a test or a shell.
            cap = max(1, int(getattr(settings, "DIGEST_DAILY_SEND_CAP", 60)))

            site_url = getattr(settings, "SITE_URL", "").rstrip("/")
            sent = skipped = deferred = 0
            for index, user in enumerate(users):
                if sent >= cap:
                    # Everyone from here on is DEFERRED, not dropped, and
                    # deterministically so: this run's roster is ordered by
                    # email and this run's membership is fixed by `pk % 7`,
                    # so the students below the line are the same students
                    # next time their slot comes round, in the same order —
                    # not a fresh shuffle of who loses. Counted by position
                    # rather than by arithmetic on the tallies, so an account
                    # deactivated mid-loop cannot inflate it.
                    deferred = len(users) - index
                    self.stdout.write(self.style.WARNING(
                        f"{tag}daily send cap of {cap} reached — "
                        f"{deferred} recipient(s) deferred to their next run"))
                    break
                if not User.objects.filter(pk=user.pk, is_active=True, deleted_at__isnull=True).exists():
                    continue
                try:
                    today = _local_today(user)
                    digest = assemble_digest(user, today=today)
                finally:
                    timezone.deactivate()

                if digest is None:
                    skipped += 1
                    self.stdout.write(f"{tag}- {user.email}: nothing to report, skipped")
                    continue

                ctx = {"user": user, "digest": digest, "site_url": site_url}
                subject = _subject(digest)
                text_body = render_to_string("crm/emails/weekly_digest.txt", ctx)
                html_body = render_to_string("crm/emails/weekly_digest.html", ctx)

                self.stdout.write(
                    f"{tag}+ {user.email}: {len(digest['closing'])} closing, "
                    f"{len(digest['actions'])} to ping, {len(digest['picks'])} new picks")
                sent += 1
                if dry:
                    continue

                if not User.objects.filter(pk=user.pk, is_active=True, deleted_at__isnull=True).exists():
                    continue
                message = EmailMultiAlternatives(subject=subject, body=text_body, to=[user.email])
                message.attach_alternative(html_body, "text/html")
                message.send()

            self.stdout.write(self.style.SUCCESS(
                f"{tag}{sent} digest(s) {'rendered' if dry else 'sent'} "
                f"· {skipped} skipped (nothing to report) "
                f"· {deferred} deferred (daily cap {cap})"))
