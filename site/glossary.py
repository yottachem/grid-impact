"""Glossary from reference/glossary.yaml: the Methods page section, and links from the first use of each
term on a page to its entry."""
import html
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SKIP = {"script", "style", "a", "h1", "h2", "h3", "title", "button", "option", "svg", "sup", "dt", "label", "select", "textarea", "nav", "footer"}
TAG = re.compile(r"(<[^>]+>)")
CSS = ("a.term { color: inherit; text-decoration: underline dotted; text-decoration-color: var(--muted); text-underline-offset: 3px; }"
       " a.term:hover { text-decoration-color: currentColor; }"
       " dl.glossary dt { font-weight: 600; margin-top: 14px; scroll-margin-top: 70px; } dl.glossary dd { margin: 2px 0 0; max-width: 72ch; }"
       " dl.glossary dt:target { color: var(--s1); }")


def terms() -> list[dict]:
    return yaml.safe_load((ROOT / "reference" / "glossary.yaml").read_text())["terms"]


def section() -> str:
    """The Glossary section for the Methods page (raw HTML, passed through by the markdown renderer)."""
    items = "".join(f'<dt id="term-{t["id"]}">{html.escape(t["term"])}</dt><dd>{html.escape(t["definition"])}</dd>'
                    for t in sorted(terms(), key=lambda t: t["term"].lower()))
    return f'\n\n## Glossary\n\n<dl class="glossary" id="glossary">{items}</dl>\n'


def link(page_html: str, href: str = "methods.html") -> str:
    """Link the first use of each glossary term in readable text, outside headings, links, scripts, and charts."""
    pats = [(t["id"], re.compile(r"(?<![\w-])(" + "|".join(re.escape(m) for m in t["match"]) + r")(?![\w-])")) for t in terms()]
    done, stack, out = set(), [], []
    for part in TAG.split(page_html):
        if part.startswith("<"):
            m = re.match(r"<\s*(/)?\s*([a-zA-Z0-9]+)", part)
            if m:
                name = m.group(2).lower()
                if m.group(1):
                    if stack and stack[-1] == name:
                        stack.pop()
                    elif name in stack:
                        while stack and stack.pop() != name:
                            pass
                elif name in SKIP and not part.endswith("/>"):
                    stack.append(name)
            out.append(part)
            continue
        if stack or not part.strip():
            out.append(part)
            continue
        part = _link_rest(part, pats, done, href)
        out.append(part)
    return "".join(out)


def _link_rest(text: str, pats, done: set, href: str) -> str:
    for tid, pat in pats:
        if tid in done:
            continue
        hit = pat.search(text)
        if hit:
            a = f'<a class="term" href="{href}#term-{tid}" title="Glossary">{hit.group(1)}</a>'
            done.add(tid)
            return _link_rest(text[:hit.start()], pats, done, href) + a + _link_rest(text[hit.end():], pats, done, href)
    return text
