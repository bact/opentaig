# OpenTAIG

A community-maintained catalog of **open problems in technical AI governance**,
each mapped to relevant principles/regulations and linked to open-source tools
that help address it. Inspired by Stanford's
[TAIG database](https://taig.stanford.edu/taig_database.html) and the paper
[*Open Problems in Technical AI Governance*](https://arxiv.org/abs/2407.14981)
(Reuel, Bucknall, et al., 2025).

The site is **fully static**, hosted on **GitHub Pages**, and generated from
**two Google Sheets** once per build. There is no backend and no database —
the sheets are the only editable source of truth, and everything else lives
in this repo.

## How it works

```
TAIG sheet  ---\
                >-- (CSV export, fetched once per build) --> build.py --> site/ --> GitHub Pages
OpenTAIG sheet -/
```

The data is split across **two decoupled sheets**, joined by research
question number (`RQ_No`), so upstream paper content and our own annotations
can evolve independently:

- **`TAIG` sheet** — the question text and taxonomy *as published by
  Stanford's TAIG database*. You update this manually whenever the upstream
  source changes; `build.py` never writes to it.
- **`OpenTAIG` sheet** — our own framework/regulation mappings and tool
  catalog, keyed by `RQ_No`. This is where our editorial work happens,
  independent of upstream updates.

`build.py` fetches both sheets, joins them by `RQ_No`, normalizes the result
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
| `Question number (in paper)` | The paper's own numbering (**`RQ_No`** — the join key to the `OpenTAIG` sheet's `map` tab). Numbers aren't necessarily contiguous (the paper itself has gaps); that's expected. |
| `Section Number` | The paper's section reference (e.g. `3.1.1`), shown on the problem detail page. |
| `Target(s)` | One of: `Data`, `Compute`, `Model & Algorithms`, `Deployment`, `All` (cross-cutting). Second-level grouping on the home page. |
| `Capacity` | One of: `Assessment`, `Access`, `Verification`, `Security`, `Operationalisation`, `Ecosystem Monitoring`. Top-level grouping on the home page. |
| `Problem Area (from Problem Areas)` | A finer sub-category (e.g. "Identification of Problematic Data"). Third-level grouping, under Target. |
| `Existing work & resources` | Citations relevant at time of publication, semicolon-separated. Shown on the problem detail page. |
| `Relevant expertise` | Disciplines useful for this problem (e.g. `Cryptography`, `ML Theory`). Shown as chips and offered as a filter facet on the home page. |
| `New work (since publication)` | Citations for follow-up work since the paper published. |

### 2. `OpenTAIG` sheet — our mappings & tool catalog

Two tabs, named **`map`** and **`tools`**.

**`map` tab** — one row per annotated question, joined to the `TAIG` sheet by
`RQ_No`:

| Column | Meaning |
|---|---|
| `RQ_No` | Join key — must match a `Question number (in paper)` value in the `TAIG` sheet. |
| `Research_Question` | **Ignored by the build.** A human-only aid so whoever is filling in a row can see which question they're annotating without cross-referencing the `TAIG` sheet — the site always displays the question text from the `TAIG` sheet instead. |
| `RGAF` | Matching [LF AI & Data RGAF](https://lfaidata.foundation/rgaf/) dimension(s). |
| `EU_AI_Act` | Matching EU AI Act article/obligation(s). |
| `UNESCO` | Matching UNESCO Ethics of AI principle(s). |
| `ASEAN` | Matching ASEAN AI Governance & Ethics guide principle(s). |
| `CoE` | Matching CoE Framework Convention on AI article(s). |
| `Tools` | Open-source tool **ids** that help address this question (see the `tools` tab below). |

**Multiple values in one cell → separate with a semicolon `;`, not a comma.**
Many canonical terms already contain commas (e.g. *"Robust, Reliable & Safe"*,
*"Article 15 (Accuracy, robustness and cybersecurity)"*), so commas can't
double as the list separator without ambiguity. Example:

```
Robust, Reliable & Safe; Transparent & Explainable
```

Leave a mapping cell **blank** if there's no match. `Tools` cell example,
referencing two tool ids from the `tools` tab:

```
scancode-toolkit; fossology
```

A `map` row whose `RQ_No` doesn't match any `TAIG` row (a typo, or a question
renumbered/removed upstream) is skipped with a build warning, not a failure.
A `TAIG` row with no matching `map` row is normal — it just has no mappings
or tools yet.

**`tools` tab** — the open-source tool catalog, one row per tool, defined
**once** and referenced by id from as many `map` rows as apply, so tool
metadata never drifts out of sync across multiple mentions:

| Column | Meaning |
|---|---|
| `id` | Short unique identifier, referenced from `map.Tools` (e.g. `scancode-toolkit`). |
| `name` | Display name. |
| `summary` | One or two sentence description. |
| `license` | **SPDX License ID** (e.g. `Apache-2.0`, `MIT`, `GPL-2.0-or-later`) — see [spdx.org/licenses](https://spdx.org/licenses/). |
| `homepage` | Project homepage URL. |
| `source` | Source code repository URL. |
| `documentation` | Documentation URL. |
| `funding` | Funding/sponsorship URL, if any. |

(These four URL columns reuse the well-known
[Python Project-URL labels](https://packaging.python.org/en/latest/specifications/well-known-project-urls/),
so the schema isn't inventing its own vocabulary.) Leave any column blank if
not applicable — the site simply omits blank fields.

### Identifying a tab

Each source in [`config.yaml`](config.yaml) is looked up by **`sheet_name`**
— the tab's visible name, exactly as shown on the tab at the bottom of the
Google Sheets window (e.g. `map`, `tools`). This is preferred over the
older `gid` (a tab's opaque numeric id, found after `#gid=` in the tab's
URL): a wrong `sheet_name` is easy to spot, while a wrong `gid` just
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
under `data.taig` / `data.mapping` / `data.tools` in `config.yaml` (or a copy
of it) to point at a local CSV instead of a URL — see
[`tests/config.local.yaml`](tests/config.local.yaml) for a working example
against the fixtures in `tests/fixtures/`.

## One-time GitHub Pages setup

In the repo settings: **Settings → Pages → Build and deployment → Source →
GitHub Actions**. After that, every workflow run publishes `site/` directly;
no `gh-pages` branch is used.

## Repository layout

```
config.yaml          site title, sheet ids + tab gids, column names, taxonomy order
frameworks.yaml       fallback vocabulary for legacy comma-separated cells
build.py              fetch (taig + map + tools) -> join by RQ_No -> render
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
