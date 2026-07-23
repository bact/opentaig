# OpenTAIG

A community-maintained catalog of **open problems in technical AI governance**,
each mapped to relevant principles/regulations and linked to open-source tools
that help address it. Inspired by Stanford's
[TAIG database](https://taig.stanford.edu/taig_database.html) and the paper
[*Open Problems in Technical AI Governance*](https://arxiv.org/abs/2407.14981)
(Reuel, Bucknall, et al., 2025).

The site is **fully static**, hosted on **GitHub Pages**, and generated from a
**Google Sheet** once per build. There is no backend and no database — the
sheet is the only editable source of truth, and everything else lives in this
repo.

## How it works

```
Google Sheet  --(CSV export, fetched once per build)-->  build.py  -->  site/  -->  GitHub Pages
```

`build.py` fetches two tabs from the sheet, normalizes them into a set of
"open problem" records, and renders the static site with Jinja2 templates.
It runs in GitHub Actions:

- **Manually**, any time, via the *Run workflow* button on the
  `Build and deploy site` workflow (Actions tab).
- **Automatically**, every 2 months (1st of Jan/Mar/May/Jul/Sep/Nov, 03:00 UTC).
- On every push to `main` (so merged content/template changes go live right away).

No secrets are needed: the sheet is read via its public CSV export URL, so it
must stay shared as **"Anyone with the link" (Viewer)**.

## Editing the data

Edit the Google Sheet — nothing else. The next build (manual or scheduled)
picks up your changes; the site is never read live, so edits don't appear
until a build runs.

The workbook has **two tabs**:

### 1. `Questions` tab — the open problems

| Column | Meaning |
|---|---|
| `Question` | The open problem itself. This is the spine of the site — every other column describes it. |
| `Capacity` | One of: `Assessment`, `Access`, `Verification`, `Security`, `Operationalization`, `Ecosystem Monitoring`. Used as the top-level grouping on the home page (mirrors the TAIG paper's taxonomy). |
| `Target` | One of: `Data`, `Compute`, `Models`, `Deployment`. Used as the sub-grouping under each Capacity. |
| `RGAF` | Matching [LF AI & Data RGAF](https://lfaidata.foundation/rgaf/) dimension(s). |
| `EU_AI_Act` | Matching EU AI Act article/obligation(s). |
| `UNESCO` | Matching UNESCO Ethics of AI principle(s). |
| `ASEAN` | Matching ASEAN AI Governance & Ethics guide principle(s). |
| `CoE` | Matching CoE Framework Convention on AI article(s). |
| `Tools` | Open-source tool **ids** that help address this question (see the `Tools` tab below). |

**Multiple values in one cell → separate with a semicolon `;`, not a comma.**
Many canonical terms already contain commas (e.g. *"Robust, Reliable & Safe"*,
*"Article 15 (Accuracy, robustness and cybersecurity)"*), so commas can't
double as the list separator without ambiguity. Example:

```
Robust, Reliable & Safe; Transparent & Explainable
```

Leave a mapping cell **blank** if there's no match — don't write "Unmapped"
(either works, but blank is cleaner).

`Tools` cell example, referencing two tool ids from the `Tools` tab:

```
scancode-toolkit; fossology
```

### 2. `Tools` tab — the open-source tool catalog

One row per tool, defined **once** and referenced by id from as many
`Questions` rows as apply — this keeps tool metadata from drifting out of
sync across multiple mentions.

| Column | Meaning |
|---|---|
| `id` | Short unique identifier, referenced from `Questions.Tools` (e.g. `scancode-toolkit`). |
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

### Finding a tab's `gid`

Open the tab in Google Sheets and look at the URL: the number after `#gid=`
is that tab's `gid`. Both gids are configured in [`config.yaml`](config.yaml)
under `data.questions.gid` / `data.tools.gid` — update them there if you add
the `Tools` tab for the first time or reorder tabs.

## Running a build locally

```bash
pip install -r requirements.txt
python build.py
```

This writes the full site to `site/` (git-ignored). Open `site/index.html`
in a browser to preview.

For offline development without hitting Google Sheets, set a `file:` path
under `data.questions` / `data.tools` in `config.yaml` (or a copy of it) to
point at a local CSV instead of a URL.

## One-time GitHub Pages setup

In the repo settings: **Settings → Pages → Build and deployment → Source →
GitHub Actions**. After that, every workflow run publishes `site/` directly;
no `gh-pages` branch is used.

## Repository layout

```
config.yaml         site title, sheet id + tab gids, column names, taxonomy order
frameworks.yaml      fallback vocabulary for legacy comma-separated cells
build.py             fetch -> parse -> normalize -> render
data/seed_taxonomy.csv  optional question -> Capacity/Target fallback (sheet always wins)
templates/           Jinja2 templates
assets/              CSS + vanilla JS (client-side search/filter, no network calls)
.github/workflows/build.yml  the build + deploy pipeline
```

## Notes

- If the sheet is ever made private, swap the CSV-export fetch in
  `fetch_source()` (`build.py`) for the Google Sheets API with a service
  account key stored as a GitHub Actions secret.
- Problem detail pages URLs are derived from the question text
  (slug + short stable hash). Editing a question's wording changes its URL.
