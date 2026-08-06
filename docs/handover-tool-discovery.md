---
SPDX-FileCopyrightText: 2026 OpenTAIG authors
SPDX-FileType: SOURCE
SPDX-License-Identifier: CC0-1.0
---

# Handover: tool-discovery / methodology session

Paste the prompt below into a fresh Claude Code session, in this repo, to
pick up the tool-discovery and curation thread (searching for candidate
open-source tools, judging them against research questions, mapping
accepted tools, and maintaining the methodology write-up) — split out from
UI/design work, which has its own handover: `handover-ui-design.md`.

---

```text
Repo: /Users/art/projects/opentaig (OpenTAIG). Continue the tool-discovery
pipeline — this project already has canonical starter prompts baked into
the repo; use those, don't reinvent process.

Read curation/README.md in full first, § "Starter prompts (for
reproducibility)" (~line 600) — it has the Phase 1 prompt and the Phase 2
prompt verbatim. Phase 1 (RQ-text-derived keywords, per problem area) has
already run across the RQ set. This session continues Phase 2: broader
keyword sources (topic-tag sweeps, mined vocabulary, snowballing, registry/
arXiv search — see "Keyword expansion (phase 2)" in curation/README.md) and
Pass A (re-judging already-accepted tools against RQs they're not yet
mapped to, since dedup_candidates.py structurally can't find that via
search).

State so far: curation/state/search_log.csv has ~342 logged queries across
free-text, topic:, mined-vocabulary, snowball, and arXiv sources.
curation/state/seen_repos.csv has ~1,650 judged repos.
curation/state/pass_a_checked.csv has the Pass A ledger (which (tool_id,
rq_no) pairs have already been checked, match or no_match — read this
before picking new pairs so a run doesn't silently redo ground already
covered). curation/candidate_tools.csv / candidate_map_updates.csv /
candidate_tool_metadata.csv are all at header-only (last batch already
merged into the live sheets by the user) — confirm this before assuming
you're starting clean. Note there are now **three** live sheets, not two:
`OpenTAIG` (`tools`/`tool_map`/`map`/`terms`/`framework` tabs) and a
separate `tool_metadata` spreadsheet (100% auto-collected, never
hand-edited) — see "tools / tool_metadata precedence" in
docs/data-schema.md before touching anything project-quality-related.

Use the Phase 2 prompt in curation/README.md as your working instructions —
follow it directly (bounded batches of one problem area or ~5-10 RQs, Pass
A before Pass B, stop for review after each batch). Pass A additionally
now has you look up each tool's already-merged record in `site/data.json`'s
top-level `tools` array before reading its README fresh (saves a read, and
surfaces `development_status`/`last_commit_date` as judgment context a
README alone won't) — see "PASS A" in curation/README.md, including the
"flag suspicious auto-collected values for review" note (a `license`/
`programming_language` that's blank or implausible for what the tool
obviously is, e.g. a spec repo, is worth a `tools`-tab override even
though the collector already tried hard to get it right — see
curation/collect_project_metadata.py's docstring for exactly how hard,
and where it still can't). Also read docs/methodology-and-findings.md for
what's already been found (F1-F6, limitations, § 6 future-work list) so
you don't re-discover known findings as if new.

Standing rules: never edit the live Google Sheets directly — human pastes
candidate_tools.csv / candidate_map_updates.csv / candidate_tool_metadata.csv
in after review. Never commit. Multi-RQ mappings are expected, not a
smell; a zero-tool RQ is a finding to report, not a gap to force a match
for; don't reject on CC license or missing GitHub LICENSE file alone —
check package-manifest files first (this is now also what
collect_project_metadata.py does automatically for already-accepted
tools' `license`/`programming_language`, so a Pass B judge should apply
the same standard a judgment call requires, not less).

Ask which batch (problem area, or Pass A vs Pass B) to run next.
```
