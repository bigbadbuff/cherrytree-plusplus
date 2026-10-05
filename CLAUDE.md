# CherryTree++ (fork of giuspen/cherrytree)

CherryTree's latest release plus a Claude integration (MCP server) and, over time, Notion-style
features. Repo: https://github.com/bigbadbuff/cherrytree-plusplus

**Before doing anything, read `claude/HANDOFF.md`.** It holds the current status, the prioritised
work queue, machine-specific state, and hard-won facts about CherryTree's file format. Update it
before you stop (see "Handoff protocol" in that file).

## Ground rules

- Base is the latest upstream **release tag** (currently `v1.7.2`), not upstream `master`.
- Default branch is `main`. Work on a feature branch, open a PR into `main`, merge it.
  `master` only mirrors upstream; never build on it.
- Keep fork-specific work under `claude/` where possible; C++ changes in `src/ct/` should be
  small and isolated (new files over edits) so upstream rebases stay easy.
- TDD, 80%+ coverage, small focused files, immutable data, conventional commits
  (`feat:`, `fix:`, …) ending with the Co-Authored-By trailer.
- When the user gives explicit instructions, act on them directly; don't re-plan or re-ask.
- Never write to the user's notebook (`~/Documents/CherryTree/Notes.ctb`) for testing; use temp copies.

## Commands

```bash
cd claude/mcp-server && uv run pytest --cov             # MCP server tests (all must pass)
./build.sh release notests && ./build/cherrytree         # build/run the app (macOS, Homebrew deps)
```
