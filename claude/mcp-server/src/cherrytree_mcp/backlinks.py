"""Notion-style backlinks: which pages link to a page (mirrors src/ct/ct_backlinks.cc)."""

from __future__ import annotations

import re

from .content.model import Span
from .errors import NotebookError
from .page_content import decode_payload
from .store.repository import Payload
from .tree import ROOT_ID, Tree

_NODE_LINK = re.compile(r"^node (\d+)(?: |$)")


def _linked_node_id(link: str | None) -> int | None:
    match = _NODE_LINK.match(link or "")
    return int(match.group(1)) if match else None


def linking_content_ids(tree: Tree, payloads: dict[int, Payload], target_id: int) -> list[int]:
    """Content ids of pages linking to the target or any clone of it, in tree order.

    Clones are reported once (by the id holding their content); the target itself and pages in
    the Trash are excluded.
    """
    target = tree.page(target_id)
    target_ids = {target.node_id, target.content_id}
    target_ids |= {page.node_id for page in tree.pages() if page.content_id == target.content_id}
    hidden = tree.trash_members()
    visited = {target.content_id}
    linking: list[int] = []
    for node_id in tree.descendants(ROOT_ID):
        page = tree.page(node_id)
        if node_id in hidden or page.content_id in visited:
            continue
        visited.add(page.content_id)
        if not page.record.is_rich:
            continue
        try:
            content = decode_payload(page.record, payloads.get(page.content_id, Payload("")))
        except NotebookError:
            continue
        if any(isinstance(b, Span) and _linked_node_id(b.attr("link")) in target_ids for b in content):
            linking.append(page.content_id)
    return linking
