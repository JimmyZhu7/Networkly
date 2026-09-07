"""Only reviewed, source-traceable company artwork may be presented as a logo."""
from functools import lru_cache
import hashlib
import json
from pathlib import Path

from django.conf import settings
from django.templatetags.static import static


@lru_cache(maxsize=8)
def verified_library(base_dir: str) -> dict[str, str]:
    root = Path(base_dir) / "static" / "img" / "firm-logos"
    try:
        manifest = json.loads((root / "sources.json").read_text())
    except (OSError, ValueError):
        return {}
    if not isinstance(manifest, dict):
        return {}
    verified = {}
    for slug, record in manifest.items():
        if not isinstance(record, dict) or record.get("reviewed") is not True:
            continue
        if not record.get("source_url", "").startswith("https://"):
            continue
        if not slug or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for c in slug):
            continue
        try:
            digest = hashlib.sha256((root / f"{slug}.png").read_bytes()).hexdigest()
        except OSError:
            continue
        if digest == record.get("sha256"):
            verified[slug] = f"img/firm-logos/{slug}.png"
    return verified


def firm_logo_url(slug: str) -> str:
    asset = verified_library(str(settings.BASE_DIR)).get(slug)
    return static(asset) if asset else ""
