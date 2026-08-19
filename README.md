---
SPDX-FileCopyrightText: 2026 OpenTAIG authors
SPDX-FileType: SOURCE
SPDX-License-Identifier: CC0-1.0
---

# OpenTAIG

A catalogue of open-source tools mapped to open problems in technical AI
governance, and linked to the regulations and ethical principles they help
address.

Maintained by [Arthit Suriyawongkul](https://github.com/bact).

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
three separate Google Sheets documents once per build — `TAIG` (the
upstream question set), `OpenTAIG` (our own framework mappings + tool
catalogue), and `OpenTAIG-auto` (auto-collected project-quality data for each
tool, kept in its own document so a future automation credential can be
scoped to write only there — see "The three documents" in
[`docs/data-schema.md`](docs/data-schema.md) for each one's URL). There is
no backend and no database: these documents are the only editable source of
truth, and everything else (including the site itself) is generated from
them.

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
python -m http.server 8000 -d site
```

then open `http://localhost:8000`. See
[`docs/development.md`](docs/development.md) for offline development
against local fixtures, and repo/deployment setup.

## Documentation

- [`docs/methodology-and-findings.md`](docs/methodology-and-findings.md) — how
  the catalogue was built, what it found, and what it didn't: coverage results,
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

Data: [CC0 1.0 Universal][cc0] (public domain).

See details at the site's [About][about-data] page.

[cc0]: https://creativecommons.org/publicdomain/zero/1.0/
[about-data]: https://bact.github.io/opentaig/about/#data

## Citation

If you use this catalogue in academic or other work, please cite it as:

> Suriyawongkul, A. (2026). OpenTAIG: A catalogue of open-source tools
> mapped to open problems in technical AI governance and linked to
> relevant principles and regulations [Data set]. GitHub.
> https://github.com/bact/opentaig

```bibtex
@misc{opentaig,
  author = {Suriyawongkul, Arthit},
  title  = {OpenTAIG: A catalogue of open-source tools mapped to open
            problems in technical AI governance and linked to relevant
            principles and regulations},
  year   = {2026},
  url    = {https://github.com/bact/opentaig},
  note   = {Accessed: YYYY-MM-DD}
}
```

This repository also carries a [`CITATION.cff`](CITATION.cff) file, so
GitHub can generate a citation in your preferred format automatically —
look for "Cite this repository" in the sidebar of the repo page. See the
site's [About][about-data] page for the same citation, always generated
fresh against the current year.
