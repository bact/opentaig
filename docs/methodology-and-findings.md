# OpenTAIG: Methodology and Findings

How the tool catalog was built, what it found, and — more usefully — where it
found nothing and why. Written as the record behind the site, and as a source
for writing up the work.

Snapshot: **97 research questions, 126 tools, 1,618 repositories judged.**
Operational detail (scripts, schemas, judgment rules, starter prompts) lives in
[`curation/README.md`](../curation/README.md); this document covers method and
results.

---

## 1. Scope and framing

The spine is the 97 open research questions from Reuel, Bucknall et al. (2025),
*Open Problems in Technical AI Governance*. The task: for each question, find
open-source tools that help **implement** a solution or **evaluate/audit** one.

Two commitments shaped everything:

1. **The question is the unit of analysis, not the theme.** A tool is mapped to
   a question by reading its README/paper against *that question's own text* —
   never by matching shared principle tags or topic labels. This is slower and
   yields fewer mappings than tag-matching, but a mapping means something.
2. **Absence is a result.** A question with no tool after genuine search effort
   is a finding to report, not a gap to paper over by relaxing the matching
   rule. Most of the interesting output of this project is negative.

---

## 2. Method

### 2.1 Pipeline

Search → dedup → judge → emit → human review → merge. Deterministic scripts do
search, dedup, and emit; judgment is model-driven; **every acceptance passes a
human review gate** before entering the live dataset. Scripts never write to the
live sheet.

### 2.2 Search: two axes, not one

Candidate discovery used two structurally different axes:

| Axis | Queries | Character |
| --- | --- | --- |
| Free-text keyword | 223 distinct | precise, low-yield, vocabulary-dependent |
| GitHub `topic:` tags | 25 distinct | high-volume, curated maintainer metadata |

261 keyword runs total; **137 (52%) returned zero hits** and are logged anyway —
a zero-hit query is evidence about the vocabulary, not wasted effort.

Free-text keywords were derived from: the RQ's own text; phrases mined from
already-accepted tools' summaries; `"alternative to X"` patterns; named
standards (NIST AI RMF, ISO 42001); and the MIT AI Risk Mitigations taxonomy.

#### Worked examples, by source (pulled from `curation/state/search_log.csv`)

Every query ever run is logged with its raw hit count and how many passed the
README-length filter as new candidates — including the zero-hit ones. A sample
across sources (full taxonomy of sources in
[`curation/README.md`](../curation/README.md) § Keyword expansion):

| Source | Example query | Raw hits | New candidates |
| --- | --- | ---: | ---: |
| RQ text (naive, 4-word AND) | `dataset license scanner` | 0 | 0 |
| RQ text (narrowed, 2-word) | `dataset license` | 6 | 6 |
| RQ text (narrowed, 2-word) | `PII detection` | 16 | 16 |
| Mined from accepted tools | `model fingerprinting` | 12 | 11 |
| Mined from accepted tools | `zkml` | 9 | 9 |
| `"alternative to X"` | `alternative to presidio` | 0 | 0 |
| `"alternative to X"` | `alternative to opsml` | 0 | 0 |
| `"similar to X"` | `similar to codecarbon` | 0 | 0 |
| Standard-anchored | `open source NIST AI RMF` | 2 | 2 |
| Standard-anchored | `ISO 42001 implementation` | 1 | 1 |
| Mitigation-taxonomy-derived | `tiered model access` | 3 | 1 |
| Mitigation-taxonomy-derived | `KYC verification API` | 3 | 2 |
| Mitigation-taxonomy-derived | `model weight tracking` | 0 | 0 |
| Mitigation-taxonomy-derived | `multi-party authorization AI` | 0 | 0 |
| GitHub `topic:` tag | `topic:ai-safety` | 202 | 182 |
| GitHub `topic:` tag | `topic:llm-security` | 173 | 130 |
| GitHub `topic:` tag | `topic:explainable-ai` | 131 | 123 |
| GitHub `topic:` tag | `topic:red-teaming` | 100 | 75 |
| GitHub `topic:` tag | `topic:ai-ethics` | 11 | 9 |

Three things this table makes concrete:

- **The 4-word-AND failure mode, caught and fixed in real time.** GitHub's
  search API ANDs every unquoted word. `dataset license scanner stars:>19...`
  returned 0 hits; dropping to `dataset license` (2 words) returned 6, and the
  same narrowing pattern repeats across the earliest log entries — this is
  where the "keep free-text queries to 2-3 words" rule in `curation/README.md`
  came from, not a rule adopted in advance.
- **`"alternative to X"` was a near-total miss** for this domain, despite being
  a documented, real README pattern in general. Every instance tried against a
  specific already-accepted tool returned zero hits — nobody writes "X is an
  open-source alternative to Presidio" in this space. Worth knowing before
  spending a batch on it again.
- **`topic:` tags outperform every free-text query by roughly an order of
  magnitude** in raw volume, at somewhat lower precision — `topic:ai-safety`
  alone (202 hits, 182 unseen) exceeds the combined new-candidate yield of the
  entire mitigation-taxonomy-derived batch (7 queries, 3 candidates).

High raw-hit volume is not the same as high *signal*, though: `LLM agent
benchmark` returned 100 hits (100 new candidates) — the single largest yield of
any free-text query in the log — but the great majority were coding-agent
benchmarks unrelated to governance and were rejected as `redundant` or
`low-substance`. Compare `proof of learning` (9 hits, 9 candidates, **0
accepted** — all were "proof of concept" and cryptocurrency "proof of work"
false positives on the shared substring). Both queries "worked" by hit count;
neither produced a tool. The raw/new columns in the log measure query breadth,
not query quality — that judgment only happens at the review step.

Two further sources proved productive after keyword search saturated:

- **Mining curated "awesome" lists for vocabulary, not for tools.** An
  awesome-list is correctly rejected as a candidate (`not-a-tool-linklist`) but
  its table of contents is a dense, human-curated glossary. 105 such lists were
  logged as rejects; mining them yielded tools no keyword had surfaced,
  including BOINC and Open Policy Agent, which resolved two zero-coverage
  questions.
- **Direct leads** to specific projects and organisations (CoSAI, OWASP GenAI
  Security Project, Cisco AI Defense, Google).

### 2.3 Judgment protocol

Model tiering: no model in the scripts; a cheaper model for keyword scoping and
coarse pre-filtering; the strongest model, as an isolated subagent, for the
final implement/eval decision — given only `{tool summary + README excerpt}` ×
`{pre-filtered RQ shortlist}`, never the full session history or RQ catalog.

Every rejection carries a category from a closed vocabulary, so rejections are
countable rather than free text.

### 2.4 Two passes over the catalog

- **Pass A** (no search): re-judge already-accepted tools against questions they
  are *not* yet mapped to. This exists because `dedup_candidates.py` drops any
  candidate already in the catalog — so keyword search **structurally cannot**
  discover that an existing tool also answers a different question.
- **Pass B**: expanded keyword and topic search across all questions.

---

## 3. Results

### 3.1 Coverage

| | |
| --- | --- |
| Research questions | 97 |
| ...with ≥1 tool | **64 (66%)** |
| ...with zero tools | **33 (34%)** |
| Tools catalogued | 126 |
| Tools with zero mappings | 0 |

Tools per question: 19 questions have exactly 1 tool; the best-served has 10.
Mappings per tool: 78 tools answer 1 question, 41 answer 2, 6 answer 3, 1
answers 5.

### 3.2 Triage

Of **1,618** repositories judged: **130 accepted, 1,488 rejected**; **1,209
(75%) were open source** by SPDX classification (OSI-approved or FSF-libre).

| Rejection reason | n | % |
| --- | ---: | ---: |
| redundant (category already covered) | 610 | 41.0% |
| low-substance | 601 | 40.4% |
| not-a-tool-linklist | 105 | 7.1% |
| not-relevant | 69 | 4.6% |
| not-a-tool-paper-artifact | 61 | 4.1% |
| out-of-scope-narrow | 17 | 1.1% |
| not-a-tool-dataset | 9 | 0.6% |
| not-open-source | 7 | 0.5% |
| commercial-sdk | 5 | 0.3% |
| adversarial-purpose | 4 | 0.3% |

Note that **`not-open-source` is a vanishingly small rejection reason (0.5%)**.
Open-source availability is not the binding constraint on this catalog;
relevance and substance are.

---

## 4. Findings

### F1. Exhausting one search axis says nothing about another

After ~90 free-text keyword angles converged to near-zero new hits, the space
looked exhausted. It wasn't. A single `topic:ai-safety` query then returned 202
repositories, 98 never seen before; eight topic tags yielded ~650 unseen
candidates.

The lesson generalises beyond this project: **"we ran out of phrasings" is not
the same finding as "no tools exist"**, and only the second belongs in a paper.
Any claim of exhaustive search should state which axes were tried.

### F2. Zero-coverage questions have two structurally distinct causes

The 33 questions with no tool are not one phenomenon:

- **20 are hardware/compute-verification questions** (chip specifications,
  workload classification, chip location, TEE attestation, anti-tamper
  hardware, compute-usage enforcement). These fail because the work is physical
  engineering and silicon design, not distributable software. No search axis
  reaches them because there is nothing on GitHub to reach.
- **13 are organisational or research questions** (proof-of-learning, shared
  model governance, deployment corrections, data-access responsibility
  allocation, forecasting). These fail differently: the MIT AI Risk Mitigations
  taxonomy names the relevant controls — multi-party authorisation, deployment
  veto powers, KYC verification, capability thresholds — but these are *internal
  organisational procedures*. Nobody open-sources a deployment veto policy
  because it is not software.

Conflating these two into "34% uncovered" loses the point. Neither is a search
failure; each is a different kind of category error between what the question
asks for and what open-source software is.

### F3. GitHub's licence detection has a systematic blind spot

GitHub's repository licence API only inspects conventional file locations
(`LICENSE`, `LICENSE.md`). It does not read package-manager metadata. Real
licences declared *only* there are invisible to it.

Confirmed repeatedly during this work — `Jorwnpay/API-Police` (`pyproject.toml`:
MIT), `gizatechxyz/LuminAIR` (`Cargo.toml` `[workspace.package]`: MIT),
`gnueaj/Machine-Unlearning-Comparator` (`pyproject.toml`: MIT) — plus
`deepchecks` (AGPL-3.0 behind a custom preamble, reported `NOASSERTION`).

Any study computing "what fraction of AI tools are open source" from GitHub's
licence field alone will **undercount open-source availability**. The check must
extend to `pyproject.toml`/`setup.py`, `package.json`, `Cargo.toml` (including
`[workspace.package]`), `*.gemspec`, and `pom.xml`/`build.gradle`.

### F4. Mapping density is an artifact of when a tool was judged

Before Pass A, **48 of 73 mapped tools (66%) carried exactly one mapping**, and
two tools had none at all — unreachable from any problem page. Every mapping had
been created at the single moment its tool was first accepted, judged only
against the problem area being searched at that time.

This is a methodological warning for any catalog built incrementally by search:
**mapping density measures curation history, not tool generality.** Pass A
brought the single-mapped share down to 62% (78 of 126) and eliminated
zero-mapped tools entirely.

### F5. Tools need not be built for AI governance to answer a governance question

Google's `magika` is a file-content-type detector built for Gmail and Drive
security routing. It never mentions AI governance, datasets, or training data.
It is nonetheless a direct answer to RQ1 (*scaling problematic-data
identification to trillion-token datasets*), because content-type detection at
99% precision is exactly the capability that question needs.

The implication for method: **keyword search anchored on governance vocabulary
structurally cannot find these tools.** They surface only by mapping a tool's
*mechanism* to a question's *need* — which is why topic sweeps and direct leads
outperformed keyword search for this class of candidate.

### F6. The research agenda is skewed away from human-experienced harms

Each question was mapped to the harm type(s) its research would help prevent,
detect, measure, or remediate, using the AIAAIC Harms Taxonomy
(Abercrombie, Benbouzid, Giudici, Golpayegani, Hernandez, Noro, Pandit,
Paraschou, Pownall, Prajapati, Sayre, Sengupta, Suriyawongkul, Thelot, Vei,
Waltersdorfer — [arXiv:2407.01294](https://arxiv.org/abs/2407.01294)): 9 harm
types, 69 specific harms.

This is a completeness check the RQ catalog cannot perform on itself, because
the catalog defines its own scope. Reading it against an independently-derived
harm taxonomy separates three states: harm addressed and tooled; harm addressed
but untooled; **harm not addressed at all**.

| Harm type | RQs | direct | enabling | tooled | zero-tool |
| --- | ---: | ---: | ---: | ---: | ---: |
| Human Rights & Civil Liberties | 28 | 24 | 4 | 24 | 4 |
| Societal & Cultural | 26 | 20 | 6 | 18 | 8 |
| Autonomy | 24 | 22 | 2 | 18 | 6 |
| Political & Economic | 21 | 8 | 13 | **6** | **15** |
| Financial & Business | 21 | 12 | 9 | 9 | **12** |
| Reputational | 11 | 1 | 10 | 10 | 1 |
| Psychological | 8 | 5 | 3 | 6 | 2 |
| Physical | 4 | 2 | 2 | 4 | 0 |
| Environmental | 2 | 2 | 0 | 2 | 0 |

**38 of 69 specific harms (55%) have no research question addressing them.**

Three observations:

- **Psychological harm is the largest blind spot**: 8 of 11 specific harms
  uncovered — nothing on addiction, coercion/manipulation, dehumanisation,
  radicalisation, anxiety/depression, alienation, sexualisation, or trauma. The
  three that are covered arrive incidentally via content-filtering and
  benchmark-validity questions, not as objects of study.
- **Environmental coverage is a false positive.** Both environmental questions
  are tooled (`codecarbon`, `ecologits`), so the category looks healthy. But
  both questions say "environmental impact" generically and both tools measure
  only energy and carbon. Water consumption, e-waste, biodiversity, landfill,
  resource depletion and pollution — 6 of 8 — have neither question specificity
  nor tooling. Data-centre water use is an active policy dispute the agenda has
  no purchase on.
- **"Autonomy/agency loss" — the defining harm of its own category — has no
  question.** The catalog engages Autonomy only in its property-like forms (IP,
  impersonation, personality rights), never the decision-making-autonomy sense.

Concentration: Human Rights + Societal & Cultural + Autonomy account for 54% of
all question→harm incidences; Psychological + Physical + Environmental together
account for 9.7%. **Technical AI governance research is oriented toward harms
measurable at the data, model, and compute layer, and away from harms that
manifest in human experience and social structure.**

Note also that Political & Economic and Financial & Business show the opposite
pattern — high question coverage, low tool coverage (15 and 12 zero-tool
questions). These are the hardware/compute cluster of F2, restated in harm
terms: the agenda *does* ask how to prevent power concentration and model-weight
theft; nobody has shipped open-source tools.

---

## 5. Limitations

Stated plainly, because several of these bound what the numbers above can
support.

1. **Bulk rejection with generalised rationales.** 1,345 of the 1,488
   rejections come from the topic-tag sweep and were categorised by a
   rule-based classifier over repository name and description, not individually
   re-read. This is reliable for *not accepting* things already reviewed and
   passed over, but the **category assignment** within those rejections is
   approximate. Do not cite the rejection-category breakdown as hand-verified.
2. **A measured false-negative rate in bulk rejection.** Two errors were caught
   by later manual review: `EuConform` (a legitimate EU AI Act tool caught by a
   generic "low-substance" fallback) and `mlflow` (rejected on the scope of a
   bundled sub-feature, never evaluated on its own model registry). Both are now
   accepted. Two known errors in ~1,345 bulk decisions is a *lower bound*, not
   an estimate — only a fraction were re-examined.
3. **Single-annotator judgment.** All mapping decisions were produced by one
   agent under a human review gate on acceptances. There is no second annotator
   and no inter-rater reliability figure. Rejections received lighter human
   scrutiny than acceptances.
4. **The harm-taxonomy mapping is unvalidated.** It is agent-produced from
   question text against the taxonomy's definitions — a starting point for
   expert review, not a validated instrument. The `direct`/`enabling`
   distinction is our own, not the taxonomy's. 11 questions were classified as
   purely cross-cutting and left unmapped; mapping them (RQ94/95 are literally
   "enumerate the risks") would soften every gap reported in F6. This is a
   defensible but consequential modelling choice.
5. **Search is GitHub-centric.** Filters were `stars:>19`, pushed within 12
   months, non-archived, non-fork, plus a README-length check. This biases
   against new, niche, and non-English projects. PyPI, npm, Hugging Face, and
   arXiv artifact sweeps are documented as sources but were not systematically
   executed.
6. **Point-in-time snapshot.** Counts reflect the state at time of writing.
   Freshness columns (`datetime_added` / `checked` / `updated`) track staleness
   per row.
7. **Below-threshold candidates were not reviewed exhaustively.** The topic
   sweep reviewed all 1,363 deduplicated candidates, but the `<50 star` tier
   was triaged in bulk rather than individually.

---

## 6. Future work: expanding coverage

Concrete next steps, grouped by what they'd actually fix. Each is tied to a
specific finding or limitation above, not a general call for "more research."

### 6.1 New search axes suggested by this session's own results

- **Use the 38 uncovered specific harms (F6) as a keyword source in their own
  right.** This session searched *toward* the RQ catalog; it never searched
  toward the harm gaps the RQ catalog doesn't know it has. Concrete queries the
  taxonomy suggests directly: `addiction detection app` / `dark pattern
  detector` / `manipulation detection UI` (Psychological); `data center water
  usage` / `e-waste tracking hardware` / `AI biodiversity impact` (the 6
  uncovered Environmental harms, distinct from the carbon/energy tools already
  found). A hit here would be a genuinely new finding: a tool the RQ catalog's
  own vocabulary was structurally incapable of surfacing.
- **Open silicon / hardware-security repositories, not just software topic
  tags.** The 20 hardware RQs were called a structural dead end based on
  searching GitHub's *software* ecosystem — but open silicon root-of-trust
  projects exist (OpenTitan, Caliptra) and weren't checked this session. Before
  re-asserting "no open-source tooling here" in a paper, search `topic:rtl`,
  `topic:silicon`, `topic:root-of-trust`, and the OpenTitan/Caliptra org repos
  directly. This might not overturn F2, but it's an unclosed loop, not a
  confirmed negative.
- **PyPI, npm, and Hugging Face Spaces sweeps (limitation 5), executed, not
  just documented.** `curation/README.md` names these as sources; none were
  systematically run. Given how much the topic-tag axis outperformed free text
  (§2.2), a registry axis GitHub search doesn't touch at all is a plausible
  next unlock, especially for tools published as a Hugging Face Space or
  `evaluate` metric rather than a standalone repo.
- **Reference implementations from standards bodies themselves**, for the
  13 organisational-process RQs (F2). The mitigation vocabulary itself
  (KYC verification, deployment veto, capability thresholds) failed as search
  terms because these are procedures, not software — but some standards bodies
  ship policy-as-code alongside the standard (e.g. OPA/Rego policy bundles,
  in-toto/Sigstore policy templates for staged-deployment attestation). Worth
  one targeted pass specifically for "policy as code" implementations of these
  controls, distinct from the policy documents themselves.

### 6.2 Closing the validation gaps (limitations 1–4)

- **Sample-audit the bulk-rejected topic-sweep candidates.** Two known false
  negatives surfaced in ~1,345 rule-classified rejections purely because they
  happened to get manually revisited later — that is a lower bound on the true
  rate, not an estimate. A random 5–10% sample, individually re-reviewed, would
  turn "at least 2 known errors" into an actual false-negative rate worth
  citing.
- **Second-annotator pass for inter-rater reliability.** All judgments this
  session came from one agent under one human review gate. Even a partial
  independent re-judgment (a different agent, or a human, on a sampled subset
  of accepts and rejects) would let coverage numbers carry an agreement figure
  instead of resting on single-annotator judgment.
- **Expert review of the harm-taxonomy mapping**, ideally from the taxonomy's
  own authors. Two modelling choices are load-bearing enough to move the
  headline 38/69 number: whether the 11 purely-cross-cutting RQs (RQ94/95 in
  particular — "enumerate the risks" arguably touches all 9 types) should stay
  unmapped, and whether the `direct`/`enabling` distinction is the right cut.
  Re-running the mapping at the 69-specific-harm granularity, not just the 9
  types, would also sharpen F6 considerably, but needs individual review per
  row rather than the type-level pass done here.

### 6.3 Process improvements for whoever continues this

- **Make awesome-list mining a first-class pipeline step, not an ad hoc
  detour.** It was the single highest-yield source discovered this session
  (12 of the 126 catalogued tools — including BOINC and Open Policy Agent,
  which resolved two zero-coverage RQs — came from mining lists already
  sitting in the reject log as `not-a-tool-linklist`) and it happened by hand,
  opportunistically.
  A repeatable version: search `topic:awesome` plus a domain term, extract
  each list's linked repos automatically, dedup against `seen_repos.csv`, feed
  the rest through the normal judgment pipeline.
- **Periodically re-check `not-open-source` rejects.** The package-metadata
  licence blind spot (F3) was confirmed four separate times this session on
  *first* encounter with each repo. It's equally plausible that some of the
  historical `not-open-source` rejects (7 total, small enough to re-check by
  hand) have since gained a licence, or had one all along in a location not
  checked at the time.
- **Track near-misses, not just accepts and rejects.** Several tools this
  session were correct rejects for a narrow, fixable reason — a missing
  licence file, a pre-release maturity gate — where the underlying capability
  was exactly right. A lightweight "revisit in N months" list for these (as
  opposed to the permanent `seen_repos.csv` record, which is correctly
  never revisited) would catch them if they mature into a real answer.

---

## 7. Reproducibility

- All scripts, schemas, judgment rules, and the phase-1/phase-2 starter prompts:
  [`curation/README.md`](../curation/README.md)
- Every keyword ever run, including zero-hit queries:
  `curation/state/search_log.csv`
- Every repository judged, with verdict, rejection category, licence and licence
  class, problem area, and originating keyword: `curation/state/seen_repos.csv`
- Question→harm mapping with per-row rationale:
  `curation/aiaaic_taxonomy_mapping.py` (mapping as reviewable data) and
  `curation/aiaaic_taxonomy_mapping.csv` (generated)

Results will not reproduce exactly — the corpus changes continuously — but the
logged keywords and judgment rules should reproduce them in spirit.
