# CherryTree + Claude (fork of giuspen/cherrytree)

This fork is based on the **v1.7.2** release and adds:

- `mcp-server/`: an MCP server that lets Claude work with a CherryTree notebook the way it works
  with Notion: search, read, create, edit, move, duplicate, bookmark and trash pages.
- `ROADMAP.md`: Notion-style app features still to build (slash menu, backlinks, properties,
  databases, …).
- A fix that lets `./build.sh` build on Apple Silicon Homebrew.

Everything fork-specific lives in `claude/` (plus small fixes), so updating to a new upstream
release is a plain rebase.

## Set up on a new Mac

```bash
git clone https://github.com/bigbadbuff/cherrytree.git ~/Desktop/cherrytree
cd ~/Desktop/cherrytree && git switch claude-integration
git remote add upstream https://github.com/giuspen/cherrytree.git
```

### 1. CherryTree app

Either install the prebuilt macOS app from <https://gitlab.com/dehesselle/cherrytree_macos/-/releases>,
or build this fork:

```bash
brew install cmake ninja pkg-config adwaita-icon-theme fmt gspell gtkmm3 gtksourceview4 libxml++ spdlog uchardet fribidi curl vte3
./build.sh release notests
./build/cherrytree
```

In CherryTree, turn on **Preferences → Miscellaneous → Reload After External Update to CT\* File**.
Without it the server refuses to write while the notebook is open, because CherryTree would
overwrite Claude's edits on its next save.

### 2. Claude integration

Needs [uv](https://docs.astral.sh/uv/). Register the server with Claude Code (all projects):

```bash
claude mcp add --scope user cherrytree \
  -e CHERRYTREE_DOCUMENT="$HOME/Documents/CherryTree/Notes.ctb" \
  -- "$(which uv)" run --locked --project "$HOME/Desktop/cherrytree/claude/mcp-server" cherrytree-mcp
```

For the Claude desktop app, add this to
`~/Library/Application Support/Claude/claude_desktop_config.json` under `mcpServers`, then restart it:

```json
"CherryTree": {
  "command": "/Users/YOU/.local/bin/uv",
  "args": ["run", "--locked", "--project", "/Users/YOU/Desktop/cherrytree/claude/mcp-server", "cherrytree-mcp"],
  "env": {"CHERRYTREE_DOCUMENT": "/Users/YOU/Documents/CherryTree/Notes.ctb"}
}
```

The notebook is created if it does not exist. Only `.ctb` (SQLite) notebooks are supported; convert
others with *File → Save As → SQLite, Not Protected*.

| Variable | Default | Purpose |
|---|---|---|
| `CHERRYTREE_DOCUMENT` | `~/Documents/CherryTree/Notes.ctb` | Notebook to work on |
| `CHERRYTREE_CONFIG` | CherryTree's `config.cfg` | Where to read the auto-reload setting |
| `CHERRYTREE_MCP_BACKUP_DIR` | `~/.local/share/cherrytree-mcp/backups` | Snapshots taken before the first write of each session (last 20 kept) |

## Tools

| Tool | What it does |
|---|---|
| `search` | All-words search over titles, tags, text, code boxes and tables |
| `fetch` | A page's metadata, child pages and content as Markdown |
| `list_pages` / `list_recent` / `list_bookmarks` | Browse the hierarchy, recent edits, favourites |
| `get_notebook_info` | Notebook path, page count, whether CherryTree has it open |
| `create_pages` | New rich text pages from Markdown, or code pages (`code_language`) |
| `update_page` | Rename and/or retag |
| `replace_text` / `insert_content_after` / `append_content` | Targeted edits that keep all formatting |
| `replace_content` | Rewrite a page from Markdown |
| `move_pages` / `duplicate_page` | Reorganise the tree |
| `trash_pages` | Move pages into a top-level **Trash** page (no permanent delete) |
| `set_bookmarks` | Bookmark / un-bookmark |

Markdown maps onto CherryTree's own conventions: `•◇▪` bullets, `☐☑☒` to-dos, fenced code → code
boxes, pipe tables → tables, `[text](cherrytree:node/<id>)` → links between pages. Images,
anchors and attachments appear as `![label](cherrytree:embedded/<n>)` placeholders and survive
rewrites as long as the placeholder is kept.

## How it stays safe

- Each tool call opens the notebook, does its work in one SQLite transaction, and closes it.
- Writes are refused while CherryTree has the notebook open, unless auto-reload is on. With
  auto-reload on, CherryTree picks up the change within about 5 seconds.
- While the app is open, new page ids skip 100 ahead, so they never collide with pages you created
  in the app but have not saved yet.
- The notebook is snapshotted before the first write of every server session.
- One rare case remains: if you are editing **the same page** in the app with unsaved changes when
  Claude edits it, CherryTree asks whether to save. Saving keeps your version of that page.

## Development

```bash
cd claude/mcp-server
uv sync
uv run pytest --cov            # unit + integration tests (coverage gate: 80%)
CHERRYTREE_BIN=/Applications/CherryTree.app/Contents/MacOS/CherryTree uv run pytest -m e2e
```

The `e2e` tests write notebooks through the server and export them with a real CherryTree binary
(`build/cherrytree`, the installed app, or `CHERRYTREE_BIN`), proving the app loads what we write.

## Updating to a new CherryTree release

```bash
git fetch upstream --tags
git rebase --onto v1.7.3 v1.7.2 claude-integration   # replace with the new tag
./build.sh release notests
```
