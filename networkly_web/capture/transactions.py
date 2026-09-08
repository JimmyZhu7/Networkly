"""Short, owner-first write fences for capture review actions."""
from contextlib import contextmanager

from django.contrib.auth import get_user_model

from crm.services import atomic_pipeline


@contextmanager
def locked_capture_row(instance):
    """Refresh a tenant row under the same lock order as account deletion.

    Cached card instances cannot authorize a second click or overwrite a newer
    resolution. All nested domain writes share this transaction and savepoints.
    Missing/deactivated owners and deleted rows are harmless no-ops.
    """
    with atomic_pipeline():
        active = get_user_model().objects.select_for_update().filter(
            pk=instance.user_id, is_active=True, deleted_at__isnull=True,
        ).exists()
        row = None
        if active:
            row = type(instance).all_objects.select_for_update(of=("self",)).filter(
                pk=instance.pk, user_id=instance.user_id,
            ).first()
        if row is None:
            yield None
        else:
            instance.__dict__.update(row.__dict__)
            yield instance
