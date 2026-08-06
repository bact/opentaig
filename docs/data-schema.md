# Data schema

The full reference for the two Google Sheets that back the site. See the
[root README](../README.md) for the high-level picture and
[`curation/README.md`](../curation/README.md) for how the tool-discovery
pipeline writes into the `tools`/`tool_map` tabs described below.

## How it works

```text
TAIG sheet  ---\
                >-- (CSV export, fetched once per build) --> build.py --> site/ --> GitHub Pages
OpenTAIG sheet -/
```

The data is split across **two decoupled sheets**, joined by research
question number (`rq_no`), so upstream paper content and our own annotations
can evolve independently:

- **`TAIG` sheet** — the question text and taxonomy *as published by
  Stanford's TAIG database*. Updated manually whenever the upstream source
  changes; `build.py` never writes to it.
- **`OpenTAIG` sheet** — our own framework/regulation mappings and tool
  catalog, keyed by `rq_no`. This is where our editorial work happens,
  independent of upstream updates.

`build.py` fetches both sheets, joins them by `rq_no`, normalizes the result
into a set of "open problem" records, and renders the static site with
Jinja2 templates. It runs in GitHub Actions:

- **Manually**, any time, via the *Run workflow* button on the
  `Build and deploy site` workflow (Actions tab).
- **Automatically**, every 2 months (1st of Jan/Mar/May/Jul/Sep/Nov, 03:00 UTC).
- On every push to `main` (so merged content/template changes go live right away).

No secrets are needed: both sheets are read via their public CSV export URLs,
so each must stay shared as **"Anyone with the link" (Viewer)**.

## Editing the data

Edit the Google Sheets — nothing else. The next build (manual or scheduled)
picks up your changes; the sheets are never read live, so edits don't appear
until a build runs.

### 1. `TAIG` sheet — upstream question text & taxonomy

One tab, one row per open problem, mirroring the Stanford TAIG database /
paper. This is the **spine** of the site — question text and taxonomy always
come from here, never from the `OpenTAIG` sheet.

| Column | Meaning |
| --- | --- |
| `Research Question` | The open problem's text, as published upstream. |
| `Question number (in paper)` | The paper's own numbering (**`rq_no`** — the join key to the `OpenTAIG` sheet's `map` and `tool_map` tabs). Numbers aren't necessarily contiguous (the paper itself has gaps); that's expected. |
| `Section Number` | The paper's section reference (e.g. `3.1.1`), shown on the problem detail page. |
| `Target(s)` | One of: `Data`, `Compute`, `Model & Algorithms`, `Deployment`, `All` (cross-cutting). Second-level grouping on the problem listing page (`/problems/`). |
| `Capacity` | One of: `Assessment`, `Access`, `Verification`, `Security`, `Operationalisation`, `Ecosystem Monitoring`. Top-level grouping on the problem listing page (`/problems/`) and the Landscape overview matrix (`/`). |
| `Problem Area (from Problem Areas)` | A finer sub-category (e.g. "Identification of Problematic Data"). Third-level grouping, under Target. |
| `Existing work & resources` | Citations relevant at time of publication, semicolon-separated. Parsed and carried through the build, but not currently rendered on the problem detail page -- pending curation of this column's data quality (see the commented-out block in `templates/problem.html`). |
| `Relevant expertise` | Disciplines useful for this problem (e.g. `Cryptography`, `ML Theory`). Shown as chips and offered as a filter facet on the problem listing page (`/problems/`). |
| `New work (since publication)` | Citations for follow-up work since the paper published. Parsed and carried through the build, but not currently rendered (see above). |

### 2. `OpenTAIG` sheet — our mappings, tool catalog, terms & framework catalogs

Five tabs, named **`map`**, **`tool_map`**, **`tools`**, **`terms`**, and
**`framework`**. All tab and column names are lowercase with underscores.

Any tab named **`tools_*_seed`** (e.g. `tools_rgaf_seed`) is a
**curation-only staging area** — a place to paste in a candidate tool list
(from a blog post, a catalogue, etc.) before reviewing and copying entries
into the real `tools`/`tool_map` tabs. The build reads only `tools` and
`tool_map`; it never reads staging tabs.

Every row on all five tabs also carries three freshness/bookkeeping
columns — see "Freshness columns" below.

**`map` tab** — one row per annotated question, joined to the `TAIG` sheet by
`rq_no`:

| Column | Meaning |
| --- | --- |
| `rq_no` | Join key — must match a `Question number (in paper)` value in the `TAIG` sheet. |
| `rgaf` | [LF AI & Data RGAF](https://lfaidata.foundation/rgaf/) dimension **ids**, referencing the `terms` tab. |
| `euaiact` | EU AI Act article/obligation **ids**, referencing the `terms` tab. |
| `unescoai` | UNESCO Ethics of AI principle **ids**, referencing the `terms` tab. |
| `aseanai` | ASEAN AI Governance & Ethics guide principle **ids**, referencing the `terms` tab. |
| `coeai` | CoE Framework Convention on AI article **ids**, referencing the `terms` tab. |
| `aiaaic` | AIAAIC Harms Taxonomy harm-type **ids**, referencing the `terms` tab. Unlike the other five columns, this is **our own editorial judgment** about which harm(s) a question's research would help address, not a crosswalk to an external authority's own text — see [`docs/methodology-and-findings.md`](methodology-and-findings.md) § Findings, F6. |

These 6 framework columns are deliberately kept separate rather than merged
into one (even though term ids are already globally unique) — each column
acts as a per-row checklist while filling in a new question, and it powers
the "pasted into the wrong column" sanity-check warning described below.

**Every column above holds ids, not free text — separate multiple ids with a
semicolon `;`.** Example `rgaf` cell (referencing two rows in the `terms`
tab):

```text
rgaf-safe; rgaf-transparent
```

Leave a cell **blank** if there's no match. A `map` row whose `rq_no`
doesn't match any `TAIG` row (a typo, or a question renumbered/removed
upstream) is skipped with a build warning, not a failure. A `TAIG` row with
no matching `map` row is normal — it just has no mappings or tools yet. An
id that doesn't exist in the `terms` catalog, or that exists but belongs to
the wrong framework (e.g. a CoE id pasted into the `aseanai` column), also
produces a build warning rather than failing.

**`tool_map` tab** — our research-question-to-tool mappings, **long/tidy
format**: one row per `(rq_no, tool_id, role)` pairing, so a tool answering
several questions, or a question answered by several tools, is just more
rows, never a semicolon-list cell to hand-edit:

| Column | Meaning |
| --- | --- |
| `rq_no` | Join key — must match a `Question number (in paper)` value in the `TAIG` sheet. |
| `tool_id` | Must match an `id` in the `tools` tab below. |
| `role` | Exactly `implement` or `eval` — whether this tool helps *implement* a solution to this question, or *evaluate/audit* one. |
| `rationale` | Free-text, one-line explanation of *why* this specific tool addresses this specific question. |

Tools map **directly** to research questions by reading the tool's
README/paper against that question's own text — never via shared
principle/term tags. See [`curation/README.md`](../curation/README.md) for
the full discovery/mapping methodology.

**`terms` tab** — the shared catalog of RGAF/EU AI Act/UNESCO/ASEAN/CoE/AIAAIC
terms, **one tab across all six frameworks**, defined once and referenced
by id from as many `map` rows as apply:

| Column | Meaning |
| --- | --- |
| `id` | A **globally unique, namespaced** id: `<namespace>-<local-part>`, dash-separated (e.g. `euaiact-a8`, `coeai-a8`, `rgaf-safe`, `aiaaic-humanrights`). See "Term id namespaces" below. |
| `framework_id` | One of `rgaf`, `euaiact`, `unescoai`, `aseanai`, `coeai`, `aiaaic` — must match a `key` in `config.yaml`'s `frameworks:` list and an `id` in the `framework` tab below. |
| `name` | Full display text (the chip label), e.g. `Article 15 (Accuracy, robustness and cybersecurity)`. |
| `summary` | Optional one-paragraph plain-language description. Blank is fine. |
| `url` | Optional direct link to this specific term's source text (e.g. straight to Article 15, not just the EU AI Act's homepage). When blank, the site falls back to that framework's `doc_url` in `config.yaml`. |

#### Term id namespaces

Ids are dash-separated: `<namespace>-<local-part>`. The **namespace** token
must never itself contain a dash, so it's always unambiguous where it ends
— use `rgaf`, `euaiact`, `unescoai`, `aseanai`, `coeai`, or `aiaaic`. The
**local part** is free-form (a short mnemonic like `a8` or `safe`, or a
longer slug) — the only hard requirement is that the full id is unique
across the *entire* tab, which the build enforces with a warning on any
duplicate.

Two `aiaaic` terms are not harm types at all, but sentinel qualifiers used so
a blank `map` cell can never be misread as "no harm identified": `aiaaic-
indirect` (the question supports addressing a harm without itself targeting
it) and `aiaaic-crosscutting` (a research-method question, not mapped to any
specific harm). Every RQ carries exactly one of: a direct harm-type chip,
a harm-type chip plus `aiaaic-indirect`, or `aiaaic-crosscutting` alone. See
`curation/emit_aiaaic_framework.py`'s docstring for the full rationale.

This exists because two different legal instruments can use identical
wording: both the EU AI Act and the CoE Framework Convention on AI have an
"Article 8 (Transparency and oversight)". Namespacing (`euaiact-a8` vs.
`coeai-a8`) keeps them distinct without any special-case logic in the
build — every id is just globally unique by construction.

**`tools` tab** — the open-source tool catalog, one row per tool, defined
**once** and referenced by id from as many `map` rows as apply, so tool
metadata never drifts out of sync across multiple mentions:

| Column | Meaning |
| --- | --- |
| `id` | Short unique identifier, referenced from `tool_map.tool_id` (e.g. `scancode-toolkit`). |
| `tool_type` | Free-text category, e.g. `software` or `specification` — not a fixed enum. Some open problems are better addressed by an open standard than by executable software (e.g. `spdx3`, `croissant`); this lets both live in one catalog. Rendered as a small chip, same treatment as `license`. |
| `name` | Display name. |
| `summary` | One or two sentence description. |
| `license` | **SPDX License ID** (e.g. `Apache-2.0`, `MIT`, `GPL-2.0-or-later`) — see [spdx.org/licenses](https://spdx.org/licenses/). |
| `programming_language` | Implementation language(s) — semicolon-separated if more than one (e.g. `Python; Rust`). GitHub's own repo-level `language` field is a reliable single-language source; a second language is a manual/curated addition for genuinely polyglot tools, not something the backfill script infers automatically. Only meaningful for `tool_type` `software`; leave blank for `specification` rows, which have no source code. Added after the initial ~130 tools were catalogued, so older rows are blank until backfilled — see `curation/backfill_programming_language.py`. |
| `homepage` | Project homepage URL. |
| `source` | Source code repository URL. |
| `documentation` | Documentation URL. |
| `funding` | Funding/sponsorship URL, if any. |

(These four URL columns reuse the well-known
[Python Project-URL labels](https://packaging.python.org/en/latest/specifications/well-known-project-urls/),
so the schema isn't inventing its own vocabulary.) Leave any column blank if
not applicable — the site simply omits blank fields.

**Project-quality / community-health columns**, added to `tools` alongside
`programming_language`. These describe the *repository*, not the tool's
governance-relevance — a signal of maintenance health and openness practice
that stands apart from the license question (a project can be permissively
licensed and still be a single-maintainer, no-tests, no-policy repo, or
GPL-licensed with excellent governance practice). Collected via
`curation/collect_project_metadata.py`, GitHub-only for now (see that
script's docstring for the exact API calls and their staleness
characteristics — several of these, especially the counts, are a snapshot
at collection time, not a live value). Designed independently, then
cross-checked against [CHAOSS](https://chaoss.community/)'s own metric
definitions after the fact — see "Prior art: CHAOSS" in
`curation/README.md` for which columns already line up with a named CHAOSS
metric and which of theirs (Contributor Absence Factor, Libyears,
issue/PR responsiveness durations, ...) aren't collected here yet:

| Column | Meaning |
| --- | --- |
| `stars` | Star count (`stargazers_count`). |
| `forks` | Fork count (`forks_count`). |
| `watchers` | **Not** GitHub's `watchers_count` field, which has been a silent alias for `stargazers_count` since GitHub folded "Watch" into "Star" years ago — sourced from `subscribers_count` instead, the field that actually reflects people subscribed to repo activity. |
| `contributors` | Approximate contributor count, from the `Link: rel="last"` page number on `/repos/{owner}/{repo}/contributors?per_page=1`. A bus-factor proxy, not exact (bots and one-line-fix drive-bys count the same as core maintainers). |
| `open_issues_count` | GitHub's own `open_issues_count` — note this conflates open pull requests into the count, a GitHub API quirk, not a bug here. |
| `releases_count` | Total release count (same `Link: rel="last"` trick as `contributors`, against `/releases`). |
| `latest_release_date` | Publish date of the most recent release, date-only. Blank for tools that don't use GitHub Releases (e.g. rolling-release or tag-only projects) — that's a real "no formal releases" signal, not a collection failure. |
| `last_commit_date` | Default branch's last push date (`pushed_at`), date-only. |
| `readme_url` | From the GitHub Community Profile API. |
| `license_url` | From the GitHub Community Profile API — the actual LICENSE file's URL, distinct from `license` (the SPDX identifier). Left blank (with a warning at collection time) when GitHub's own license detector returns `NOASSERTION` for the repo — confirmed on a real catalogued tool where the API's `html_url` pointed at an unrelated file, not any license file. |
| `code_of_conduct_url` | From the GitHub Community Profile API. Blank if the repo has none. |
| `contributing_url` | From the GitHub Community Profile API. Blank if the repo has none. |
| `security_policy_url` | GitHub's Community Profile API doesn't reliably surface this, so it's a best-effort fallback: probes `SECURITY.md`, `.github/SECURITY.md`, `docs/SECURITY.md` on the default branch. Blank if none of those exist (doesn't rule out a security policy living somewhere non-standard). |
| `governance_url` | Same best-effort fallback shape as `security_policy_url`, probing `GOVERNANCE.md`, `MAINTAINERS.md`, `MAINTAINERS`, `.github/GOVERNANCE.md`, `.github/MAINTAINERS.md`. |
| `sbom_url` | GitHub auto-generates an SPDX SBOM from the dependency graph for every public repo that has it enabled — this is that API endpoint (`/repos/{owner}/{repo}/dependency-graph/sbom`), which returns the SBOM JSON directly. Confirmed present on a repo that never published its own SBOM file, so this isn't asking whether the *tool* publishes one, just whether GitHub's dependency graph is on (true for almost all public repos). Fetching the URL needs GitHub auth, same as any other API call. |
| `dependents_count` | **Not auto-collected.** GitHub's "Used by" dependency-graph count (the `/network/dependents` page) has no public API — the only way to get it is scraping the HTML page, which `collect_project_metadata.py` deliberately does not do (fragile against markup changes, and bulk scraping sits in GitHub ToS gray territory that a one-off manual check doesn't). Fill in by hand for a tool worth spot-checking, or leave blank. |
| `funder` | Name(s) of the organization(s)/person(s) that funded the project (semicolon-separated if more than one) — from `codemeta.json`'s `funder` field. A distinct CodeMeta concept from `funding` (below): *who paid for it* vs *a URL to fund/cite it*. Blank if the repo has no `codemeta.json`, which is most of them (common in the R/rOpenSci ecosystem, rare elsewhere). |
| `openssf_best_practices_url` | `https://www.bestpractices.dev/projects/<id>` if the project has ever registered for an OpenSSF (formerly CII) Best Practices badge — via the public `bestpractices.dev/projects.json?q=<repo-name>` lookup (note: `q=`, not `pq=`/`url=` — those don't work, confirmed by hand), filtered client-side to a `repo_url` match. Blank if never registered (most projects). |
| `openssf_best_practices_badge_level` | `in_progress` / `passing` / `silver` / `gold`, from the same lookup. |
| `openssf_scorecard_url` | `https://scorecard.dev/viewer/?uri=github.com/<org>/<repo>` if OpenSSF Scorecard has ever scanned the repo — via the public `api.scorecard.dev` API. Blank if never scanned. |
| `openssf_scorecard_score` | Aggregate score, 0–10, from the same API. |
| `openssf_scorecard_branch_protection`, `openssf_scorecard_code_review`, `openssf_scorecard_maintained`, `openssf_scorecard_vulnerabilities` | Four individual Scorecard check scores (0–10), picked as the highest-signal checks for "is this tool safe to recommend" out of the ~18 Scorecard reports. **A score of `-1` means Scorecard could not evaluate that check** (confirmed on a real catalogued tool — an auth/permission limit on Scorecard's own scanning infrastructure, not a finding about the repo) — read `-1` as "unknown", never as "worst possible score." The full per-check breakdown (Binary-Artifacts, CI-Tests, Fuzzing, Pinned-Dependencies, SAST, Signed-Releases, Token-Permissions, ...) is always re-fetchable from `openssf_scorecard_url`'s API if another check becomes worth its own column. |
| `development_status` | From `codemeta.json`'s `developmentStatus` — typically a [repostatus.org](https://www.repostatus.org/) or tidyverse-lifecycle URL/label (e.g. `active`, `wip`, `inactive`, `unsupported`). A maturity signal independent of raw activity counts. Blank if no `codemeta.json`. |
| `paper_url` | DOI or URL of an academic paper describing the tool, if one exists — checked in order from `codemeta.json`'s `citation[].url` (more structured, checked first) and `CITATION.cff`'s `preferred-citation.doi`/`.url` (very common in this catalog's domain — confirmed present on scikit-learn, deepchecks, and others). Blank if the tool has no associated publication. |
| `software_heritage_id` | [Software Heritage](https://www.softwareheritage.org/) archival identifier (a `swh:1:...` SWHID), if the project has explicitly recorded one — from `CITATION.cff`'s `identifiers` (`type: swh`) or `codemeta.json`'s `@id`. Blank for the large majority of tools, which don't record this even if Software Heritage has in fact archived them (Software Heritage archives essentially all public GitHub repos automatically — this column only reflects whether the *project itself* advertises a citable SWHID, not whether an archival copy exists at all). |

`funding` (the existing column, from the original schema — a plain URL) is
auto-enriched by `collect_project_metadata.py` when blank, checked in order:
`.github/FUNDING.yml` (parsed, GitHub's own platform keys mapped to their
canonical URLs — `github` → GitHub Sponsors, `open_collective`, `patreon`,
`ko_fi`, `tidelift`, `custom`, etc.), then `pyproject.toml`'s
`[project.urls]` table matched case/punctuation-insensitively against the
PyPA well-known label `Funding` (confirmed against real projects using both
`funding` lowercase and `Funding` capitalized), then `codemeta.json`'s own
`funding` field if it's URL-shaped. First hit wins; every candidate found is
still logged at collection time so a human can see what was passed over. The
script never overwrites an existing `funding` value — enrichment only, same
"don't override curated content" rule as everywhere else in this pipeline.

**`framework` tab** — descriptive metadata about each framework/regulation
itself, one row per `key` in `config.yaml`'s `frameworks:` list. This keeps
purely informational content editable in the sheet, while the build-wiring
(which `map`-tab column and display order belong to each framework) stays in
`config.yaml`:

| Column | Meaning |
| --- | --- |
| `id` | Must match a `key` in `config.yaml`'s `frameworks:` list (e.g. `euaiact`). |
| `name` | Short display name (the label shown throughout the site, e.g. `EU AI Act`). |
| `fullname` | Full official title (e.g. `Artificial Intelligence Act`). Shown as a subtitle on the Frameworks page when it differs from `name`. |
| `summary` | Optional one-paragraph description. Blank is fine. |
| `homepage` | General info page for the framework/regulation. |
| `source` | Direct link to the actual source document/legal text. This is what the site links to as "(source)" — `homepage` is used only as a fallback when `source` is blank. |
| `group` | The publishing body (e.g. `European Union`, `The Linux Foundation`). Shown as a subtitle alongside `fullname`. |

A `key` in `config.yaml` with no matching row here falls back to the key
itself as the display label, with no source link — a build warning, not a
failure. A row here with no matching `key` in `config.yaml` is also just a
warning (orphaned metadata, not wired to any mapping column).

### Freshness columns

Every tab above (`map`, `tool_map`, `tools`, `terms`, `framework`) also
carries three timestamp columns, expected to be filled in on every row:

| Column | Meaning |
| --- | --- |
| `datetime_added` | When the row was first added. |
| `datetime_checked` | When the row was last reviewed for staleness (content re-fetched/re-read and compared against what's already there). |
| `datetime_updated` | When the row's content actually last changed. A check that finds nothing new bumps `datetime_checked` only — `datetime_updated` stays put. |

These are informational bookkeeping for a future scheduler/crawler to decide
what's stale enough to re-fetch; a blank value on any of the three produces
a build warning, but nothing in `build.py` reads or compares the values yet.

### Identifying a tab

Each source in [`config.yaml`](../config.yaml) is looked up by
**`sheet_name`** — the tab's visible name, exactly as shown on the tab at
the bottom of the Google Sheets window (e.g. `map`, `tools`, `terms`,
`framework`). This is preferred over the older `gid` (a tab's opaque
numeric id, found after `#gid=` in the tab's URL): a wrong `sheet_name` is
easy to spot, while a wrong `gid` just produces a bare `400 Bad Request`
from Google's export endpoint. If you rename a tab, update the matching
`sheet_name` in `config.yaml`.
