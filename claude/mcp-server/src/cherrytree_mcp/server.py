"""MCP tool definitions. Each tool is a thin adapter over ``Notebook`` plus ``render``."""

from __future__ import annotations

import functools
import logging
import sqlite3
from typing import Annotated, Callable, ParamSpec, TypeVar

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from . import __version__, render
from .errors import NotebookError
from .notebook import NewPage, Notebook

log = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")

READ = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
ADD = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)
CHANGE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False)
SET = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)

PageArg = Annotated[int | str, Field(description="Page id (preferred), a path like 'Projects / Ideas', or a unique title")]
PagesArg = Annotated[list[int | str], Field(description="Page ids, paths or unique titles")]
ParentArg = Annotated[
    int | str | None, Field(description="Parent page id/path/title; omit (or 'root') for the top level")
]
MarkdownArg = Annotated[
    str, Field(description="Markdown for rich text pages; raw text for code/plain pages")
]

INSTRUCTIONS = """\
This server is the user's CherryTree notebook: a tree of pages (CherryTree "nodes"), each with
a numeric id, a title, optional tags, child pages and rich text content.

Find and read: `search` (all words must match title/tags/content) or `list_pages` (the
hierarchy), then `fetch` a page; `list_backlinks` shows which pages link to a page. Refer to
pages by id whenever you have one.

Edit: prefer `replace_text`, `insert_content_after` and `append_content`; they keep colours,
underline, images and anything else Markdown cannot express. `replace_content` rewrites the
whole page from Markdown. Content is Markdown: headings, **bold**, *italic*, ~~strike~~,
`code`, [links](https://…), - bullets, 1. numbered, - [ ] to-dos, > quotes, ---, fenced code
blocks (become code boxes) and pipe tables (become CherryTree tables). Link to another page
with [text](cherrytree:node/<id>). Images, anchors and attachments appear as
![label](cherrytree:embedded/<n>); keep those tokens when rewriting a page or they are dropped.

Templates: pages under a top-level "Templates" page; `create_page_from_template` copies one and
fills {{title}}, {{date}} and {{time}}.

`trash_pages` moves pages under a top-level "Trash" page (restore with `move_pages`); there is
no permanent delete. If a write is refused because CherryTree has the notebook open, tell the
user to enable Preferences → Miscellaneous → "Reload After External Update to CT* File".
"""


class NewPageInput(BaseModel):
    title: str = Field(description="Single-line page title")
    content: str = Field("", description="Page body: Markdown, or raw text when code_language is set")
    tags: list[str] = Field(default_factory=list, description="Tags (spaces inside a tag become '-')")
    code_language: str | None = Field(
        None, description="Make a code page with syntax highlighting (e.g. 'python', 'sql', 'text') instead of rich text"
    )


def _readable_errors(func: Callable[P, R]) -> Callable[P, R]:
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return func(*args, **kwargs)
        except NotebookError as exc:
            raise ToolError(str(exc)) from exc
        except sqlite3.Error as exc:
            log.exception("SQLite error in %s", func.__name__)
            if "locked" in str(exc):
                raise ToolError("The notebook is busy (CherryTree is saving). Retry in a moment.") from exc
            raise ToolError(f"Notebook database error: {exc}") from exc
        except OSError as exc:
            log.exception("File error in %s", func.__name__)
            raise ToolError(f"File error: {exc}") from exc

    return wrapper


def build_server(notebook: Notebook) -> MCPServer:
    server = MCPServer(
        "cherrytree",
        title="CherryTree",
        instructions=INSTRUCTIONS + f"\nNotebook file: {notebook.path}\n",
        version=__version__,
    )

    def tool(annotations: ToolAnnotations):
        def register(func: Callable[P, R]) -> Callable[P, R]:
            return server.tool(annotations=annotations)(_readable_errors(func))

        return register

    # ------------------------------------------------------------ read

    @tool(READ)
    def search(
        query: Annotated[str, Field(description="Words to find; every word must appear")],
        limit: Annotated[int, Field(ge=1, le=100)] = 20,
        include_trash: bool = False,
    ) -> str:
        """Search page titles, tags and content (including code boxes and tables)."""
        return render.search_results(query, notebook.search(query, limit, include_trash))

    @tool(READ)
    def fetch(page: PageArg) -> str:
        """Read a page: metadata, child pages and its full content as Markdown."""
        return render.page(notebook.fetch(page))

    @tool(READ)
    def list_pages(
        parent: ParentArg = None,
        depth: Annotated[int, Field(ge=1, le=10, description="Levels below the starting point to show")] = 2,
    ) -> str:
        """Show the page hierarchy (the whole notebook, or below one page) with ids."""
        start = "the whole notebook" if parent in (None, "", "root", "/") else f"{parent!r}"
        return render.outline(notebook.outline(parent, depth), f"Pages in {start}:")

    @tool(READ)
    def list_recent(limit: Annotated[int, Field(ge=1, le=100)] = 15) -> str:
        """List the most recently modified pages."""
        return render.summaries("Recently modified pages:", notebook.recent(limit))

    @tool(READ)
    def list_bookmarks() -> str:
        """List bookmarked pages (CherryTree's favourites)."""
        return render.summaries("Bookmarked pages:", notebook.bookmarks())

    @tool(READ)
    def list_backlinks(page: PageArg) -> str:
        """List the pages whose content links to this page (Notion-style backlinks)."""
        return render.summaries(f"Pages linking to {notebook.describe(page)}:", notebook.backlinks(page))

    @tool(READ)
    def get_notebook_info() -> str:
        """Notebook file, page count, and whether CherryTree has it open (affects writes)."""
        return render.info(notebook.info())

    # ------------------------------------------------------------ write

    @tool(ADD)
    def create_pages(pages: list[NewPageInput], parent: ParentArg = None) -> str:
        """Create one or more pages (appended under `parent`, or at the top level)."""
        specs = [NewPage(p.title, p.content, tuple(p.tags), p.code_language) for p in pages]
        return notebook.create_pages(specs, parent).message

    @tool(SET)
    def update_page(
        page: PageArg,
        title: Annotated[str | None, Field(description="New title")] = None,
        tags: Annotated[list[str] | None, Field(description="Replace all tags ([] clears them)")] = None,
    ) -> str:
        """Rename a page and/or replace its tags."""
        return notebook.update_page(page, title, tags).message

    @tool(CHANGE)
    def replace_content(page: PageArg, content: MarkdownArg) -> str:
        """Rewrite a page's entire content. Formatting Markdown can't express is lost, and list markers,
        numbering and divider lines are normalised to CherryTree's defaults; prefer targeted edits."""
        return notebook.replace_content(page, content).message

    @tool(ADD)
    def append_content(page: PageArg, content: MarkdownArg) -> str:
        """Add content at the end of a page."""
        return notebook.append_content(page, content).message

    @tool(ADD)
    def insert_content_after(
        page: PageArg,
        after_text: Annotated[str, Field(description="Unique text on the line to insert after (plain text, not Markdown)")],
        content: MarkdownArg,
    ) -> str:
        """Insert new lines right after the line containing `after_text`."""
        return notebook.insert_content_after(page, after_text, content).message

    @tool(CHANGE)
    def replace_text(
        page: PageArg,
        old_text: Annotated[str, Field(description="Exact plain text to replace (as shown in fetch, minus Markdown marks)")],
        new_text: Annotated[str, Field(description="Replacement plain text; inherits the old text's formatting")],
        replace_all: bool = False,
    ) -> str:
        """Find and replace text in a page, keeping all surrounding formatting."""
        return notebook.replace_text(page, old_text, new_text, replace_all).message

    @tool(CHANGE)
    def move_pages(
        pages: PagesArg,
        new_parent: ParentArg = None,
        position: Annotated[int | None, Field(ge=0, description="0-based position among the new siblings; default last")] = None,
    ) -> str:
        """Move pages under a new parent (or to the top level), optionally at a position."""
        return notebook.move_pages(pages, new_parent, position).message

    @tool(ADD)
    def duplicate_page(page: PageArg, new_parent: ParentArg = None, include_children: bool = True) -> str:
        """Copy a page (and by default its subpages); the copy goes under `new_parent` or next to the original."""
        return notebook.duplicate_page(page, new_parent, include_children).message

    @tool(ADD)
    def create_page_from_template(
        template: PageArg,
        title: Annotated[str, Field(description="Title of the new page (fills {{title}})")],
        parent: ParentArg = None,
    ) -> str:
        """Create a page by copying a template page and its subpages, filling {{title}}, {{date}} and
        {{time}} in names and text. Templates usually live under a top-level "Templates" page."""
        return notebook.create_page_from_template(template, title, parent).message

    @tool(CHANGE)
    def trash_pages(pages: PagesArg) -> str:
        """Move pages (with their subpages) into the notebook's Trash page."""
        return notebook.trash_pages(pages).message

    @tool(SET)
    def set_bookmarks(pages: PagesArg, bookmarked: bool = True) -> str:
        """Bookmark (or un-bookmark) pages."""
        return notebook.set_bookmarks(pages, bookmarked).message

    return server
