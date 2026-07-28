# Development

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
[`tests/config.local.yaml`](../tests/config.local.yaml) for a working
example against the fixtures in `tests/fixtures/`.

## One-time GitHub Pages setup

In the repo settings: **Settings → Pages → Build and deployment → Source →
GitHub Actions**. After that, every workflow run publishes `site/` directly;
no `gh-pages` branch is used.

## Repository layout

```text
config.yaml          site title, sheet ids + tab names, column names, taxonomy order
build.py              fetch (taig + map + tool_map + tools + terms + framework) -> join by rq_no/id -> render
templates/            Jinja2 templates
assets/               CSS + vanilla JS (client-side search/filter, no network calls)
tests/fixtures/       local CSV fixtures for offline build verification
curation/             tool-discovery pipeline -- see curation/README.md
docs/                 this directory: schema reference, development notes, and other design/planning docs
.github/workflows/build.yml  the build + deploy pipeline
```

See [`docs/data-schema.md`](data-schema.md) for the full Google Sheets
schema and [`curation/README.md`](../curation/README.md) for the
tool-discovery pipeline.

## Notes

- The home page groups problems **Capacity → Target → Problem Area**,
  mirroring the paper's own section structure. `Relevant expertise` is a
  filter facet (like the frameworks) but doesn't get its own browse page.
- If a sheet is ever made private, swap the CSV-export fetch in
  `fetch_source()` (`build.py`) for the Google Sheets API with a service
  account key stored as a GitHub Actions secret.
- Problem detail page URLs are derived from the question text
  (slug + short stable hash). Editing a question's wording changes its URL.
