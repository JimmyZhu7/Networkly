"""Prepare optional mail classification before the atomic local write phase.

No mailbox text is persisted here. Automatic classifiers remain free to the
user; their provider cost is bounded independently of paid rescan credits.
"""
from dataclasses import dataclass
import logging

from django.contrib.auth import get_user_model
from django.db import connection

from core.ratelimits import window_exceeded
from directory import ai_extract
from . import appmail, mailfacts
from .gmail_residue import MAX_RESIDUE_THREADS
from .locks import enrichment_lock

logger = logging.getLogger(__name__)


@dataclass
class PreparedEnrichment:
    application: appmail.Detection | None = None
    auto: list | None = None


def prepare_findings(user, findings, *, dry_run=False, guard=None):
    """Bound optional calls to the existing 100-thread ceiling per hour.

    No optional provider calls in dry runs, existing write transactions, or
    overlapping same-account passes. A failed/exhausted cache gate falls back
    to deterministic classification and the existing review surfaces.
    """
    prepared = [PreparedEnrichment() for _ in findings]
    enabled = not dry_run and not connection.in_atomic_block and ai_extract.is_configured()
    if not enabled:
        return prepared
    calls = 0

    def classify(provider, subject, snippet):
        nonlocal calls
        if calls >= MAX_RESIDUE_THREADS:
            return None
        if guard is not None:
            guard()
        if not get_user_model().objects.filter(
            pk=user.pk, is_active=True, deleted_at__isnull=True,
        ).exists():
            return None
        try:
            exceeded = window_exceeded(
                f"capture:optional-ai:{user.pk}", limit=MAX_RESIDUE_THREADS, seconds=3600,
            )
        except Exception:
            logger.warning("Optional mail classification rate guard unavailable for user %s", user.pk)
            return None
        if exceeded:
            return None
        calls += 1
        return provider(subject, snippet)

    with enrichment_lock(user.pk) as acquired:
        if not acquired:
            return prepared
        resolver = appmail.Resolver(user)
        for index, finding in enumerate(findings):
            if not finding.get("found"):
                continue
            try:
                prepared[index].application = appmail.detect(
                    finding, firm_domains=resolver.domains,
                    ai_classifier=lambda subject, snippet: classify(
                        ai_extract.extract_application_event_ai, subject, snippet,
                    ),
                )
            except Exception:
                # The apply phase retries the cheap detector and reports any
                # deterministic parser failure through its usual counters.
                logger.warning("Optional application classification failed for user %s", user.pk)
            if not finding.get("auto_reply") or finding.get("outreach_sent") or finding.get("bounced") or finding.get("soft_bounce"):
                continue
            try:
                text = mailfacts._finding_text(finding)
                prepared[index].auto = mailfacts._detect_auto(text) or mailfacts._detect_ai(
                    text, finding, ai_classifier=lambda subject, snippet: classify(
                        ai_extract.extract_mail_fact_ai, subject, snippet,
                    ),
                )
            except Exception:
                logger.warning("Optional auto-reply classification failed for user %s", user.pk)
    return prepared
