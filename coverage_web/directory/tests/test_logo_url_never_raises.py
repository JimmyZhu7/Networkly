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
def test_a_generated_static_mark_still_wins(settings, tmp_path):
    settings.BASE_DIR = tmp_path
    (tmp_path / "static" / "img" / "firm-logos").mkdir(parents=True)
    (tmp_path / "static" / "img" / "firm-logos" / "gen.png").write_bytes(b"png")
    firm = Firm.objects.create(name="Gen", slug="gen", logo="firm-logos/whatever.png")
    assert firm.logo_url.endswith("img/firm-logos/gen.png")


@pytest.mark.django_db
def test_no_logo_at_all_is_still_empty():
    firm = Firm.objects.create(name="Bare", slug="bare")
    assert firm.logo_url == ""
