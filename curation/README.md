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
question *N*?" by reading the tool's README / linked paper and comparing it
to question *N*'s own text — not by matching principle tags.

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
  curation would want data on. Accept the tool (leave the judgment's own
  `license` field blank as usual — see "Extract" below — GitHub's detected
  SPDX id still flows through to `seen_repos.csv`'s classification via
  `search_candidates.csv`, unaffected by leaving it blank in the judgment),
  and note the licensing anomaly in the mapping `rationale` so a reader
  doesn't have to go re-derive it.
- **This does NOT extend to source-available/non-compete licenses like the
  Business Source License (BUSL).** A CC license is non-OSI but still
  *free* (`licenses.py` classifies it `free-not-osi`) — it just wasn't
  written with software in mind. BUSL is different in kind, not just
  in degree: it's a genuinely proprietary license during its embargo
  period (`licenses.py` classifies it `non-free`), converting to open
  source only years later. `edgelesssys/marblerun` (BUSL-1.1) was
  initially accepted by conflating these two cases — caught on user
  review and reversed (see its `state/seen_repos.csv` row, verdict
  `reject`/`not-open-source`). The rule of thumb: `license_class ==
  "free-not-osi"` → accept and record honestly; `license_class ==
  "non-free"` → reject as `not-open-source`, full stop, regardless of how
  good the tool otherwise is.
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
   **Needs a real GitHub token and unrestricted network — see "Setup"
   below.** The agent's built-in web
   search can supplement this for blog/paper-surfaced tools GitHub search
   misses (it goes through a different path and isn't subject to the same
   restriction).
4. **Extract** *(script + agent)* — for each surviving candidate, distil a
   one-line `summary` and note any linked paper from the README. Leave
   `license` blank rather than guess (the script already captures the SPDX
   id from the GitHub API when present). **Follow the README's outbound
   links when they're cheap to check** — see "Outbound links as judgment
   signal" below.
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
   - **Clear both CSVs back to just their header row** once merged —
     `emit_candidates.py` appends across runs (see step 7), so a batch left
     in place keeps sitting alongside the next one instead of signalling
     "already handled."
   - The next site build picks up the changes.

### Freshness columns

Every tab `build.py` owns (`map`, `tool_map`, `tools`, `terms`, `framework`,
and `tool_metadata` in its own spreadsheet) carries three timestamp
columns, and every row is expected to have all three filled in:

- **`datetime_added`** — when the row was first added.
- **`datetime_checked`** — when the row was last reviewed for staleness
  (content re-fetched/re-read and compared against what's already there).
- **`datetime_updated`** — when the row's content actually last changed. A
  check that finds nothing new bumps `datetime_checked` only —
  `datetime_updated` stays put.

`tools` and `tool_metadata` each carry their own independent set of these
three (curation activity vs. collection activity — see "`tools` /
`tool_metadata` precedence" in `docs/data-schema.md`), never merged into
one value.

These are purely informational today: `build.py` warns (doesn't fail) if
any of the three is blank on a row, but no build logic compares the values
to decide staleness yet — they're carried through to `data.json` as-is.
They exist so a future scheduler/crawler can decide what's stale enough to
re-fetch. `emit_candidates.py` stamps all three to the same run timestamp
on newly emitted rows, since a row that's just been added has also,
trivially, just been checked and updated; `collect_project_metadata.py`
does the same for `tool_metadata` rows it writes.

### Outbound links as judgment signal

A repo's README usually links out — to an arXiv paper, a benchmark or
leaderboard entry, a docs site, a project page. Those links are cheap,
high-value context for the step 4/5 judgment, and often settle questions
the README alone leaves open:

- **An arXiv link** gives you the abstract, which usually states the
  problem being solved far more precisely than a README's marketing
  paragraph. This is frequently what decides whether a tool genuinely
  addresses an RQ or just shares vocabulary with it.
- **A benchmark/leaderboard entry** is evidence the tool is actually used
  and evaluated by others, not just published — useful against the
  `low-substance` and `not-a-tool-paper-artifact` reject categories.
- **A docs site** (vs. only a README) is a decent proxy for the tool being
  independently installable and maintained, which is exactly the
  `out-of-scope-narrow` question of whether something is a standalone tool
  or a feature inside a larger platform.

One caveat worth knowing, because it shows up constantly in real READMEs:
**Papers With Code (`paperswithcode.com`) was shut down by Meta in July
2025** and now redirects to Hugging Face. Many repos still carry PWC badges
and links that no longer resolve to what they advertise — a dead PWC badge
is *not* evidence against a tool, it's just a stale link. For the same
signal today, use:

- [Hugging Face Papers](https://huggingface.co/papers) — the official
  successor, paper-to-code links and trending papers.
- [`paperswithcode/paperswithcode-data`](https://github.com/paperswithcode/paperswithcode-data)
  — the archived PWC dataset (papers, abstracts, paper↔code links,
  evaluation tables). Frozen, not updated, but still the best historical
  record for anything published before the sunset.

Community successors exist (CodeSOTA, OpenCodePapers, and others) but
none are verified here — treat them as leads, not citations, and prefer
the primary source (the arXiv paper itself) when it's one click away.

Don't over-invest: this is a judgment aid, not a required research step.
Follow a link when the README is ambiguous and the link is one fetch away;
skip it when the README already answers the question.

### Rejection tracking & licence classification

`state/seen_repos.csv` (step 6/7) is the running log of every judged repo —
**this is the methodology data for a paper claim like "area X surfaced N
candidates, of which M were open source."** It used to record only
`full_name, verdict, timestamp_utc, note`, which made that claim
unanswerable without re-reading 80+ free-text rejection notes by hand. It
now also carries:

| Column | Meaning |
| --- | --- |
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

The regex-based backfill isn't perfectly reliable, even where it didn't
print a low-confidence warning: a later spot-check found two of its rows
tagged `reject_category: not-open-source` whose free-text note was actually
about relevance, with a correctly-open licence already sitting right next
to it in the same row (`microsoft/responsible-ai-toolbox-privacy`,
`SecObserve/SecObserve` — both corrected in place). Live `emit_candidates.py`
runs can't produce this particular mismatch (it cross-checks
`reject_category` against `license_class` at write time and errors on the
conflict), so it's specific to the 144 backfilled rows. If you're relying
on `not-open-source` counts for a paper claim, it's worth spot-checking a
sample of the backfilled rows against their own `note` text before citing
the number.

### Built: `licenseid` as a second chance for `tool_metadata`'s auto-collection

`collect_project_metadata.py`'s `license`/`programming_language`
resolution (see its module docstring) gives GitHub's own detector a
second chance via [`bact/licenseid`](https://github.com/bact/licenseid),
but only when GitHub's detection genuinely came up empty or looks
implausible — the full `license` order is `codemeta.json` →
`CITATION.cff` → **GitHub's own detection, if it found one** →
ecosystem package manifests' own clean-SPDX license field → `licenseid`
text-matching Maven's free-text `pom.xml` license name, then the actual
LICENSE file, as the true last resort (and the slowest step by far —
gating it behind every earlier source having already failed matters for
run time as much as correctness). GitHub's detection is checked ahead of
ecosystem manifests, not behind them, since it's free either way
(already fetched for every tool) and reliable when it has an answer —
confirmed on real repos:

- DPV's `CITATION.cff` declares `license: W3C` directly, a real, valid
  SPDX id — resolves authoritatively without `licenseid` ever running.
  (Its `programming_language` gets fixed too now, just differently: `HTML`
  from GitHub's byte-counter is recognized as implausible, triggers a
  manifest check, and correctly resolves to blank — DPV genuinely isn't
  software in any ecosystem this catches. Blank isn't always the most
  *useful* answer even when it's the *correct* one from this chain's
  perspective, which is exactly why "flag suspicious auto-collected
  values for review" in PASS A above still matters.)
- fossology has no such metadata, but GitHub correctly detects
  `GPL-2.0-only` there — while `licenseid`'s own best match against that
  same LICENSE file text is the *wrong* `LGPL-2.1-only` at 0.75
  similarity (plausible-looking, not an obvious miss the way a near-zero
  score is). `licenseid` is a genuine second chance for what everything
  else missed, not a challenger to a source that already answered.
  (fossology's `programming_language` has the same "correct but not
  useful" blank as DPV, for a different reason: it's genuinely PHP+C —
  confirmed via GitHub's own per-language byte breakdown — but predates
  Composer and has no `composer.json` for the chain to find.)

Only trusted at or above an 80% similarity floor — a single trust/no-trust
line, not a "record but flag" middle tier: below 0.8, a match is noise,
not signal, and is discarded outright rather than recorded for later
review — confirmed on real repos, RobustBench and SCLBD/DeepfakeBench
both top-match at 0.07-0.09 similarity to a license that plainly isn't
theirs.

`programming_language` follows the same "trust the free answer first"
principle: GitHub's own guess is used directly whenever it's plausible
(not blank, and not a markup/prose/data language or another confirmed
false-positive case — see NON_IMPLEMENTATION_LANGUAGES in the module
docstring) — zero extra calls for the common case. Only when that trust
is misplaced does the collector spend the extra calls to check every
ecosystem manifest's presence, and **every one found contributes**, not
just the first — genuine polyglot detection (e.g. `Rust; JavaScript` for
a Tauri app), not just a single corrected guess.

**Not yet implemented — the same idea, one layer earlier**, at the Pass B
accept/reject *gate* itself (`search_repos.py`'s `license_spdx_id`,
`licenses.py`'s `classify()`, `emit_candidates.py`'s `not-open-source`
check — see "Rejection tracking & licence classification" above), which
still rests entirely on GitHub's own detector and doesn't consult
`licenseid` at all. A candidate GitHub's detector calls `NOASSERTION` or
"not open source" is rejected as `not-open-source` today even if its
actual LICENSE file text would match a real open license via `licenseid`
— the exact failure mode `collect_project_metadata.py`'s chain now
catches for *already-accepted* tools has no equivalent for *candidates
not yet accepted*. Since `licenseid` is now a real, already-integrated
dependency (not a new one to evaluate), wiring it into this gate is
mostly a matter of *where*, not *whether*: a `search_repos.py` or
`emit_candidates.py` step, run only for repos GitHub's own check didn't
clear, recording the licenseid-matched id as a `tools`-tab override (not
`tool_metadata`, since it came from a different, non-GitHub method) and
flagging it for careful human review — license is a hard inclusion
criterion, not just a display field, so a detector disagreement deserves
a second pair of eyes, not less scrutiny. The `tools`/`tool_metadata`
license-conflict warning in `build.py` already covers the case this would
create, so no further `build.py` work should be needed once it's picked
up.

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

Phase 1 (rounds 1–9) scoped keywords by reading each target RQ's own text
and improvising short phrases from it, one problem area at a time. That
works but is manual and only mines one source of vocabulary. Phase 2 —
started once every RQ range has had at least one real search pass — adds
more systematic keyword sources on top of it, plus three hard-learned
mechanical rules that apply to all of them:

- **Free-text search and metadata search are different *axes*, and
  exhausting one says nothing about the other.** This is the single most
  important lesson of phase 2, learned the expensive way: after ~90
  free-text keyword angles had converged to near-zero new hits, we
  concluded the space was exhausted. It wasn't — it was exhausted *on the
  free-text axis*. A single `topic:ai-safety` query then returned 202
  repos, 98 of them never seen before (see source 0 below). Before
  declaring any area searched out, check that you've tried more than one
  axis: free text, `topic:` tags, and the non-GitHub registries in source
  9. "We ran out of phrasings" is not the same finding as "no tools exist,"
  and only the second one belongs in a paper.
- **GitHub's search API ANDs every unquoted word.** A 4-5 word free-text
  query routinely returns zero hits even when good candidates exist —
  every multi-word query in round 3 with 4+ unquoted words returned 0. Keep
  free-text queries to 2-3 words. Two things measured directly, so nobody
  re-derives them: quoting a phrase made **no difference** to result count
  (`"prompt injection" scanner` and `prompt injection scanner` both
  returned 15), and a literal `AND` between terms is silently **ignored,
  not honoured** (same 15) — so write `foo bar`, never `"foo" AND "bar"`.
  Quoting still costs nothing and is worth keeping for genuinely literal
  patterns like source 2's `"alternative to X"`. `topic:` qualifiers pass
  through `build_query()` untouched and sidestep this rule entirely.
- **Log every keyword regardless of hit count.** A 0-hit query is not
  wasted effort — `search_repos.py` already logs it to `search_log.csv`
  unconditionally, and it's real negative evidence for the paper (which
  phrasings are too narrow for GitHub's index vs. genuinely describe an
  empty space). When a query returns nothing, the fix is to broaden
  (fewer/more common words) not to add more qualifying terms.

The keyword sources, in the order worth trying:

0. **GitHub topic tags (`topic:<tag>`) — do this first.** Topics are
   curated metadata that maintainers self-apply, so they cluster tools by
   *what the tool is for* rather than by whatever words happen to appear in
   its README. This is a fundamentally different axis from free text and by
   far the highest-yield source measured so far. Actual first-run numbers,
   all with the standard `stars:>19 pushed:>…` filters, against a
   253-repo known set:

   | query | total | new |
   | --- | --- | --- |
   | `topic:ai-safety` | 202 | 98 |
   | `topic:llm-security` | 173 | 96 |
   | `topic:explainable-ai` | 131 | 98 |
   | `topic:guardrails` | 116 | 96 |
   | `topic:red-teaming` | 100 | 99 |
   | `topic:ai-governance` | 96 | 92 |
   | `topic:responsible-ai` | 60 | 58 |
   | `topic:ai-ethics` | 11 | 10 |

   For comparison, our best *free-text* queries at the same point returned
   0–30 hits each, mostly already-seen. Note the API caps a page at 100, so
   a topic with `total > 100` needs pagination to mine fully —
   `search_repos.py` currently fetches one page (`per_page=100`), which is
   a known limitation to fix or work around (narrow with an extra term, or
   raise `--min-stars`, to get under 100). Other tags worth trying:
   `machine-learning-security`, `adversarial-machine-learning`,
   `privacy-preserving-ml`, `differential-privacy`, `federated-learning`,
   `fairness-ml`, `interpretability`, `model-evaluation`, `llm-evaluation`,
   `mlops`, `data-provenance`, `deepfake-detection`, `watermarking`,
   `machine-unlearning`, `ai-alignment`, `llmops`, `ai-red-team`,
   `prompt-injection`, `ai-compliance`. Because volume is high and
   precision is lower than a targeted free-text query, treat topic sweeps
   as a *candidate firehose* to run through the normal
   `dedup_candidates.py` → pre-filter → judgment pipeline, not as
   pre-qualified results.
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
   batch-search source. Four sources, layered:
   - [**"The AI Risk Repository: A Comprehensive Meta-Review, Database, and
     Taxonomy of Risks From Artificial Intelligence"**](https://arxiv.org/abs/2408.12622)
     (Slattery et al., 2024) — a causal taxonomy (entity/intentionality/
     timing) plus a domain taxonomy (7 societal-impact domains) over 700+
     risks extracted from 40+ existing frameworks. The primary source, not
     just methodology background for the navigator below.
   - [**airisk.mit.edu/navigator**](https://airisk.mit.edu/navigator#/taxonomies)
     — the browsable web app over the same repository/taxonomy, easier for
     an agent to search interactively than the paper's PDF tables; see
     also the [*Patterns* write-up](https://www.cell.com/patterns/fulltext/S2666-3899(26)00026-7)
     of the repository's ongoing use.
   - [**"A Collaborative, Human-Centred Taxonomy of AI, Algorithmic, and
     Automation Harms"**](https://arxiv.org/abs/2407.01294) (Abercrombie,
     Benbouzid, et al.) — a distinct taxonomy (not the same paper as
     Slattery et al. above, despite the similar subject), built through
     expert consultation and crowdsourced testing to stay legible to a
     broad, non-specialist audience — civil society, educators,
     policymakers, product teams — not just practitioners. Its
     harm-category vocabulary is more accessible/concrete than the
     Repository's, so worth checking both when a target RQ doesn't map
     cleanly onto the Repository's domain taxonomy. This paper has a
     *second*, separate use on this project beyond keyword mining: it's also
     the source taxonomy for the `aiaaic` framework on the live site itself
     (a coverage-completeness check on the RQ catalog, not a search input —
     see `aiaaic_taxonomy_mapping.py` under "Files" below).
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
6. **The matrix: Domain × Artifact × Tool-type.** Rather than improvising
   flat phrases, generate them by combining one term from each of three
   columns — it produces systematic coverage instead of whatever came to
   mind, and makes the *gaps* in what's been tried visible:

   | Domain (the problem) | Artifact (the target) | Tool type (the software) |
   | --- | --- | --- |
   | bias, toxicity, hallucination, prompt injection, privacy leakage, data poisoning, drift, compliance | LLM, foundation model, dataset, RAG, agent, prompt, embedding, model weights | scanner, fuzzer, guardrail, validator, shield, evaluator, auditor, benchmark, monitor, linter |

   Keep the result inside the 2-3 word rule — pick **two** columns, not all
   three (`prompt injection scanner`, `LLM guardrail`, `dataset bias
   evaluator`), since a full three-column combination usually lands at 4+
   words and returns nothing. The tool-type column is the part phase-1
   keywords systematically under-used: we searched problems far more often
   than we searched *software shapes*.

   `keyword_matrix.py` (built) runs this mechanically — a PICOC-style
   generalization to four dimensions (`target`/`action`/`objective`/
   `context`, roughly Population/Intervention/Outcome/Context) instead of
   one fixed three-column table, and it already knows what's been tried:

   ```bash
   python curation/keyword_matrix.py --list-dims
   python curation/keyword_matrix.py --dims target,action --limit 30
   ```

   It cross-checks every generated phrase against `search_log.csv` and by
   default only prints the ones not yet tried (`--show-tried` prints
   everything, commenting out the already-tried ones, to see the *shape* of
   what's been covered). Still combines exactly **two** dimensions per run —
   the script enforces this rather than trusting the caller. Deterministic;
   no model, no network.

   Before spending a real search-and-triage pass on a batch of generated
   phrases, sanity-check their *recall* with a **Quasi-Gold-Standard (QGS)**:
   5-10 repos already known to be relevant (ideally spanning several problem
   areas — ready-made ones are any tool already in the live catalog).
   `validate_qgs.py` (built) runs each candidate keyword and reports which
   QGS repos it actually finds, without touching `search_candidates.csv`:

   ```bash
   python curation/validate_qgs.py \
       --qgs google/magika --qgs IBM/ICX360 --qgs leondz/garak \
       --keyword "LLM guardrail" --keyword "prompt injection scanner"
   ```

   A QGS repo that no keyword in the batch finds is a concrete signal to go
   read *that repo's own README* for the vocabulary it actually uses (source
   1 above), rather than guessing more phrasings blind. Logged to
   `search_log.csv` with a `qgs-validation` note so these calibration probes
   are never mistaken for real discovery runs when computing paper
   statistics (same pattern as the raw-curl calibration probes already in
   the log from round 1). Deterministic; no model; needs `GITHUB_TOKEN`.
7. **Governance sub-domain jargon.** Developers almost never write "AI
   governance" in a README; they write the specific technical term for the
   problem they solved. Vocabulary worth sweeping, by pillar — terms
   already in `search_log.csv` are excluded, so this is the untried
   remainder:
   - *Safety / alignment*: `jailbreak detection`, `hallucination
     detection`, `factuality checker`, `refusal mechanism`, `toxic content
     filter`, `constitutional AI`, `alignment fuzzer`.
   - *Security / robustness*: `backdoor detection`, `data poisoning
     defense`, `evasion attack defense`, `MLSecOps`, `AI BOM`,
     `model extraction defense`.
   - *Privacy / data*: `PII scrubber`, `data anonymization`, `federated
     learning`, `privacy-preserving ML`, `PPML`.
   - *Fairness / bias*: `bias mitigation`, `demographic parity`,
     `disparate impact`, `counterfactual testing`, `representation
     auditing`.
   - *Transparency / accountability*: `mechanistic interpretability`,
     `saliency map`, `concept activation vector`, `data card`, `provenance
     tracking`.
8. **Mine curated "awesome" lists for vocabulary — not for tools.** An
   awesome-list is correctly a `not-a-tool-linklist` **reject** as a
   candidate, but its table of contents is a dense, human-curated glossary
   of exactly the niche terms this section needs (e.g. "concept activation
   vectors"). Feed those terms back in as search keywords. **We already
   have 13 of these logged as rejects in `state/seen_repos.csv`** — filter
   `reject_category == "not-a-tool-linklist"` and mine them; that costs
   zero new searches. Several are directly on-topic for still-thin areas
   (`Awesome-LLM-Watermark`, `Awesome-LLM-Fingerprinting`,
   `awesome-llm-copyright-protection`, three deepfake-detection lists, a
   membership-inference literature list, a model-inversion list). To find
   more: `awesome AI safety`, `awesome LLM security`, `awesome AI
   fairness`, `awesome MLSecOps`.
9. **Backward snowballing (`snowball.py`, built).** A tool's own README
   usually names its closest neighbours in plain prose (forks-from, "similar
   projects", dependency lists, comparison tables) even when its vocabulary
   doesn't overlap with any keyword we'd think to try. `snowball.py` fetches
   a seed repo's README, extracts every `github.com/<owner>/<repo>` link,
   and runs each linked repo through the *same* filters as a real keyword
   search (stars/pushed/archived/fork + README-length) — so a snowballed
   repo has to clear the identical bar, it's just a different source of
   candidates, not a looser one. Seed it from repos already in
   `search_candidates.csv` (`--from-candidates`) or from specific repos
   (`--repo owner/repo`, repeatable). Logs one row per seed to
   `search_log.csv` (`keyword` = `snowball:<seed>`) — a seed whose README
   links to nothing new is real negative evidence, same as a 0-hit keyword.
   Deterministic; no model; needs `GITHUB_TOKEN`.
10. **Non-GitHub registries (`search_registries.py`, built).** Everything
   above searches one index; these surface tools before or instead of GitHub
   prominence. Both registries below have a real public JSON search API (no
   auth, no scraping):
   - **npm** — `registry.npmjs.org`'s official search API. Each hit's
     `repository` field is resolved back to `github.com/owner/repo` and run
     through the exact same filters as `search_repos.py`/`snowball.py`
     (stars/pushed/archived/fork + README length), so an npm-sourced
     candidate clears the identical bar — it's a different index, not a
     looser one. Note the related-but-separate lesson under judgment rules:
     package metadata is also where a licence often lives when GitHub
     reports none.

     ```bash
     python curation/search_registries.py --registry npm --keyword "LLM guardrail"
     ```
   - **Hugging Face** — Spaces and Models, via `huggingface.co/api/{spaces,models}`.
     Most hits aren't mirrored to a top-level GitHub repo, so these are kept
     as their own candidate rows (`full_name` = `hf:<id>`; `stars` = likes,
     a rough popularity proxy; no README-length filter — read the model/space
     card directly at the judgment step instead, the format differs from a
     GitHub README).

     ```bash
     python curation/search_registries.py --registry huggingface-spaces --keyword "fairness"
     python curation/search_registries.py --registry huggingface-models --keyword "toxicity classifier"
     ```
   - **PyPI has no working public search API**, confirmed live: the old
     XML-RPC `search()` method was retired in 2018, and the search *page*
     (`pypi.org/search/?q=...`) returns a bot-detection "Client Challenge"
     page (Fastly), not results, so it can't be scraped either. Use GitHub's
     own search instead (`search_repos.py`, optionally add `language:python`)
     — nearly every PyPI-published tool worth including also has a GitHub
     repo, and classifiers like `Topic :: Scientific/Engineering ::
     Artificial Intelligence` live in that repo's `pyproject.toml`/`setup.py`
     rather than anywhere independently searchable.
   - **arXiv "code available" (`search_arxiv.py`, built)** paired with `LLM
     auditing`, `model evaluation`, `AI governance` — many real tools start
     as a paper artifact (TextAttack, ART). The script queries arXiv's
     public Atom API, pulls every `github.com/owner/repo` link out of each
     hit's abstract/comment field, and runs it through the same filters as
     the other scripts. Judge these against `not-a-tool-paper-artifact`
     extra carefully: the category exists to reject one-off replication
     scripts, *not* maintained tools that happen to have a paper — a repo
     still actively pushed/starred well after the paper's date is
     reasonable evidence it's the latter.

     ```bash
     python curation/search_arxiv.py --keyword "LLM auditing"
     ```

     Couldn't be exercised against a live response from the sandbox this
     was written in (`export.arxiv.org/api/query` timed out every attempt,
     while the bare host and other registries' APIs answered fine) — run it
     once for real and sanity-check the output before relying on it.
   - **General web search (Google/Bing) as an agent-driven step, logged with
     `log_websearch.py` (built).** There's no free, keyless search API to
     script this the way the registries above can be scripted — it has to
     stay an agent using its own WebSearch tool, the way step 3 of the
     pipeline already allows ("can supplement this for blog/paper-surfaced
     tools GitHub search misses"). What was missing was provenance: a web
     search wasn't landing in `search_log.csv` at all, unlike every other
     source here. `log_websearch.py` closes that gap — call it right after
     a WebSearch tool call to log what was searched and how many leads it
     produced (`keyword` prefixed `websearch:` so it's never confused with a
     scripted API hit when computing paper statistics from the log). It does
     **not** touch `search_candidates.csv` — a web search surfaces leads
     (a blog post, a homepage, a link buried in prose), not structured rows
     safe to auto-parse; those still go through the normal pipeline by hand.

     ```bash
     python curation/log_websearch.py --keyword "open source AI incident database" \
         --hit-count 8 --new-leads 2 \
         --note "found aiaaic.org and oecd.ai/en/incidents in top 5 results"
     ```
   - **Papers With Code is dead** — shut down by Meta in July 2025 and
     redirecting to Hugging Face. Use [HF Papers](https://huggingface.co/papers)
     and the archived [`paperswithcode-data`](https://github.com/paperswithcode/paperswithcode-data)
     dump instead; see "Outbound links as judgment signal".

### Starter prompts (for reproducibility)

The two prompts below are what actually kicked off real discovery rounds in
this project, generalized from their original session-specific form (which
named particular tools to re-check, exact round counts, etc.) so someone
else — or a future you — can point a fresh Claude Code session at this repo
and get a *methodologically equivalent* run. "Equivalent" is the honest
word, not "identical": GitHub's index changes daily, so re-running this
won't surface the exact same candidates. What should reproduce is the
*process* — which areas get searched, how candidates get judged, what gets
logged and why — which is what actually matters for a methods section.

#### Phase 1 prompt

```text
Read curation/README.md in full before doing anything else — it's the
methodology doc for this tool-discovery pipeline (the "RQ is the spine"
rule, model tiering, the live sheet schema, and the reject/licence
tracking). Also read docs/data-schema.md for the exact tab/column layout.

The whole pipeline is built and has already been run against live data —
nothing here is a scaffold. Tabs and columns are all lowercase with
underscores: `map`, `tool_map`, `tools`, `terms`, `framework`, plus any
`tools_*_seed` staging tabs. RQ↔tool mappings live in `tool_map`, one row
per (rq_no, tool_id, role) pairing with a free-text rationale — never a
semicolon-list cell.

Do, in order:

1. `pip install -r requirements.txt`
2. Confirm GITHUB_TOKEN is set (`export GITHUB_TOKEN=$(gh auth token)` if I
   use the gh CLI). Shell state doesn't persist between tool calls, so
   re-export it in each Bash call that needs it.
3. `python build.py` (fetches the live sheets directly) then
   `python curation/export_rq_context.py` — refresh rq_context.json against
   the real catalog. Report any build warnings; there should be zero,
   including freshness-column ones (every live row carries datetime_added /
   datetime_checked / datetime_updated).
4. If any staging tab (e.g. `tools_rgaf_seed`) still has untriaged rows,
   fold them into this round rather than leaving them.
5. Pick one problem area from rq_context.json that has thin or zero tool
   coverage, propose 2-3-word search keywords for it (GitHub's search API
   ANDs every unquoted word — longer phrases return zero hits more often
   than not), then run `python curation/search_repos.py --keyword "..."`
   for real. Every keyword tried gets logged to state/search_log.csv
   automatically, hit or not — that provenance log is for a paper, so
   don't skip or hand-edit it.
6. Show me state/search_candidates.csv before going further. I want to see
   real candidate quality and tune the filters (--min-stars /
   --pushed-after-months / --min-readme-chars) if needed.
7. Then continue the pipeline: `dedup_candidates.py` → extract/map
   judgments → `emit_candidates.py`. Stop after emit and show me
   candidate_tools.csv + candidate_map_updates.csv for human review — I
   paste into the sheet myself, you never write to it. (These two files
   accumulate across runs now — clear them back to just their header row
   after I confirm a batch is merged, so the next batch starts clean.)

Judgment rules that matter (details in curation/README.md):
- Map a tool to an RQ by reading its README/paper against that question's
  own text. Never via shared principle/term tags.
- **A tool doesn't need to be built for "AI governance" to legitimately
  answer an RQ -- judge the capability, not the marketing.** Google's
  magika is a general-purpose file-content-type detector built for Gmail/
  Drive/Safe Browsing security routing; it never mentions AI governance,
  datasets, or training data anywhere in its own framing. It's still a
  direct, correct answer to RQ1 (scaling problematic-data identification)
  because content-type detection at 99% precision/recall is exactly the
  capability RQ1 needs, regardless of what the maintainers built it for.
  The practical implication: don't filter candidates by whether they
  self-describe as an AI/governance/safety tool -- a security scanner, a
  file-format detector, a general data-quality library, or a scientific-
  computing tool can all be the right answer if its actual mechanism fits
  the RQ's actual question. This also means free-text keyword search
  anchored on governance vocabulary ("AI safety", "responsible AI", etc.)
  structurally can't find these -- they surface from mapping a tool's
  *mechanism* to an RQ's *need*, which is most of why topic-tag sweeps and
  direct user-suggested leads outperformed keyword search this session.
- Leave `programming_language` blank, same as `license` -- both are
  auto-collected into `tool_metadata` from the GitHub repo API once the
  tool is live and `collect_project_metadata.py` runs (see "tools /
  tool_metadata precedence" in `docs/data-schema.md`), so filling in
  GitHub's own single dominant-by-bytes language by hand here would just
  be a redundant override that blocks future auto-refresh for no benefit.
  Only fill it in when it's a genuine judgment call the collector can't
  make: a real, user-facing second implementation language for a
  genuinely polyglot tool (semicolon-separated, e.g. `Python; Rust` --
  not an incidental scripting/config language mixed into the repo), since
  the auto-collected value is always single-language.
- **`name` is the opposite case -- always fill it in, don't leave it
  blank like `license`/`programming_language`.** It's auto-collected too
  (GitHub's own repo `name` field), but that's frequently an unusable
  slug or an unwieldy literal project-repo name (e.g.
  `www-project-top-10-for-large-language-model-applications` for the
  OWASP LLM Top 10 repo) -- a real display name is exactly the judgment
  call this override exists for, not a redundant echo of what the
  collector already has.
- One tool legitimately answering several RQs is expected, not a smell.
- An RQ with zero tools is a real finding worth reporting, not a search
  failure to paper over by loosening the matching rule.
- Every reject needs a `reject_category` from emit_candidates.py's
  REJECT_CATEGORIES, not just free text.
- A repo with no GitHub-detected LICENSE file is not automatically
  `not-open-source` -- GitHub's license API only checks conventional file
  names/locations, not package-manager metadata. Before rejecting for lack
  of a license, check `pyproject.toml`/`setup.py` (Python), `package.json`
  (npm), `Cargo.toml` (Rust), `*.gemspec` (Ruby), `pom.xml`/`build.gradle`
  (Java/Kotlin) for a license field -- a real license declared only there
  is a common miss.
- A licence GitHub reports as NOASSERTION may just be a detector miss on a
  custom-preamble LICENSE file (check the raw file before assuming it's
  non-standard) -- and a non-OSI licence (e.g. a Creative Commons one) is
  not itself a rejection reason; accept and record it honestly instead.
- When a README is ambiguous, follow its outbound links before judging --
  an arXiv abstract usually states the problem far more precisely than the
  README, and a benchmark/leaderboard entry or real docs site is evidence
  against `low-substance` / `not-a-tool-paper-artifact`. See "Outbound
  links as judgment signal" in curation/README.md. Note that Papers With
  Code shut down in July 2025, so stale PWC badges in a README resolve to
  nothing -- that's not evidence against the tool.

Model tiering: no model inside the scripts; cheaper model for keyword
scoping, summary distillation, and the coarse RQ pre-filter; strongest
model only for the final per-tool implement/eval judgment, as an isolated
subagent given just {summary + README excerpt + pre-filtered RQ shortlist}
— never the whole session history or the full research-question catalog.
If you split a large batch across parallel subagents, synthesize their
results yourself: each one only sees its own slice and will make
locally-true, globally-false claims about RQ coverage.
```

#### Phase 2 prompt

Use once phase 1 has had at least one real pass over every RQ range — see
"Keyword expansion (phase 2)" above for what this adds and why.

Phase 2 applies to **every** RQ, not only the thin ones: a broader keyword
vocabulary can surface a better or complementary tool for a well-covered
question just as easily as a first tool for an empty one. Thin/zero RQs are
worth doing *first* — coverage going 0→1 is unambiguous evidence the
expansion worked, where a 3rd tool on an already-covered RQ is a judgment
call — but they aren't the scope.

Phase 2 also has a second workstream that isn't keyword search at all, and
it exists because of a structural blind spot: `dedup_candidates.py` drops
any candidate already in the `tools` tab, so a search that surfaces an
*already-accepted* tool for a new RQ is silently discarded before judgment.
Every mapping in `tool_map` was therefore created at the single moment its
tool was first accepted, judged only against the area being searched right
then — which is why most tools in the catalog carry exactly one mapping
despite this project's own rule that multi-RQ tools are expected. Re-judging
the existing catalog against the full RQ set needs no search at all and is
probably the highest-yield thing in phase 2.

```text
Read curation/README.md in full, especially the "Keyword expansion (phase
2)" section — it documents 5 keyword sources, plus two mechanical rules
learned the hard way (GitHub's search API ANDs every unquoted word, so keep
free-text queries to 2-3 words; log every keyword including 0-hit ones).

Every RQ range should already have had at least one real search-and-
judgment pass (phase 1). This session is phase 2, which has two separate
workstreams. Do pass A first — it needs no network search and is where the
cheap wins are.

Work in bounded batches either way: one problem area, or ~5-10 RQs, per
batch, stopping for my review after each. Don't try to cover all 97 RQs in
one run.

=== PASS A: re-map the existing catalog (no search) ===

`dedup_candidates.py` drops candidates already in the `tools` tab, so
keyword search structurally cannot find a new RQ for a tool we already
have. Every existing mapping was made when its tool was first accepted,
judged only against the problem area being searched at that moment. So:

Take the tools already in the live catalog and re-judge them against RQs
they are NOT currently mapped to. Prioritise tools currently carrying only
one mapping, and RQs with zero coverage. Use the same judgment rules and
the same model tiering as any other batch — read the tool's README/docs
against the candidate RQ's own text, no forced matches.

**Before reading the README, look up the tool's already-known record** in
`site/data.json`'s top-level `tools` array (keyed by `id`) —
`python3 -c "import json; d=json.load(open('site/data.json')); print(json.dumps(next(t for t in d['tools'] if t['id']=='<id>'), indent=2))"`,
or `jq '.tools[] | select(.id=="<id>")' site/data.json`. This is the
**already-merged view of both `tools` and `tool_metadata`** (every field
from both tabs, resolved through the precedence rule in `docs/data-schema.md`)
— `summary`, `license`, `tool_type`, `programming_languages`,
`development_status`, `paper_url`, and the community-health signals
(`stars`, `contributors`, `last_commit_date`, OpenSSF scores, ...) are all
right there, no separate lookup needed against either sheet. Use it before
spending a README read: an existing `summary` often already answers
whether the tool's mechanism could plausibly fit the candidate RQ, and
`development_status`/`last_commit_date` are relevant judgment context a
README alone won't surface (e.g. a tool that's `unsupported` or hasn't
been pushed to in years is weaker evidence for a `match`, everything else
equal). Fall back to the actual README/docs (via `source`/`documentation`)
only when the recorded summary isn't enough to judge fit against the
specific RQ text — don't skip that step, `site/data.json`'s `summary` was
itself written against a *different* RQ's need originally, and this is
exactly the mismatch Pass A exists to catch.

**While you're looking at that merged record anyway, sanity-check
`license` and `programming_language` for a value that looks wrong, and
override it in `tools` if so.** Both are auto-collected through a fairly
deep priority chain now (`codemeta.json` → `CITATION.cff` → GitHub's own
detection, if plausible → ecosystem package manifests → `licenseid`
text-matching as the true last resort — see
`collect_project_metadata.py`'s docstring), and it self-corrects a lot on
its own: DPV used to resolve `programming_language` as `HTML` (its
rendered spec pages outweigh the actual `.ttl`/`.owl` files in byte
count); the chain now recognizes `HTML` as an implausible answer,
searches for an ecosystem manifest, finds none (correct — DPV isn't
software in any of the ecosystems this catches), and leaves it genuinely
blank instead. But blank isn't always the *most useful* answer even when
it's the *correct* one from this chain's perspective — fossology/fossology
is confirmed genuinely PHP+C (5.9M PHP bytes, 2.5M C, via GitHub's own
per-language byte breakdown), byte-counts as `HTML` for the same
generated-content reason as DPV, and also resolves to blank, because it
predates Composer and has no `composer.json` for the chain to find. Both
cases are "no signal available," not "wrong signal" — the chain can't
tell those apart, and only a human (or AI judge) reading the repo
actually can. A `license` below `licenseid`'s 80% confidence floor is
discarded outright by the collector itself now, not flagged — so there's
nothing to catch in `tools`/`tool_metadata` build warnings for that case;
the sanity-check that matters is a blank or implausible value sitting in
the merged record with nothing to explain it, which is exactly this kind
of read-the-record-anyway judgment call.

**Before picking pairs to check, read `state/pass_a_checked.csv`** and skip
any (tool_id, rq_no) pair already in it, whether its recorded verdict was
`match` or `no_match` — a `tool_map` row alone only tells you what's
*accepted*, not what's already been looked at and ruled out, so without
this file a fresh Pass A run silently redoes the same negative judgments
instead of covering new ground (tools added since the last Pass A run, or
RQs never yet considered for a given tool).

For every RQ actually read against a tool this batch — whether it matched
or not — record it: matches go in `mappings` as normal, and every
non-matching RQ you deliberately ruled out goes in that same judgment's
`checked_no_match` list (plain rq_no, or `{"rq_no": ..., "note": ...}` if
the reasoning is worth a line). `emit_candidates.py` logs both to
`state/pass_a_checked.csv` — this is what makes the next Pass A run able to
skip ground already covered instead of starting from zero every time.

Feed accepted new pairings through `emit_candidates.py` as normal, with a
`repo`/`id` for the *existing* tool and a `mappings` entry for the new RQ —
same judgment-file shape as any other batch. A judgment whose repo is
already in `seen_repos.csv` will be skipped for the seen-log (correct —
it's already logged) but its `mappings` still emit to
`candidate_map_updates.csv`, which is what pass A produces.
`emit_candidates.py` checks `--data-json` (`site/data.json`, default) for
tool ids already live and automatically skips writing a `tools` row for
them — it emits only the new `(rq_no, tool_id, role)` pairing. Run `python
build.py` first each session so that check reflects the current live
sheet, not a stale one.

Also check for tools present in the `tools` tab with no `tool_map` row at
all — those are unreachable from the site's problem pages and are pure
loss.

=== PASS B: expanded keyword search (all RQs, thin ones first) ===

Apply the keyword sources from the README's "Keyword expansion (phase 2)"
section. Source 4 (the RQ's own text) is what phase 1 already used;
everything else is new. **Start with source 0 (`topic:` tag sweeps)** — it
is a different search axis from free text and by far the highest-yield
source measured (a single `topic:ai-safety` query returned 202 repos, 98
unseen; ~650 unseen across 8 tags). Sources 6, 9, and 10 now have scripts,
not just descriptions — use them, don't reinvent the query by hand:
`keyword_matrix.py` (source 6, PICOC-style two-dimension combos, already
cross-checks against `search_log.csv`), `snowball.py` (source 9, backward
snowball from a seed repo's README links), `search_registries.py` (source
10, npm + Hugging Face Spaces/Models), `search_arxiv.py` (source 10, arXiv
abstract/comment link extraction — not yet exercised against a live
response, sanity-check its first real run), `log_websearch.py` (source 10,
provenance logging for an agent-driven WebSearch-tool query, since that
axis has no scriptable API), and `validate_qgs.py` (a pre-flight recall
check against 5-10 known-relevant repos, worth running on a keyword batch
before spending a real search-and-triage pass on it). Sub-domain jargon and
mining already-rejected awesome-lists for vocabulary (the rest of sources 7
and 8) are still manual. Read the "Keyword expansion" section in full
rather than working from this summary. The free-text sources:

1. Mine 2-3 word phrases from the live `tools.summary` /
   `tool_map.rationale` columns that haven't been tried yet (cross-check
   against curation/state/search_log.csv).
2. `"alternative to <name>"` / `"similar to <name>"` as exact quoted
   phrases, where `<name>` is a real product genuinely relevant to the
   target RQ — either a known proprietary tool in that space, or one of
   our own already-accepted OSS tools (to find its competitors/siblings).
   Don't invent placeholder names to fill the pattern.
3. `"open source"` + a named standard/framework/principle we haven't
   searched by yet (e.g. "NIST AI RMF", "ISO 42001", "RGAF") — only worth
   it for standard-anchored tools, not as a blanket prefix.
5. AI risk taxonomies as a keyword *reference*, not a blind batch-search
   source: the MIT AI Risk Repository (https://airisk.mit.edu/navigator#/taxonomies,
   paper https://arxiv.org/abs/2408.12622, Slattery et al. 2024, also
   published in https://www.cell.com/patterns/fulltext/S2666-3899(26)00026-7),
   the distinct "A Collaborative, Human-Centred Taxonomy of AI, Algorithmic,
   and Automation Harms" (https://arxiv.org/abs/2407.01294, Abercrombie,
   Benbouzid, et al. — not the same paper as the Repository above, worth
   checking both since its harm categories are pitched more accessibly),
   and the named Mitigation/Control categories in "Mapping AI Risk
   Mitigations"
   (https://cdn.prod.website-files.com/669550d38372f33552d2516e/6887e58496902e3bcad04a5a_1b0850b4406f7dc6a79365c4b56f0f51_Mapping%20AI%20Risk%20Mitigations.pdf).
   Cross-reference each target RQ against these taxonomies first to find
   the 1-2 most relevant risk/mitigation entries, then derive a short
   keyword from that — don't batch-search the whole taxonomy blind.

Cover every RQ eventually, ordering thin/zero-coverage ones first because
their success is measurable (0→1 coverage is unambiguous). Already-covered
RQs still get a pass — a better or complementary tool is a legitimate find.

=== PASS C: isolated judgment (mandatory, not optional) ===

Don't emit a mapping straight from whatever you concluded inline in this
session. Once you have a shortlist of {candidate, RQ(s)} pairs from pass A
or B, spawn a strongest-model subagent per batch and give it *only*:
the RQ's own text, the candidate's name/summary/README excerpt, and the
shortlist of RQs to judge it against — nothing else about this project or
session. Ask it for an independent MAP yes/no + role + rationale per pair,
and explicitly ask it to disagree with your shortlist if it thinks a
candidate doesn't fit. This isn't belt-and-suspenders: in the run that
established this rule, the isolated pass overturned two inline calls that
looked reasonable in the moment (`ccfingerprint`/`machine-genome` on
RQ57/58/82 — see "Judgment rules" below for the specific mechanism
mismatch). Only feed the isolated pass's verdicts into
`emit_candidates.py`.

=== Steps ===

1. `pip install -r requirements.txt`, then confirm GITHUB_TOKEN is set
   (`export GITHUB_TOKEN=$(gh auth token)` if I use the gh CLI). Shell
   state doesn't persist between tool calls, so re-export it in each Bash
   call that needs it.
2. `python build.py` then `python curation/export_rq_context.py` — refresh
   against the live sheets. Confirm zero build warnings before anything
   else.
3. Record the baseline: per-problem-area coverage counts from
   rq_context.json, plus `python curation/report_triage.py` and
   `python curation/report_triage.py --by keyword` — the second gives the
   per-keyword found/accepted/open-source/rejected table that's the
   paper-relevant write-up data for "which expansion source actually
   worked." Both already read the full accumulated `search_log.csv` /
   `state/seen_repos.csv`, so there's nothing else to hand-maintain for
   this — don't build a separate results log. Re-run both at the end of the
   session and show me the before/after.
4. Run pass A on a bounded batch. Show me the proposed new mappings for
   review before moving on.
5. Run pass B on a bounded batch: propose 2-4 new keywords per area not
   already in curation/state/search_log.csv, run them via
   curation/search_repos.py (or the source-6/9/10 scripts above where they
   fit better than a plain keyword), then show me the real candidate
   quality before judging anything — same review gate as phase 1.
6. Run pass C (isolated judgment) on whatever pass A/B surfaced — see
   "PASS C" above. Don't skip this even for calls that feel obvious inline.
7. Continue the pipeline (dedup_candidates.py → pass C's verdicts →
   emit_candidates.py, passing `--problem-area "..."`). Log rejects too,
   not just accepts — a repo you looked at and dismissed is exactly what
   the "found N, M open source" write-up statistic needs, and skipping it
   silently undercounts `found`. Stop after emit and show me
   candidate_tools.csv + candidate_map_updates.csv for review — I paste
   into the live sheet myself, you never write to it. Those two files
   accumulate across runs; clear them back to just their header row once I
   confirm a batch is merged.

Judgment rules (details in curation/README.md — same as phase 1):
- Map a tool to an RQ by reading its README/paper against that question's
  own text. Never via shared principle/term tags.
- A tool doesn't need to be built for "AI governance" to legitimately
  answer an RQ — judge the capability, not the marketing. Google's magika
  (a general file-content-type detector for Gmail/Drive security routing,
  never mentioning AI or training data) is a correct RQ1 answer purely
  because content-type detection at scale is what RQ1 needs. Don't filter
  candidates by self-description as an AI/safety/governance tool — a
  security scanner, a scientific-computing library, a file-format detector
  can all be right if the mechanism fits. This is also why keyword search
  anchored on governance vocabulary structurally under-performs topic-tag
  sweeps and direct leads for this kind of candidate.
- Leave `programming_language` blank, same as `license` -- both are
  auto-collected into `tool_metadata` from the GitHub repo API once the
  tool is live (see "tools / tool_metadata precedence" in
  `docs/data-schema.md`), so filling in GitHub's own single
  dominant-by-bytes language by hand here is a redundant override that
  blocks future auto-refresh for no benefit. Only fill it in for a
  genuine judgment call the collector can't make: a real, user-facing
  second implementation language for a genuinely polyglot tool
  (semicolon-separated, e.g. `Python; Rust`), since the auto-collected
  value is always single-language. Also worth prioritising a batch of
  `collect_project_metadata.py` against pre-existing tools missing
  project-quality data, since pass A already has you re-reading the live
  catalog.
- **`name` is the opposite case -- always fill it in, don't leave it
  blank like `license`/`programming_language`.** It's auto-collected too
  (GitHub's own repo `name` field), but that's frequently an unusable
  slug or an unwieldy literal project-repo name -- a real display name is
  exactly the judgment call this override exists for.
- One tool legitimately answering several RQs is expected, not a smell.
  This matters more in phase 2 than phase 1 — pass A exists precisely
  because that rule was under-applied when tools were first judged.
- An RQ with zero tools after a real search attempt is a finding worth
  reporting as-is, not a failure to paper over by loosening the matching
  rule. In our own phase-1 run the hardware/compute-verification areas
  (chip specs, anti-tamper hardware, chip location, workload verification,
  compute-usage enforcement) and the pure-policy/forecasting questions
  stayed at zero across many keyword angles. Treat that as a prior to
  verify, not an assumption — but don't force a weak taxonomy-derived
  match just to move the number.
- A subsequent phase-2 run confirmed the hardware/policy prior *and*
  extended it: RQ36/37 (access-continuum research methodology), RQ41 (data-
  access-responsibility allocation), RQ57/58 (proof-of-learning), RQ69
  (data-extraction-attack identification), RQ80 (model-weight infrastructure
  protection), RQ88 (fine-tuning-resistant models) and RQ90 (identity-gated
  dual-use capability) stayed at zero across a dozen+ 2-3 word keyword
  angles each (`proof of learning`, `model weight protection`, `third-party
  model audit`, `memorization detection LLM`, `jailbreak resistant
  fine-tuning`, etc. — see search_log.csv for the full list already tried).
  RQ36 itself is since resolved (`api-police`, mapped `implement`) but the
  rest of that set is still zero. Treat these RQs the same as the
  hardware/policy set: don't re-run the same keyword angles hoping for a
  different answer: try a *genuinely different* angle (a taxonomy term, a
  tool-name-based query) or move on.
- **Important scope correction on both bullets above.** Those zero results
  are established for the **free-text keyword axis only**. They were
  recorded before `topic:` tag search was ever tried, and the first
  `topic:` sweep returned ~650 never-seen repos across 8 tags (see
  "Keyword expansion" source 0). So the correct current statement is "no
  tool found via ~90 free-text keyword angles", **not** "no tool exists" —
  and the paper must say the former until a topic-tag and registry sweep
  has also come back empty for those specific RQs. The hardware/compute
  set may well survive that test, since the productive topic tags are
  safety/security/ethics/XAI-flavoured and unlikely to contain chip-level
  tooling; but that is a prediction to verify, not a result. Do not cite a
  zero-coverage figure as a finding until every RQ behind it has been
  through more than one search axis.
- **A third phase-2 run tested that prediction directly and it held, with
  six exceptions.** Ran Pass A (re-judging the existing catalog) first,
  then topic-tag sweeps (`topic:confidential-computing`,
  `topic:trusted-execution-environment`, `topic:trusted-computing`,
  `topic:sgx`, `topic:hardware-security`, `topic:tpm`), then targeted
  free-text and a registry search (`search_registries.py`), against every
  RQ that was still zero at that point. **Resolved from zero:** RQ35 (an
  HPC-allocation-accounting tool, `xdmod`), RQ50 (three independent
  TEE-attestation implementations), RQ57 (`model-provenance-kit`, already
  in the catalog, re-mapped via Pass A), RQ80 (two infra-level
  confidential-computing tools — a third, `marblerun`, was initially
  accepted here too but reversed on user review for its BUSL-1.1 license;
  see "The one rule that shapes everything" above), RQ88 (`TamperBench`, a purpose-built
  tamper-resistance benchmark), RQ93 (four already-catalogued
  unlearning/model-editing tools, re-mapped via Pass A). **Confirmed still
  zero** after this real multi-axis attempt (not just untested): RQ13–18,
  34, 37, 41, 48/49, 51/52/53, 58, 69, 71–79, 82, 96 — i.e. essentially all
  of chip/firmware/anti-tamper hardware, compute-workload classification,
  export-control enforcement, and the pure-forecasting questions, plus a
  few closely-related software-plausible ones (RQ37/41 access-risk
  allocation, RQ58 spoofing-robust proof-of-learning, RQ69 live
  extraction-attack detection, RQ82 shared model governance) that got a
  real candidate looked at and rejected on mechanism grounds rather than
  never searched. See `state/seen_repos.csv` rows with `problem_area` in
  those areas for the specific rejects and why (e.g. `AIJack` simulates/
  defends against extraction attacks rather than detecting one in
  progress — RQ69's actual ask). **A fourth pass tried the two remaining
  untested axes on this same 27-RQ set and both came back empty too:**
  `snowball.py` off 5 already-accepted hardware/security tools (trustee,
  cmc, dstack, TamperBench, model-provenance-kit) surfaced only generic
  shared dependencies (`huggingface/transformers`, `astral-sh/uv`) or
  sibling infra already in the same genre as an already-covered RQ —
  nothing addressing a new one; and `search_arxiv.py`, exercised live for
  the first time, extracted only ~1 GitHub link per query across 4 queries
  (proof-of-learning, adversarial-spoofing, shared-governance,
  extraction-attack-detection phrasings), none passing the quality filters
  — arXiv abstracts/comments mostly don't carry a paper-specific code link
  at all, which is itself a real, citable low-yield finding about that axis,
  not a search failure. With five independent axes (free-text, topic-tags,
  registries, snowball, arXiv) all empty, RQ13–18, 34, 37, 41, 48/49,
  51/52/53, 58, 69, 71–79, 82, 96 (27 RQs) are as close to a settled
  zero-coverage finding as this pipeline can currently produce — cite it as
  "no open-source tool found across 5 independent discovery axes," not "no
  tool exists." **One concrete methodology finding worth
  citing on its own:** `topic:tpm` is polluted by an acronym collision —
  most of its results are `tmux` "Tmux Plugin Manager" configs, not
  Trusted Platform Module tooling, since both communities use the same
  three-letter tag. A topic tag's precision isn't guaranteed by its name
  alone; skim the actual hits before trusting a sweep's `new_candidates`
  count as a quality signal.
- **Delegate the final RQ mapping judgment to an isolated subagent, per
  "Model tiering" above — don't just reason it inline.** In the same
  session as the finding above, judgment calls made inline (in the main
  agent's full-context turn) were then re-checked by a strongest-model
  subagent given *only* {candidate summary + README excerpt + the specific
  RQ text(s)}, no other session context. The isolated pass **overturned two
  of the inline calls**: `ccfingerprint` and `machine-genome` had been
  provisionally mapped to RQ57/58/82 on "model identity/provenance" keyword
  overlap, but under isolated review neither actually produces the
  evidence those RQs ask for (vendor-substitution detection for an API
  consumer ≠ an owner proving they trained a set of weights; a
  self-asserted signed provenance claim ≠ verified ownership; a lineage
  registry ≠ distributed governance control). This is exactly the
  category-error failure mode this README already warns about elsewhere
  (the garak/RQ89 mistake, ml-privacy-meter/RQ69) — the isolation
  structurally helps catch it, because the subagent has no session-long
  momentum toward "yes" and is handed nothing but the RQ's own text to
  judge against. Treat a same-context inline judgment as a draft, not a
  final verdict; always run the isolated-subagent pass before emitting.
- Every reject needs a `reject_category` from emit_candidates.py's
  REJECT_CATEGORIES, not just free text.
- **A repo with no GitHub-detected LICENSE file is not automatically
  `not-open-source`.** GitHub's repo-level license API only looks at a
  handful of conventional file names/locations (`LICENSE`, `LICENSE.md`,
  etc.) — it does not read package-manager metadata, and a real license is
  routinely declared *only* there. Confirmed twice in one session:
  `Jorwnpay/API-Police` (GitHub: no license; `pyproject.toml`:
  `license = { text = "MIT" }` + an OSI-Approved classifier) and
  `gizatechxyz/LuminAIR` (GitHub: no license; `Cargo.toml`'s
  `[workspace.package]`: `license = "MIT"`). Before rejecting anything as
  `not-open-source` for lacking a detected license, check the
  ecosystem-appropriate metadata file for a license field:
  `pyproject.toml`/`setup.py`/`setup.cfg` (Python), `package.json`
  (npm/Node), `Cargo.toml` — check `[package]` *and* `[workspace.package]`,
  a workspace member can inherit the latter (Rust), `go.mod`'s
  neighbouring `LICENSE*`/module docs (Go modules don't carry license
  metadata inline, but check anyway), `*.gemspec` (Ruby),
  `pom.xml`/`build.gradle` (Java/Kotlin). Only reject as `not-open-source`
  once none of these — nor the raw repo — declares a license.
- A licence GitHub reports as NOASSERTION may just be a detector miss on a
  custom-preamble LICENSE file (check the raw file before assuming it's
  non-standard) — and a non-OSI licence (e.g. a Creative Commons one) is
  not itself a rejection reason; accept and record it honestly instead.
- When a README is ambiguous, follow its outbound links before judging —
  an arXiv abstract usually states the problem far more precisely than the
  README, and a benchmark/leaderboard entry or real docs site is evidence
  against `low-substance` / `not-a-tool-paper-artifact`. See "Outbound
  links as judgment signal" in curation/README.md. Note that Papers With
  Code shut down in July 2025, so stale PWC badges in a README resolve to
  nothing — that's not evidence against the tool. This matters more in
  pass A than pass B: re-judging an existing tool against a *new* RQ is
  exactly the case where the README's headline framing (written for its
  original use case) is least likely to settle the question on its own.

Model tiering per the README: no model in the scripts; cheaper model for
keyword scoping and the coarse RQ pre-filter; strongest model only for the
final per-tool implement/eval judgment, as an isolated subagent given just
{tool summary + README excerpt + pre-filtered RQ shortlist} — never the
whole session history or the full RQ catalog. If you split a batch across
parallel subagents, synthesize their results yourself: each only sees its
own slice and will make locally-true, globally-false claims about coverage.
```

## Prior art: CHAOSS

The project-quality/community-health columns (`stars` through
`openssf_scorecard_vulnerabilities` in the `tools` tab — see
`docs/data-schema.md`) were designed independently, then checked against
[CHAOSS](https://chaoss.community/) (Community Health Analytics in Open
Source Software, a Linux Foundation project) after the fact — noted here as
prior art, since CHAOSS is the closest thing this space has to a standards
body for exactly this question. Their knowledge base indexes
[89 individual metrics](https://www.chaoss.community/kbtopic/all-metrics/)
and [17 metrics models](https://www.chaoss.community/kbtopic/all-metrics-models/)
(combinations of metrics answering a broader question, e.g. "OSS Project
Viability: Governance", "Starter Project Health", "Safety"). Their metric
definitions live as markdown files across several working-group repos —
`chaoss/wg-risk` (focus areas: `security`, `transparency`, `business-risk`,
`dependency-risk-assessment`, `code-quality`, `licensing`) is the most
relevant one to this catalog's purpose.
[`chaoss/collectoss`](https://github.com/chaoss/collectoss) is their
reference *collection* tool (Python, PostgreSQL-backed, Docker-distributed)
for gathering the raw forge data those metrics are computed from —
architecturally a different approach from `collect_project_metadata.py`
(a relational warehouse ingesting full history across many repos, vs. a
one-shot per-tool snapshot into a spreadsheet), but the same underlying
data sources.

**What's already CHAOSS-aligned**, i.e. names or near-equivalents to a
named CHAOSS metric, confirmed by reading the actual metric definitions
rather than assumed from the name alone:

| This catalog's column | CHAOSS metric | Note |
| --- | --- | --- |
| `openssf_best_practices_url`/`_badge_level` | [OpenSSF Best Practices Badge](https://www.chaoss.community/kb/metric-openssf-best-practices-badge/) | exact match — CHAOSS names this metric directly |
| `sbom_url` | [SPDX Document](https://www.chaoss.community/kbtopic/all-metrics/) | exact match in spirit; CHAOSS's version isn't GitHub-specific |
| `programming_language` | Programming Language Distribution | same idea; CHAOSS's is repo-wide byte-proportion, ours is GitHub's single dominant language (see `collect_project_metadata.py`'s docstring) |
| `contributors` | [Contributors](https://www.chaoss.community/kbtopic/all-metrics/) | same idea, cruder implementation — see the gap below |
| `forks` | [Technical Fork](https://www.chaoss.community/kb/metric-technical-fork/) | CHAOSS's definition is platform-agnostic ("independent copies... on code development platforms"); ours is specifically GitHub's fork-button count |
| `license_url`/`license` | Licenses Declared / OSI Approved Licenses / License Coverage | we already do more here than a single column suggests — `licenses.py`'s OSI/FSF classification (see "Rejection tracking & licence classification") predates this comparison and is closer to CHAOSS's three-metric split than to a single field |
| `code_of_conduct_url` | Code of Conduct for a Project | exact match |
| `readme_url` | Documentation Discoverability | related, narrower (existence + location, not discoverability/quality) |
| `funding`/`funder` | Sponsorship, and the *Funding* metrics model | related; CHAOSS's model is broader (impact of funding, not just presence) |
| `paper_url` | Academic Open Source Project Impact | related, narrower (presence of a citable paper, not impact) |

**What CHAOSS defines that this catalog doesn't have** — candidates for a
future round, roughly in order of how directly they'd improve on something
we already collect cheaply:

- **[Contributor Absence Factor](https://www.chaoss.community/kb/metric-contributor-absence-factor/)**
  (née "Bus Factor") — the minimum number of contributors responsible for
  50% of all contributions, computed from per-contributor commit counts
  (`GET /repos/{owner}/{repo}/stats/contributors`). Strictly more
  informative than our current `contributors` (a raw headcount that treats
  a drive-by one-line fix the same as a maintainer with 40% of all
  commits) for the exact question this catalog cares about — is a tool a
  one-person project that could vanish.
- **Elephant Factor** — the organizational analogue: minimum number of
  *organizations* (not individuals) responsible for 50% of contributions.
  Needs contributor→employer mapping, which GitHub doesn't expose
  directly; harder to collect than Contributor Absence Factor.
- **Libyears** — average age, in years, of a project's dependencies
  relative to their latest available version; a supply-chain-staleness
  signal distinct from anything currently collected. Needs a dependency
  manifest + registry lookups per ecosystem (PyPI/npm/crates.io/...), more
  work than anything else in this table.
- **Time to First Response / Issue Resolution Duration / Review Cycle
  Duration** — responsiveness metrics from issue/PR timestamps. We collect
  `open_issues_count` (a snapshot) but nothing about how fast issues
  actually get addressed.
- **Test Coverage** — no general cross-language API for this (would need
  a CI-provider-specific integration, e.g. Codecov/Coveralls badges, not a
  single GitHub call), which is likely why it's absent here.
- **Bot Activity** — CHAOSS explicitly flags filtering bot commits/issues
  before computing other metrics; our `contributors`/`open_issues_count`
  don't currently exclude bots, a real accuracy gap worth noting even
  before adopting Contributor Absence Factor.

None of the above are implemented — this section is the "note it as prior
art" this catalog owes CHAOSS, plus a concrete starting list if a future
round wants to close the gap with their more rigorous definitions rather
than reinventing similar-but-less-precise ones from scratch.

**Deferred decision, not acted on**: whether to compute the gap-list
metrics above ourselves (extending `collect_project_metadata.py`, more
GitHub API calls) or pull some/all of them from an existing third-party
API instead. Checked two real candidates rather than assuming:

- **CHAOSS's own Augur** (their former hosted metrics platform) is
  deprecated — its repo now reads "no longer part of CHAOSS, use
  CollectOSS instead." Not usable as a hosted API; `collectoss` above is
  the only route into CHAOSS's own metric computations, and that's a
  self-hosted warehouse, not a query-able public endpoint.
- **[ecosyste.ms](https://ecosyste.ms/)** (`repos.ecosyste.ms`,
  `packages.ecosyste.ms`) is a real, public, no-auth-needed aggregator API
  that already surfaces a lot of overlapping ground in one call per repo:
  stars/forks/subscribers/open_issues, a `funding` field already resolved
  from `.github/FUNDING.yml`, a `metadata` block noting which of
  README/CHANGELOG/CONTRIBUTING/LICENSE/CITATION/SECURITY/codemeta.json
  exist, and even an embedded `scorecard` field — confirmed against a
  real catalogued tool's repo (`repos.ecosyste.ms/api/v1/hosts/GitHub/
  repositories/PyThaiNLP%2Fpythainlp`), not assumed from their docs. Their
  `packages.ecosyste.ms` side (per-registry package metadata — PyPI, npm,
  crates.io, ...) was also checked for a `dependents_count` answer (the
  one column this catalog deliberately left manual-only, no GitHub API
  existing for it) — no explicit dependent-count field surfaced in the
  single package looked up, so that specific gap isn't obviously solved by
  switching, but worth a closer look if this gets picked up later.

If this ever gets picked up: ecosyste.ms could plausibly *replace* several
of `collect_project_metadata.py`'s direct-to-GitHub calls (fewer requests
per tool, someone else's infrastructure absorbing the GitHub API budget)
rather than only adding new columns on top — worth weighing against the
loss of direct control over collection timing/logic before committing
either way.

## Setup

Base setup (clone, `pip install -r requirements.txt`) is in
[`docs/development.md`](../docs/development.md). Curation additionally
needs a GitHub token, since `search_repos.py` hits the real GitHub Search
API:

```bash
export GITHUB_TOKEN=<a personal access token, no special scopes needed —
                      `gh auth token` works if you use the gh CLI>
```

Shell state doesn't persist between separate tool-call invocations in an
agent session, so re-export it in each one that runs a curation script.
`search_repos.py --help` documents its flags (`--min-stars`,
`--pushed-after-months`, `--min-readme-chars` are all overridable if the
defaults need adjusting after seeing real results).

`collect_project_metadata.py` additionally needs a one-time local setup
step for `license` resolution (see its module docstring's "license /
programming_language" bullet for the full priority chain this feeds into):

```bash
licenseid update
```

Downloads the SPDX license list and builds a local SQLite similarity
index at `~/.local/share/licenseid/licenses.db` (or wherever
[`bact/licenseid`](https://github.com/bact/licenseid) puts it on your
platform) — takes a few seconds, no ongoing maintenance beyond an
occasional `licenseid update --force` to pick up new SPDX license-list
releases. Not required to run the script at all — without it, license
resolution just skips straight to GitHub's own (weaker) detection for any
repo `codemeta.json`/the ecosystem manifests don't already answer, with a
single warning printed once per run rather than a hard failure.

### Live sheet schema (current)

Quick recap for curation work — see [`docs/data-schema.md`](../docs/data-schema.md)
for the full column-by-column reference. All tab and column names are
lowercase with underscores. Six sources, across **two spreadsheets**
(five tabs in `OpenTAIG`, plus the separate `tool_metadata` spreadsheet —
see "`tools` / `tool_metadata` precedence" in `docs/data-schema.md`), are
owned by this pipeline, each carrying the three freshness columns above:

- **`map`** — `rq_no` + one column per framework (`rgaf`, `euaiact`,
  `unescoai`, `aseanai`, `coeai`, `aiaaic`) + freshness columns. `aiaaic` is our
  own coverage-completeness mapping against the AIAAIC Harms
  Taxonomy, not a crosswalk to an external authority's text like the other
  five — see `emit_aiaaic_framework.py` below and
  [`docs/methodology-and-findings.md`](../docs/methodology-and-findings.md)
  § Findings, F6.
- **`tool_map`** — `rq_no, tool_id, role, rationale` + freshness columns.
  One row per `(rq_no, tool_id, role)` pairing.
- **`tools`** (in `OpenTAIG`) — `id, tool_type, summary, homepage, source,
  documentation` + freshness columns, **plus every judgment-vs-collection
  field also present in `tool_metadata`** (`name, license,
  programming_language, funding, funder, stars, forks, watchers,
  contributors, open_issues_count, releases_count, latest_release_date,
  last_commit_date, readme_url, license_url, code_of_conduct_url,
  contributing_url, security_policy_url, governance_url, sbom_url,
  dependents_count, development_status, paper_url, software_heritage_id,
  openssf_best_practices_url, openssf_best_practices_badge_level,
  openssf_scorecard_url, openssf_scorecard_score,
  openssf_scorecard_branch_protection, openssf_scorecard_code_review,
  openssf_scorecard_maintained, openssf_scorecard_vulnerabilities`) — but
  as an **optional human-or-AI-judgment override**, not the primary source:
  a non-blank cell here always wins; the literal text `none`
  (case-insensitive) forces blank instead of falling through; a truly empty
  cell falls through to `tool_metadata`'s collected value. `name` and
  `license` look like fixed identity fields but are collected from the
  GitHub API too (a repo's own name is often an unusable slug) — same
  precedence as the rest of this list, not a straight `tools`-only read.
  `dependents_count` is the one field with nothing to fall through to
  (never auto-collected — no public API for GitHub's dependency-graph
  count), so it always resolves to whatever is here. Never written to by
  any script.
- **`tool_metadata`** (its own spreadsheet) — `id, source` (the latter
  purely for a human skimming the sheet; `build.py` ignores it — a tool's
  `source` always comes from `tools`, since that's how this script finds
  the repo to collect from) + the same judgment-vs-collection field list as
  above (including `name`), minus `dependents_count`. 100% written by
  `collect_project_metadata.py`, safe to bulk-overwrite on every run — no
  hand edit is ever expected here, so there's nothing a collection run
  could clobber. `build.py` warns at build time if `tools` and
  `tool_metadata` disagree on `license` — a hard inclusion criterion, not
  just a display field, so a detector disagreement is worth a second look
  even though the `tools` override still wins. **Has fewer rows than
  `tools` whenever a tool's `source` isn't a resolvable GitHub URL** — not
  a bug, and expect the gap to widen for now as discovery expands beyond
  GitHub (arXiv, other forges, ...). Not necessarily permanent — see
  "Prior art: CHAOSS" above for ecosyste.ms, an aggregator API that could
  plausibly fill this back in for non-GitHub sources it indexes, if a
  future collector gets built against it — see
  `collect_project_metadata.py`'s docstring.
- **`terms`** — `id, framework_id, name, summary, url` + freshness columns.
- **`framework`** — `id, name, fullname, summary, homepage, source, group`
  + freshness columns.

`tools_rgaf_seed` is a staging-only tab (not read by `build.py`) holding
the 32 tools sourced from the LF AI & Data RGAF blog post. All 32 have now
been triaged (accepted into `tools`/`tool_map`, or rejected) — see
`state/seen_repos.csv` rows with `problem_area=rgaf-seed-triage`.

## Files

- **`export_rq_context.py`** — built. Reshapes a local `site/data.json`
  into `rq_context.json`. Deterministic; no model, no network.
- **`search_repos.py`** — built. Real GitHub Search API + README-length
  filter, plus a `state/search_log.csv` provenance log (every keyword tried,
  exact query, hit counts — kept for methodology/paper documentation, not
  just the surviving candidates). Deterministic; no model; needs
  `GITHUB_TOKEN` + unrestricted network (see "Setup" above).
- **`dedup_candidates.py`** — built. Drops candidates already live in
  `tools` (matched by GitHub repo path) or already judged in
  `state/seen_repos.csv`. Deterministic; no model, no network. Writes
  `state/candidates_to_review.csv` (git-ignored, regenerated each run).
- **`emit_candidates.py`** — built. Takes a judgments JSON (step 4+5 output)
  and appends to `candidate_tools.csv` + `candidate_map_updates.csv` (each
  row stamped with `datetime_added`/`datetime_checked`/`datetime_updated`
  set to the run time; deduplicated across runs so re-running or running
  several batches in a session accumulates rather than clobbers). A `tools`
  row is skipped automatically (via `--data-json`, default `site/data.json`)
  when the tool's `id` is already live — this is what makes pass-A safe:
  re-mapping an already-accepted tool onto a new RQ emits only the new
  `tool_map` row, never a duplicate `tools` row. Run `python build.py`
  before emitting so that check is current. It also appends every judged
  repo (accept or reject) to `state/seen_repos.csv`,
  with a validated `reject_category` and licence classification — see
  "Rejection tracking & licence classification" above. A judgment can also
  carry a `checked_no_match` list (RQs read against this tool and ruled
  out, alongside the `mappings` it did match) — both get logged to
  `state/pass_a_checked.csv` (`tool_id, rq_no, verdict, note,
  timestamp_utc`), the only record of a *negative* Pass A result, since
  `tool_map` only ever holds accepted mappings. Deduplicated on
  `(tool_id, rq_no)`. Never pasted into the sheet — process data, like
  `seen_repos.csv`. Deterministic; no model, no network.
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
- **`collect_project_metadata.py`** — built. Writes every project-quality/
  community-health field, unconditionally, to `tool_metadata` (full list
  in `docs/data-schema.md`; source-by-source detail is in the script's own
  docstring, not duplicated here). Since `tool_metadata` is 100%
  machine-owned (see "`tools`/`tool_metadata` precedence" above -- any
  hand override always lives in `tools` instead, never here), this script
  never has to check "is this already curated" before writing; that's
  resolved later, by `build.py`, not at collection time. Folds in what
  used to be a separate script, `backfill_programming_language.py`
  (removed) -- `programming_language` comes free from the same repo-core
  API call already made for stars/forks/etc. Pulls from GitHub REST (repo
  core, contributors, releases, community profile, well-known-path probes
  for security/governance files, the auto-generated dependency-graph SBOM
  endpoint, and raw-content reads of `.github/FUNDING.yml`,
  `pyproject.toml`, `codemeta.json`, `CITATION.cff`), plus the public
  bestpractices.dev / api.scorecard.dev APIs (unauthenticated, so the
  GitHub token is never sent to them). NOT `dependents_count`, which has
  no public API and is deliberately not scraped -- that one's `tools`-only.
  Writes `state/tool_metadata.csv`, safe to paste in as a **full
  replacement** of the tab's contents, not a cell-by-cell merge (nothing
  there is ever hand-edited). Defaults to tools missing `stars` (i.e.
  never collected); pass `--refresh-all` to re-collect the volatile fields
  (star counts, release counts, Scorecard score, etc.) for everything.
  Interruption-safe for a full ~130-tool run: prints the GitHub core rate
  limit and a worst-case call estimate before starting, re-checks every 20
  tools and stops early below 100 remaining, writes and flushes each row
  immediately rather than batching to the end, and skips ids already in
  `--out` on a re-run (`--restart` to ignore that checkpoint and also drop
  rows for tools removed from the catalog since the last run; `--limit N`
  for a deliberately small batch) -- so a rate limit, network blip, or
  Ctrl-C loses at most one row, not the whole run. Two real quirks it
  defends against, both confirmed against live data before being handled
  rather than assumed from docs: GitHub's community-profile API can
  return a `license_url` pointing at an unrelated file when its own
  license detector returns `NOASSERTION` — same blind spot as F3 in
  `docs/methodology-and-findings.md`, just hitting a different field; and
  OpenSSF Scorecard's per-check score of `-1` means "could not evaluate,"
  not "worst score." GitHub-only for now; GitLab/Codeberg would need
  their own fetch functions, not built speculatively since no catalogued
  tool is hosted there yet. Needs `GITHUB_TOKEN` + network; no model.
- **`keyword_matrix.py`** — built. PICOC-style keyword generator over four
  dimensions (target/action/objective/context); prints two-dimension combos
  not already in `state/search_log.csv`. See "Keyword expansion" source 6.
  Deterministic; no model, no network.
- **`snowball.py`** — built. Backward snowballing: extracts `github.com/...`
  links from a seed repo's README and runs each through the same
  stars/pushed/archived/fork + README-length filters as `search_repos.py`,
  reusing its functions directly. See "Keyword expansion" source 9.
  Deterministic; no model; needs `GITHUB_TOKEN`.
- **`validate_qgs.py`** — built. Quasi-Gold-Standard recall check: runs a
  batch of candidate keywords and reports which of a known-relevant repo set
  each one actually finds, before spending a real triage pass on them. Never
  writes to `search_candidates.csv`. See "Keyword expansion" source 6.
  Deterministic; no model; needs `GITHUB_TOKEN`.
- **`search_registries.py`** — built. Non-GitHub registry search: npm (via
  the official search API, resolved back to a GitHub repo and filtered
  identically to `search_repos.py`) and Hugging Face Spaces/Models (kept as
  their own candidate rows, `full_name` = `hf:<id>`). See "Keyword
  expansion" source 10. Deterministic; no model; needs `GITHUB_TOKEN` for
  the npm path only.
- **`search_arxiv.py`** — built. arXiv Atom API search, extracting
  `github.com/...` links from each hit's abstract/comment and resolving
  them through the same filters as `search_repos.py`. See "Keyword
  expansion" source 10. Deterministic; no model; needs `GITHUB_TOKEN`.
  Not yet exercised against a live arXiv response — see the script's own
  docstring.
- **`log_websearch.py`** — built. Appends one provenance row to
  `state/search_log.csv` for an agent-driven WebSearch-tool query
  (`keyword` prefixed `websearch:`); doesn't touch
  `state/search_candidates.csv` since web-search leads need manual
  judgment, not auto-parsing. See "Keyword expansion" source 10.
  Deterministic; no model, no network.
- **`report_triage.py`** — built. Reads `state/seen_repos.csv` and prints
  found/accepted/open-source/rejected counts by problem area (or keyword),
  plus breakdowns by reject category and licence class. Deterministic; no
  model, no network.
- **`backfill_triage_columns.py`** — one-time migration, already run; kept
  for auditability. See "Rejection tracking & licence classification" above.
- **`aiaaic_taxonomy_mapping.py`** — the question→harm mapping for the
  AIAAIC Harms Taxonomy coverage-completeness check, as reviewable
  Python data (a `MAPPING` dict, one entry per RQ, each with the harm
  type(s), whether the RQ *directly* addresses them or only *enables*
  addressing them, and a free-text note for the judgment-call rows). Running
  it also prints the harm-type coverage table and the list of the taxonomy's
  69 specific harms with no RQ addressing them. Deterministic; no model, no
  network — but the `MAPPING` data itself is agent-produced editorial
  judgment, not derived from anything; see limitations in
  [`docs/methodology-and-findings.md`](../docs/methodology-and-findings.md).
  Writes `aiaaic_taxonomy_mapping.csv` (**committed** — the citable, one-row-
  per-RQ artifact referenced by the methodology doc, unlike the
  `candidate_*_aiaaic.csv` files below).
- **`emit_aiaaic_framework.py`** — one-time, already run (results merged into
  the live sheet 2026-07-29); kept in case the mapping or RQ catalog changes
  and the `aiaaic` framework's live-sheet rows need re-pasting. Reads
  `aiaaic_taxonomy_mapping.py`'s `MAPPING` and config.yaml's column headers to
  emit `candidate_framework_aiaaic.csv` / `candidate_terms_aiaaic.csv` /
  `candidate_map_aiaaic.csv` — pasteable rows for the `framework`/`terms`/`map`
  tabs, in the same shape as `emit_candidates.py`'s output but for a
  framework, not a tool. These three are **git-ignored**, not committed:
  unlike `candidate_tools.csv`, they carry no judgment of their own, only a
  deterministic projection of `aiaaic_taxonomy_mapping.py`'s data — delete and
  re-run any time. `--granularity specific` emits all 69 specific harms
  instead of the 9 top-level types (not recommended for publishing without
  re-reviewing each row — see the script's own docstring).
- **`candidate_tools_from_rgaf.csv`** — removed (was a pre-triage snapshot of
  the original 32 tools from the sheet's `tools_rgaf_seed` staging tab,
  seeded from the LF AI & Data blog post ["Putting RGAF to Work"](https://lfaidata.foundation/communityblog/2026/04/22/putting-rgaf-to-work-build-and-audit-responsible-ai-with-open-source/)).
  All 32 have since been triaged directly in the live `tools_rgaf_seed` tab
  (see "Live sheet schema" above), and the same information is preserved,
  correctly and non-stale, in `state/seen_repos.csv` rows with
  `problem_area=rgaf-seed-triage` — that snapshot was fully redundant with
  it and read by no script.
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
  `emit_candidates.py` (step 7). **Appended across runs**, not overwritten
  (deduplicated on `id` / `(rq_no, tool_id, role)`), so several batches in
  one session accumulate into these two files and a human only has to
  paste each one once. After merging accepted rows into the live sheet,
  **clear both files back to just their header row** so the next batch
  starts from a clean "pending review" list -- `state/seen_repos.csv` is
  what actually prevents a merged tool being re-proposed, not these.

## Automation (later)

Once the on-demand pipeline is proven on a problem area, steps 1–7 can be
wrapped in a scheduled agent that opens a candidate PR each period —
preferably a scheduled Routine in the Claude environment (no repo secret
needed), or a GitHub Actions + Claude Code Action job (needs an
`ANTHROPIC_API_KEY` secret, open-internet runner). Each run should handle a
bounded slice of questions to cap cost and keep the review PR small.
