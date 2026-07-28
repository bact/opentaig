# Tool curation

Working files for **discovering open-source tools and mapping them to the
open problems (research questions) they help address.**

Nothing in this directory is read by `build.py` or deployed with the site.
The Google Sheets connector is read-only, so — as with every prior data
change in this project — the output here is **candidate CSVs for human
review**, which a person then pastes into the live `OpenTAIG` sheet. That
review step is also the quality gate against false positives.

## The one rule that shapes everything: the research question is the spine

Tools map **directly** to research questions. Terms/principles map
**directly** to research questions. Both hang off the `rq_no` independently
— a tool is **never** attached to a question *because* they happen to share
a principle. Concretely, discovery decides "does this tool help address
question _N_?" by reading the tool's README / linked paper and comparing it
to question _N_'s own text — not by matching principle tags.

The schema supports this via the `tool_map` tab: one row per `(rq_no,
tool_id, role)` pairing, plus a free-text `rationale` for *why* that tool
addresses that specific question. Long/tidy format rather than a
semicolon-list cell on the `map` tab, precisely so a tool answering several
questions or a question answered by several tools is just more rows, never
a cell to hand-edit. (This used to live as `tools_implement`/`tools_eval`
columns on the `map` tab itself; that couldn't hold a rationale and made
adding one pairing risk clobbering another already in the same cell.)

> An earlier version of this directory tried to derive `RQ ↔ tool` mappings
> from *shared principle ids* (term overlap). That is exactly the
> indirection the rule above rules out, and it was too noisy to be useful.
> Those files (`generate_candidate_mapping.py`, `candidate_mapping*.csv`,
> `live_map_snapshot.csv`) have been removed.

Two consequences of judging strictly against each question's own text,
worth keeping in mind so they don't get "corrected" away in a future run:

- **One tool answering several questions is expected, not a smell.** A
  license scanner can plausibly help both *automate* collection (RQ2) and
  let you *verify accuracy* when aggregating sources (RQ3). Map each
  `rq_no` it genuinely earns, independently — don't cap a tool at one
  question to look conservative.
- **A question with zero mapped tools is a real, useful finding** —
  evidence of a coverage gap in the open-source ecosystem, not a failed
  search. Don't treat an empty result as something to fix by loosening the
  matching rule; report it as-is. Coverage gaps are exactly the kind of
  signal worth surfacing (e.g. for a paper analyzing which research
  questions currently have no open tooling at all).
- **A Creative Commons license (e.g. `CC-BY-NC-4.0`) is not a reason to
  reject a candidate.** CC licenses aren't OSI-approved for software and
  are unusual to see on a code repo (they're intended for creative/data
  works, not source code) — but that unusualness is itself worth keeping,
  not filtering away: it's exactly the kind of observation a paper on tool
  curation would want data on. Accept the tool, record the license as-is in
  the `license` column (don't normalize it to something it isn't), and note
  the licensing anomaly in the mapping `rationale` so a reader doesn't have
  to go re-derive it.
- **Judge the thing that was actually found, not the platform it lives
  inside.** A candidate that's a feature/module bundled inside a much
  larger general-purpose platform (e.g. a governance feature inside an
  MLOps suite) isn't independently distributable, installable, or
  documented — so it isn't a standalone tool and gets rejected
  (`out-of-scope-narrow`) even if the host platform is itself relevant.
  This doesn't rule the host platform out — it just means the platform
  would need its own separate judgment, against its own README/docs and
  a specific question's own text, in its own right — not inherited from
  the sub-feature that surfaced it.

## Pipeline

Deterministic work lives in Python scripts (no model needed); only the
judgment steps need a model.

1. **Export RQ context** — `python build.py && python curation/export_rq_context.py`
   → `rq_context.json` (git-ignored, regenerated each run): every research
   question with its text, taxonomy, and the tool ids already mapped to it.
   This is the spine the agent reads so it maps new tools directly to
   questions and never re-proposes an existing one. **Built.**
2. **Scope** *(agent)* — draft/refine search keywords per problem area for a
   bounded slice of questions.
3. **Search** *(script: `search_repos.py`, built)* — runs keywords against
   the real GitHub Search API (`stars:>N pushed:>DATE archived:false
   fork:false`, plus a README-length filter to drop 1-line stubs), writing
   the full raw hit list per keyword (`state/search_raw/`) and a
   deduplicated, README-filtered candidate list (`state/search_candidates.csv`).
   **Needs a real GitHub token and unrestricted network — see "Running
   locally" below, this is why that matters.** The agent's built-in web
   search can supplement this for blog/paper-surfaced tools GitHub search
   misses (it goes through a different path and isn't subject to the same
   restriction).
4. **Extract** *(script + agent)* — for each surviving candidate, distil a
   one-line `summary` and note any linked paper from the README. Leave
   `license` blank rather than guess (the script already captures the SPDX
   id from the GitHub API when present).
5. **Map to RQ** *(agent — the core judgment step)* — read the README/paper
   and decide which `rq_no`(s) it genuinely helps address, and whether each
   is `implement` or `eval`, with a one-line rationale per pair. **Direct**
   judgment against the question text (from `rq_context.json`) — never via
   shared principle ids. A `reject` verdict needs a `reject_category` from
   the closed vocabulary in `emit_candidates.py`'s `REJECT_CATEGORIES`, not
   just free text — see "Rejection tracking & licence classification" below.
6. **Dedup** *(script: `dedup_candidates.py`, built)* — drop anything already
   in `tools` or in a `state/seen_repos.csv` log; record verdicts so future
   runs don't repeat.
7. **Emit** *(script: `emit_candidates.py`, built)* — two review CSVs in
   exact live-tab column order: `candidate_tools.csv` (new `tools` rows) and
   `candidate_map_updates.csv` (`rq_no, tool_id, role, rationale`, one row
   per pair) — which is now also the exact column order of the `tool_map`
   tab itself, so step 8 is a straight append, not a merge. Each freshly
   emitted row is also stamped with `datetime_added`, `datetime_checked`,
   and `datetime_updated` all set to the run time (see "Freshness columns"
   below). Every judged repo — accepted or rejected — is logged to
   `state/seen_repos.csv` with its licence classification and reject
   category; pass `--problem-area "..."` so that's recorded too.
8. **Review & merge** *(human)* — accept/edit, then:
   - paste accepted rows from `candidate_tools.csv` into the `tools` tab
     (fine to be selective here, e.g. only tools with a confirmed
     open-source license);
   - **append** (don't merge-into-a-cell) matching rows from
     `candidate_map_updates.csv` into the `tool_map` tab — drop any row
     whose `tool_id` you didn't add to `tools`. Since `tool_map` is one row
     per pairing rather than a semicolon list, there's no existing-cell
     content to preserve or clobber.
   - The next site build picks up the changes.

### Freshness columns

Every tab `build.py` owns (`map`, `tool_map`, `tools`, `terms`, `framework`)
carries three timestamp columns, and every row is expected to have all
three filled in:

- **`datetime_added`** — when the row was first added.
- **`datetime_checked`** — when the row was last reviewed for staleness
  (content re-fetched/re-read and compared against what's already there).
- **`datetime_updated`** — when the row's content actually last changed. A
  check that finds nothing new bumps `datetime_checked` only —
  `datetime_updated` stays put.

These are purely informational today: `build.py` warns (doesn't fail) if
any of the three is blank on a row, but no build logic reads or compares
the values yet. They exist so a future scheduler/crawler can decide what's
stale enough to re-fetch. `emit_candidates.py` stamps all three to the same
run timestamp on newly emitted rows, since a row that's just been added has
also, trivially, just been checked and updated.

### Rejection tracking & licence classification

`state/seen_repos.csv` (step 6/7) is the running log of every judged repo —
**this is the methodology data for a paper claim like "area X surfaced N
candidates, of which M were open source."** It used to record only
`full_name, verdict, timestamp_utc, note`, which made that claim
unanswerable without re-reading 80+ free-text rejection notes by hand. It
now also carries:

| Column | Meaning |
|---|---|
| `reject_category` | One value from `emit_candidates.py`'s `REJECT_CATEGORIES` — a closed vocabulary (`not-open-source`, `not-relevant`, `not-a-tool-linklist`, `not-a-tool-dataset`, `not-a-tool-paper-artifact`, `adversarial-purpose`, `commercial-sdk`, `low-substance`, `out-of-scope-narrow`, `redundant`). `emit_candidates.py` requires one on every `reject` verdict now — a bare `reject_reason` string is no longer enough. |
| `license_spdx_id` | The judgment's `license` field, falling back to the SPDX id `search_repos.py` captured from the GitHub API. Recorded on **accepts too**, not just rejects — you can't compute "M of N were open source" from the rejects alone. |
| `license_class` | `license_spdx_id` run through `licenses.py`'s `classify()` against the *official* SPDX license list's `isOsiApproved`/`isFsfLibre` flags — not a hand-maintained guess. One of `osi-approved`, `free-not-osi` (FSF-libre but not OSI, e.g. `CC-BY-4.0`), `non-free` (a real SPDX id that's neither, e.g. `CC-BY-NC-4.0`), `source-available` (GitHub found a LICENSE file it couldn't match — `NOASSERTION`), `none-declared`, or `unknown`. `emit_candidates.py` cross-checks this against `reject_category`: rejecting something as `not-open-source` while its licence classifies as open is an error, not a warning. |
| `problem_area` | The problem area this batch was searched for — pass `--problem-area "..."` to `emit_candidates.py`, or set a per-judgment `problem_area` key to override it for one row. |
| `found_via_keyword`, `stars` | Also pulled from `search_candidates.csv` by repo — provenance for *how* a candidate was found, alongside *why* it was accepted/rejected. |

`report_triage.py` reads the log and prints two tables: found/accepted/
open-source/rejected counts grouped by `problem_area` (or `--by keyword`),
and a breakdown of rejections by category and of all judged repos by
licence class:

```bash
python curation/report_triage.py
python curation/report_triage.py --by keyword
```

The 144 rows written before this schema existed were backfilled by
`curation/backfill_triage_columns.py` (a one-time migration, kept in the
repo — not deleted after running — so the reconstruction stays auditable:
licence/keyword/stars came from an exact join against
`search_candidates.csv`; `problem_area` from which of four timestamp
clusters a row falls in; `reject_category` from a regex pass over the
existing free-text notes, with every low-confidence fallback printed for a
manual look rather than silently guessed). Going forward every new run
populates these columns itself — the migration script never needs to run
again.

### Model tiering (cost control)

- **No model** for anything in `search_repos.py` / `export_rq_context.py` —
  pure Python, keep it that way.
- **Cheaper model** for orchestration: keyword scoping (step 2), one-line
  summary distillation (step 4), and a coarse pre-filter narrowing each
  candidate to ~3–5 plausible `rq_no`s before the expensive step.
- **Strongest available model, as an isolated subagent** for step 5 (the
  final implement/eval RQ judgment) — give it *only* {candidate summary +
  README excerpt + paper abstract} × {the pre-filtered RQ shortlist}, never
  the whole session history or the entire research-question catalog. A human review gate follows
  regardless, so it's fine to try the cheaper model for step 5 first and
  escalate only where review shows it's too noisy.

### Keyword expansion (phase 2)

Phase 1 (rounds 1–3+) scoped keywords by reading each target RQ's own text
and improvising short phrases from it, one problem area at a time. That
works but is manual and only mines one source of vocabulary. Phase 2 —
started once every RQ range has had at least one real search pass — adds
four more systematic keyword sources on top of it, plus two hard-learned
mechanical rules that apply to all five:

- **GitHub's search API ANDs every unquoted word.** A 4-5 word free-text
  query routinely returns zero hits even when good candidates exist —
  every multi-word query in round 3 with 4+ unquoted words returned 0. Keep
  free-text queries to 2-3 words. For a literal pattern (see strategy 2
  below) use an exact quoted phrase instead, which GitHub matches as a
  substring rather than an AND of words.
- **Log every keyword regardless of hit count.** A 0-hit query is not
  wasted effort — `search_repos.py` already logs it to `search_log.csv`
  unconditionally, and it's real negative evidence for the paper (which
  phrasings are too narrow for GitHub's index vs. genuinely describe an
  empty space). When a query returns nothing, the fix is to broaden
  (fewer/more common words) not to add more qualifying terms.

The five keyword sources, in the order worth trying:

1. **Mine vocabulary from our own accepted tools.** Extract recurring
   2-3 word technical phrases from the live `tools.summary` and
   `tool_map.rationale` columns that haven't been tried as search keywords
   yet (check against `search_log.csv`). This is the cheapest source —
   it's grounded in terms that have *already* proven to surface real tools
   for adjacent RQs, so it's likely to surface siblings. Deterministic
   extraction (n-gram frequency) is fine for generating the candidate
   list; still worth a human/agent pass to drop generic noise (e.g. "open
   source", "machine learning") before searching.
2. **`"alternative to <name>"` / `"similar to <name>"` as exact quoted
   phrases.** Many READMEs literally self-describe this way ("X is an
   open-source alternative to Y"), so this is a real, high-precision
   pattern, not a hopeful guess — but only when `<name>` is an actual
   product genuinely relevant to the target RQ (a well-known proprietary
   tool in that space, or one of our own already-accepted OSS tools to
   find its competitors). Don't invent placeholder names to fill the
   pattern.
3. **`"open source"` / `"free software"` + a *named standard or
   principle*.** Deprioritized as a blanket strategy — GitHub results are
   already software repos, so literally adding "open source" to a generic
   query is mostly redundant with the star/license filters already
   applied. Where it *does* earn its keep: searching by an exact
   framework/principle name we haven't searched by yet (e.g. "NIST AI RMF
   implementation", "ISO 42001 audit", "RGAF compliance checklist") to
   catch standard-anchored tools that don't share vocabulary with any RQ's
   own phrasing.
4. **RQ text keywords, formalized.** This is what phase 1 already did
   informally each round — keep doing it as the default per-RQ source, but
   apply the 2-3-word-query rule explicitly rather than improvising full
   phrases that turn out to be 4+ words.
5. **AI risk taxonomies as a keyword reference corpus**, not a blind
   batch-search source. Three sources, layered:
   - [**"The AI Risk Repository: A Comprehensive Meta-Review, Database, and
     Taxonomy of Risks From Artificial Intelligence"**](https://arxiv.org/abs/2407.01294)
     (Slattery et al., 2024) — the actual taxonomy paper: a causal taxonomy
     (7 risk domains, 24 subdomains) plus a database of 700+ risks
     extracted from 40+ existing frameworks. This is the primary source,
     not just methodology background for the navigator below.
   - [**airisk.mit.edu/navigator**](https://airisk.mit.edu/navigator#/taxonomies)
     — the browsable web app over the same repository/taxonomy, easier for
     an agent to search interactively than the paper's PDF tables; see
     also the [*Patterns* write-up](https://www.cell.com/patterns/fulltext/S2666-3899(26)00026-7)
     of the repository's ongoing use.
   - The named Mitigation/Control categories in
     ["Mapping AI Risk Mitigations"](https://cdn.prod.website-files.com/669550d38372f33552d2516e/6887e58496902e3bcad04a5a_1b0850b4406f7dc6a79365c4b56f0f51_Mapping%20AI%20Risk%20Mitigations.pdf)
     — a separate, complementary document once a risk domain is
     identified, giving the *mitigation-technique* vocabulary (not just
     risk-category vocabulary) to search with.

   Together these give a structured, pre-classified vocabulary of risk
   categories and named mitigation techniques (red-teaming, watermarking,
   differential privacy, content provenance, bias auditing, ...) that map
   cleanly to searchable tool categories — and the classification comes
   free, useful for the paper independent of search. Use it the same way
   as source 4:
   cross-reference each target RQ against the taxonomy first to find the
   1-2 most relevant risk/mitigation entries, *then* derive a short
   keyword from that — don't batch-search the whole taxonomy blind. Cache
   the source documents locally on first use (same pattern as
   `licenses.py`'s SPDX cache) rather than re-fetching every session.

## Running locally (do this next)

**This pipeline was built inside a Claude Code Remote sandbox whose GitHub
access is hard-bound to a single repository at the network layer** — not
just the GitHub MCP tool, but *any* HTTP call to `api.github.com` from that
session gets `403 sessions are bound to their configured repositories` for
anything outside that one repo, including the Search API `search_repos.py`
needs. It also can't reach `docs.google.com` directly (worked around there
via a separate Drive connector). **None of this applies to a normal local
Claude Code session** — normal internet, your own GitHub token, no binding.
That's why steps 3 onward should run locally from here on.

Setup, once, on your machine:

```bash
git clone https://github.com/bact/opentaig.git && cd opentaig   # or: git pull, if already cloned
git checkout main   # this pipeline is merged into main
pip install -r requirements.txt
export GITHUB_TOKEN=<a personal access token, no special scopes needed —
                      `gh auth token` works if you use the gh CLI>
```

Then, each curation run:

```bash
python build.py                          # fetches the LIVE sheets directly (works fine locally)
python curation/export_rq_context.py      # refresh rq_context.json from the full live catalog
python curation/search_repos.py --keyword "..." --keyword "..."   # step 3
```

Then continue in that local Claude Code session with steps 2 (scoping,
before searching) and 4–8 above — point it at this file for the full
pipeline description and the RQ-is-the-spine rule. `search_repos.py --help`
documents all its flags (`--min-stars`, `--pushed-after-months`,
`--min-readme-chars` are all overridable if the defaults need adjusting
after seeing real results).

### Live sheet schema (current)

All tab and column names are lowercase with underscores. Five tabs are
owned by this pipeline, each carrying the three freshness columns above:

- **`map`** — `rq_no` + one column per framework (`rgaf`, `euaiact`,
  `unescoai`, `aseanai`, `coeai`) + freshness columns.
- **`tool_map`** — `rq_no, tool_id, role, rationale` + freshness columns.
  One row per `(rq_no, tool_id, role)` pairing.
- **`tools`** — `id, tool_type, name, summary, license, homepage, source,
  documentation, funding, implement, eval` + freshness columns.
- **`terms`** — `id, framework_id, name, summary, url` + freshness columns.
- **`framework`** — `id, name, fullname, summary, homepage, source, group`
  + freshness columns.

`tools_rgaf_seed` is a staging-only tab (not read by `build.py`) holding
tools sourced from the LF AI & Data RGAF blog post, pending triage into
`tools`/`tool_map`.

(Historical note: the `tool_map` tab replaced `tools_implement`/
`tools_eval` semicolon-list columns that used to live on `map`, and every
tab/column name used to be a mix of casings, e.g. `RQ_No`, `RGAF`,
`tools-rgaf`. That migration is done; nothing left to set up.)

## Files

- **`export_rq_context.py`** — built. Reshapes a local `site/data.json`
  into `rq_context.json`. Deterministic; no model, no network.
- **`search_repos.py`** — built. Real GitHub Search API + README-length
  filter, plus a `state/search_log.csv` provenance log (every keyword tried,
  exact query, hit counts — kept for methodology/paper documentation, not
  just the surviving candidates). Deterministic; no model; needs
  `GITHUB_TOKEN` + unrestricted network (see "Running locally" above).
- **`dedup_candidates.py`** — built. Drops candidates already live in
  `tools` (matched by GitHub repo path) or already judged in
  `state/seen_repos.csv`. Deterministic; no model, no network. Writes
  `state/candidates_to_review.csv` (git-ignored, regenerated each run).
- **`emit_candidates.py`** — built. Takes a judgments JSON (step 4+5 output)
  and writes `candidate_tools.csv` + `candidate_map_updates.csv` (each row
  stamped with `datetime_added`/`datetime_checked`/`datetime_updated` set
  to the run time), and appends every judged repo (accept or reject) to
  `state/seen_repos.csv`, with a validated `reject_category` and licence
  classification — see "Rejection tracking & licence classification" above.
  Deterministic; no model, no network.
- **`licenses.py`** — built. Classifies a GitHub-reported SPDX license id as
  `osi-approved` / `free-not-osi` / `non-free` / `source-available` /
  `none-declared` / `unknown`, from the official SPDX license list's
  `isOsiApproved`/`isFsfLibre` flags (fetched once, cached to
  `state/spdx_licenses.json`). Deterministic; no model; network only on
  first run or `refresh=True`. Field names (`is_osi_approved`,
  `is_fsf_libre`) follow the SPDX 3.0 model / the `is-osi`/`is-fsf`
  predicates in [bact/licenseid](https://github.com/bact/licenseid) — see
  that project instead if the input is unstructured license *text* rather
  than an already-resolved SPDX id.
- **`report_triage.py`** — built. Reads `state/seen_repos.csv` and prints
  found/accepted/open-source/rejected counts by problem area (or keyword),
  plus breakdowns by reject category and licence class. Deterministic; no
  model, no network.
- **`backfill_triage_columns.py`** — one-time migration, already run; kept
  for auditability. See "Rejection tracking & licence classification" above.
- **`candidate_tools_from_rgaf.csv`** — historical snapshot: the original 32
  tools pulled from the sheet's `tools_rgaf_seed` staging tab (seeded from
  the LF AI & Data blog post ["Putting RGAF to Work"](https://lfaidata.foundation/communityblog/2026/04/22/putting-rgaf-to-work-build-and-audit-responsible-ai-with-open-source/)),
  before triage. Most have since been triaged (real GitHub repo resolved,
  README read, mapped into `tools`/`tool_map`, or rejected) directly in the
  live `tools_rgaf_seed` tab; a handful remain untriaged there. **To
  continue:** run the same discovery→judgment steps (4–5) against the
  remaining rows in the live tab, same as any other candidate batch — this
  file itself is not kept in sync with that progress.
- **`rq_context.json`** — generated (git-ignored, purely derived from a
  fresh `site/data.json`), see step 1.
- **`state/search_raw/*.json`**, **`state/search_candidates.csv`**,
  **`state/search_log.csv`**, **`state/seen_repos.csv`**,
  **`state/spdx_licenses.json`** — generated, but **commit these**: unlike
  `rq_context.json` they're the running audit trail / dedup base /
  provenance log / licence-classification cache across runs (and
  contributors), not a disposable snapshot. See steps 3, 6, and "Rejection
  tracking & licence classification".
- **`candidate_tools.csv`**, **`candidate_map_updates.csv`** — generated by
  `emit_candidates.py` (step 7), one batch at a time. Commit them alongside
  the run that produced them if you want a record of what was proposed
  before human review, or just leave the latest batch in place — either
  way they get overwritten by the next `emit_candidates.py` run.

## Automation (later)

Once the on-demand pipeline is proven on a problem area, steps 1–7 can be
wrapped in a scheduled agent that opens a candidate PR each period —
preferably a scheduled Routine in the Claude environment (no repo secret
needed), or a GitHub Actions + Claude Code Action job (needs an
`ANTHROPIC_API_KEY` secret, open-internet runner). Each run should handle a
bounded slice of questions to cap cost and keep the review PR small.
