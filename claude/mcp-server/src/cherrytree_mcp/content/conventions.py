"""CherryTree text conventions shared by both Markdown converters.

CherryTree has no structural lists, rules or quotes: they are plain characters typed into
the buffer, recognised by the editor by convention. These are the editor defaults
(``ct_const.h``) and its link target encoding (``ct_const.h`` LINK_TYPE_*).
"""

from __future__ import annotations

import base64
import binascii
import re
from urllib.parse import quote, unquote, urlparse

BULLET_CHARS = "•◇▪-→⇒"
TODO_CHARS = "☐☑☒"  # unchecked, checked, cancelled
NUMBER_SUFFIXES = ".)->"
INDENT_UNIT = "   "
HORIZONTAL_RULE = "~" * 33

NODE_URL_PREFIX = "cherrytree:node/"
EMBEDDED_URL_PREFIX = "cherrytree:embedded/"

# A subset of GtkSourceView 4 language ids that CherryTree ships with.
KNOWN_SYNTAXES = frozenset(
    """
    c cpp csharp css csv cmake d dart diff docker dosbatch dot erlang fish fortran fsharp go
    gradle groovy haskell html ini java javascript json jsx julia kotlin latex less lua
    makefile markdown matlab meson objc ocaml pascal perl php powershell prolog protobuf
    python python3 R rst ruby rust scala scheme scss sh sql swift tcl terraform toml
    typescript typescript-jsx vala vbnet verilog vhdl xml yaml plain-text
    """.split()
)

_SYNTAX_ALIASES = {
    "": "plain-text",
    "text": "plain-text",
    "txt": "plain-text",
    "plain": "plain-text",
    "plaintext": "plain-text",
    "py": "python3",
    "python": "python3",
    "bash": "sh",
    "shell": "sh",
    "zsh": "sh",
    "console": "sh",
    "js": "javascript",
    "node": "javascript",
    "ts": "typescript",
    "tsx": "typescript-jsx",
    "yml": "yaml",
    "md": "markdown",
    "c++": "cpp",
    "cs": "csharp",
    "rb": "ruby",
    "rs": "rust",
    "kt": "kotlin",
    "ps1": "powershell",
    "dockerfile": "docker",
    "make": "makefile",
    "r": "R",
    "tf": "terraform",
}

_FENCE_NAMES = {"python3": "python", "plain-text": ""}


def syntax_for_fence(info: str) -> str:
    """Map a Markdown fence info string to a CherryTree syntax id."""
    words = info.strip().split()
    language = words[0].lower() if words else ""
    language = _SYNTAX_ALIASES.get(language, language)
    return language if language in KNOWN_SYNTAXES else "plain-text"


def fence_for_syntax(syntax: str) -> str:
    return _FENCE_NAMES.get(syntax, syntax)


# ---------------------------------------------------------------- links


def _b64encode(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _b64decode(text: str) -> str | None:
    try:
        return base64.b64decode(text, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return None


def _url_escape(text: str) -> str:
    """Percent-encode only what would break a Markdown link; keep other Unicode readable."""
    return re.sub(r"[\s%#()<>\[\]]", lambda match: quote(match.group()), text)


def link_to_url(link: str) -> str:
    """CherryTree ``link`` attribute -> URL usable in Markdown."""
    kind, _, rest = link.partition(" ")
    if kind == "webs":
        return rest
    if kind == "node":
        node_id, _, anchor = rest.partition(" ")
        return f"{NODE_URL_PREFIX}{node_id}" + (f"#{_url_escape(anchor)}" if anchor else "")
    if kind in ("file", "fold"):
        path = _b64decode(rest)
        if path is not None:
            return "file://" + _url_escape(path) + ("/" if kind == "fold" else "")
    return link


_NODE_URL = re.compile(r"^cherrytree:node/(\d+)(?:#(.*))?$")


def url_to_link(url: str) -> str:
    """URL from Markdown -> CherryTree ``link`` attribute."""
    match = _NODE_URL.match(url)
    if match:
        anchor = unquote(match.group(2) or "")
        return f"node {match.group(1)}" + (f" {anchor}" if anchor else "")
    if url.startswith("file://"):
        path = unquote(urlparse(url).path)
        if path.endswith("/") and len(path) > 1:
            return f"fold {_b64encode(path.rstrip('/'))}"
        return f"file {_b64encode(path)}"
    return f"webs {url}"
