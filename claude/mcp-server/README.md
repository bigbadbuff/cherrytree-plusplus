# cherrytree-mcp

MCP server that lets Claude search, read and edit CherryTree (`.ctb`) notebooks, Notion-style.
Setup, tool list and safety notes: see [`../README.md`](../README.md).

Layout:

| Module | Role |
|---|---|
| `content/ctxml.py` | Lossless codec for CherryTree's node XML + code box / table / image rows |
| `content/from_markdown.py`, `to_markdown.py` | Markdown ⇄ CherryTree rich text |
| `content/editing.py` | Formatting-preserving edits (replace, insert after line, append) |
| `store/` | SQLite schema and row access |
| `tree.py` | Hierarchy, paths, page references, Trash |
| `backlinks.py` | Pages linking to a page (mirrors `src/ct/ct_backlinks.cc`) |
| `safety.py` | App-open detection, auto-reload check, id gap, backups |
| `notebook.py` | The operations behind every tool |
| `server.py`, `render.py` | MCP tool definitions and their text output |
