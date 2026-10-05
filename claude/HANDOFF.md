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
  16 tools, 136 tests, ~94% coverage, e2e tests that export through a real CherryTree binary.
  Module map: `claude/mcp-server/README.md`. Setup and tool table: `claude/README.md`.
- Verified live: with the notebook open in CherryTree 1.7.0, a write through the installed server
  was picked up by the app ("Document was Reloaded After External Update") and rendered correctly.
- Code review findings H1–H5, M6–M10, L11 fixed with regression tests (PR "fix/review-findings").

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

- [ ] **Close the last reload race in the app (C++, small)**: if CherryTree saves (autosave or
  Ctrl+S) after Claude writes but before its 5-second mtime poll, it records the new mtime and never
  reloads, keeping a stale in-memory copy that can later overwrite Claude's pages. Fix in the fork:
  before saving (`ct_storage_control.cc` save path / `CtMainWin` autosave in `ct_main_win_file.cc`),
  if `fs::getmtime(file) > _mod_time`, run the existing reload flow first. Add a regression test
  under `tests/` if feasible, rebuild, and live-test with the MCP server.
- [ ] **L12 lossy round trips** (`to_markdown.py`): bullet glyph variety (`→ ⇒ ◇` → `•`), `1)` →
  `1.`, renumbering, `~~~` rules normalised to 33 `~`. Only affects `replace_content` rewrites;
  targeted edits are lossless. Fix by preserving the original marker text, or document.

### Fixed (2026-10-05, with regression tests)

- [x] H1 `\r` written raw → now `&#13;` (widget offsets no longer shift)
- [x] H2 indented lines became code blocks / lost indentation → code rule off, indentation restored
- [x] H3 plain-page insert merged lines → inserted text always ends its line
- [x] H4 same-second write never reloaded → mtime bumped past previous value after every write
- [x] H5 backup pruning across similarly named notebooks → one backup folder per notebook
- [x] M6 lazy continuation lines absorbed into lists/quotes
- [x] M7 code fence shorter than an inner backtick run
- [x] M8 trashing/moving a page with its subpage flattened the subtree
- [x] M9 safety failed open without lsof → fails closed (gap + reload required); all configs checked
- [x] M10 unreadable errors → `NotACherryTreeDocument` is a `NotebookError`, `mode=rw` open,
  surrogates stripped, `sqlite3.Error`/`OSError` mapped to tool errors
- [x] L11 search loaded image BLOBs

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
