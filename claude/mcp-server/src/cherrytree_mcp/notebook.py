"""The notebook service: every operation the MCP tools expose, Notion-style.

Each call opens the document, works inside one SQLite transaction and closes it again, so
the CherryTree app (which keeps the file open) is never blocked for long. Writes first pass
the safety checks in ``safety`` and snapshot the document once per session.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from . import page_content
from .backlinks import linking_content_ids
from .content.conventions import syntax_for_fence
from .content.model import RICH_TEXT_SYNTAX
from .errors import InvalidRequest
from .safety import AppState, BackupKeeper, advance_mtime, check_write_allowed, first_new_id
from .search import SearchHit, search_pages
from .store.repository import NodeRecord, Repository, TreeEntry
from .tree import ROOT_ID, TRASH_TAG, PageRef, Tree

TRASH_TITLE = "Trash"
_ROOT_REFS = (None, "", "/", "root", 0, "0")

Probe = Callable[[Path], AppState]
WriteAction = Callable[[Repository, Tree, AppState], tuple[str, tuple[int, ...]]]


@dataclass(frozen=True)
class NewPage:
    title: str
    content: str = ""
    tags: Sequence[str] = ()
    code_language: str | None = None


@dataclass(frozen=True)
class PageView:
    node_id: int
    title: str
    path: str
    tags: tuple[str, ...]
    syntax: str
    read_only: bool
    created: int
    modified: int
    children: tuple[tuple[int, str], ...]
    clone_of: int | None
    bookmarked: bool
    in_trash: bool
    body: str

    @property
    def is_rich(self) -> bool:
        return self.syntax == RICH_TEXT_SYNTAX


@dataclass(frozen=True)
class OutlineEntry:
    node_id: int
    depth: int
    title: str
    tags: tuple[str, ...]
    child_count: int


@dataclass(frozen=True)
class PageSummary:
    node_id: int
    path: str
    modified: int


@dataclass(frozen=True)
class WriteResult:
    message: str
    node_ids: tuple[int, ...]


@dataclass(frozen=True)
class NotebookInfo:
    path: Path
    page_count: int
    bookmark_count: int
    app_state: AppState


def _tags(tags: Sequence[str]) -> str:
    return " ".join("-".join(tag.split()) for tag in tags if tag.strip())


def _title(title: str) -> str:
    cleaned = title.strip()
    if not cleaned or "\n" in cleaned:
        raise InvalidRequest("page titles must be a single non-empty line")
    return cleaned


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" + ("" if count == 1 else "s")


class Notebook:
    def __init__(self, path: Path, *, probe: Probe, backups: BackupKeeper, clock: Callable[[], float] = time.time):
        self.path = path
        self._probe = probe
        self._backups = backups
        self._clock = clock

    def _now(self) -> int:
        return int(self._clock())

    # ------------------------------------------------------------ plumbing

    def _read(self, action: Callable[[Repository, Tree], object]):
        with Repository.open(self.path) as repo:
            return action(repo, Tree(repo.nodes(), repo.tree()))

    def _write(self, action: WriteAction) -> WriteResult:
        state = self._probe(self.path)
        check_write_allowed(state)
        with Repository.open(self.path) as repo:
            previous_mtime = self.path.stat().st_mtime
            self._backups.ensure(self.path, repo)
            with repo.transaction():
                message, node_ids = action(repo, Tree(repo.nodes(), repo.tree()), state)
        advance_mtime(self.path, previous_mtime, self._clock())
        if state.open_in_app:
            message += (
                " CherryTree has this notebook open and reloads it within about 5 seconds; if the user has"
                " unsaved edits to the same page there, saving them in CherryTree overrides this change."
            )
        return WriteResult(message, node_ids)

    @staticmethod
    def _parent(tree: Tree, ref: PageRef | None) -> int:
        return ROOT_ID if ref in _ROOT_REFS else tree.resolve(ref)  # type: ignore[arg-type]

    @staticmethod
    def _resolve_all(tree: Tree, refs: Sequence[PageRef]) -> list[int]:
        if not refs:
            raise InvalidRequest("no pages given")
        return list(dict.fromkeys(tree.resolve(ref) for ref in refs))

    @staticmethod
    def _subtree_roots(tree: Tree, node_ids: list[int]) -> list[int]:
        """Drop pages whose ancestor is also selected: they travel with it, keeping the subtree."""
        return [n for n in node_ids if not any(other != n and tree.is_within(n, other) for other in node_ids)]

    # ------------------------------------------------------------ reads

    def info(self) -> NotebookInfo:
        app_state = self._probe(self.path)  # probe before opening, so our own handle is not in the way

        def action(repo: Repository, tree: Tree) -> NotebookInfo:
            return NotebookInfo(self.path, len(tree.pages()), len(repo.bookmarks()), app_state)

        return self._read(action)

    def fetch(self, ref: PageRef) -> PageView:
        def action(repo: Repository, tree: Tree) -> PageView:
            page = tree.page(tree.resolve(ref))
            record = page.record
            content = page_content.load(repo, record)
            return PageView(
                node_id=page.node_id,
                title=record.name,
                path=tree.path_str(page.node_id),
                tags=tuple(record.tags.split()),
                syntax=record.syntax,
                read_only=record.is_read_only,
                created=record.ts_creation,
                modified=record.ts_lastsave,
                children=tuple((child.node_id, child.name) for child in tree.children_of(page.node_id)),
                clone_of=page.content_id if page.is_clone else None,
                bookmarked=page.node_id in repo.bookmarks(),
                in_trash=tree.in_trash(page.node_id),
                body=page_content.to_display(record, content),
            )

        return self._read(action)

    def search(self, query: str, limit: int = 20, include_trash: bool = False) -> list[SearchHit]:
        if not query.strip():
            raise InvalidRequest("search query is empty")
        return self._read(
            lambda repo, tree: search_pages(tree, repo.payloads(include_blobs=False), query, limit, include_trash)
        )

    def outline(self, ref: PageRef | None = None, depth: int = 2) -> list[OutlineEntry]:
        def action(_repo: Repository, tree: Tree) -> list[OutlineEntry]:
            start = self._parent(tree, ref)
            entries: list[OutlineEntry] = []
            trash = tree.trash_id()

            def visit(node_id: int, level: int) -> None:
                page = tree.page(node_id)
                kids = tree.children_of(node_id)
                entries.append(OutlineEntry(node_id, level, page.name, tuple(page.record.tags.split()), len(kids)))
                expand = level < depth - (1 if start == ROOT_ID else 0) and (node_id != trash or start == trash)
                for kid in kids if expand else ():
                    visit(kid.node_id, level + 1)

            for top in [tree.page(start)] if start != ROOT_ID else tree.children_of(ROOT_ID):
                visit(top.node_id, 0)
            return entries

        return self._read(action)

    def recent(self, limit: int = 15) -> list[PageSummary]:
        def action(_repo: Repository, tree: Tree) -> list[PageSummary]:
            pages = sorted(tree.pages(), key=lambda p: (-p.record.ts_lastsave, p.node_id))
            seen: set[int] = set()
            hidden = tree.trash_members()
            summaries: list[PageSummary] = []
            for page in pages:
                if page.content_id in seen or page.node_id in hidden:
                    continue
                seen.add(page.content_id)
                summaries.append(PageSummary(page.node_id, tree.path_str(page.node_id), page.record.ts_lastsave))
            return summaries[:limit]

        return self._read(action)

    def describe(self, ref: PageRef) -> str:
        """``[id] Parent / Page`` for a page reference."""
        return self._read(lambda _repo, tree: tree.describe(tree.resolve(ref)))

    def backlinks(self, ref: PageRef) -> list[PageSummary]:
        def action(repo: Repository, tree: Tree) -> list[PageSummary]:
            ids = linking_content_ids(tree, repo.payloads(include_blobs=False), tree.resolve(ref))
            return [PageSummary(node_id, tree.path_str(node_id), tree.page(node_id).record.ts_lastsave) for node_id in ids]

        return self._read(action)

    def bookmarks(self) -> list[PageSummary]:
        def action(repo: Repository, tree: Tree) -> list[PageSummary]:
            return [
                PageSummary(node_id, tree.path_str(node_id), tree.page(node_id).record.ts_lastsave)
                for node_id in repo.bookmarks()
                if tree.has(node_id)
            ]

        return self._read(action)

    # ------------------------------------------------------------ page creation & properties

    def _new_record(self, node_id: int, spec: NewPage, now: int) -> NodeRecord:
        is_code = spec.code_language is not None
        syntax = syntax_for_fence(spec.code_language or "") if is_code else RICH_TEXT_SYNTAX
        return NodeRecord(node_id, _title(spec.title), syntax, _tags(spec.tags), 0, 0 if is_code else 1, 0, now, now)

    def create_pages(self, pages: Sequence[NewPage], parent: PageRef | None = None) -> WriteResult:
        if not pages:
            raise InvalidRequest("no pages given")
        for spec in pages:
            _title(spec.title)

        def action(repo: Repository, tree: Tree, state: AppState) -> tuple[str, tuple[int, ...]]:
            parent_id = self._parent(tree, parent)
            first_id, sequence, now = first_new_id(repo.max_node_id(), state), tree.next_sequence(parent_id), self._now()
            created: list[int] = []
            for index, spec in enumerate(pages):
                record = self._new_record(first_id + index, spec, now)
                content = page_content.parse_input(record, spec.content)
                entry = TreeEntry(record.node_id, parent_id, sequence + index, 0)
                repo.insert_node(record, page_content.to_payload(record, content), entry)
                created.append(record.node_id)
            listing = ", ".join(f"[{node_id}] {spec.title.strip()}" for node_id, spec in zip(created, pages))
            return f"Created {_plural(len(created), 'page')}: {listing}.", tuple(created)

        return self._write(action)

    def update_page(self, ref: PageRef, title: str | None = None, tags: Sequence[str] | None = None) -> WriteResult:
        if title is None and tags is None:
            raise InvalidRequest("nothing to update: give a title and/or tags")

        def action(repo: Repository, tree: Tree, _state: AppState) -> tuple[str, tuple[int, ...]]:
            page = tree.page(tree.resolve(ref))
            changes: dict[str, object] = {"ts_lastsave": self._now()}
            if title is not None:
                changes["name"] = _title(title)
            if tags is not None:
                changes["tags"] = _tags(tags)
            repo.update_node(page.record.with_changes(**changes))
            return f"Updated page [{page.node_id}].", (page.node_id,)

        return self._write(action)

    # ------------------------------------------------------------ content edits

    def _edit(self, ref: PageRef, transform: Callable[[NodeRecord, page_content.NodeContent], tuple[page_content.NodeContent, str]]) -> WriteResult:
        def action(repo: Repository, tree: Tree, _state: AppState) -> tuple[str, tuple[int, ...]]:
            page = tree.page(tree.resolve(ref))
            record = page.record
            if record.is_read_only:
                raise InvalidRequest(f"page [{page.node_id}] {record.name!r} is read-only in CherryTree")
            new_content, message = transform(record, page_content.load(repo, record))
            repo.write_payload(record.node_id, page_content.to_payload(record, new_content), self._now())
            return f"{message} Page [{page.node_id}] {record.name!r}.", (page.node_id,)

        return self._write(action)

    def replace_content(self, ref: PageRef, content: str) -> WriteResult:
        return self._edit(ref, lambda record, current: (page_content.replaced(record, current, content), "Replaced content."))

    def append_content(self, ref: PageRef, content: str) -> WriteResult:
        return self._edit(ref, lambda record, current: (page_content.appended(record, current, content), "Appended content."))

    def insert_content_after(self, ref: PageRef, after_text: str, content: str) -> WriteResult:
        return self._edit(
            ref,
            lambda record, current: (page_content.inserted_after(record, current, after_text, content), "Inserted content."),
        )

    def replace_text(self, ref: PageRef, old_text: str, new_text: str, replace_all: bool = False) -> WriteResult:
        def transform(_record: NodeRecord, current: page_content.NodeContent):
            updated, count = page_content.text_replaced(current, old_text, new_text, replace_all)
            return updated, f"Made {_plural(count, 'replacement')}."

        return self._edit(ref, transform)

    # ------------------------------------------------------------ structure

    @staticmethod
    def _place(repo: Repository, tree: Tree, node_ids: list[int], parent_id: int, position: int | None) -> None:
        siblings = [p.node_id for p in tree.children_of(parent_id) if p.node_id not in node_ids]
        index = len(siblings) if position is None else max(0, min(position, len(siblings)))
        for sequence, node_id in enumerate(siblings[:index] + node_ids + siblings[index:], start=1):
            page = tree.page(node_id)
            if (page.parent_id, page.sequence) != (parent_id, sequence):
                master = page.content_id if page.is_clone else 0
                repo.set_tree_entry(TreeEntry(node_id, parent_id, sequence, master))

    def move_pages(self, refs: Sequence[PageRef], new_parent: PageRef | None, position: int | None = None) -> WriteResult:
        def action(repo: Repository, tree: Tree, _state: AppState) -> tuple[str, tuple[int, ...]]:
            parent_id = self._parent(tree, new_parent)
            node_ids = self._subtree_roots(tree, self._resolve_all(tree, refs))
            for node_id in node_ids:
                if parent_id != ROOT_ID and tree.is_within(parent_id, node_id):
                    raise InvalidRequest(f"cannot move [{node_id}] into itself or one of its own subpages")
            self._place(repo, tree, node_ids, parent_id, position)
            destination = "the top level" if parent_id == ROOT_ID else f"[{parent_id}] {tree.path_str(parent_id)}"
            return f"Moved {_plural(len(node_ids), 'page')} to {destination}.", tuple(node_ids)

        return self._write(action)

    def trash_pages(self, refs: Sequence[PageRef]) -> WriteResult:
        def action(repo: Repository, tree: Tree, state: AppState) -> tuple[str, tuple[int, ...]]:
            node_ids = self._subtree_roots(tree, self._resolve_all(tree, refs))
            trash_id = tree.trash_id()
            if trash_id in node_ids:
                raise InvalidRequest("the Trash page itself cannot be trashed")
            if trash_id is None:
                trash_id, now = first_new_id(repo.max_node_id(), state), self._now()
                record = NodeRecord(trash_id, TRASH_TITLE, RICH_TEXT_SYNTAX, TRASH_TAG, 0, 1, 0, now, now)
                entry = TreeEntry(trash_id, ROOT_ID, tree.next_sequence(ROOT_ID), 0)
                repo.insert_node(record, page_content.to_payload(record, ()), entry)
            self._place(repo, tree, node_ids, trash_id, None)
            return f"Moved {_plural(len(node_ids), 'page')} to Trash [{trash_id}].", tuple(node_ids)

        return self._write(action)

    def duplicate_page(self, ref: PageRef, new_parent: PageRef | None = None, include_children: bool = True) -> WriteResult:
        def action(repo: Repository, tree: Tree, state: AppState) -> tuple[str, tuple[int, ...]]:
            source = tree.page(tree.resolve(ref))
            parent_id = source.parent_id if new_parent is None else self._parent(tree, new_parent)
            originals = [source.node_id, *(tree.descendants(source.node_id) if include_children else [])]
            first_id, now = first_new_id(repo.max_node_id(), state), self._now()
            new_ids = {old: first_id + index for index, old in enumerate(originals)}
            for old in originals:
                page = tree.page(old)
                record = page.record.with_changes(node_id=new_ids[old], ts_creation=now, ts_lastsave=now)
                if old == source.node_id:
                    entry = TreeEntry(record.node_id, parent_id, tree.next_sequence(parent_id), 0)
                else:
                    entry = TreeEntry(record.node_id, new_ids[page.parent_id], page.sequence, 0)
                repo.insert_node(record, repo.payload(page.content_id), entry)
            copy_id = new_ids[source.node_id]
            return (
                f"Duplicated [{source.node_id}] as [{copy_id}] ({_plural(len(originals), 'page')} copied).",
                (copy_id,),
            )

        return self._write(action)

    def set_bookmarks(self, refs: Sequence[PageRef], bookmarked: bool) -> WriteResult:
        def action(repo: Repository, tree: Tree, _state: AppState) -> tuple[str, tuple[int, ...]]:
            node_ids = self._resolve_all(tree, refs)
            current = list(repo.bookmarks())
            if bookmarked:
                updated = current + [node_id for node_id in node_ids if node_id not in current]
            else:
                updated = [node_id for node_id in current if node_id not in node_ids]
            repo.set_bookmarks(updated)
            verb = "Bookmarked" if bookmarked else "Removed bookmarks from"
            return f"{verb} {_plural(len(node_ids), 'page')}.", tuple(node_ids)

        return self._write(action)
