# OpenTAIG

Static site: Jinja2 + Python. `build.py` → `templates/*.html` → `site/`
(gitignored, regenerated every run). No backend, no database — three
Google Sheets are the only editable source of truth.

```bash
python build.py            # cached fetch (fast, dev loop)
python build.py --no-cache # fresh fetch (use before trusting a "is X fixed now" check)
```

## Standing rules (never violate without being told to)

- **Never edit the Google Sheets directly.** All data changes happen in
  the sheets by a human; `build.py` only reads them.
- **Never commit.** The user does all git operations manually.
- **No dead CSS.** Before deleting a selector, `grep` its usage across
  `templates/` and `assets/app.js` (watch for dynamically-built Jinja
  classes, e.g. `chip-badge-{{ entry.badge_level_class }}` — a plain-text
  grep misses those; check the template source, not just literal strings).
  Delete confirmed-unused rules rather than leaving them.
- **British English everywhere** — site copy, templates, and docs (code
  identifiers, CSS custom properties, data field names, URLs stay
  as-is): colour, licence (noun) vs license (verb), catalogue, organise,
  recognise, favour, behaviour, centre, labelled, grey. See "Writing
  style" in `docs/development.md`.

## Key files

| File | What it's for |
|---|---|
| `build.py` | Everything: fetch → join → precompute → render. Read `build_quality_display()`/`freshness_parts()`/`select_highlighted_problems()` before adding template logic — the convention here is **precompute in Python, keep templates dumb** (blank-guarded, join-ready lists, never date math or number formatting in Jinja). |
| `config.yaml` | Site title/tagline/description, sheet ids + tab names, column-name mapping, taxonomy order. Column names must match sheet headers exactly. |
| `templates/_filter_macros.html` | Shared `disclosure_header()` macro — `tools_index.html` and `problems_index.html`'s filter bars must stay structurally identical (Search always visible with its own scoped Reset; other facet groups individually collapsible, each with its own scoped Reset). |
| `templates/_matrix.html` / `_matrix_compact.html` | Landscape page's full matrix / the compact per-RQ mini-heatmap reused atop Explorer and Tools listings. |
| `assets/style.css` | Lumina design system — CSS custom props, light/dark via `prefers-color-scheme`. Chip system: `.chip` base + `.chip-ns` label prefix (`Label: value` grammar). |
| `assets/app.js` | Vanilla JS, no build step. `enhanceMultiselect()`/`resetMultiselectsIn()` are the shared dropdown-facet machinery — reuse them, don't hand-roll a new dropdown. |
| `docs/development.md` | **Read this first for anything UI/behaviour-related** — the Notes section documents current structure in detail and must be kept in sync with any structural change. |
| `docs/data-schema.md` | Authoritative sheet schema — every tab, every column, the `tools`/`tool_metadata` precedence rule. |
| `curation/README.md` | Tool-discovery pipeline (search → judge → map to RQs). |

## Data model gotchas

- **`tools` vs `tool_metadata` precedence**: every project-quality field
  (stars, license, OpenSSF scores, ...) can be set in either tab. A
  non-blank `tools` cell always wins; the literal token `none` forces
  blank; otherwise `tool_metadata`'s (100% machine-written) value is used.
  Never assume a field is always populated — most are legitimately blank
  far more often than not.
- **Freshness is tracked twice, never merged**: `tool.freshness` (the
  `tools` tab's own curation bookkeeping) and `tool.metadata_freshness`
  (the collector's, blank if the tool has no `tool_metadata` row yet) stay
  two distinct `Freshness(added, checked, updated)` records everywhere,
  including in the UI (`.tool-freshness` on the tool detail page).
- **`data.json`'s provenance is mixed, not one licence for the whole
  file**: problem text/taxonomy is from the upstream TAIG database (its
  own terms apply); tool metadata is aggregated third-party data
  (OpenSSF, ecosyste.ms, each repo's own public data); only the
  problem↔tool and problem↔framework mapping work is original OpenTAIG
  curation (CC0-1.0). See the `sources` object in `data.json` itself and
  the About page's Data section before assuming anything here is
  OpenTAIG's to relicense.

## Accessibility (WCAG 2.2)

Non-negotiable on every change, not just when explicitly asked:
keyboard-navigable, screen-reader-friendly labelling, no colour-only
signalling, and check contrast for anything on a coloured surface —
`a:visited`'s default colour is illegible on some chip backgrounds, which
is why `assets/style.css`'s `a:visited:not(.chip):not(...)` exclusion
chain exists. Any **new** coloured-surface link class needs adding to
that same chain.

## Verification workflow

`python build.py` → serve `site/` locally → check in-browser (visual +
keyboard tab order + a screen-reader-relevant DOM check, not just
"looks right") → link-integrity check (regex over every generated
`href`, expect 0 broken — re-run with `--no-cache` first if you're
verifying a just-fixed data issue, since a stale local cache can show
phantom breakage or phantom fixes).
