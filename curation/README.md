# Tool curation working files

This directory holds **review artifacts only** — nothing here is read by
`build.py` or deployed with the site. This session has no write access to
Google Sheets, so every file here is meant to be reviewed and then pasted
into the live `OpenTAIG` sheet by hand, the same way every prior data
migration in this project has worked.

## Files

- **`candidate_tools_from_rgaf.csv`** — the 32 tools from the sheet's
  `tools-rgaf` tab (itself a curation-only staging tab seeded from the LF
  AI & Data community blog post ["Putting RGAF to Work"](https://lfaidata.foundation/communityblog/2026/04/22/putting-rgaf-to-work-build-and-audit-responsible-ai-with-open-source/)),
  reformatted to the `tools` tab's exact column order. No id collides with
  the 3 rows already live in `tools` (`scancode-toolkit`, `spdx3`,
  `croissant`). **To use:** review, then append these rows to the live
  `tools` tab.

- **`live_map_snapshot.csv`** — a point-in-time snapshot (fetched this
  session) of the live `map` tab's 5 framework columns only (`RQ_No`,
  `RGAF`, `EUAIAct`, `UNESCOAI`, `ASEANAI`, `CoEAI`) — the input to the
  script below. Not authoritative; re-fetch before re-running if the sheet
  has changed since.

- **`generate_candidate_mapping.py`** — intersects each candidate tool's
  `implement`/`eval` term ids against each RQ's mapped term ids (across
  all 5 frameworks, not just RGAF, so it keeps working if a future tool
  declares e.g. an EU AI Act article). Produces:
  - `candidate_mapping.csv` — tidy form, one row per
    `(RQ_No, tool_id, role, shared_term)`. This is the source of truth —
    it shows *which* term justified each suggestion.
  - `candidate_mapping_by_rq.csv` — the same data pivoted to one row per
    `RQ_No` with semicolon-joined tool lists, easier to scan.

  Re-run with `python curation/generate_candidate_mapping.py` after
  updating either input CSV.

## Important caveat: this is a rough shortlist, not an answer

The current `tools-rgaf` seed only tags tools against the 9 broad RGAF
principles (e.g. `rgaf-safe`, `rgaf-transparent`) — there's no finer
granularity yet. Since many RQs and many tools all share the same handful
of broad principles, the overlap signal is **noisy**: `candidate_mapping.csv`
has 1,462 rows across 83 RQs and 32 tools, and several RQs get 10+
candidate tools per role. Term overlap means "plausibly relevant," not
"definitely relevant" — **read `candidate_mapping_by_rq.csv` and
hand-pick the tools that actually fit each question** before pasting
anything into the live `map` tab's `tools_implement`/`tools_eval` columns.
Don't paste either file in wholesale.

When pasting, **merge, don't overwrite**: some `RQ_No` rows already have
values in `tools_implement`/`tools_eval` (e.g. RQ 3 already has
`scancode-toolkit` in `tools_eval`) that must be preserved.

## Deferred (not built here)

Broader web search/crawling for tools beyond the two named seed sources
(the LF AI & Data post, already in `tools-rgaf`; OECD's AI tools catalogue
at oecd.ai/en/catalogue/tools, not yet pulled in — this sandbox's network
policy blocks that domain) stays out of scope for this pass. A future
pass could also add finer-grained (non-RGAF) term tags to more tools to
sharpen the overlap signal above.
