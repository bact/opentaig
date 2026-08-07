---
SPDX-FileCopyrightText: 2026 OpenTAIG authors
SPDX-FileType: SOURCE
SPDX-License-Identifier: CC0-1.0
---

# OpenTAIG

A catalog of open-source tools mapped to open problems in technical AI
governance, and linked to the regulations and ethical principles they help
address.

Inspired by the
[Open Problems in Technical AI Governance database][taig-db]
and
[Putting Responsible Generative AI Framework to Work blog post][putting-rgaf].

We are committed to making this website accessible by adhering to
[Web Content Accessibility Guidelines (WCAG) 2.2][wcag] guidelines and
supporting full keyboard navigation.
While we continually strive to improve accessibility, we recognise there are
areas that still need attention. If you encounter any barriers or experience
difficulty navigating the site, please open an issue so we can address them.

[taig-db]: https://taig.stanford.edu/taig_database.html
[putting-rgaf]: https://lfaidata.foundation/communityblog/2026/04/22/putting-rgaf-to-work-build-and-audit-responsible-ai-with-open-source/
[wcag]: https://www.w3.org/TR/WCAG22/

## How it works

The site is **fully static**, hosted on **GitHub Pages**, and generated from
three Google Sheets once per build — the upstream TAIG question set, our own
framework mappings + tool catalog, and auto-collected project-quality data
for each tool (kept in its own sheet so a future automation credential can
be scoped to write only there). There is no backend and no database: the
sheets are the only editable source of truth, and everything else
(including the site itself) is generated from them.

The build runs automatically in GitHub Actions (on every push to `main`,
and on a schedule), or can be triggered manually from the Actions tab.

## Quick start

```bash
pip install -r requirements.txt
python build.py
```

Writes the site to `site/` (git-ignored) — open `site/index.html` to
preview, or serve it so relative links behave like the deployed site:

```bash
python3 -m http.server 8000 -d site
```

then open `http://localhost:8000`. See
[`docs/development.md`](docs/development.md) for offline development
against local fixtures, and repo/deployment setup.

## Documentation

- [`docs/methodology-and-findings.md`](docs/methodology-and-findings.md) — how
  the catalog was built, what it found, and what it didn't: coverage results,
  the harm-taxonomy completeness check, and stated limitations.
- [`docs/data-schema.md`](docs/data-schema.md) — the full Google Sheets
  schema: every tab, every column, how they join.
- [`curation/README.md`](curation/README.md) — the tool-discovery pipeline:
  how candidate tools are found, judged, and mapped to research questions.
- [`docs/development.md`](docs/development.md) — local builds, GitHub Pages
  setup, and repository layout. `docs/` is also where other project
  documentation (design notes, plans, agent handover docs) lives as it's
  written.

## Editing the data

Edit the Google Sheets — nothing else. `build.py` never writes to them, and
the next build (manual or scheduled) is what picks up your changes.

## License

Code: [Apache License 2.0](LICENSE).

Data (the catalog itself — open problems, tool mappings, and
project-quality/community-health fields, published as `data.json` at the
built site's root, linked from its About page):
[CC0-1.0](https://creativecommons.org/publicdomain/zero/1.0/), public
domain.
