"""Full-text search across page titles, tags and content (all words must match)."""

from __future__ import annotations

from dataclasses import dataclass

from .errors import NotebookError
from .page_content import decode_payload, searchable_text
from .store.repository import Payload
from .tree import Tree

SNIPPET_RADIUS = 70
TITLE_WEIGHT = 3
TAG_WEIGHT = 2
PHRASE_IN_TITLE_BONUS = 5


@dataclass(frozen=True)
class SearchHit:
    node_id: int
    path: str
    tags: tuple[str, ...]
    snippet: str
    modified: int
    score: int


def _snippet(text: str, words: list[str], phrase: str) -> str:
    folded = text.casefold()
    position = folded.find(phrase)
    if position == -1:
        position = min((folded.find(w) for w in words if w in folded), default=-1)
    if position == -1:
        return ""
    start = max(0, position - SNIPPET_RADIUS)
    end = min(len(text), position + SNIPPET_RADIUS)
    body = " ".join(text[start:end].split())
    return ("…" if start else "") + body + ("…" if end < len(text) else "")


def search_pages(
    tree: Tree, payloads: dict[int, Payload], query: str, limit: int, include_trash: bool
) -> list[SearchHit]:
    phrase = " ".join(query.casefold().split())
    words = phrase.split()
    hits: list[SearchHit] = []
    seen_content: set[int] = set()
    hidden = frozenset() if include_trash else tree.trash_members()
    for page in sorted(tree.pages(), key=lambda p: (p.is_clone, p.node_id)):
        if page.content_id in seen_content or page.node_id in hidden:
            continue
        seen_content.add(page.content_id)
        record = page.record
        try:
            content = searchable_text(decode_payload(record, payloads.get(record.node_id, Payload(""))))
        except NotebookError:
            content = ""
        title, tags = record.name.casefold(), record.tags.casefold()
        haystack = f"{title}\n{tags}\n{content.casefold()}"
        if not all(word in haystack for word in words):
            continue
        score = sum(TITLE_WEIGHT * (w in title) + TAG_WEIGHT * (w in tags) + (w in content.casefold()) for w in words)
        score += PHRASE_IN_TITLE_BONUS * (phrase in title)
        hits.append(
            SearchHit(
                page.node_id, tree.path_str(page.node_id), tuple(record.tags.split()),
                _snippet(content, words, phrase), record.ts_lastsave, score,
            )
        )
    hits.sort(key=lambda h: (-h.score, -h.modified, h.node_id))
    return hits[:limit]
