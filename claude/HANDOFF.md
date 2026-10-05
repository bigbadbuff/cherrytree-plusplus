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
- Apps: `/Applications/CherryTree.app` = stock 1.7.0 (dehesselle build, no fork fixes);
  `~/Applications/CherryTree++.app` = launcher for this repo's `build/cherrytree` (1.7.2 + fixes).
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

- [x] **Close the last reload race in the app (C++)**: `CtStorageControl::save` now keeps the
  recorded mod time behind the file when it changed on disk since load/last save, so the
  "Reload After External Update" sentinel still reloads after the app's own (partial) save.
  Covered by `tests/tests_external_update.cpp` (target `run_tests_plusplus`); upstream's
  `run_tests_with_x_2` read/write suite still passes. Only builds of this repo have the fix.
- [x] **CherryTree++.app launcher**: `claude/macos/make-app.sh` builds a launcher bundle for
  `build/cherrytree` (icon from `icons/cherrytree.svg`, settings shared with the stock app via
  `XDG_CONFIG_HOME`); `claude/macos/test-make-app.sh` checks it. Installed at
  `~/Applications/CherryTree++.app` and live-tested (MCP write → app reloaded).
- [x] **Slash command menu** (`src/ct/ct_slash_menu.{h,cc}`, hook in `CtTextView::for_event_after_key_press`,
  palette gained an optional action-id filter, config `slash_command_menu`, preference checkbox).
  Unit tests in `tests/tests_slash_menu.cpp` (mutation-checked). **Not yet seen in the GUI**: the user
  declined screen access for CherryTree++, so ask them to try `/` on an empty line.
- [x] **Fix `fs::is_file_image` on macOS** (upstream bug, `ct_filesystem.cc`; all 88 `run_tests_no_x` now pass): `g_content_type_guess`
  returns UTIs like `public.png` on macOS, so the `image/` check fails (upstream test
  `FileSystemGroup.is_file_image` fails here; pasting image files inserts them as attachments).
  Fix: compare `g_content_type_get_mime_type(content_type)`.
- [ ] **Next Notion features** (see ROADMAP): backlinks panel, `[[` page-link autocomplete, templates.
- [ ] **Retire the stock 1.7.0 app** once the user agrees (ask first; it is their install). It
  lacks the reload-race fix. Opening `.ctb` files by double-click in Finder still goes to the stock
  app; the launcher does not handle Finder "open document" events yet.
- [x] **L12 lossy round trips**: documented, not fixed. `replace_content` normalises custom bullet
  glyphs, `1)`-style numbering and divider lengths to CherryTree's defaults (stated in the tool
  description); targeted edits are lossless. Revisit only if the user customises these.

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

After the queue: continue down `claude/ROADMAP.md` (backlinks and templates are the cheapest
high-value app features next).

## C++ tests (macOS)

Fork tests live in target `run_tests_plusplus` (`tests/tests_plusplus_app.h` gives a hidden-window
harness; text-buffer tests must call `gtk_init_check` + `Gtk::Main::init_gtkmm_internals`).

`build.sh` disables tests on macOS, so use a separate build dir:

```bash
git submodule update --init tests/googletest
PKG_CONFIG_PATH=/opt/homebrew/opt/icu4c/lib/pkgconfig:/opt/homebrew/opt/curl/lib/pkgconfig \
  cmake -S . -B build-tests -GNinja -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON -DINSTALL_GTEST=''
LIBRARY_PATH=/opt/homebrew/lib ninja -C build-tests run_tests_plusplus run_tests_with_x_2
(cd build-tests && ./run_tests_plusplus && ./run_tests_with_x_2)
```

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
- Markdown auto-formatting while typing (`CtMarkdownFilter`) exists in the source but is compiled
  out: `MD_AUTO_REPLACEMENT` is never defined, so there is no such preference in any build.

## Handoff protocol

Before your context fills or you stop: update "Done", "Work queue" and "State of the user's Mac"
above, commit on your branch, push, and open/merge the PR into `main`. Never leave work only in the
working tree.
