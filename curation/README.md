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
**directly** to research questions. Both hang off the `RQ_No` independently
— a tool is **never** attached to a question *because* they happen to share
a principle. Concretely, discovery decides "does this tool help address
question _N_?" by reading the tool's README / linked paper and comparing it
to question _N_'s own text — not by matching principle tags.

The schema supports this via the `tool_map` tab: one row per `(RQ_No,
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
  `RQ_No` it genuinely earns, independently — don't cap a tool at one
  question to look conservative.
- **A question with zero mapped tools is a real, useful finding** —
  evidence of a coverage gap in the open-source ecosystem, not a failed
  search. Don't treat an empty result as something to fix by loosening the
  matching rule; report it as-is. Coverage gaps are exactly the kind of
  signal worth surfacing (e.g. for a paper analyzing which research
  questions currently have no open tooling at all).

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
   and decide which `RQ_No`(s) it genuinely helps address, and whether each
   is `implement` or `eval`, with a one-line rationale per pair. **Direct**
   judgment against the question text (from `rq_context.json`) — never via
   shared principle ids.
6. **Dedup** *(script: `dedup_candidates.py`, built)* — drop anything already
   in `tools` or in a `state/seen_repos.csv` log; record verdicts so future
   runs don't repeat.
7. **Emit** *(script: `emit_candidates.py`, built)* — two review CSVs in
   exact live-tab column order: `candidate_tools.csv` (new `tools` rows) and
   `candidate_map_updates.csv` (`rq_no, tool_id, role, rationale`, one row
   per pair) — which is now also the exact column order of the `tool_map`
   tab itself, so step 8 is a straight append, not a merge.
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

### Model tiering (cost control)

- **No model** for anything in `search_repos.py` / `export_rq_context.py` —
  pure Python, keep it that way.
- **Cheaper model** for orchestration: keyword scoping (step 2), one-line
  summary distillation (step 4), and a coarse pre-filter narrowing each
  candidate to ~3–5 plausible `RQ_No`s before the expensive step.
- **Strongest available model, as an isolated subagent** for step 5 (the
  final implement/eval RQ judgment) — give it *only* {candidate summary +
  README excerpt + paper abstract} × {the pre-filtered RQ shortlist}, never
  the whole session history or the entire research-question catalog. A human review gate follows
  regardless, so it's fine to try the cheaper model for step 5 first and
  escalate only where review shows it's too noisy.

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

### Live sheet setup: the `tool_map` tab

The OpenTAIG sheet needs a `tool_map` tab before `build.py` will run
against it — a one-time setup step, done once:

1. Add a tab named exactly `tool_map`, header row `rq_no, tool_id, role,
   rationale`.
2. Migrate the one pairing that used to live in `map`'s `tools_implement`/
   `tools_eval` columns: `rq_no=3, tool_id=scancode-toolkit, role=eval` (add
   a `rationale` if you have one handy; blank is fine, it just won't render
   a caption on the site until filled in).
3. Optional cleanup: the `tools_implement`/`tools_eval` columns on `map` are
   no longer read by the build, so you can delete them from that tab — but
   leaving them is harmless, they're just inert now.

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
  and writes `candidate_tools.csv` + `candidate_map_updates.csv`, and
  appends every judged repo (accept or reject) to `state/seen_repos.csv`.
  Deterministic; no model, no network.
- **`candidate_tools_from_rgaf.csv`** — the 32 tools from the sheet's
  `tools_rgaf_seed` staging tab (seeded from the LF AI & Data blog post
  ["Putting RGAF to Work"](https://lfaidata.foundation/communityblog/2026/04/22/putting-rgaf-to-work-build-and-audit-responsible-ai-with-open-source/)),
  in the `tools` tab's exact column order. No id collides with the rows
  already live in `tools`. **To use:** review, then append to the `tools`
  tab. (These rows carry `implement`/`eval` *term* tags from the source;
  those are descriptive metadata only — they are **not** how the tools get
  mapped to questions.)
- **`rq_context.json`** — generated (git-ignored, purely derived from a
  fresh `site/data.json`), see step 1.
- **`state/search_raw/*.json`**, **`state/search_candidates.csv`**,
  **`state/search_log.csv`**, **`state/seen_repos.csv`** — generated, but
  **commit these**: unlike `rq_context.json` they're the running audit
  trail / dedup base / provenance log across runs (and contributors), not a
  disposable snapshot. See steps 3 and 6.
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
