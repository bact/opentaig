---
SPDX-FileCopyrightText: 2026 OpenTAIG authors
SPDX-FileType: SOURCE
SPDX-License-Identifier: CC0-1.0
---

# Handover: UI design / implementation session

Paste the prompt below into a fresh Claude Code session, in this repo, to
pick up the site's UI/design thread (Landscape matrix, mini-heatmap,
tool/problem listing pages, tool cards) — split out from tool-discovery/
curation work, which has its own handover: `handover-tool-discovery.md`.

---

```text
Repo: /Users/art/projects/opentaig (OpenTAIG static site). Jinja2 + Python
generator: build.py -> templates/*.html -> site/ (gitignored).

Continue UI/design work on the site: Landscape matrix, mini-heatmap,
tool/problem listing pages, tool cards.

Key files:
- build.py — build_matrix() (Capacity x Target coverage matrix data),
  select_highlighted_problems() + first_words() (tool-card problem chips,
  word-boundary-safe truncation)
- templates/_matrix.html — full Landscape page matrix
- templates/_matrix_compact.html — mini-heatmap atop Explorer/Tools listing
  pages (shared header row for target columns, separator row before
  Operationalisation/Ecosystem Monitoring's "All" rows)
- templates/tools_index.html — tool cards, incl. "Problems addressed:" chips
  and the language/license chips (`entry.tool.programming_languages` — a
  list, iterate it; `entry.tool.license` — blank-guard it, `{% if %}`, it's
  legitimately empty for plenty of tools) at templates/tools_index.html:45-46
- assets/style.css — Lumina design system (CSS custom props, light/dark via
  prefers-color-scheme)
- docs/development.md — Notes section documents current UI structure, keep
  it in sync with any structural change

Current data model, if a tool card or listing page ever needs a new field:
`Tool` objects (build.py) merge **two** sources per field, not one — a
hand-curated/AI-judged `tools` tab and an auto-collected `tool_metadata`
spreadsheet, resolved by a precedence rule (`tools` override wins if
non-blank; the literal text `none` forces blank; otherwise falls through
to `tool_metadata`) — see "tools / tool_metadata precedence" in
docs/data-schema.md before assuming any field is always populated. Most
project-quality fields (`stars`, `forks`, `contributors`, OpenSSF scores,
`development_status`, ...) are legitimately blank far more often than not
(never collected, or the tool predates a collection run) — any new UI
surfacing one of these needs the same blank-guard treatment `license`
already gets, not an assumption it's always there.

Verification workflow used so far: `cd /Users/art/projects/opentaig &&
python build.py` -> serve site/ on localhost -> hard-reload (bypass cache)
-> use javascript_exec / getBoundingClientRect / getComputedStyle for
pixel-exact checks (more reliable than screenshot-coordinate clicking in
this tooling) -> Python regex link-integrity check for 0 broken hrefs.

Standing rules:
- Never edit the live Google Sheets directly.
- Never commit — user does all git operations manually.
- No dead CSS/template code — grep for a selector's usage before deleting
  it, but also delete confirmed-unused rules rather than leaving them.

Ask what's next.
```
