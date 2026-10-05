# Handoff notes for the next Claude session

_Last updated: 2026-10-05 by Claude (Opus 5.5)._ Keep this file current; it is the memory that
survives a full context window.

## Goal (from the user)

1. Run the **latest CherryTree release** on macOS, from this fork, so the work survives machine changes.
2. Let Claude work with CherryTree **the way it works with Notion** (search, fetch, create, edit,
   move, …) → done as an MCP server in `claude/mcp-server/`.
3. Add **Notion-style features** to the app itself → planned in `claude/ROADMAP.md`, not started.

## Repo and branches

| Thing | Value |
|---|---|
| Repo | `bigbadbuff/cherrytree-plusplus` (renamed from the `bigbadbuff/cherrytree` fork) |
| Remotes | `origin` = cherrytree-plusplus, `upstream` = giuspen/cherrytree |
| Default branch | `main` = tag `v1.7.2` + our work (merged via PRs) |
| `master` | upstream mirror, 138+ unreleased commits past v1.7.2: do not build on it |
| Workflow | feature branch → PR into `main` → merge; update this file in the same PR |

## Done

- `build.sh` fixed for Apple Silicon Homebrew (icu4c/curl pkg-config paths, `LIBRARY_PATH`).
  `./build.sh release notests` builds CherryTree 1.7.2 → `build/cherrytree`.
- MCP server `claude/mcp-server/` (Python 3.12, `mcp` SDK 2.x `MCPServer`, `markdown-it-py`, uv):
  16 tools, 116 tests, ~94% coverage, e2e tests that export through a real CherryTree binary.
  Module map: `claude/mcp-server/README.md`. Setup and tool table: `claude/README.md`.
- Verified live: with the notebook open in CherryTree 1.7.0, a write through the installed server
  was picked up by the app ("Document was Reloaded After External Update") and rendered correctly.

## State of the user's Mac (forrestbuff)

- Checkout: `~/Desktop/cherrytree`. Homebrew build deps installed. Built binary: `build/cherrytree`.
- Installed app: `/Applications/CherryTree.app` = 1.7.0 (dehesselle macOS build; no 1.7.2 .app exists).
- Notebook: `~/Documents/CherryTree/Notes.ctb` with page [1] "Welcome" (bookmarked) and a test page
  [101] "Live edit test" (user may delete it).
- CherryTree config `~/Library/Application Support/net.giuspen.CherryTree/cherrytree/config.cfg`:
  we set `mod_time_sentinel=true` (was `false`). Required for safe writes while the app is open.
- MCP registered for Claude Code (user scope, `~/.claude.json`):
  `uv run --locked --project ~/Desktop/cherrytree/claude/mcp-server cherrytree-mcp`,
  env `CHERRYTREE_DOCUMENT=~/Documents/CherryTree/Notes.ctb`. `claude mcp list` shows it connected.
- Claude Desktop (`~/Library/Application Support/Claude/claude_desktop_config.json`): a
  `"CherryTree"` entry was added, but the running Desktop app overwrote the file once. **Verify it is
  still there**; if not, ask the user to quit Claude Desktop and add it (snippet in `claude/README.md`).

## Work queue (in priority order)

Code review of the MCP server (2026-10-05) found no file-corrupting bugs. These issues remain; each
fix needs a failing test first. Tick them off here as they land.

- [ ] **H1 `\r` shifts widgets** (`content/ctxml.py`): CherryTree stores `\r` as `&#13;`; we write a raw
  `\r`, which XML parsers normalise away on load, shifting every later widget offset by one.
  Fix: emit `&#13;` for `\r` in node and table XML.
- [ ] **H2 leading whitespace lost on replace_content** (`from_markdown.py`/`to_markdown.py`): a
  4-space-indented line becomes a code block (embedded image placeholders inside it are dropped);
  tabs/short indents are stripped. Fix: disable markdown-it `code` rule; preserve leading
  whitespace from source lines (via `token.map`) and emit it in `to_markdown`.
- [ ] **H3 plain-page insert merges lines** (`content/editing.py` `insert_after_line_plain`):
  `("a\nb", "a", "X")` → `"a\nXb"`. Fix: ensure inserted text ends with `\n`.
- [ ] **H4 reload race** (`notebook.py`/`safety.py`): CherryTree compares mtimes in whole seconds
  and resets its stored mtime after its own saves; a write in the same second as an app save is
  never reloaded. Fix: after commit, bump file mtime to `max(now, old_mtime + 1s)`; tool result and
  instructions should say unsaved app edits to the same page win if the user saves.
- [ ] **H5 backup pruning** (`safety.py` `BackupKeeper._prune`): glob `stem-*` also matches other
  notebooks (`notes` vs `notes-work`) and can delete the just-made backup. Fix: one backup
  subfolder per notebook (hash of resolved path); never prune the newest.
- [ ] **M6 lines after a list/quote get absorbed** (`from_markdown.py`): `"• milk\nNext"` round-trips
  to an indented continuation; `"> q\nplain"` puts `indent=1` on `plain` (lazy continuation).
- [ ] **M7 code fence too short** (`to_markdown.py` `_render_codebox`): count backtick runs
  anywhere, not just at column 0.
- [ ] **M8 trashing a page and its subpage flattens them** (`notebook.py` `trash_pages`/`move_pages`):
  drop requested pages whose ancestor is also requested.
- [ ] **M9 safety fails open** (`safety.py`): if `lsof` is missing/times out, writes proceed with
  id gap 1. Keep the 100 gap when detection is unavailable. Also check `~/.config/cherrytree/config.cfg`
  (used by a self-built binary) besides the .app config; require reload on in every config that exists.
- [ ] **M10 unreadable errors** (`server.py`, `store/repository.py`): make `NotACherryTreeDocument`
  a `NotebookError`; open SQLite with `mode=rw` URI so a missing file is not created as 0 bytes;
  strip lone surrogates in `sanitize_text`; map `sqlite3.Error`/`OSError` to `ToolError`.
- [ ] **L11 search loads image BLOBs** (`repository.payloads`): select `NULL` for `png` in search.
- [ ] **L12 lossy round trips** (`to_markdown.py`): bullet glyph variety, `1)` vs `1.`, numbering,
  `~~~` rules are normalised. Acceptable; document or preserve.

After the queue: pick from `claude/ROADMAP.md` with the user (slash menu, backlinks and templates
are the cheapest high-value app features).

## CherryTree facts you would otherwise re-derive (all verified)

- `.ctb` = SQLite, tables `node, codebox, grid, image, children, bookmark` (schema in
  `src/ct/ct_storage_sqlite.cc`). Rich text `node.txt` = `<node><rich_text attr=…>text</rich_text>…</node>`
  with attributes `weight=heavy, style=italic, underline, strikethrough=true, scale=h1..h6|small|sup|sub,
  family=monospace, foreground, background, justification, indent=N, link`.
- Widget `offset` = char position in the final buffer where each earlier widget counts as 1 char.
- Table XML stores the **header row last**; `col_widths="0,0"` means default widths.
- Links: `webs URL`, `node ID [anchor]`, `file <base64 path>`, `fold <base64 path>`.
- Lists are plain text: 3 spaces per level; bullets `•◇▪-→⇒` by level; to-dos `☐☑☒`;
  numbers `1.` `1)` `1-` `1>` by level. Rule = 33 `~`. Tags are space-separated.
- Clones: `children.master_id > 0`; content and name live on the master node.
- The app keeps the .ctb open, saves only changed nodes, numbers new nodes `max(in-memory id)+1`,
  and with `mod_time_sentinel=true` polls mtime every 5 s and reloads (asking to save first if dirty).
- Headless verification: `CherryTree file.ctb -t outdir -w -s -S` (text) or `-x` (HTML) loads the
  file exactly like the GUI and exits; e2e tests use this.
- Markdown auto-formatting while typing already exists (Preferences → Rich Text → "Enable Markdown
  Auto Replacement (Experimental)", off by default).

## Handoff protocol

Before your context fills or you stop: update "Done", "Work queue" and "State of the user's Mac"
above, commit on your branch, push, and open/merge the PR into `main`. Never leave work only in the
working tree.
