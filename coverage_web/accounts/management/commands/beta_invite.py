"""Reserve beta seats without creating users or sending invitations."""

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from accounts.beta import capacity_status, invite_emails


class Command(BaseCommand):
    help = "Reserve invitation-only beta seats by Google email. Sends no email."

    def add_arguments(self, parser):
        parser.add_argument("emails", nargs="+")

    def handle(self, *args, **options):
        try:
            results = invite_emails(options["emails"])
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages)) from exc
        for seat, created in results:
            state = "reserved" if created else ("already used" if seat.redeemed_at else "already reserved")
            self.stdout.write(f"{seat.email or 'Deleted account seat'}: {state}")
        status = capacity_status()
        self.stdout.write(f"{status['used']}/{status['limit']} seats counted. No email sent.")
