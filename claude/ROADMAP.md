# Roadmap: Notion-style features for this fork

Everything specific to this fork lives under `claude/` (plus small, upstreamable fixes), so
rebasing onto a new upstream CherryTree release stays painless. App features below will touch
`src/ct/` and should be kept as isolated as possible (new files over edits to existing ones).

Effort: **S** = a day or less, **M** = a few days, **L** = a week+, **XL** = architectural.

## Already in CherryTree (turn on / document, don't rebuild)

| Notion feature | CherryTree equivalent | Where |
|---|---|---|
| `* ` → bullet, `[] ` → to-do, `:: ` → ▪ | Built in | `ct_text_view.cc` `for_event_after_key_press` |
| Toggle headings | Collapsible header anchors | `ct_text_view.cc` `expand_collapsed_anchors` |
| Favorites | Bookmarks | `bookmark` table |
| Synced blocks | Shared nodes (clones), node-level only | `children.master_id` |
| Quick switcher / command search | Command palette | `ct_dialogs_cmd_palette.cc` |
| Page tags | Node tags | `node.tags` |
| Page links / anchors | Node links + anchors | `link="node N anchor"` |
| Auto-reload on external change | *Preferences → Misc → Reload After External Update to CT\* File* | `ct_main_win_file.cc` `mod_time_sentinel_restart` |

## App features (C++, `src/ct/`)

0. **Markdown shortcuts while typing** (S–M): upstream has an experimental `CtMarkdownFilter`
   (`**bold**` etc. as you type) but it is compiled out (`MD_AUTO_REPLACEMENT` is never defined).
   Evaluate it: define the flag in a test build, check behaviour, then enable or replace it.

1. ~~**Slash command menu**~~ **done** (`ct_slash_menu.cc`): `/` at line start opens the command
   palette restricted to insert/format actions; headings chosen on an empty line format what you
   type next. Toggle: *Preferences → Rich Text → Typing / at Line Start Opens the Insert Menu*.
2. **Backlinks panel** (M): "Linked from" list under the node header, built by scanning rich text
   for `link="node <id>"`. Cache per document; refresh on save.
3. **`[[` page mention autocomplete** (M): type `[[` → fuzzy node picker → inserts a node link.
4. **Templates** (S): a "Templates" node; *New node from template* duplicates the chosen subtree
   (with `{{date}}` / `{{title}}` substitution).
5. **Callout blocks** (M): coloured, icon-prefixed box. Likely a new anchored widget type modelled
   on `CtCodebox`; needs a storage representation in all four formats (or a styled 1×1 table).
6. **Page properties** (L): typed properties per node (select, multi-select, date, number,
   checkbox, URL). Store in a new SQLite table `node_property(node_id, key, type, value)`; stock
   CherryTree ignores unknown tables, but XML/multifile formats need an extension too.
7. **Database views of child nodes** (L, needs 6): table and Kanban board of a node's children,
   grouped/sorted/filtered by properties. New view widget swapped into the text area.
8. **Emoji page icons + cover images** (M): extend `custom_icon_id` with an emoji code point; cover
   image as a special first image anchor.
9. **Inline comments** (L): comments anchored to text ranges, stored in a new table, shown in a side
   panel. Also unlocks a `comments` tool for Claude.
10. **Page history** (M): snapshot node XML on save into a `node_history` table; diff/restore dialog.
11. **Drag-and-drop block reordering** (XL): GtkTextView is not block based. Would need a block
    model layered over the buffer. Park unless the rest lands well.
12. **Inline databases inside a page** (XL): depends on 6/7 plus an anchored-widget host.

## Claude integration (`claude/mcp-server/`) follow-ups

- **Live in-app bridge** (L): a local socket API inside CherryTree so edits land in the open buffer
  instantly (no file reload, no unsaved-change prompt), plus "what is the user looking at" context.
- **Comments tool** once inline comments (9) exist.
- **Properties / database query tools** once 6/7 exist (parity with Notion's data source tools).
- **Round-trip colours, underline, justification** through Markdown (e.g. `<span style>`/`<u>`).
- **Image upload**: insert images from a local path or URL into a node.
- **More storage formats**: `.ctd` (XML) and multi-file folders; encrypted `.ctx`/`.ctz` via 7za.
- **Multiple notebooks** in one server (`open_document` tool) instead of one per registration.
- **Claude Desktop / claude.ai**: register in Claude Desktop config; optional remote connector.
