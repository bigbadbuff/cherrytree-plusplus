"""Plain-text renderings of notebook results, shaped for Claude to read."""

from __future__ import annotations

import time
from typing import Sequence

from .notebook import NotebookInfo, OutlineEntry, PageSummary, PageView
from .search import SearchHit

INDENT = "  "


def format_time(timestamp: int) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(timestamp)) if timestamp else "unknown"


def _kind(view: PageView) -> str:
    if view.is_rich:
        return "rich text (content is Markdown)"
    if view.syntax == "plain-text":
        return "plain text (content is raw text)"
    return f"code: {view.syntax} (content is raw text)"


def page(view: PageView) -> str:
    flags = [
        flag
        for flag, active in (
            ("read-only", view.read_only),
            ("bookmarked", view.bookmarked),
            ("in trash", view.in_trash),
            (f"clone of [{view.clone_of}]", view.clone_of is not None),
        )
        if active
    ]
    children = "; ".join(f"[{node_id}] {name}" for node_id, name in view.children) or "none"
    header = [
        f'<page id="{view.node_id}" title="{view.title}">',
        f"path: {view.path}",
        f"tags: {', '.join(view.tags) or 'none'}",
        f"type: {_kind(view)}",
        f"created: {format_time(view.created)} · modified: {format_time(view.modified)}",
        *([f"flags: {', '.join(flags)}"] if flags else []),
        f"children: {children}",
    ]
    return "\n".join([*header, "<content>", view.body, "</content>", "</page>"])


def search_results(query: str, hits: Sequence[SearchHit]) -> str:
    if not hits:
        return f"No pages match {query!r}."
    lines = [f"{len(hits)} page(s) match {query!r}:"]
    for hit in hits:
        tags = f" #{' #'.join(hit.tags)}" if hit.tags else ""
        lines.append(f"- [{hit.node_id}] {hit.path}{tags} (modified {format_time(hit.modified)})")
        if hit.snippet:
            lines.append(f"{INDENT}{hit.snippet}")
    return "\n".join(lines)


def outline(entries: Sequence[OutlineEntry], heading: str) -> str:
    if not entries:
        return f"{heading}\n(no pages)"
    lines = [heading]
    for index, entry in enumerate(entries):
        next_depth = entries[index + 1].depth if index + 1 < len(entries) else -1
        hidden = entry.child_count if entry.child_count and next_depth <= entry.depth else 0
        tags = f" #{' #'.join(entry.tags)}" if entry.tags else ""
        more = f" (+{hidden} subpages)" if hidden else ""
        lines.append(f"{INDENT * entry.depth}- [{entry.node_id}] {entry.title}{tags}{more}")
    return "\n".join(lines)


def summaries(heading: str, items: Sequence[PageSummary]) -> str:
    if not items:
        return f"{heading}\n(none)"
    return "\n".join([heading, *(f"- [{i.node_id}] {i.path} (modified {format_time(i.modified)})" for i in items)])


def info(details: NotebookInfo) -> str:
    state = details.app_state
    if not state.detection_available:
        app = "unknown (lsof unavailable)"
    elif state.open_in_app:
        app = "open in CherryTree"
    else:
        app = "not open in CherryTree"
    reload = "on" if state.reload_enabled else "off"
    return "\n".join(
        [
            f"notebook: {details.path}",
            f"pages: {details.page_count} · bookmarks: {details.bookmark_count}",
            f"app: {app} · CherryTree auto-reload after external changes: {reload}",
            "writes: " + ("blocked until auto-reload is enabled" if state.open_in_app and not state.reload_enabled else "allowed"),
        ]
    )
