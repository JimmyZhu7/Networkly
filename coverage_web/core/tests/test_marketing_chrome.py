"""Marketing contrast, bounded motion, and accessible comparison navigation."""
from pathlib import Path
import re

import pytest

STATIC = Path(__file__).resolve().parents[2] / "static"


def _css(name):
    return (STATIC / "css" / name).read_text()


def _luminance(hex_color):
    values = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    channels = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in values]
    return sum(c * weight for c, weight in zip(channels, (.2126, .7152, .0722)))


@pytest.mark.django_db
def test_home_monogram_ink_clears_AA(client):
    """Illustrative initials inherit accessible semantic colors in both themes."""
    html = client.get("/").content.decode()
    css = _css("marketing.css")
    assert 'class="mk-avatar"' in html
    assert re.search(r'\.mk-avatar\s*\{[^}]*background: var\(--accent-soft\);[^}]*color: var\(--accent-ink\)', css)
    for fg, bg in [("#214ba9", "#eef2fc"), ("#c6d5ff", "#2b374d")]:
        light, dark = sorted((_luminance(fg), _luminance(bg)), reverse=True)
        assert (light + .05) / (dark + .05) >= 4.5


@pytest.mark.django_db
@pytest.mark.parametrize("url,asset", [("/", "marketing.css"), ("/pricing/", "pricing.css")])
def test_hero_sheen_plays_once(client, url, asset):
    """The replacement heroes have bounded motion and honor reduced motion."""
    html = client.get(url).content.decode()
    css = _css(asset)
    assert f'css/{asset}' in html
    assert "infinite" not in css
    assert re.search(r"prefers-reduced-motion:\s*reduce", css)
    assert "animation: none" in css or "animation:none" in css
    assert 'class="kin-hero' not in html


@pytest.mark.django_db
def test_pricing_table_stacks_instead_of_scrolling_on_a_phone(client):
    """The native table keeps named columns and an explicit keyboard-scroll region."""
    html = client.get("/pricing/").content.decode()
    assert re.search(r'<div class="cmp-scroll"[^>]*tabindex="0"[^>]*role="region"[^>]*aria-label="[^"]*scroll horizontally', html)
    assert "overflow-x:auto" in _css("pricing.css")
    assert "<table" in html
    assert re.search(r'<th[^>]*>\s*Free', html)
    assert re.search(r'<th[^>]*>\s*Pro', html)
