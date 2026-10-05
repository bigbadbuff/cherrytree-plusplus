"""Read-only view of the node hierarchy, plus resolving Claude's page references."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .errors import AmbiguousPage, PageNotFound
from .store.repository import NodeRecord, TreeEntry

ROOT_ID = 0
TRASH_TAG = "mcp-trash"
PATH_SEPARATOR = " / "

PageRef = int | str


@dataclass(frozen=True)
class Page:
    node_id: int  # position in the tree (children.node_id)
    parent_id: int
    sequence: int
    record: NodeRecord  # the content holder: the master node for clones

    @property
    def name(self) -> str:
        return self.record.name

    @property
    def content_id(self) -> int:
        return self.record.node_id

    @property
    def is_clone(self) -> bool:
        return self.content_id != self.node_id


class Tree:
    def __init__(self, records: dict[int, NodeRecord], entries: tuple[TreeEntry, ...]) -> None:
        pages: dict[int, Page] = {}
        for entry in entries:
            record = records.get(entry.master_id if entry.master_id > 0 else entry.node_id)
            if record is not None:
                pages[entry.node_id] = Page(entry.node_id, entry.father_id, entry.sequence, record)
        children: defaultdict[int, list[Page]] = defaultdict(list)
        for page in pages.values():
            children[page.parent_id].append(page)
        self._pages = pages
        self._children = {parent: sorted(kids, key=lambda p: (p.sequence, p.node_id)) for parent, kids in children.items()}

    # ------------------------------------------------------------ structure

    def pages(self) -> list[Page]:
        return list(self._pages.values())

    def page(self, node_id: int) -> Page:
        try:
            return self._pages[node_id]
        except KeyError:
            raise PageNotFound(f"no page with id {node_id}") from None

    def has(self, node_id: int) -> bool:
        return node_id in self._pages

    def children_of(self, parent_id: int) -> list[Page]:
        return list(self._children.get(parent_id, ()))

    def next_sequence(self, parent_id: int) -> int:
        return max((p.sequence for p in self.children_of(parent_id)), default=0) + 1

    def path(self, node_id: int) -> list[str]:
        names: list[str] = []
        seen: set[int] = set()
        current = self._pages.get(node_id)
        while current is not None and current.node_id not in seen:
            seen.add(current.node_id)
            names.append(current.name)
            current = self._pages.get(current.parent_id)
        return names[::-1]

    def path_str(self, node_id: int) -> str:
        return PATH_SEPARATOR.join(self.path(node_id))

    def descendants(self, node_id: int) -> list[int]:
        found: list[int] = []
        seen: set[int] = {node_id}
        stack = [p.node_id for p in reversed(self.children_of(node_id))]
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            found.append(current)
            stack.extend(p.node_id for p in reversed(self.children_of(current)))
        return found

    def is_within(self, node_id: int, ancestor_id: int) -> bool:
        return node_id == ancestor_id or node_id in self.descendants(ancestor_id)

    def trash_id(self) -> int | None:
        for page in self.children_of(ROOT_ID):
            if TRASH_TAG in page.record.tags.split():
                return page.node_id
        return None

    def trash_members(self) -> frozenset[int]:
        """The Trash page and everything under it."""
        trash = self.trash_id()
        return frozenset() if trash is None else frozenset([trash, *self.descendants(trash)])

    def in_trash(self, node_id: int) -> bool:
        return node_id in self.trash_members()

    # ------------------------------------------------------------ resolution

    def describe(self, node_id: int) -> str:
        return f"[{node_id}] {self.path_str(node_id)}"

    def _pick(self, candidates: list[Page], ref: str) -> int:
        if not candidates:
            raise PageNotFound(f"no page matches {ref!r}; use search or list_pages to find it")
        if len(candidates) > 1:
            listing = "\n".join(self.describe(p.node_id) for p in candidates)
            raise AmbiguousPage(f"{ref!r} matches several pages; use an id:\n{listing}")
        return candidates[0].node_id

    def _match(self, pages: list[Page], name: str) -> list[Page]:
        exact = [p for p in pages if p.name == name]
        return exact or [p for p in pages if p.name.casefold() == name.casefold()]

    def resolve(self, ref: PageRef) -> int:
        """Accept an id (int or digits), a path ``A / B / C`` or a unique page name."""
        text = str(ref).strip()
        if text.isdigit():
            node_id = int(text)
            if node_id not in self._pages:
                raise PageNotFound(f"no page with id {node_id}")
            return node_id
        if not text:
            raise PageNotFound("empty page reference")
        if "/" in text:
            parent = ROOT_ID
            for part in (piece.strip() for piece in text.split("/")):
                parent = self._pick(self._match(self.children_of(parent), part), text)
            return parent
        return self._pick(self._match(self.pages(), text), text)
