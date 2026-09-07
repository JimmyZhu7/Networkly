"""`Firm.logo_url` on a public page must degrade to the monogram, never to a 400.

Production media is the private avatar store, which raises
`SuspiciousFileOperation` for any key outside its prefix. 134 of the 139
local firms carry a stored `logo` under `firm-logos/`, so every firm without
a generated static PNG would have thrown from the Opportunities feed.
"""
from __future__ import annotations

from unittest import mock

import pytest
from django.core.exceptions import SuspiciousFileOperation

from directory.models import Firm


@pytest.mark.django_db
def test_a_refusing_storage_yields_the_empty_fallback_not_an_exception(settings, tmp_path):
    settings.BASE_DIR = tmp_path  # no generated static PNGs exist here
    firm = Firm.objects.create(name="Firm With Old Logo", slug="firm-with-old-logo", logo="firm-logos/x.png")
    # `firm.logo.storage` is Django's lazy DefaultStorage proxy, whose class has
    # no `url` to patch; the property that actually raises is FieldFile.url.
    with mock.patch.object(type(firm.logo), "url", new_callable=mock.PropertyMock,
                           side_effect=SuspiciousFileOperation("outside avatars/")):
        assert firm.logo_url == ""


@pytest.mark.django_db
def test_an_unverified_static_mark_is_not_presented_as_official(settings, tmp_path):
    settings.BASE_DIR = tmp_path
    (tmp_path / "static" / "img" / "firm-logos").mkdir(parents=True)
    (tmp_path / "static" / "img" / "firm-logos" / "gen.png").write_bytes(b"png")
    firm = Firm.objects.create(name="Gen", slug="gen", logo="firm-logos/whatever.png")
    assert firm.logo_url == ""


@pytest.mark.django_db
def test_no_logo_at_all_is_still_empty():
    firm = Firm.objects.create(name="Bare", slug="bare")
    assert firm.logo_url == ""


@pytest.mark.parametrize("tamper", [False, True])
def test_only_reviewed_matching_assets_are_served(settings, tmp_path, tamper):
    import hashlib
    import json
    from directory.firm_logos import firm_logo_url
    settings.BASE_DIR = tmp_path
    root = tmp_path / "static" / "img" / "firm-logos"
    root.mkdir(parents=True)
    original = b"reviewed bytes"
    (root / "known.png").write_bytes(b"replacement" if tamper else original)
    (root / "sources.json").write_text(json.dumps({"known": {
        "reviewed": True, "source_url": "https://example.com/logo.png",
        "sha256": hashlib.sha256(original).hexdigest(),
    }}))
    assert firm_logo_url("known") == ("" if tamper else "/static/img/firm-logos/known.png")


def test_old_uploaded_logo_cannot_bypass_review():
    assert Firm(slug="unreviewed", name="Unreviewed", logo="firm-logos/old.png").logo_url == ""
