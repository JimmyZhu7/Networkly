"""Bind sensitive settings changes to a proposal and a later human reply.

The authority comes from stored, tenant-scoped conversation rows. Neither
model arguments nor text quoted in an uploaded document can grant it.
"""

import json

from .models import ChatMessage


_CONFIRMATIONS = frozenset({
    "yes", "yes please", "yes do it", "yes confirm", "confirm", "confirmed",
    "i confirm", "do it", "go ahead", "please proceed", "proceed",
})


def approved_settings(user, conversation):
    """Read once at turn start, after the actual user message is persisted.

    Only the immediately preceding completed answer can supply proposals.
    A failure, another human message, or a changed value requires a new
    proposal. Keeping this snapshot fixed also blocks same-turn self-approval.
    """
    rows = list(
        ChatMessage.objects.for_user(user)
        .filter(conversation=conversation)
        .order_by("-created", "-id")[:50]
    )
    if len(rows) < 3:
        return ()
    reply, answer = rows[:2]
    if (
        reply.role != ChatMessage.ROLE_USER
        or reply.is_tool_result
        or any(block.get("type") != "text" for block in reply.blocks())
        or " ".join(reply.text.casefold().split()).rstrip(".! ") not in _CONFIRMATIONS
        or answer.role != ChatMessage.ROLE_ASSISTANT
        or answer.notice
        or answer.tool_names
        or not answer.text.strip()
    ):
        return ()

    proposals = {}
    for row in rows[2:]:
        if row.notice:
            return ()
        if row.role == ChatMessage.ROLE_USER and not row.is_tool_result:
            break
        if not row.is_tool_result:
            continue
        for block in reversed(row.blocks()):
            if not block.get("is_error"):
                continue
            try:
                result = json.loads(block.get("content", ""))
            except (TypeError, ValueError):
                continue
            proposal = result.get("settings_proposal") if isinstance(result, dict) else None
            if (
                isinstance(proposal, dict)
                and set(proposal) == {"field", "value", "before"}
                and all(isinstance(value, str) for value in proposal.values())
            ):
                # Newest proposal for each field wins; an earlier proposed
                # value in the same answer must not remain authorized.
                proposals.setdefault(proposal["field"], proposal)
    return tuple(proposals.values())
