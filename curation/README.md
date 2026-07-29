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
     cleanly onto the Repository's domain taxonomy.
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
9. **Non-GitHub registries.** Everything above searches one index; these
   surface tools before or instead of GitHub prominence:
   - **PyPI / npm** — package metadata carries classifiers (e.g. `Topic ::
     Scientific/Engineering :: Artificial Intelligence`) that can be
     combined with keywords like `auditor`, `privacy`, `guardrail`. Note
     the related-but-separate lesson under judgment rules: package metadata
     is also where a licence often lives when GitHub reports none.
   - **Hugging Face** — Spaces, and `evaluate`-library metric modules,
     searched by `fairness`, `robustness`, `toxicity`. Catches tools
     shipped as a Space or metric rather than a repo.
   - **arXiv "code available"** paired with `LLM auditing`, `model
     evaluation`, `AI governance` — many real tools start as a paper
     artifact (TextAttack, ART). Judge these against
     `not-a-tool-paper-artifact` carefully: the category exists to reject
     one-off replication scripts, *not* maintained tools that happen to
     have a paper.
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
unseen; ~650 unseen across 8 tags). Sources 6-9 (the Domain×Artifact×Tool
matrix, sub-domain jargon, mining already-rejected awesome-lists for
vocabulary, and non-GitHub registries) are also new and largely untried.
Read that section in full rather than working from this summary. The
free-text sources:

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

=== Steps ===

1. `pip install -r requirements.txt`, then confirm GITHUB_TOKEN is set
   (`export GITHUB_TOKEN=$(gh auth token)` if I use the gh CLI). Shell
   state doesn't persist between tool calls, so re-export it in each Bash
   call that needs it.
2. `python build.py` then `python curation/export_rq_context.py` — refresh
   against the live sheets. Confirm zero build warnings before anything
   else.
3. Record the baseline: per-problem-area coverage counts from
   rq_context.json, plus `python curation/report_triage.py`. Re-run both at
   the end of the session and show me the before/after — measuring whether
   the expanded strategy actually moved coverage is the point of phase 2,
   and the delta is paper-relevant.
4. Run pass A on a bounded batch. Show me the proposed new mappings for
   review before moving on.
5. Run pass B on a bounded batch: propose 2-4 new keywords per area not
   already in curation/state/search_log.csv, run them via
   curation/search_repos.py, then show me the real candidate quality before
   judging anything — same review gate as phase 1.
6. Continue the pipeline (dedup_candidates.py → judgment →
   emit_candidates.py, passing `--problem-area "..."`). Stop after emit and
   show me candidate_tools.csv + candidate_map_updates.csv for review — I
   paste into the live sheet myself, you never write to it. Those two files
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

### Live sheet schema (current)

Quick recap for curation work — see [`docs/data-schema.md`](../docs/data-schema.md)
for the full column-by-column reference. All tab and column names are
lowercase with underscores. Five tabs are owned by this pipeline, each
carrying the three freshness columns above:

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
  "Rejection tracking & licence classification" above. Deterministic; no
  model, no network.
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
- **`candidate_tools_from_rgaf.csv`** — historical snapshot only: the
  original 32 tools pulled from the sheet's `tools_rgaf_seed` staging tab
  (seeded from the LF AI & Data blog post ["Putting RGAF to Work"](https://lfaidata.foundation/communityblog/2026/04/22/putting-rgaf-to-work-build-and-audit-responsible-ai-with-open-source/)),
  before triage. All 32 have since been triaged directly in the live
  `tools_rgaf_seed` tab (see "Live sheet schema" above) — this file was
  never updated to reflect that and is kept only as a record of the
  starting batch, not a to-do list.
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
