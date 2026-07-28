# OpenTAIG

A catalog of open-source tools mapped to open problems in technical
AI governance and linked to relevant principles and regulations.

Inspired by [TAIG database](https://taig.stanford.edu/taig_database.html)
and the paper
[*Open Problems in Technical AI Governance*](https://arxiv.org/abs/2407.14981)
(Reuel, Bucknall, et al., 2025).

The site is **fully static**, hosted on **GitHub Pages**, and generated from
**two Google Sheets** once per build. There is no backend and no database —
the sheets are the only editable source of truth, and everything else lives
in this repo.

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
  Stanford's TAIG database*. You update this manually whenever the upstream
  source changes; `build.py` never writes to it.
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
|---|---|
| `Research Question` | The open problem's text, as published upstream. |
| `Question number (in paper)` | The paper's own numbering (**`rq_no`** — the join key to the `OpenTAIG` sheet's `map` and `tool_map` tabs). Numbers aren't necessarily contiguous (the paper itself has gaps); that's expected. |
| `Section Number` | The paper's section reference (e.g. `3.1.1`), shown on the problem detail page. |
| `Target(s)` | One of: `Data`, `Compute`, `Model & Algorithms`, `Deployment`, `All` (cross-cutting). Second-level grouping on the home page. |
| `Capacity` | One of: `Assessment`, `Access`, `Verification`, `Security`, `Operationalisation`, `Ecosystem Monitoring`. Top-level grouping on the home page. |
| `Problem Area (from Problem Areas)` | A finer sub-category (e.g. "Identification of Problematic Data"). Third-level grouping, under Target. |
| `Existing work & resources` | Citations relevant at time of publication, semicolon-separated. Shown on the problem detail page. |
| `Relevant expertise` | Disciplines useful for this problem (e.g. `Cryptography`, `ML Theory`). Shown as chips and offered as a filter facet on the home page. |
| `New work (since publication)` | Citations for follow-up work since the paper published. |

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
|---|---|
| `rq_no` | Join key — must match a `Question number (in paper)` value in the `TAIG` sheet. |
| `rgaf` | [LF AI & Data RGAF](https://lfaidata.foundation/rgaf/) dimension **ids**, referencing the `terms` tab. |
| `euaiact` | EU AI Act article/obligation **ids**, referencing the `terms` tab. |
| `unescoai` | UNESCO Ethics of AI principle **ids**, referencing the `terms` tab. |
| `aseanai` | ASEAN AI Governance & Ethics guide principle **ids**, referencing the `terms` tab. |
| `coeai` | CoE Framework Convention on AI article **ids**, referencing the `terms` tab. |

These 5 framework columns are deliberately kept separate rather than merged
into one (even though term ids are already globally unique) — each column
acts as a per-row checklist while filling in a new question, and it powers
the "pasted into the wrong column" sanity-check warning described below.

**Every column above holds ids, not free text — separate multiple ids with a
semicolon `;`.** Example `rgaf` cell (referencing two rows in the `terms`
tab):

```
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
|---|---|
| `rq_no` | Join key — must match a `Question number (in paper)` value in the `TAIG` sheet. |
| `tool_id` | Must match an `id` in the `tools` tab below. |
| `role` | Exactly `implement` or `eval` — whether this tool helps *implement* a solution to this question, or *evaluate/audit* one. |
| `rationale` | Free-text, one-line explanation of *why* this specific tool addresses this specific question. |

Tools map **directly** to research questions by reading the tool's
README/paper against that question's own text — never via shared
principle/term tags. See [`curation/README.md`](curation/README.md) for the
full discovery/mapping methodology.

**`terms` tab** — the shared catalog of RGAF/EU AI Act/UNESCO/ASEAN/CoE
terms, **one tab across all five frameworks**, defined once and referenced
by id from as many `map` rows as apply:

| Column | Meaning |
|---|---|
| `id` | A **globally unique, namespaced** id: `<namespace>-<local-part>`, dash-separated (e.g. `euaiact-a8`, `coeai-a8`, `rgaf-safe`). See "Term id namespaces" below. |
| `framework_id` | One of `rgaf`, `euaiact`, `unescoai`, `aseanai`, `coeai` — must match a `key` in `config.yaml`'s `frameworks:` list and an `id` in the `framework` tab below. |
| `name` | Full display text (the chip label), e.g. `Article 15 (Accuracy, robustness and cybersecurity)`. |
| `summary` | Optional one-paragraph plain-language description. Blank is fine. |
| `url` | Optional direct link to this specific term's source text (e.g. straight to Article 15, not just the EU AI Act's homepage). When blank, the site falls back to that framework's `doc_url` in `config.yaml`. |

#### Term id namespaces

Ids are dash-separated: `<namespace>-<local-part>`. The **namespace** token
must never itself contain a dash, so it's always unambiguous where it ends
— use `rgaf`, `euaiact`, `unescoai`, `aseanai`, or `coeai`. The **local
part** is free-form (a short mnemonic like `a8` or `safe`, or a longer
slug) — the only hard requirement is that the full id is unique across the
*entire* tab, which the build enforces with a warning on any duplicate.

This exists because two different legal instruments can use identical
wording: both the EU AI Act and the CoE Framework Convention on AI have an
"Article 8 (Transparency and oversight)". Namespacing (`euaiact-a8` vs.
`coeai-a8`) keeps them distinct without any special-case logic in the
build — every id is just globally unique by construction.

**`tools` tab** — the open-source tool catalog, one row per tool, defined
**once** and referenced by id from as many `map` rows as apply, so tool
metadata never drifts out of sync across multiple mentions:

| Column | Meaning |
|---|---|
| `id` | Short unique identifier, referenced from `tool_map.tool_id` (e.g. `scancode-toolkit`). |
| `tool_type` | Free-text category, e.g. `software` or `specification` — not a fixed enum. Some open problems are better addressed by an open standard than by executable software (e.g. `spdx3`, `croissant`); this lets both live in one catalog. Rendered as a small chip, same treatment as `license`. |
| `name` | Display name. |
| `summary` | One or two sentence description. |
| `license` | **SPDX License ID** (e.g. `Apache-2.0`, `MIT`, `GPL-2.0-or-later`) — see [spdx.org/licenses](https://spdx.org/licenses/). |
| `homepage` | Project homepage URL. |
| `source` | Source code repository URL. |
| `documentation` | Documentation URL. |
| `funding` | Funding/sponsorship URL, if any. |
| `implement` | Term **ids** (from the `terms` tab) this tool helps *implement* — free-standing tool metadata, independent of any specific question. |
| `eval` | Term **ids** (from the `terms` tab) this tool helps *evaluate or audit*. |

(These four URL columns reuse the well-known
[Python Project-URL labels](https://packaging.python.org/en/latest/specifications/well-known-project-urls/),
so the schema isn't inventing its own vocabulary.) Leave any column blank if
not applicable — the site simply omits blank fields.

**`framework` tab** — descriptive metadata about each framework/regulation
itself, one row per `key` in `config.yaml`'s `frameworks:` list. This keeps
purely informational content editable in the sheet, while the build-wiring
(which `map`-tab column and display order belong to each framework) stays in
`config.yaml`:

| Column | Meaning |
|---|---|
| `id` | Must match a `key` in `config.yaml`'s `frameworks:` list (e.g. `euaiact`). |
| `name` | Short display name (the label shown throughout the site, e.g. `EU AI Act`). |
| `fullname` | Full official title (e.g. `Artificial Intelligence Act`). Shown as a subtitle on the Principles & Regulations page when it differs from `name`. |
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
|---|---|
| `datetime_added` | When the row was first added. |
| `datetime_checked` | When the row was last reviewed for staleness (content re-fetched/re-read and compared against what's already there). |
| `datetime_updated` | When the row's content actually last changed. A check that finds nothing new bumps `datetime_checked` only — `datetime_updated` stays put. |

These are informational bookkeeping for a future scheduler/crawler to decide
what's stale enough to re-fetch; a blank value on any of the three produces
a build warning, but nothing in `build.py` reads or compares the values yet.

### Identifying a tab

Each source in [`config.yaml`](config.yaml) is looked up by **`sheet_name`**
— the tab's visible name, exactly as shown on the tab at the bottom of the
Google Sheets window (e.g. `map`, `tools`, `terms`, `framework`). This is preferred over
the older `gid` (a tab's opaque numeric id, found after `#gid=` in the
tab's URL): a wrong `sheet_name` is easy to spot, while a wrong `gid` just
produces a bare `400 Bad Request` from Google's export endpoint. If you
rename a tab, update the matching `sheet_name` in `config.yaml`.

## Running a build locally

```bash
pip install -r requirements.txt
python build.py
```

This writes the full site to `site/` (git-ignored). Open `site/index.html`
in a browser to preview.

For offline development without hitting Google Sheets, set a `file:` path
under `data.taig` / `data.mapping` / `data.tool_map` / `data.tools` /
`data.terms` / `data.framework` in `config.yaml` (or a copy of it) to point
at a local CSV instead of a URL — see
[`tests/config.local.yaml`](tests/config.local.yaml) for a working example
against the fixtures in `tests/fixtures/`.

## One-time GitHub Pages setup

In the repo settings: **Settings → Pages → Build and deployment → Source →
GitHub Actions**. After that, every workflow run publishes `site/` directly;
no `gh-pages` branch is used.

## Repository layout

```
config.yaml          site title, sheet ids + tab names, column names, taxonomy order
build.py              fetch (taig + map + tool_map + tools + terms + framework) -> join by rq_no/id -> render
templates/            Jinja2 templates
assets/               CSS + vanilla JS (client-side search/filter, no network calls)
tests/fixtures/       local CSV fixtures for offline build verification
.github/workflows/build.yml  the build + deploy pipeline
```

## Notes

- The home page groups problems **Capacity → Target → Problem Area**,
  mirroring the paper's own section structure. `Relevant expertise` is a
  filter facet (like the frameworks) but doesn't get its own browse page.
- If a sheet is ever made private, swap the CSV-export fetch in
  `fetch_source()` (`build.py`) for the Google Sheets API with a service
  account key stored as a GitHub Actions secret.
- Problem detail page URLs are derived from the question text
  (slug + short stable hash). Editing a question's wording changes its URL.
