"""Inspect shipped directory CSS without coupling assertions to inline style tags."""
from pathlib import Path
import re

from django.contrib.staticfiles import finders


def presentation_css(html=None):
    if html is not None:
        assert re.search(r'<link\b[^>]*href="[^"]*presentation-directory(?:\.[a-f0-9]+)?\.css"', html), "Directory presentation must be linked on the rendered page"
    path = finders.find("css/presentation-directory.css")
    assert path, "Directory presentation must resolve through Django staticfiles"
    return re.sub(r"/\*.*?\*/", "", Path(path).read_text(), flags=re.S)


def split_selectors(prelude):
    """Split selector lists without splitting commas inside :is/:not."""
    out, start, depth = [], 0, 0
    for i, char in enumerate(prelude):
        depth += (char == "(") - (char == ")")
        if char == "," and depth == 0:
            out.append(prelude[start:i].strip())
            start = i + 1
    return out + [prelude[start:].strip()]


def expanded_selectors(selector):
    match = re.search(r":is\(([^()]*)\)", selector)
    if not match:
        return [" ".join(selector.split())]
    return [s for branch in split_selectors(match.group(1))
            for s in expanded_selectors(selector[:match.start()] + branch + selector[match.end():])]


def rules(css):
    return [(selector, body) for prelude, body in re.findall(r"([^{}@]+)\{([^{}]*)\}", css)
            for raw in split_selectors(prelude) for selector in expanded_selectors(raw)]


def rule(css, selector):
    wanted = {selector, ".directory-page " + selector, ".directory-drawer " + selector}
    found = [body for candidate, body in rules(css) if candidate in wanted]
    assert found, f"No shipped presentation rule for {selector!r}"
    return " ".join(" ".join(found).split())


def media_blocks(css, condition):
    blocks = []
    for match in re.finditer(r"@media\s*\(" + condition + r"\)\s*\{", css):
        depth, i = 1, match.end()
        while depth and i < len(css):
            depth += (css[i] == "{") - (css[i] == "}")
            i += 1
        blocks.append(css[match.end():i - 1])
    assert blocks, f"Missing media condition: {condition}"
    return "\n".join(blocks)
