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
`data.tool_metadata` / `data.terms` / `data.framework` in `config.yaml` (or
a copy of it) to point at a local CSV instead of a URL — see
[`tests/config.local.yaml`](../tests/config.local.yaml) for a working
example against the fixtures in `tests/fixtures/`.

## One-time GitHub Pages setup

In the repo settings: **Settings → Pages → Build and deployment → Source →
GitHub Actions**. After that, every workflow run publishes `site/` directly;
no `gh-pages` branch is used.

## Repository layout

```text
config.yaml          site title, sheet ids + tab names, column names, taxonomy order
build.py              fetch (taig + map + tool_map + tools + tool_metadata + terms + framework) -> join by rq_no/id -> render
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

## Writing style

Use British English spelling throughout the site's copy (templates, chip
labels, error/empty-state text, etc.) and in project documentation —
e.g. "colour" not "color", "organise"/"recognise" not "organize"/"recognize",
"licence" (noun) vs. "license" (verb), "behaviour", "centre". Code
identifiers (CSS custom properties, Python/JS names, data field names) are
unaffected and stay as-is even where they use American spelling already.

## Notes

- **Visited-link color policy**: the global `a:visited` rule
  (`assets/style.css`) excludes every link that is its own colored surface
  -- chips (`.chip`, covers badge/scorecard/licence/language/framework-term/
  doc-checklist/...), `.tool-problem-chip`, `.matrix-cell`,
  `.mini-heatmap-cell`, `.button-primary`, `.skip-link` -- via one
  `:not(...)` chain, rather than a per-component override repeating each
  one's own color (confirmed unreadable in practice: a visited OpenSSF
  badge chip rendered orange text on a dark moss-green background). Any
  **new** colored-surface link class needs adding to that same exclusion
  list; a plain-text link on the page's own background (citation list,
  breadcrumbs, tool-detail links, the tool card's own name link, ...)
  doesn't need anything -- the visited color is safe there and left as an
  intentional "you've already opened this" cue.
- Chip sizing: `.chip` and `.chip-ns` (the small uppercase "Label:" prefix
  used by licence/language/badge/scorecard chips) both pin their own
  `line-height` rather than inheriting the body's tall `1.55` -- a chip
  carrying a smaller nested `.chip-ns` span mixes two font sizes on one
  inline line, which under the inherited line-height rendered visibly
  taller than a plain single-size chip (e.g. tool-type) sitting next to it
  in the same row. `.chip-license`/`.chip-language` use the regular sans
  font, not `--font-mono` -- monospace was tried for the licence chip
  (it's an SPDX identifier, arguably ID-like) but dropped in favor of
  matching every other chip, once it was clear mixing font-families
  per-chip was adding complexity for very little payoff.
- `/` is the Landscape page: a Capacity x Target coverage matrix (`_matrix.html`,
  built by `build_matrix()`), linking into `/problems/`. The problem listing
  itself ("Explorer") groups problems **Capacity → Target → Problem Area**,
  mirroring the paper's own section structure, and repeats the same matrix
  (compact, filters below don't affect it) above its filter bar.
  `Relevant expertise` is a filter facet (like the frameworks) but doesn't
  get its own browse page.
- The compact mini-heatmap (`_matrix_compact.html`, atop the Explorer and
  Tools listing pages) prints each target column name once, in a shared
  header row, rather than repeating it inside every capacity row — a second
  header row (labelled "All") separates Operationalisation / Ecosystem
  Monitoring from the four core-target rows above them, since those two
  capacities don't break down by target. Both mini-heatmap cells and the
  full Landscape matrix's cells (`.matrix-cell`) top-align their content
  (`justify-content: flex-start`), so a cell's count/caption sits at a fixed
  position regardless of how many lines its wrapped text below takes.
- Each tool card on `/tools/` shows up to 3 of its mapped problems as
  clickable chips ("Problems addressed:"), chosen to diversify across
  Capacity/Target and to balance Evaluate/Implement problem types, with
  "+N more problems" for the remainder. Selection lives in
  `select_highlighted_problems()` in `build.py`, alongside `first_words()`,
  which truncates a problem's question to the chip's character budget on a
  word boundary (never mid-word).
- Project-quality/community-health tool fields (`stars` through
  `openssf_scorecard_vulnerabilities`) live in a separate `tool_metadata`
  spreadsheet, 100% written by `curation/collect_project_metadata.py`, not
  hand-edited. The same field names also exist in `tools` as an optional
  human override (`build.py`'s `apply_tool_metadata()`/
  `resolve_metadata_field()`): a non-blank `tools` cell always wins, the
  literal text `none` forces blank, otherwise `tool_metadata`'s value is
  used. See "`tools` / `tool_metadata` precedence" in
  `docs/data-schema.md` for the full rule and why it's split this way
  (permission isolation for a future write-automation credential).
- Project-quality/community-health display, both driven by that same
  `tool_metadata` data:
  - **Tool card** (`tools_index.html`): everything lives in one
    `.tool-list-head` row now -- name (`.tool-list-name`, deliberately
    styled bigger/bolder than the rest of the row so it doesn't get lost
    among all the chips), role, then labeled chips (`License: MIT`,
    `Language: Python, C++` -- one combined chip for every language, not
    one per language) each using the same `chip-ns` "label: value" grammar
    as the OpenSSF chips (`OpenSSF Best Practices: Gold`, `OpenSSF
    Scorecard: 5.0`), then the plain-text stats line
    (stars/contributors/latest-release-relative, "&middot;"-joined, each
    token independently blank-guarded) pushed to the row's far end with
    `margin-left: auto` (same technique as the site nav's trailing GitHub
    link) so it reads as a secondary glance-signal, not competing with the
    identity/quality chips. No separate row for any of this -- the summary
    flows directly into "Problems addressed" below it. Badge/Scorecard
    color buckets (in_progress/passing/silver/gold and low/4-6.9/&ge;7)
    all reuse the exact same neutral -> moss-soft -> moss -> moss-ink ramp
    `_matrix.html` uses for coverage -- one hue family, increasing
    saturation = increasing goodness, deliberately not color-per-tier
    (an earlier ochre/gold choice read as a caution color, not "best").
    All of this is precomputed per-tool in `build_quality_display()`
    (`build.py`) -- date math (`relative_date()`) and count abbreviation
    (`format_count()`, e.g. `27400` -> `"27.4k"`) never happen in the
    template. The Tools filter bar's "Filter by project quality" section
    facets on OpenSSF Best Practices badge level (a multiselect dropdown,
    same `.multiselect`/`enhanceMultiselect()` machinery as every other
    dropdown facet on the site -- not bare checkboxes) and Scorecard score
    (a `&ge;4`/`&ge;7` threshold `<select>`, since it's a continuous value,
    not a category) -- both read `data-badge-level`/`data-scorecard-score`
    off each `.tool-list-item` in `app.js`. The card's `data-search` also
    folds in `tool.keywords`, so a tool matches search on its GitHub
    topics even though the card never displays them.
  - **Tools filter bar shape matches Problems page's** (Search always
    visible with its own scoped Reset; other facet groups individually
    collapsible, each with its own scoped Reset -- not one master Show/Hide
    over the whole bar, and not one global Reset). `disclosure_header()`
    (the Show/Hide section-header macro) now lives in
    `templates/_filter_macros.html`, imported by both `problems_index.html`
    and `tools_index.html`, so the two bars can't structurally drift again.
    The result count (`N of M shown`) sits inline next to the "Search"
    section title on both pages now (`.filter-count`, deliberately smaller/
    unbolded/non-uppercase so it reads as a live annotation, not a second
    label competing with "Search"), not on its own line below the search
    row. `.filter-field` (every dropdown/select's label+control wrapper) is
    a fixed `flex: 0 0 220px`, not `min-width` -- a field with a long label
    (e.g. "UNESCO Recommendation on the Ethics of AI") would otherwise
    render wider than its siblings and desync the columns once fields wrap
    onto a second row; fixed width makes every field a true grid column
    (long labels wrap within it instead), matching row-to-row and
    column-to-column across "Filter by frameworks & principles"' six
    dropdowns.
  - License/Language chips on the tool card are real links to
    `/tools/?license=MIT` / `/tools/?language=Python,C%2B%2B`
    (comma-joined, URL-encoded, OR-matched against `data-license`/
    `data-language` -- pipe-delimited `"|Python|C++|"`, same convention
    Problems page's "pipe" facet type already uses, so `license` can go
    multi-valued later without touching the matching logic). Read once
    from `location.search` on page load in `app.js` (not tied to any
    checkbox -- open-ended cardinality, unlike the 4-value badge facet),
    showing a dismissible `.active-filter-banner` so it's obvious why the
    list is narrowed (no section to auto-expand for this any more -- Search,
    where the resulting count shows, is always visible). The banner sits
    outside the collapsible section bodies (stays visible regardless of
    which of those are expanded) and gets its own top `border-radius`
    rather than `overflow: hidden` on `.filter-bar`, since that class is
    shared with Problems page's absolute-positioned multiselect dropdowns,
    which `overflow: hidden` would clip. The Tool *detail* page's own
    license chip stays pointed at its SPDX reference
    (`spdx.org/licenses/...`) -- deliberately not this same filter-link,
    since "what does this license mean" is the relevant question there,
    vs. "show me other tools with it" from the listing card.
  - **Tool detail page** (`tool.html`): a fixed-order, fixed-label,
    always-all-slots "Project health" checklist for 10 fields (Homepage/
    Source/Documentation/README/License file/Contributing guide/Code of
    conduct/Security policy/Governance/Funding) plus `sbom_url`/`paper_url`
    appended present-only (no ghost) since only the fixed 10 are meant to
    flag absence. Present is a real `<a class="chip-doc-present">` link;
    absent is a `<span class="chip-doc-missing">` (dashed ghost,
    deliberately *not* a link, so keyboard users don't tab through dead
    stops) with a `visually-hidden` "(not published)" suffix -- link-vs-span
    carries the state for screen readers, not color alone, same idiom as
    `_solution_table.html`'s `solution_cell()`. The SPDX license chip
    (`chip-license`) is itself the link to `spdx.org` now (no separate
    "(license text)" link).
- If a sheet is ever made private, swap the CSV-export fetch in
  `fetch_source()` (`build.py`) for the Google Sheets API with a service
  account key stored as a GitHub Actions secret.
- Problem and tool detail pages use directory-style URLs: `/problems/<rq_no>-<slugified
  question>/` and `/tools/<tool-id>/` (each a directory containing its own
  `index.html`), so links display without a `.html` suffix. `rq_no` is the
  stable id (the sheet's own question number), so editing a question's
  wording doesn't change its URL. The Tools listing itself repeats the same
  matrix component, and its own listing lives at `/tools/`.
