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
