"""Guard against page scripts that fail in browsers but pass `node --check`."""
import re
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parent.parent / "site" / "templates"
# window properties that are non-configurable: a top-level const/let/class with these
# names throws "Identifier has already been declared" and the whole script stops.
RESTRICTED = {"top", "window", "document", "location"}


def test_no_restricted_globals_in_page_scripts():
    for f in TEMPLATES.glob("*.tmpl"):
        for script in re.findall(r"<script>(.*?)</script>", f.read_text(), re.S):
            names = re.findall(r"^(?:const|let|class)\s+([A-Za-z_$][\w$]*)", script, re.M)
            bad = RESTRICTED & set(names)
            assert not bad, f"{f.name} declares restricted global(s) {bad}"


def test_map_popup_does_not_blink():
    """The map popup must ignore the pointer (else the map sees a mouseleave and it flickers),
    and hover must go through the single controller rather than per-layer mousemove handlers."""
    t = (TEMPLATES / "map.html.tmpl").read_text()
    assert ".maplibregl-popup { pointer-events: none; }" in t
    assert not re.search(r'map\.on\("mousemove",\s*"', t), "per-layer mousemove handler found; use the HOVER controller"


def test_glossary_links_first_use_only_outside_code():
    import sys
    sys.path.insert(0, str(TEMPLATES.parent))
    import glossary
    ids = [t["id"] for t in glossary.terms()]
    assert len(ids) == len(set(ids))
    html = '<h2>PJM</h2><p>PJM runs a capacity auction. PJM again.</p><script>const PJM = 1;</script>'
    out = glossary.link(html)
    assert out.count('href="methods.html#term-pjm"') == 1
    assert "<h2>PJM</h2>" in out and "const PJM = 1;" in out
    assert 'href="methods.html#term-capacity-auction"' in out
