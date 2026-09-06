"""Serve only the signed-in owner's current avatar, from either backend."""
from django.core.exceptions import SuspiciousFileOperation
from django.http import FileResponse, Http404, HttpResponse
from django.views.decorators.http import require_safe
from botocore.exceptions import BotoCoreError, ClientError

from core.storage import avatar_content_type


@require_safe
def avatar(request, path):
    user = request.user
    if (not user.is_authenticated or not user.is_active or getattr(user, "deleted_at", None)
            or not user.avatar or user.avatar.name != path):
        raise Http404
    try:
        content_type = avatar_content_type(path)
        content = user.avatar.storage.open(path, "rb")
    except (SuspiciousFileOperation, FileNotFoundError):
        raise Http404 from None
    except ClientError as exc:
        if exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") in {403, 404}:
            raise Http404 from None
        return HttpResponse(status=503, headers={"Cache-Control": "private, no-store"})
    except (BotoCoreError, OSError):
        return HttpResponse(status=503, headers={"Cache-Control": "private, no-store"})
    response = FileResponse(content, content_type=content_type)
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response
