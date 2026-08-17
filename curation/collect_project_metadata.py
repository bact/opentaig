#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2026 OpenTAIG authors
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Collect project-quality / community-health metadata for the
`tool_metadata` tab -- the only tab in `OpenTAIG-auto`, a separate Google
Sheets document from the main `OpenTAIG` one (see "The three documents" in
docs/data-schema.md for each document's URL), 100% written by this script,
joined onto `tools` by `id` at build time (see "tools / tool_metadata
precedence" in build.py and docs/data-schema.md).
GitHub-only for now (GitLab/Codeberg would need their own fetch functions;
no tool in the catalog is hosted there yet, so they aren't built
speculatively -- see the module docstring bottom for what that would take).

Because of this, `tool_metadata` can legitimately have **fewer rows than
`tools`** -- any `tools` row whose `source` isn't a resolvable GitHub URL
(`extract_repo_path()` returns None for it) has nothing here to collect
from and simply gets no `tool_metadata` row at all; see `unresolvable_
source` below. Confirmed today: `aiaaic-repository`'s `source` is a Google
Sheet, not a repo. Expect this gap to widen for now as tool discovery
expands beyond GitHub (arXiv papers, other forges, specs with no code
repo at all -- see docs/methodology-and-findings.md § 6 future work) --
not a sign of a missed collection run or a bug. Not necessarily permanent,
though: an aggregator API like ecosyste.ms (see "Prior art: CHAOSS" in
curation/README.md) indexes many non-GitHub registries and forges, so a
future collector built against it could shrink this gap back down for
sources it covers -- not built yet, just worth keeping in mind rather than
assuming GitHub-only is the permanent ceiling.

Read-only against both live sheets: only ever *reads* `site/data.json` (the
last local `python build.py` output) and public read APIs, and writes a
CSV -- it never touches either Google Sheet directly. Because `tool_metadata`
is machine-owned (no hand edit ever lives there -- overrides for any field
always go in `tools` instead, resolved by build.py's precedence rule, not
here), the CSV this script writes is safe to paste in as a **full
replacement** of the tab's contents, not a cell-by-cell merge -- there is
nothing to preserve. Folds in what used to be a separate script,
`backfill_programming_language.py` (removed): `programming_language` comes
free from the same repo-core API call already made for stars/forks/etc.,
so a dedicated script for just that one field was redundant once this one
existed.

Sources -- one repo costs ~18 GitHub API calls in the common case (GitHub's
own language/license detection trusted directly, no package-manifest
probing needed) up to ~28 in the worst case (that detection was blank or
implausible, see NON_IMPLEMENTATION_LANGUAGES) + 3 third-party calls
(bestpractices.dev, scorecard.dev, sponsors.ecosyste.ms -- the last one
cached per repo *owner*, so it's often free for a tool sharing an org with
one already processed this run) + local (no-network-per-call) license text
matching via `licenseid`, all confirmed by hand against real repos before
this script was written, not assumed from documentation:

  - `GET /repos/{owner}/{repo}` -> stars (`stargazers_count`), forks
    (`forks_count`), watchers (`subscribers_count` -- NOT `watchers_count`,
    which has been a silent alias for `stargazers_count` since GitHub folded
    "Watch" into "Star"), open_issues_count (`open_issues_count`; GitHub
    conflates open PRs into this count, a known quirk, not a bug in this
    script), last_commit_date (`pushed_at`, date part only), and
    `default_branch` (needed by several probes below). Also returns
    `license` (`license.spdx_id`, "" if `NOASSERTION`) and
    `programming_language` (`language`, GitHub's single dominant-by-bytes
    guess) -- but for both, this is now the **last-resort fallback**, not
    the primary source; see the dedicated bullet below for why and what
    supersedes it.
  - `GET /repos/{owner}/{repo}/contributors?per_page=1&anon=true` ->
    approximate contributor count from the `Link: rel="last"` page number
    (paginating 1-per-page makes the last page number equal the count). A
    bus-factor proxy, not exact -- bots and one-line-fix drive-bys count
    the same as core maintainers.
  - `GET /repos/{owner}/{repo}/releases?per_page=1` -> releases_count (same
    Link-header trick) and latest_release_date (`published_at` of the one
    release returned).
  - `GET /repos/{owner}/{repo}/community/profile` -> readme_url,
    license_url, code_of_conduct_url, contributing_url (each an
    `html_url` under `files.*`). Does NOT reliably include a security
    policy (confirmed empty on a repo that has one) -- see below. Also:
    when GitHub's own license detector can't classify a repo (`spdx_id`
    "NOASSERTION"), `files.license.html_url` is unreliable -- confirmed on
    a real catalogued tool, where it pointed at an unrelated TOML data
    file, not any license file. Same blind spot as F3 in
    docs/methodology-and-findings.md, hitting the URL field instead of the
    SPDX id this time; this script discards it (leaves `license_url` blank
    with a warning) rather than record the junk value.
  - Security policy / governance: GitHub's community profile API doesn't
    reliably surface either, so both are a best-effort fallback probe of
    `GET /repos/{owner}/{repo}/contents/{path}` over a short list of
    well-known paths, first 200 wins. Blank if none exist -- doesn't rule
    out either living somewhere non-standard.
  - SBOM: GitHub auto-generates an SPDX SBOM from the dependency graph for
    every public repo with it enabled (confirmed 200 on a repo that never
    published its own SBOM file) -- `sbom_url` is the API endpoint itself
    (`/repos/{owner}/{repo}/dependency-graph/sbom`), which returns the SBOM
    JSON directly; fetching it needs the same GitHub auth as any other API
    call here (no separate browsable page confirmed to exist). Recorded
    only if that endpoint returns 200 -- most repos have it, some (very
    old, or dependency graph disabled) don't.
  - `.github/FUNDING.yml`, `pyproject.toml` (`[project.urls]`, matched
    case/punctuation-insensitively against the PyPA well-known label
    "Funding" -- confirmed against pandas (`funding`, lowercase) and pytest
    (`Funding`, both real examples)), and `codemeta.json` (`funding` field,
    when itself URL-shaped) are all tried for a `funding` URL, written to
    `tool_metadata` unconditionally -- "should this override a value
    someone typed in `tools`" is answered later, by build.py's precedence
    rule, not here. First source with a hit wins, in that order; every
    candidate found across all three is still logged so a human can see
    what was passed over. `FUNDING.yml`'s own platform keys (`github`,
    `patreon`, `open_collective`, `ko_fi`, `tidelift`, `custom`, etc.) are
    mapped to their canonical URLs; `custom` entries are used as-is.
  - `codemeta.json` (rarer in this catalog's domain -- common in the
    R/rOpenSci ecosystem, confirmed present on ropensci/drake as a real
    example whose shape this script's parsing was checked against) also
    supplies: `funder` (the `funder` field's organization/person name(s),
    a distinct concept from `funding` per CodeMeta's own vocabulary --
    *who* funded it vs *a URL to fund/cite it*), `development_status`
    (CodeMeta's `developmentStatus`, typically a repostatus.org or
    tidyverse-lifecycle URL -- a maturity signal this catalog didn't have
    before), and one of the two sources for `paper_url` / `software_heritage_id`
    below.
  - `CITATION.cff` (common in this catalog's domain -- confirmed present on
    scikit-learn, deepchecks, pythainlp) supplies `paper_url` (from
    `preferred-citation.doi`, else `.url`) and `software_heritage_id` (from
    a top-level `identifiers` entry with `type: swh`) when codemeta.json
    doesn't already have them. `paper_url` -- the DOI or URL of an academic
    paper describing the tool, when one exists -- checks codemeta's own
    `citation[].url` first, since a repo can carry both files and
    CodeMeta's `citation` block is the more structured of the two.
  - `license` / `programming_language`: GitHub's own repo-core detection
    (above) is wrong often enough to matter for this catalog's domain --
    confirmed on a real catalogued tool, W3C's DPV vocabulary
    (w3c-cg/dpv), which GitHub reports as "HTML" (its rendered spec pages
    dominate the byte count; the repo is actually Turtle/RDF) with license
    "" (GitHub's detector doesn't recognize the W3C Software and Document
    License 2023 text at all). Both fields now go through a priority chain
    before ever falling back to GitHub's guess -- structured package
    metadata first, then GitHub, then `licenseid`'s fuzzy text match as the
    genuine last resort (not a challenger to a source that already
    answered, and the slowest step of this whole chain by far, so gating
    it behind "nothing else found anything" also matters for run time, not
    just correctness):
      1. `codemeta.json`'s own `license`/`programmingLanguage` fields, if
         present (see fetch_codemeta() -- reuses the same fetch already
         made for `funder`/`development_status` above, no extra call).
      2. `license` only: `CITATION.cff`'s own top-level `license` field,
         if present (see fetch_citation_cff() -- reuses the same fetch
         already made for `paper_url`/`software_heritage_id` above).
         Confirmed on the DPV case this whole chain is built around: its
         CITATION.cff declares `license: W3C` directly -- a real, valid
         SPDX id -- resolving it authoritatively without ever needing
         `licenseid`'s fuzzy match at all.
      3. `programming_language` only: an ecosystem package-manifest file's
         mere *presence* at the repo root -- `Cargo.toml` -> Rust,
         `go.mod` -> Go, `package.json` -> JavaScript (or TypeScript if
         `tsconfig.json` is also present), `pyproject.toml` -> Python,
         `pom.xml` -> Java, `build.gradle.kts` -> Kotlin, `build.gradle`
         -> Java -- checked in that order, first one found wins (see
         PACKAGE_MANIFEST_LANGUAGES, detect_language_from_manifests()).
         A semantic-web repo like DPV has none of these manifests (it
         isn't a software package in any of these ecosystems), so this
         step correctly finds nothing there either -- catching the *false
         positive* GitHub's byte-counter produces for `programming_
         language` is a job for a human/AI judgment call in `tools`, not
         something a script can safely automate (see "flag suspicious
         auto-collected values for review" in curation/README.md's PASS A
         section; unlike `license`, no CITATION.cff/codemeta.json field
         happened to cover DPV's language the way it covered its license).
      4. `license` only: `Cargo.toml`/`package.json`/`pyproject.toml`'s own
         `license` field, when present -- each ecosystem's convention
         already expects this to be a clean SPDX expression (crates.io/npm/
         PEP 639 all require or strongly encourage it), so these are used
         as-is, no further matching needed (see resolve_license(),
         parse_cargo_toml_license(), parse_package_json_license(),
         parse_pyproject_toml_license()).
      5. `license` only: GitHub's own repo-core detection (`core["license"]`
         from the first bullet above), *if it found one*. This ranks ABOVE
         `licenseid`'s fuzzy text match, not below it -- confirmed on a
         real repo, fossology/fossology: GitHub correctly detects
         `GPL-2.0-only`, but licenseid's own best match against that same
         LICENSE file's text is the *wrong* `LGPL-2.1-only` at 0.75
         similarity (plausible-looking, not obviously wrong the way a
         near-zero score is). `licenseid` is a genuine second chance for
         cases GitHub missed entirely (`NOASSERTION` or blank), not a
         challenger to a case it already got right -- steps 6/7 below only
         run when GitHub's own detection is empty.
      6. `license` only: Maven's `pom.xml` <licenses><license><name> --
         free text (e.g. "The Apache License, Version 2.0"), NOT
         guaranteed valid SPDX the way step 4's fields are, so it's
         normalized through [`licenseid`][licenseid] rather than used
         directly (see parse_pom_xml_license_name(), match_license_text()).
      7. `license` only: the repo's actual `LICENSE`/`LICENSE.md`/
         `LICENSE.txt`/etc. file text (see LICENSE_FILE_PATHS), matched
         against the full SPDX list via `licenseid`'s fuzzy text matcher
         (SQLite FTS5 + RapidFuzz, not an LLM -- deterministic). Only
         trusted at or above LICENSEID_CONFIDENCE_FLOOR (0.8) -- confirmed
         on real repos that below that, a "match" is noise, not signal
         (RobustBench and SCLBD/DeepfakeBench both top-match at 0.07-0.09
         similarity to a license that plainly isn't theirs); a below-floor
         match is discarded outright (logged as a warning), not recorded
         for later review -- a single trust/no-trust line, not a "record
         but flag" middle tier.
      8. `programming_language` only: GitHub's own repo-core `language`
         (from the first bullet above) -- the true last resort, only
         reached if every step above came up empty.
    `licenseid` needs a **one-time local setup step** before first use --
    `licenseid update`, which downloads the SPDX license list and builds a
    local SQLite similarity index (see curation/README.md's Setup). If
    that database isn't present, steps 6/7 above are skipped for the whole
    run (a single warning printed once, not once per tool) and license
    resolution falls through to codemeta.json / CITATION.cff / ecosystem
    manifests / GitHub's own detection only.

[licenseid]: https://github.com/bact/licenseid

  - `keywords`: GitHub's own repo `topics` (free in the repo-core response
    above, the primary source -- hand-curated tags, not inferred) unioned
    with whatever package-manifest `keywords` field(s) happen to already be
    in `manifests` when this runs -- `Cargo.toml`, `package.json`,
    `pyproject.toml` (PEP 621's `[project].keywords`, falling back to
    `[tool.poetry].keywords`), `composer.json`. Opportunistic, not a
    dedicated fetch: `pyproject.toml` is always fetched (see
    fetch_package_manifests()), the rest only when `include_all` was
    already set for language/license resolution -- a repo whose language
    and license both resolved from GitHub/codemeta.json directly never has
    its package.json/Cargo.toml/composer.json checked for keywords at all.
    A deliberate cost tradeoff (this field doesn't justify its own extra
    GitHub calls on every tool), not a bug -- see collect_keywords().
  - `sponsors`: active GitHub Sponsors count for the repo's OWNER
    (user or org, not the individual repo -- GitHub Sponsors listings are
    account-level, and there's no public per-repo count), via
    `GET sponsors.ecosyste.ms/api/v1/accounts/{owner}` (public, no auth).
    Blank if that owner has no Sponsors listing at all (`has_sponsors_
    listing: false`, confirmed on real accounts, e.g. pandas-dev) -- not
    the same as a listing with zero current sponsors, which is rare but
    real and reads as 0. Cached per owner for the whole run (see
    `sponsors_cache` in main()) -- multiple tools under one org share a
    single lookup. Known limitation, confirmed by hand: an owner
    ecosyste.ms has never indexed before returns 0 with no error on its
    first-ever lookup (it syncs GitHub's Sponsors data asynchronously,
    after responding, not inline) -- see fetch_sponsors_count()'s
    docstring for what that means for a freshly-added tool's first
    collection run.
  - `documentation`: `pyproject.toml`'s own `Documentation` well-known
    Project-URL (`[project.urls]`, matched the same case/punctuation-
    insensitive way as `funding`'s `Funding` label -- see
    pyproject_url_by_label()), then `Cargo.toml`'s `package.documentation`
    field (a direct URL string, the crates.io convention -- usually
    docs.rs). No fuzzy-match last resort the way `license` has `licenseid`
    -- an approximately-right documentation link is worse than none, so
    this only ever records a URL the project explicitly labeled as its
    documentation. Opportunistic like `keywords`: `pyproject.toml` is
    always fetched already (for `funding`), `Cargo.toml` only when
    `include_all` was already set for language/license resolution -- see
    collect_documentation().
  - `homepage`: `pyproject.toml`'s `Homepage` well-known Project-URL, then
    `package.json`'s top-level `homepage`, then `Cargo.toml`'s `package.
    homepage`, then GitHub's own repo `homepage` field (see fetch_repo_
    core()) as the true last resort -- ranked below every manifest
    declaration because it's frequently blank even when a real homepage
    exists elsewhere, and occasionally just duplicates the repo's own
    GitHub URL rather than naming a distinct site. Opportunistic like
    `keywords`/`documentation` in the normal run; unconditional in the
    `--fields` backfill path -- see collect_homepage().

Both third-party calls (bestpractices.dev, scorecard.dev) -- and
sponsors.ecosyste.ms above -- are made with a **plain, unauthenticated
request** -- never through the GitHub-authed session, so the GITHUB_TOKEN
header is never sent to a third-party host. The same is true of every
GitHub *contents* fetch used for YAML/TOML/JSON parsing below -- they go
through the normal authed `session`, since they're still github.com, just
returned as base64-decoded raw content via the `vnd.github.raw+json` media
type rather than JSON-wrapped.

  - OpenSSF Best Practices: `GET bestpractices.dev/projects.json?q=<repo
    name>` (public, no auth -- note it needs `q=`, not the `pq=`/`url=`
    forms one might guess from the badge-embed docs, confirmed by hand),
    then filtered client-side for a result whose own `repo_url` matches
    this repo (case-insensitive, trailing-slash/`.git` tolerant) --
    `q=` is full-text search, not an exact lookup, so the match check does
    the real work, not the query term. Uses `badge_level` ("in_progress" /
    "passing" / "silver" / "gold") and `id` (-> the badge URL). Most
    projects were never submitted for a badge at all; blank in that case.
  - OpenSSF Scorecard: `GET api.scorecard.dev/projects/github.com/{owner}/
    {repo}` (public, no auth). 200 with an aggregate `score` (0-10) if ever
    scanned, 404 if never scanned -- blank in that case. The response's
    `checks: [{name, score, reason, ...}]` breakdown also feeds four
    individual columns picked as the highest-signal checks for assessing a
    governance-relevant tool: `openssf_scorecard_branch_protection`,
    `openssf_scorecard_code_review`, `openssf_scorecard_maintained`,
    `openssf_scorecard_vulnerabilities`. The other ~14 checks Scorecard
    reports (Binary-Artifacts, CI-Tests, Fuzzing, Pinned-Dependencies,
    SAST, Signed-Releases, Token-Permissions, ...) aren't given their own
    column -- would bloat the sheet for checks with less direct bearing on
    "is this tool safe to recommend"; the full breakdown is always
    re-fetchable from the API by URL if a specific one ever becomes worth
    adding. **A per-check score of `-1` is Scorecard's own sentinel for
    "could not evaluate this check"** (confirmed on a real catalogued
    tool: Branch-Protection returned -1 with reason "some github tokens
    can't read classic branch protection rules" -- an auth/permission
    limit on Scorecard's own scanning infrastructure, not a finding about
    the repo) -- read it as "unknown", never as "worst possible score."

`dependents` is deliberately NOT collected here -- GitHub's "Used by"
dependency-graph count has no public API, only an HTML page
(`/network/dependents`), and this script doesn't scrape it: fragile against
markup changes, and bulk-scraping a GitHub HTML page for data with no API
sits in ToS gray territory that a one-off manual check in a browser doesn't.
Leave that column for manual spot-checks.

Same GITHUB_TOKEN / session requirement as search_repos.py -- see that
script's docstring, or curation/README.md's "Setup" section, for the
`gh auth token` vs repo-scoped-token distinction. Also needs a one-time
`licenseid update` before first use (builds a local SQLite license-text
index) -- see the "license / programming_language" bullet above and
curation/README.md's "Setup". Runs fine without it, just with license
resolution skipping straight to GitHub's own (weaker) detection for any
repo codemeta.json/the ecosystem manifests didn't already answer.

By default, only considers `tool_type` "software" or "specification" rows
with a GitHub `source` URL and no `stars` value yet (i.e. never collected)
-- a specification developed in the open on GitHub has the same
project-quality signals as software (stars, contributors, governance files,
release history, ...), so it's collected the same way. `programming_language`
just comes back whatever GitHub's own language detector reports for the
repo (often a thin build/lint script, sometimes blank) -- no special-casing
here or in build.py; a human can still override it in `tools` if that value
is misleading for a given spec repo. Pass
`--refresh-all` to re-collect for every eligible tool regardless, which is
the only way the volatile fields (stars/forks/watchers/contributors/
open_issues_count/releases_count/scorecard score) actually get refreshed
after the first pass, since site/data.json only reflects what's already
live in the sheets. The one-shot/rarely-changing fields (readme_url,
license_url, governance_url, funder, development_status, paper_url,
software_heritage_id, ...) get re-collected on every `--refresh-all` run
too, even though they don't need it as often -- there's no per-field
freshness tracking here, only per-row (see pass_a_checked.csv's docstring
in emit_candidates.py for the same limitation applied to RQ mappings).

Rate limits and interruption safety: prints the current GitHub core rate
limit (`/rate_limit`) before starting, with a rough call estimate for the
run (~18-28 calls/tool depending on how often GitHub's own language/license
answers are trusted directly -- see the "license / programming_language"
bullet above), and re-checks every 20 tools --
stopping early rather than continuing once remaining quota drops below 100.
Every row is written to `--out` and flushed immediately after that tool is
processed, not batched to the end, so an interruption for any reason (rate
limit, network blip, Ctrl-C, a calling tool's own execution timeout) loses
at most the one in-flight row. Re-running the exact same command afterwards
resumes automatically: ids already present in `--out` are skipped (pass
`--restart` to ignore that checkpoint and overwrite `--out` from scratch).
`--limit N` caps a single run to N tools, for a deliberately small first
batch. The third-party APIs (bestpractices.dev, scorecard.dev) have no
published rate limit to preflight-check against; the existing `--sleep`
between tools (default 1s) throttles those too, gently.

Usage:

    python build.py   # refresh site/data.json against both live sheets first
    export GITHUB_TOKEN=$(gh auth token)
    python curation/collect_project_metadata.py               # first run
    python curation/collect_project_metadata.py                # resumes if interrupted
    python curation/collect_project_metadata.py --refresh-all   # re-collect everything
    python curation/collect_project_metadata.py --limit 20      # a small first batch

    # For a batch just emitted by emit_candidates.py, not yet pasted into the
    # live tools tab -- collects straight from candidate_tools.csv so the
    # tool_metadata rows are ready to paste in the same round-trip:
    python curation/collect_project_metadata.py \\
        --candidates curation/candidate_tools.csv \\
        --out curation/candidate_tool_metadata.csv --restart

    # Cheaply backfill just a few columns for every already-collected tool
    # missing them (e.g. right after adding new columns to a live sheet that
    # predates them) -- a few calls/tool instead of ~18-28, and skips every
    # other column entirely. Output is a column patch, not a full row --
    # paste it into ONLY the requested columns, matched by id, never as a
    # row/tab replacement (see --fields' own help text, or main()'s
    # completion message, for exactly why):
    python curation/collect_project_metadata.py --fields keywords,sponsors,documentation \\
        --out curation/state/backfill.csv --restart
"""
import argparse
import csv
import datetime
import json
import os
import re
import sys
import time
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import quote

csv.field_size_limit(sys.maxsize)

import requests
import yaml
from licenseid.matcher import AggregatedLicenseMatcher

GITHUB_API = "https://api.github.com"
BESTPRACTICES_API = "https://www.bestpractices.dev/projects.json"
SCORECARD_API = "https://api.scorecard.dev/projects"
SPONSORS_API = "https://sponsors.ecosyste.ms/api/v1/accounts"
REPO_PATH_RE = re.compile(r"github\.com[:/]+([^/]+/[^/.]+?)(?:\.git)?/?$", re.IGNORECASE)
SECURITY_POLICY_PATHS = ["SECURITY.md", ".github/SECURITY.md", "docs/SECURITY.md"]
GOVERNANCE_PATHS = ["GOVERNANCE.md", "MAINTAINERS.md", "MAINTAINERS",
                     ".github/GOVERNANCE.md", ".github/MAINTAINERS.md"]
SCORECARD_CHECK_COLUMNS = {
    "Branch-Protection": "openssf_scorecard_branch_protection",
    "Code-Review": "openssf_scorecard_code_review",
    "Maintained": "openssf_scorecard_maintained",
    "Vulnerabilities": "openssf_scorecard_vulnerabilities",
}
# Common LICENSE filenames, checked in this order -- first one found wins
# (stops there even if licenseid can't match its text, rather than trying
# every remaining name looking for a luckier match).
LICENSE_FILE_PATHS = ["LICENSE", "LICENSE.md", "LICENSE.txt", "LICENSE-MIT", "COPYING", "COPYING.md"]
# Ecosystem package-manifest files that make a repo's implementation
# language(s) unambiguous even when GitHub's own byte-counter is misled by
# generated/rendered content -- e.g. a semantic-web vocabulary repo that's
# almost entirely `.ttl`/`.owl`/`.jsonld` files GitHub can't byte-count as
# "language" at all, with just enough rendered HTML spec pages for GitHub's
# detector to call the whole repo "HTML" (the real case this whole
# resolution chain exists for -- see NON_IMPLEMENTATION_LANGUAGES and
# detect_languages_from_manifests() below). Only consulted when GitHub's
# own guess is blank or implausible -- see main()'s `language_needs_
# manifests`. Every entry present contributes to the result (genuine
# polyglot support, e.g. a Tauri app -> "Rust; JavaScript"), in this order.
# No universal C/C++ manifest exists the way the others do (CMakeLists.txt
# isn't authoritative/ubiquitous enough to trust the same way) -- and even
# where a manifest convention exists, not every repo in that ecosystem
# actually uses it: fossology/fossology is genuinely PHP+C (confirmed via
# GET /repos/{owner}/{repo}/languages: 5.9M PHP bytes, 2.5M C, vs. 6.5M
# HTML from generated/vendored content, which is what GitHub's `language`
# reports), but predates widespread Composer adoption and has no
# composer.json -- resolves to blank here, correctly reflecting "no
# manifest signal available" rather than a wrong guess, but still a real
# case for a human to fill in via `tools` (see "flag suspicious
# auto-collected values for review" in curation/README.md's PASS A
# section).
PACKAGE_MANIFEST_LANGUAGES = [
    ("Cargo.toml", "Rust"),
    ("go.mod", "Go"),
    ("package.json", "JavaScript"),  # refined to TypeScript if tsconfig.json is also present
    ("pyproject.toml", "Python"),
    ("pom.xml", "Java"),
    ("build.gradle.kts", "Kotlin"),
    ("build.gradle", "Java"),
    ("composer.json", "PHP"),
]
# GitHub Linguist languages that are markup/prose/data, or that commonly
# dominate a repo's byte count without being its real implementation
# language -- confirmed on real catalogued tools, not assumed: w3c-cg/dpv
# (a semantic-web vocabulary) byte-counts as `HTML` because of its rendered
# spec pages; several ML/research repos in this catalog (llm-attributor,
# granite-guardian, ml-privacy-meter) byte-count as `Jupyter Notebook`
# because notebook cell *output* blobs (embedded images, base64 data)
# routinely outweigh the actual Python source. GitHub's `language` field is
# trusted directly when it's NOT one of these (the common case, zero extra
# API calls) -- only when it's blank or in this set does main() bother
# probing PACKAGE_MANIFEST_LANGUAGES at all. Not exhaustive by design --
# extend if another confirmed false positive shows up; being too aggressive
# here just means spending calls checking manifests unnecessarily, not a
# correctness risk either way.
NON_IMPLEMENTATION_LANGUAGES = {
    "HTML", "CSS", "SCSS", "Less", "Markdown", "TeX", "Roff", "XSLT",
    "YAML", "JSON", "XML", "Jupyter Notebook",
}
# licenseid's similarity score below which a match is discarded outright --
# treated as "no match" (resolve_license() falls through to whatever's next
# in its chain, or "" if there's nothing left) rather than recorded. A
# single trust/no-trust line, not a "recorded but flagged" middle tier:
# below this, a match isn't a weak signal, it's noise -- confirmed on real
# repos, RobustBench's actual LICENSE text top-matches `BSD-4-Clause` at
# 0.09 similarity, SCLBD/DeepfakeBench at 0.07 -- neither is remotely the
# repo's real license, and even the moderate end of the discarded range
# (demml/opsml at 0.79) is close enough to this floor to not be worth
# trusting either.
LICENSEID_CONFIDENCE_FLOOR = 0.8
# FUNDING.yml's own platform keys -> a function building the canonical URL.
# `github`/`custom` can hold a single string or a list; every other key is a
# single string. See https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/displaying-a-sponsor-button-in-your-repository
FUNDING_YML_URL_BUILDERS = {
    "github": lambda v: f"https://github.com/sponsors/{v}",
    "patreon": lambda v: f"https://patreon.com/{v}",
    "open_collective": lambda v: f"https://opencollective.com/{v}",
    "ko_fi": lambda v: f"https://ko-fi.com/{v}",
    "tidelift": lambda v: f"https://tidelift.com/funding/github/{v}",
    "community_bridge": lambda v: f"https://funding.communitybridge.org/projects/{v}",
    "liberapay": lambda v: f"https://liberapay.com/{v}",
    "issuehunt": lambda v: f"https://issuehunt.io/r/{v}",
    "otechie": lambda v: f"https://otechie.com/{v}",
    "lfx_crowdfunding": lambda v: f"https://crowdfunding.lfx.linuxfoundation.org/projects/{v}",
    "polar": lambda v: f"https://polar.sh/{v}",
    "buy_me_a_coffee": lambda v: f"https://buymeacoffee.com/{v}",
    "custom": lambda v: v,  # already a full URL
}

# Matches the live `tool_metadata` sheet's actual column order exactly
# (re-verified against a live header fetch after `homepage` was added) so a
# run's output pastes in without reordering -- nothing enforces the two
# staying in sync, so re-check against the live header if a paste ever looks
# misaligned. `keywords`/`sponsors`/`homepage` all already exist as live
# columns (positioned here to match, not appended at the end) -- no sheet
# changes needed for them at this point.
OUT_FIELDNAMES = [
    "id", "name", "license", "programming_language", "homepage", "source", "documentation",
    "funding", "funder", "paper_url",
    "datetime_added", "datetime_checked", "datetime_updated",
    "keywords", "stars", "forks", "watchers", "contributors", "sponsors", "last_commit_date",
    "open_issues_count", "releases_count", "latest_release_date",
    "readme_url", "license_url", "governance_url", "contributing_url",
    "code_of_conduct_url", "security_policy_url", "sbom_url",
    "openssf_best_practices_url", "openssf_best_practices_badge_level",
    "openssf_scorecard_url", "openssf_scorecard_score",
    "openssf_scorecard_branch_protection", "openssf_scorecard_code_review",
    "openssf_scorecard_maintained", "openssf_scorecard_vulnerabilities",
    "development_status", "software_heritage_id",
]


def extract_repo_path(source_url: str) -> str | None:
    m = REPO_PATH_RE.search(source_url or "")
    return m.group(1) if m else None


def normalize_repo_url(url: str) -> str:
    return (url or "").strip().lower().rstrip("/").removesuffix(".git")


def fetch_raw_file(session: requests.Session, repo_path: str, path: str) -> str | None:
    """Contents of a single file at the repo's default branch, or None if it
    doesn't exist / isn't fetchable. Used for every YAML/TOML/JSON file this
    script reads -- still a normal authed GitHub API call, just asking for
    raw content instead of the JSON-wrapped-and-base64 default."""
    try:
        resp = session.get(f"{GITHUB_API}/repos/{repo_path}/contents/{path}",
                            headers={"Accept": "application/vnd.github.raw+json"}, timeout=30)
        if resp.status_code != 200:
            return None
        return resp.text
    except requests.RequestException:
        return None


def fetch_repo_core(session: requests.Session, repo_path: str, warnings: list) -> dict:
    """Returns {} on any failure (404/renamed/private/rate-limited) rather
    than raising -- a single unreachable repo shouldn't abort the batch."""
    try:
        resp = session.get(f"{GITHUB_API}/repos/{repo_path}", timeout=30)
        if resp.status_code == 403 and "rate limit" in resp.text.lower():
            warnings.append(f"{repo_path}: rate limited (resets at {resp.headers.get('X-RateLimit-Reset')})")
            return {}
        if resp.status_code != 200:
            warnings.append(f"{repo_path}: GitHub API returned {resp.status_code} for repo core")
            return {}
        data = resp.json()
        # "NOASSERTION" is GitHub's own detector saying it couldn't classify
        # the license confidently -- same blind spot as license_url below
        # (F3 in docs/methodology-and-findings.md); recorded as blank rather
        # than as a fake SPDX id.
        license_spdx = (data.get("license") or {}).get("spdx_id") or ""
        if license_spdx == "NOASSERTION":
            license_spdx = ""
        return {
            # The repo's own name (`name`, not `full_name` -- no owner
            # prefix), for tool_metadata's auto-collected `name` column.
            # Often not display-ready (a slug, or an ugly long project-repo
            # name like a WWW-project repo's) -- that's exactly what
            # `tools`' own `name` override is for, same precedence as
            # `license`, not a reason to skip collecting it here.
            "name": data.get("name") or "",
            "stars": data.get("stargazers_count"),
            "forks": data.get("forks_count"),
            "watchers": data.get("subscribers_count"),
            "open_issues_count": data.get("open_issues_count"),
            "last_commit_date": (data.get("pushed_at") or "")[:10],
            "license": license_spdx,
            # GitHub's own repo topics -- free in this same response, the
            # base of `keywords` (see collect_keywords()) before any
            # package-manifest keywords are unioned in.
            "topics": data.get("topics") or [],
            # GitHub's own repo `homepage` field -- a maintainer-set URL,
            # but ranked BELOW every manifest's own homepage declaration in
            # collect_homepage() (below), not above: it's frequently blank
            # even when a real homepage exists elsewhere (in pyproject.toml/
            # package.json/Cargo.toml), and occasionally just duplicates the
            # repo's own GitHub URL rather than a distinct site -- treated
            # as the fallback, not the primary source.
            "homepage": data.get("homepage") or "",
            # Same field backfill_programming_language.py used to fetch
            # separately -- free here, already in this response. Single
            # dominant-by-bytes language only; a second, genuinely
            # polyglot language is a manual addition in `tools`, not
            # something this script infers (see docs/data-schema.md).
            "programming_language": data.get("language") or "",
            "default_branch": data.get("default_branch") or "main",
        }
    except requests.RequestException as e:
        warnings.append(f"{repo_path}: repo core request failed ({e})")
        return {}


def fetch_last_page_count(session: requests.Session, url: str, params: dict, warnings: list,
                          context: str) -> int | None:
    """Shared Link-header pagination trick: per_page=1 makes the last page
    number equal the total count. Used for contributors and releases."""
    try:
        resp = session.get(url, params=params, timeout=30)
        if resp.status_code != 200:
            return None  # common for empty/archived repos; not worth a warning on its own
        link = resp.headers.get("Link", "")
        m = re.search(r'page=(\d+)>; rel="last"', link)
        if m:
            return int(m.group(1))
        return 1 if resp.json() else 0
    except requests.RequestException as e:
        warnings.append(f"{context}: request failed ({e})")
        return None


def fetch_contributors_count(session: requests.Session, repo_path: str, warnings: list) -> int | None:
    return fetch_last_page_count(
        session, f"{GITHUB_API}/repos/{repo_path}/contributors",
        {"per_page": 1, "anon": "true"}, warnings, f"{repo_path} contributors")


def fetch_releases(session: requests.Session, repo_path: str, warnings: list) -> dict:
    count = fetch_last_page_count(
        session, f"{GITHUB_API}/repos/{repo_path}/releases",
        {"per_page": 1}, warnings, f"{repo_path} releases")
    if not count:
        return {"releases_count": count}
    try:
        resp = session.get(f"{GITHUB_API}/repos/{repo_path}/releases",
                            params={"per_page": 1}, timeout=30)
        latest = resp.json()
        return {
            "releases_count": count,
            "latest_release_date": (latest[0].get("published_at") or "")[:10] if latest else "",
        }
    except requests.RequestException as e:
        warnings.append(f"{repo_path}: latest release request failed ({e})")
        return {"releases_count": count}


def fetch_community_profile(session: requests.Session, repo_path: str, warnings: list) -> dict:
    try:
        resp = session.get(f"{GITHUB_API}/repos/{repo_path}/community/profile", timeout=30)
        if resp.status_code != 200:
            warnings.append(f"{repo_path}: GitHub API returned {resp.status_code} for community profile")
            return {}
        files = resp.json().get("files") or {}

        def html_url(key: str) -> str:
            entry = files.get(key)
            return (entry or {}).get("html_url") or ""

        # When GitHub's license detector can't classify a repo's license, it
        # sets spdx_id "NOASSERTION" and its html_url is unreliable -- seen
        # on a real catalogued tool pointing at an unrelated TOML data file,
        # not any license file. Same underlying blind spot as F3 in
        # docs/methodology-and-findings.md, just hitting the URL field this
        # time instead of the SPDX id -- leave blank rather than record junk.
        license_entry = files.get("license") or {}
        license_url = license_entry.get("html_url") or ""
        if license_entry.get("spdx_id") in (None, "NOASSERTION"):
            if license_url:
                warnings.append(f"{repo_path}: license_url discarded, GitHub's own "
                                 f"detector returned NOASSERTION for it ({license_url!r})")
            license_url = ""

        return {
            "readme_url": html_url("readme"),
            "license_url": license_url,
            "code_of_conduct_url": html_url("code_of_conduct"),
            "contributing_url": html_url("contributing"),
        }
    except requests.RequestException as e:
        warnings.append(f"{repo_path}: community profile request failed ({e})")
        return {}


def probe_paths(session: requests.Session, repo_path: str, paths: list, default_branch: str) -> str:
    """First of `paths` (repo-root-relative) that exists, as a browsable
    blob URL; "" if none do. Used for security policy and governance/
    maintainers files, neither of which the community profile API reliably
    surfaces."""
    for path in paths:
        try:
            resp = session.get(f"{GITHUB_API}/repos/{repo_path}/contents/{path}", timeout=30)
            if resp.status_code == 200:
                return f"https://github.com/{repo_path}/blob/{default_branch}/{path}"
        except requests.RequestException:
            continue  # a single probe failing isn't worth a warning; just move to the next path
    return ""


def fetch_sbom_url(session: requests.Session, repo_path: str) -> str:
    """GitHub auto-generates an SPDX SBOM from the dependency graph for
    every public repo that has it enabled -- confirmed 200 on a repo that
    never published its own SBOM file, so this needs no probing, just one
    existence check. Returns the API endpoint itself (it returns the SBOM
    JSON directly); fetching it needs the same GitHub auth as any other
    call here."""
    try:
        resp = session.get(f"{GITHUB_API}/repos/{repo_path}/dependency-graph/sbom", timeout=30)
        if resp.status_code == 200:
            return f"{GITHUB_API}/repos/{repo_path}/dependency-graph/sbom"
    except requests.RequestException:
        pass
    return ""


def fetch_package_manifests(session: requests.Session, repo_path: str, include_all: bool) -> dict:
    """pyproject.toml is always fetched, `include_all` or not -- it's needed
    for `funding` regardless of whether license/language resolution ever
    reach it (see collect_funding()), so there's no case where skipping it
    saves a call. The rest of PACKAGE_MANIFEST_LANGUAGES (plus tsconfig.json,
    only probed if package.json exists) are only fetched when `include_all`
    is set by the caller -- GitHub's own language guess was blank/
    implausible, or license is still unresolved after codemeta.json/
    CITATION.cff/GitHub (see main()). For the common case where neither
    trigger fires, this saves 6-7 GitHub calls per tool that would almost
    always just be 404s anyway (a repo only uses one ecosystem, if any)."""
    result = {"pyproject.toml": fetch_raw_file(session, repo_path, "pyproject.toml")}
    if not include_all:
        return result
    for filename, _ in PACKAGE_MANIFEST_LANGUAGES:
        if filename == "pyproject.toml":
            continue
        result[filename] = fetch_raw_file(session, repo_path, filename)
    if result.get("package.json"):
        result["tsconfig.json"] = fetch_raw_file(session, repo_path, "tsconfig.json")
    return result


def detect_languages_from_manifests(manifests: dict) -> list[str]:
    """Every ecosystem manifest that exists, not just the first -- genuine
    polyglot detection (e.g. a Tauri app with a Rust backend and a
    JavaScript frontend -> ["Rust", "JavaScript"]), unlike GitHub's own
    single-dominant-language guess. Only called when that guess was blank
    or implausible (see NON_IMPLEMENTATION_LANGUAGES) -- for the common
    case where GitHub's answer is trusted directly, this never runs, and
    `manifests` was never even fetched beyond pyproject.toml."""
    languages = []
    for filename, language in PACKAGE_MANIFEST_LANGUAGES:
        if not manifests.get(filename):
            continue
        if filename == "package.json" and manifests.get("tsconfig.json"):
            language = "TypeScript"
        if language not in languages:  # pom.xml and build.gradle both map to "Java" -- don't double-add
            languages.append(language)
    return languages


def parse_cargo_toml_license(text: str, warnings: list, repo_path: str) -> str:
    """Cargo.toml's `package.license` is conventionally already a clean
    SPDX expression (crates.io requires it for publishing) -- used as-is,
    no licenseid pass needed."""
    try:
        data = tomllib.loads(text)
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
        warnings.append(f"{repo_path}: Cargo.toml failed to parse ({e})")
        return ""
    return (data.get("package") or {}).get("license") or ""


def parse_package_json_license(text: str, warnings: list, repo_path: str) -> str:
    """package.json's `license` is conventionally already a clean SPDX
    expression per npm's own docs -- used as-is. Handles both the modern
    string form and the legacy `{"type": "MIT"}` object form npm
    deprecated years ago but some older repos still carry."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        warnings.append(f"{repo_path}: package.json failed to parse ({e})")
        return ""
    license_val = data.get("license")
    if isinstance(license_val, str):
        return license_val
    if isinstance(license_val, dict):
        return license_val.get("type", "") or ""
    return ""


def parse_pyproject_toml_license(text: str, warnings: list, repo_path: str) -> str:
    """pyproject.toml's `[project].license` is a clean SPDX expression
    under PEP 639 (the modern form, a plain string), or `{text = "..."}`
    under the legacy PEP 621 form -- both used as-is. The other legacy form,
    `{file = "..."}`, just points at a LICENSE file instead of naming the
    license, so there's nothing to extract here -- the LICENSE-file +
    licenseid step in resolve_license() covers that case anyway."""
    try:
        data = tomllib.loads(text)
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
        warnings.append(f"{repo_path}: pyproject.toml failed to parse ({e})")
        return ""
    license_val = (data.get("project") or {}).get("license")
    if isinstance(license_val, str):
        return license_val
    if isinstance(license_val, dict):
        return license_val.get("text", "") or ""
    return ""


def parse_pom_xml_license_name(text: str, warnings: list, repo_path: str) -> str:
    """Maven's pom.xml <licenses><license><name> is free text (e.g. "The
    Apache License, Version 2.0"), NOT guaranteed to be a valid SPDX id the
    way Cargo.toml/package.json/pyproject.toml's fields are -- the caller
    (resolve_license()) routes this through licenseid rather than using it
    directly."""
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        warnings.append(f"{repo_path}: pom.xml failed to parse ({e})")
        return ""
    # Maven POMs commonly (but not always) declare the default namespace;
    # try both so a namespace-less pom.xml still matches.
    for path, namespaces in (("m:licenses/m:license/m:name", {"m": "http://maven.apache.org/POM/4.0.0"}),
                              ("licenses/license/name", None)):
        el = root.find(path, namespaces)
        if el is not None and el.text and el.text.strip():
            return el.text.strip()
    return ""


# Manifest files collect_keywords() actually reads for a `keywords` field --
# unlike PACKAGE_MANIFEST_LANGUAGES, deliberately excludes go.mod/pom.xml/
# build.gradle* (no keywords convention exists in those ecosystems). Used by
# both the normal run (opportunistically, whatever's already in `manifests`)
# and the `--fields` backfill path below (fetched unconditionally, since
# that mode skips language/license resolution -- and the manifest-gating
# triggers built for those -- entirely).
KEYWORD_MANIFEST_FILENAMES = ["Cargo.toml", "package.json", "pyproject.toml", "composer.json"]
# Manifest files collect_documentation() reads -- just the two ecosystems
# with an explicit "documentation URL" convention (PyPA's well-known
# `Documentation` Project-URL label, Cargo's `package.documentation` field).
DOCUMENTATION_MANIFEST_FILENAMES = ["pyproject.toml", "Cargo.toml"]
# Manifest files collect_homepage() reads -- PyPA's well-known `Homepage`
# Project-URL label, package.json's top-level `homepage`, Cargo's `package.
# homepage`. No composer.json/go.mod/pom.xml/build.gradle* equivalent
# checked -- same reasoning as KEYWORD_MANIFEST_FILENAMES, extend if a
# confirmed convention for one of those shows up.
HOMEPAGE_MANIFEST_FILENAMES = ["pyproject.toml", "package.json", "Cargo.toml"]
# The only columns cheap enough to backfill without the rest of a normal
# collection run -- each needs an entry in BACKFILL_MANIFEST_FILES (if it
# reads any manifest) or its own branch in main()'s backfill loop (like
# `sponsors`, which reads no manifest at all). Adding another field here
# would need its own cheap, standalone fetch path to be worth doing this way.
BACKFILL_FIELDS = {"keywords", "sponsors", "documentation", "homepage"}
# field -> manifest filenames it reads, for the `--fields` backfill path's
# per-tool fetch (see main()) -- computed as the UNION across every
# requested field before fetching, so e.g. `--fields keywords,documentation`
# fetches pyproject.toml once, not twice, one request per distinct filename
# regardless of how many fields want it. `sponsors` reads no manifest (all
# via sponsors.ecosyste.ms), so it has no entry here.
BACKFILL_MANIFEST_FILES = {
    "keywords": KEYWORD_MANIFEST_FILENAMES,
    "documentation": DOCUMENTATION_MANIFEST_FILENAMES,
    "homepage": HOMEPAGE_MANIFEST_FILENAMES,
}


def parse_cargo_toml_keywords(text: str, warnings: list, repo_path: str) -> list[str]:
    try:
        data = tomllib.loads(text)
    except (tomllib.TOMLDecodeError, UnicodeDecodeError):
        return []  # already warned once for this file by the license parser
    return [k for k in (data.get("package") or {}).get("keywords") or [] if isinstance(k, str) and k]


def parse_package_json_keywords(text: str, warnings: list, repo_path: str) -> list[str]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    return [k for k in data.get("keywords") or [] if isinstance(k, str) and k]


def parse_composer_json_keywords(text: str, warnings: list, repo_path: str) -> list[str]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        warnings.append(f"{repo_path}: composer.json failed to parse ({e})")
        return []
    return [k for k in data.get("keywords") or [] if isinstance(k, str) and k]


def parse_pyproject_toml_keywords(text: str, warnings: list, repo_path: str) -> list[str]:
    """PEP 621's `[project].keywords` (a plain list of strings) is checked
    first; `[tool.poetry].keywords` (Poetry's own pre-PEP-621 convention,
    still common in older or Poetry-only projects that never migrated their
    metadata to the `[project]` table) is checked as a fallback, not merged
    with it -- a project using both would be unusual, and PEP 621 is the
    modern standard."""
    try:
        data = tomllib.loads(text)
    except (tomllib.TOMLDecodeError, UnicodeDecodeError):
        return []
    project_keywords = [k for k in (data.get("project") or {}).get("keywords") or []
                         if isinstance(k, str) and k]
    if project_keywords:
        return project_keywords
    return [k for k in (data.get("tool") or {}).get("poetry", {}).get("keywords") or []
            if isinstance(k, str) and k]


def collect_keywords(topics: list[str], manifests: dict, warnings: list, repo_path: str) -> str:
    """GitHub's own repo topics (hand-curated tags, the primary source),
    unioned with whatever package-manifest `keywords` fields happen to
    already be in `manifests` -- opportunistic, not a dedicated fetch pass:
    `manifests` only has pyproject.toml unless `include_all` was set for
    language/license resolution (see fetch_package_manifests()), so a repo
    whose language/license were both resolved from GitHub/codemeta.json
    directly never has its package.json/Cargo.toml/composer.json keywords
    checked at all -- a deliberate cost tradeoff (this field doesn't
    justify its own extra GitHub calls), not a bug; pyproject.toml is
    always present, so Python projects' keywords are the one case never
    missed this way. No pom.xml/build.gradle case -- Maven/Gradle have no
    equivalent standard "keywords" convention. Deduped case-insensitively,
    first-seen casing kept (topics win ties, since they're checked first);
    "" if nothing found anywhere."""
    seen_lower = set()
    keywords = []

    def add_all(values):
        for v in values:
            if v.lower() not in seen_lower:
                seen_lower.add(v.lower())
                keywords.append(v)

    add_all(topics)
    for filename, parser in (
        ("Cargo.toml", parse_cargo_toml_keywords),
        ("package.json", parse_package_json_keywords),
        ("pyproject.toml", parse_pyproject_toml_keywords),
        ("composer.json", parse_composer_json_keywords),
    ):
        text = manifests.get(filename)
        if text:
            add_all(parser(text, warnings, repo_path))
    return "; ".join(keywords)


def fetch_sponsors_count(owner: str, cache: dict, warnings: list) -> int | None:
    """Active GitHub Sponsors count for a repo's owner (user or org), via
    sponsors.ecosyste.ms's public, unauthenticated `/accounts/{login}` API
    -- a plain `requests.get`, never through the GitHub-authed session, same
    as bestpractices.dev/scorecard.dev below. A sponsors listing belongs to
    the OWNER account, not the individual repo (GitHub has no per-repo
    sponsor count), so `owner` -- not `repo_path` -- is both the lookup key
    and the cache key: multiple tools sharing an org (confirmed in this
    catalog, e.g. several `aboutcode-org` repos) cost one call total, not
    one per tool.

    Returns None (not 0) when the owner has no GitHub Sponsors listing at
    all (`has_sponsors_listing: false`, confirmed on real accounts with no
    listing, e.g. pandas-dev) -- that's a different fact than "a listing
    exists with zero current sponsors," which is genuinely rare but
    possible and should read as 0, not blank. Uses `active_sponsors_count`
    (current, not the lifetime-cumulative `sponsors_count` the API also
    returns) as the more meaningful "how many sponsors does this project
    have right now" signal.

    Known limitation, confirmed by hand: an owner ecosyste.ms has never
    indexed before returns `sponsors_count`/`active_sponsors_count` as 0
    with `last_synced_at: null` on its very first lookup, even when
    `has_sponsors_listing` later turns out true -- ecosyste.ms syncs GitHub
    Sponsors data asynchronously in the background after first request, not
    inline with it. This script does one request and takes whatever comes
    back (no retry/wait loop, which would slow every run for a one-time
    cold-start cost) -- an owner's sponsor count collected on their very
    first appearance in this catalog may read as 0 for one run and correct
    itself on the next `--refresh-all`."""
    if owner in cache:
        return cache[owner]
    try:
        resp = requests.get(f"{SPONSORS_API}/{quote(owner)}", timeout=30)
        if resp.status_code != 200:
            warnings.append(f"{owner}: sponsors.ecosyste.ms returned {resp.status_code}")
            cache[owner] = None
            return None
        data = resp.json()
        result = data.get("active_sponsors_count") if data.get("has_sponsors_listing") else None
        cache[owner] = result
        return result
    except requests.RequestException as e:
        warnings.append(f"{owner}: sponsors.ecosyste.ms request failed ({e})")
        cache[owner] = None
        return None


def match_license_text(matcher: "AggregatedLicenseMatcher", text: str, warnings: list,
                       repo_path: str, source_desc: str) -> str:
    """Runs `text` through licenseid's fuzzy SPDX matcher, returning the top
    match's license id -- only if its similarity is at or above
    LICENSEID_CONFIDENCE_FLOOR (0.8). A single trust/no-trust line, not a
    "record but flag" middle tier: below the floor, the match is discarded
    outright (treated as "no match", logged as a warning) rather than
    recorded for a human to maybe catch later -- confirmed on real repos
    that a below-floor "similarity" is noise, not a weak signal (e.g.
    RobustBench's actual LICENSE text top-matches `BSD-4-Clause` at 0.09,
    SCLBD/DeepfakeBench at 0.07 -- neither is remotely the repo's real
    license)."""
    try:
        results = matcher.match(text=text)
    except Exception as e:  # licenseid's own exception types aren't documented; don't let one repo's malformed input abort the batch
        warnings.append(f"{repo_path}: licenseid match against {source_desc} failed ({e})")
        return ""
    if not results:
        return ""
    top = results[0]
    license_id = top.get("license_id", "")
    score = top.get("similarity", top.get("score", 0))
    if not license_id:
        return ""
    if score < LICENSEID_CONFIDENCE_FLOOR:
        warnings.append(f"{repo_path}: licenseid's best match for {source_desc} was {license_id!r} "
                         f"at similarity {score:.2f} (below the {LICENSEID_CONFIDENCE_FLOOR} "
                         f"confidence floor) -- discarded, not recorded")
        return ""
    return license_id


def resolve_license(session: requests.Session, repo_path: str, codemeta_license: str,
                    citation_license: str, manifests: dict, github_license: str, warnings: list,
                    matcher: "AggregatedLicenseMatcher | None") -> str:
    """Priority chain, first non-empty result wins:

    1. codemeta.json's own `license` field (already fetched by the caller)
       -- a hand-curated declaration, trusted ahead of anything else.
    2. CITATION.cff's own `license` field (also already fetched by the
       caller) -- equally authoritative as codemeta.json.
    3. GitHub's own detected license (`github_license`, from
       fetch_repo_core), *if it found one*. Checked here, ahead of the
       ecosystem-manifest step below, because it's free (already fetched
       for every tool regardless) and reliable when it has an answer at
       all -- its actual failure mode is coming up empty (`NOASSERTION` or
       blank), not being confidently wrong, so there's no correctness
       reason to spend extra calls checking manifests first.
    4. An ecosystem manifest whose license field is conventionally already
       clean SPDX (Cargo.toml, package.json, pyproject.toml) -- only
       reached (and only fetched at all, per main()'s `license_needs_
       manifests`) if steps 1-3 all came up empty.
    5. pom.xml's free-text license name, normalized via licenseid.
    6. The actual LICENSE file's text, matched via licenseid.

    licenseid is a genuine second chance for cases everything else missed,
    not a challenger to a source that already answered -- confirmed on a
    real repo, fossology/fossology: GitHub correctly detects
    `GPL-2.0-only`, but licenseid's own best match against that same
    LICENSE file text is the *wrong* `LGPL-2.1-only` at 0.75 similarity (a
    plausible-looking but incorrect guess). It's also the slow step of
    this whole chain (a local but non-trivial fuzzy-match computation, run
    twice in the worst case) -- both reasons steps 5/6 only run once every
    earlier step has failed, never unconditionally.

    Returns "" if none of these find anything. `matcher` is None when
    licenseid's local database isn't available (see main()) -- steps 5/6
    are skipped in that case, silently, since main() already warned about
    it once for the whole run."""
    if codemeta_license:
        return codemeta_license

    if citation_license:
        return citation_license

    if github_license:
        return github_license

    for filename, parser in (
        ("Cargo.toml", parse_cargo_toml_license),
        ("package.json", parse_package_json_license),
        ("pyproject.toml", parse_pyproject_toml_license),
    ):
        text = manifests.get(filename)
        if text:
            value = parser(text, warnings, repo_path)
            if value:
                return value

    if matcher is None:
        return ""

    pom_text = manifests.get("pom.xml")
    if pom_text:
        pom_license_name = parse_pom_xml_license_name(pom_text, warnings, repo_path)
        if pom_license_name:
            matched = match_license_text(matcher, pom_license_name, warnings, repo_path, "pom.xml")
            if matched:
                return matched

    for filename in LICENSE_FILE_PATHS:
        text = fetch_raw_file(session, repo_path, filename)
        if text:
            # Found *a* LICENSE file -- stop here even if licenseid
            # couldn't match its text, rather than trying every remaining
            # filename hoping for a luckier match against a different file.
            return match_license_text(matcher, text, warnings, repo_path, filename)

    return ""


def funding_yml_urls(text: str, warnings: list, repo_path: str) -> list[str]:
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError as e:
        warnings.append(f"{repo_path}: FUNDING.yml failed to parse ({e})")
        return []
    urls = []
    for key, value in data.items():
        builder = FUNDING_YML_URL_BUILDERS.get(key)
        if not builder or not value:
            continue
        values = value if isinstance(value, list) else [value]
        urls.extend(builder(v) for v in values if v)
    return urls


def pyproject_url_by_label(text: str, label: str, warnings: list, repo_path: str) -> str:
    """`[project.urls]`'s value for `label`, matched case/punctuation-
    insensitively against PyPA's well-known Project-URL labels (spec:
    packaging.python.org/en/latest/specifications/well-known-project-urls)
    -- confirmed against real projects using both `funding` (pandas) and
    `Funding` (pytest) for the same label. Shared by pyproject_funding_url()
    and pyproject_documentation_url(); "" if `label` isn't present at all."""
    try:
        data = tomllib.loads(text)
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
        warnings.append(f"{repo_path}: pyproject.toml failed to parse ({e})")
        return ""
    urls = (data.get("project") or {}).get("urls") or {}
    target = re.sub(r"[^a-z0-9]", "", label.lower())
    for candidate_label, url in urls.items():
        if re.sub(r"[^a-z0-9]", "", candidate_label.lower()) == target:
            return url
    return ""


def pyproject_funding_url(text: str, warnings: list, repo_path: str) -> str:
    return pyproject_url_by_label(text, "funding", warnings, repo_path)


def pyproject_documentation_url(text: str, warnings: list, repo_path: str) -> str:
    return pyproject_url_by_label(text, "documentation", warnings, repo_path)


def parse_cargo_toml_documentation(text: str, warnings: list, repo_path: str) -> str:
    """Cargo.toml's `package.documentation` is a direct URL string (the
    crates.io convention -- usually a docs.rs link), used as-is, no label
    matching needed the way pyproject.toml's `[project.urls]` table does."""
    try:
        data = tomllib.loads(text)
    except (tomllib.TOMLDecodeError, UnicodeDecodeError):
        return ""  # already warned once for this file by the license/keywords parsers
    return (data.get("package") or {}).get("documentation") or ""


def collect_documentation(manifests: dict, warnings: list, repo_path: str) -> str:
    """Priority: pyproject.toml's `Documentation` well-known Project-URL,
    then Cargo.toml's own `documentation` field. No fuzzy fallback the way
    `license` has `licenseid` -- an approximately-right documentation URL is
    worse than none, so this only ever returns a source that named itself
    as documentation explicitly. "" if neither manifest is present in
    `manifests` (opportunistic like collect_keywords() in the normal run --
    pyproject.toml is always fetched, Cargo.toml only when already fetched
    for language/license reasons -- or unconditional in the --fields
    backfill path, see main())."""
    pyproject_text = manifests.get("pyproject.toml")
    if pyproject_text:
        url = pyproject_documentation_url(pyproject_text, warnings, repo_path)
        if url:
            return url
    cargo_text = manifests.get("Cargo.toml")
    if cargo_text:
        return parse_cargo_toml_documentation(cargo_text, warnings, repo_path)
    return ""


def parse_package_json_homepage(text: str, warnings: list, repo_path: str) -> str:
    """npm's package.json has a top-level `homepage` string -- unlike its
    `keywords`/`license` fields, not nested under anything."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return ""  # already warned once for this file by the license/keywords parsers
    homepage = data.get("homepage")
    return homepage if isinstance(homepage, str) else ""


def parse_cargo_toml_homepage(text: str, warnings: list, repo_path: str) -> str:
    """Cargo.toml's `package.homepage` -- the crates.io convention for a
    project's own site, distinct from `package.documentation` (docs.rs-style
    API docs) and `package.repository` (the source repo itself)."""
    try:
        data = tomllib.loads(text)
    except (tomllib.TOMLDecodeError, UnicodeDecodeError):
        return ""
    return (data.get("package") or {}).get("homepage") or ""


def collect_homepage(manifests: dict, github_homepage: str, warnings: list, repo_path: str) -> str:
    """Priority: pyproject.toml's `Homepage` well-known Project-URL, then
    package.json's top-level `homepage`, then Cargo.toml's `package.
    homepage`, then GitHub's own repo `homepage` field as the last resort
    (see fetch_repo_core() for why it ranks below the manifests: often
    blank, occasionally just a duplicate of the repo's own GitHub URL).
    Manifest checks are opportunistic in the normal run (whatever's already
    in `manifests`), unconditional in the --fields backfill path -- same
    pattern as collect_keywords()/collect_documentation()."""
    pyproject_text = manifests.get("pyproject.toml")
    if pyproject_text:
        url = pyproject_url_by_label(pyproject_text, "homepage", warnings, repo_path)
        if url:
            return url
    package_json_text = manifests.get("package.json")
    if package_json_text:
        url = parse_package_json_homepage(package_json_text, warnings, repo_path)
        if url:
            return url
    cargo_text = manifests.get("Cargo.toml")
    if cargo_text:
        url = parse_cargo_toml_homepage(cargo_text, warnings, repo_path)
        if url:
            return url
    return github_homepage


def fetch_codemeta(session: requests.Session, repo_path: str, warnings: list) -> dict:
    text = fetch_raw_file(session, repo_path, "codemeta.json")
    if not text:
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        warnings.append(f"{repo_path}: codemeta.json failed to parse ({e})")
        return {}

    result = {}

    funder = data.get("funder")
    if funder:
        entries = funder if isinstance(funder, list) else [funder]
        names = [e.get("name") for e in entries if isinstance(e, dict) and e.get("name")]
        if names:
            result["funder"] = "; ".join(names)

    funding = data.get("funding")
    if isinstance(funding, str) and funding.startswith(("http://", "https://")):
        result["funding_candidate"] = funding

    dev_status = data.get("developmentStatus")
    if isinstance(dev_status, str):
        result["development_status"] = dev_status
    elif isinstance(dev_status, dict):
        result["development_status"] = dev_status.get("name", "") or dev_status.get("url", "")

    citation = data.get("citation")
    if citation:
        entries = citation if isinstance(citation, list) else [citation]
        for entry in entries:
            url = isinstance(entry, dict) and entry.get("url")
            if url:
                result["paper_url"] = url
                break

    identifier = data.get("@id") or data.get("identifier")
    if isinstance(identifier, str) and identifier.startswith("swh:"):
        result["software_heritage_id"] = identifier

    # CodeMeta's `license` is typically a URL (e.g.
    # https://spdx.org/licenses/MIT) -- the trailing path segment is the
    # SPDX id; a bare id with no slashes is used as-is. Checked first in
    # resolve_license()'s priority chain, ahead of every package-manifest
    # field and licenseid text-matching -- a tool's own codemeta.json
    # declaring its license is the most authoritative source available.
    license_val = data.get("license")
    if isinstance(license_val, str) and license_val:
        result["license"] = license_val.rstrip("/").rsplit("/", 1)[-1] if "/" in license_val else license_val

    # `programmingLanguage` can be a bare string, a schema.org
    # ComputerLanguage object ({"name": "Python"}), or a list of either --
    # confirmed all three shapes appear in real codemeta.json files across
    # the R/rOpenSci and semantic-web ecosystems.
    prog_lang = data.get("programmingLanguage")
    if isinstance(prog_lang, str) and prog_lang:
        result["programming_language"] = prog_lang
    elif isinstance(prog_lang, dict):
        name = prog_lang.get("name", "")
        if name:
            result["programming_language"] = name
    elif isinstance(prog_lang, list):
        names = [(pl.get("name") if isinstance(pl, dict) else pl) for pl in prog_lang]
        names = [n for n in names if n]
        if names:
            result["programming_language"] = "; ".join(names)

    return result


def fetch_citation_cff(session: requests.Session, repo_path: str, warnings: list) -> dict:
    text = fetch_raw_file(session, repo_path, "CITATION.cff")
    if not text:
        return {}
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError as e:
        warnings.append(f"{repo_path}: CITATION.cff failed to parse ({e})")
        return {}

    result = {}

    preferred = data.get("preferred-citation") or {}
    doi = preferred.get("doi")
    paper_url = f"https://doi.org/{doi}" if doi else preferred.get("url", "")
    if paper_url:
        result["paper_url"] = paper_url

    for entry in data.get("identifiers") or []:
        if isinstance(entry, dict) and entry.get("type") == "swh" and entry.get("value"):
            result["software_heritage_id"] = entry["value"]
            break

    # CITATION.cff's top-level `license` is an SPDX expression (a single
    # string, or a list of strings for a multi-licensed project) --
    # conventionally already clean SPDX, same as Cargo.toml/package.json/
    # pyproject.toml's license fields, so used as-is in resolve_license()'s
    # priority chain, no licenseid pass needed.
    license_val = data.get("license")
    if isinstance(license_val, str) and license_val:
        result["license"] = license_val
    elif isinstance(license_val, list):
        names = [v for v in license_val if isinstance(v, str) and v]
        if names:
            result["license"] = "; ".join(names)

    return result


def fetch_openssf_best_practices(repo_path: str, warnings: list) -> dict:
    """Plain, unauthenticated request -- bestpractices.dev never sees the
    GitHub token. `q=` is full-text search, not an exact lookup, so results
    are filtered client-side against this repo's own URL."""
    repo_name = repo_path.split("/")[-1]
    target = normalize_repo_url(f"https://github.com/{repo_path}")
    try:
        resp = requests.get(BESTPRACTICES_API, params={"q": repo_name}, timeout=30)
        if resp.status_code != 200:
            warnings.append(f"{repo_path}: bestpractices.dev returned {resp.status_code}")
            return {}
        for project in resp.json():
            if normalize_repo_url(project.get("repo_url", "")) == target:
                return {
                    "openssf_best_practices_url": f"https://www.bestpractices.dev/projects/{project['id']}",
                    "openssf_best_practices_badge_level": project.get("badge_level", ""),
                }
        return {}  # not registered -- the normal case for most tools
    except requests.RequestException as e:
        warnings.append(f"{repo_path}: bestpractices.dev request failed ({e})")
        return {}


def fetch_openssf_scorecard(repo_path: str, warnings: list) -> dict:
    """Plain, unauthenticated request -- scorecard.dev never sees the
    GitHub token either."""
    try:
        resp = requests.get(f"{SCORECARD_API}/github.com/{quote(repo_path)}", timeout=30)
        if resp.status_code == 404:
            return {}  # never scanned -- the normal case for most tools
        if resp.status_code != 200:
            warnings.append(f"{repo_path}: scorecard.dev returned {resp.status_code}")
            return {}
        data = resp.json()
        result = {
            "openssf_scorecard_url": f"https://scorecard.dev/viewer/?uri=github.com/{repo_path}",
            "openssf_scorecard_score": data.get("score"),
        }
        for check in data.get("checks") or []:
            column = SCORECARD_CHECK_COLUMNS.get(check.get("name"))
            if column:
                result[column] = check.get("score")
        return result
    except requests.RequestException as e:
        warnings.append(f"{repo_path}: scorecard.dev request failed ({e})")
        return {}


def collect_funding(session: requests.Session, repo_path: str, codemeta_candidate: str,
                    pyproject_text: str | None, warnings: list) -> str:
    """Always computes and returns whatever it finds -- this script writes
    unconditionally to `tool_metadata`, which is 100% machine-owned;
    "should this override a curated value" is resolved later, in build.py,
    by the tools/tool_metadata precedence rule, not here. Tries
    FUNDING.yml, then pyproject.toml's `Funding` project URL, then
    codemeta.json's own `funding` field (only if URL-shaped); first hit
    wins, but every candidate found is logged so a human can see what was
    passed over. `pyproject_text` comes from fetch_package_manifests() --
    already fetched once for license/language resolution, not re-fetched
    here."""
    candidates = []
    funding_yml = fetch_raw_file(session, repo_path, ".github/FUNDING.yml")
    if funding_yml:
        candidates.extend(funding_yml_urls(funding_yml, warnings, repo_path))

    if pyproject_text:
        url = pyproject_funding_url(pyproject_text, warnings, repo_path)
        if url:
            candidates.append(url)

    if codemeta_candidate:
        candidates.append(codemeta_candidate)

    if not candidates:
        return ""
    if len(candidates) > 1:
        warnings.append(f"{repo_path}: {len(candidates)} funding URL candidates found "
                         f"({', '.join(candidates)}); used the first")
    return candidates[0]


def check_rate_limit(session: requests.Session) -> tuple[int, int]:
    """(remaining, limit) for the GitHub core API. Never raises -- a failed
    preflight check shouldn't block the run, just leave the estimate
    unprinted."""
    try:
        resp = session.get(f"{GITHUB_API}/rate_limit", timeout=15)
        core = resp.json().get("resources", {}).get("core", {})
        return core.get("remaining", -1), core.get("limit", -1)
    except (requests.RequestException, ValueError):
        return -1, -1


def load_checkpointed_ids(out_path: Path) -> set:
    """ids already written to --out by an earlier, interrupted run of this
    script -- skipped on this run rather than re-collected. This is what
    makes it safe to just re-run the same command after an interruption
    (rate limit, network blip, this session's own tool timeout, ...)
    instead of losing everything and starting over."""
    if not out_path.exists():
        return set()
    with open(out_path, "r", encoding="utf-8") as f:
        return {row["id"] for row in csv.DictReader(f)}


def _backfill_field_missing(tool: dict, field: str) -> bool:
    """Used only by --fields backfill selection. `sponsors` is Optional[int]
    in site/data.json -- 0 is a real, already-collected answer (an owner
    with a Sponsors listing and no current sponsors), not "missing", so it
    needs `is None` specifically rather than a truthiness check (which
    would treat 0 as blank and re-fetch it forever). `keywords` has no such
    zero-vs-blank distinction -- an empty list and "never collected" mean
    the same thing."""
    value = tool.get(field)
    if field == "sponsors":
        return value is None
    return not value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-json", default="site/data.json",
                         help="local build output to read the live tool catalog from")
    parser.add_argument("--candidates", default=None,
                         help="collect for tools not yet in the live sheet instead of "
                              "site/data.json -- point this at candidate_tools.csv (or "
                              "anything with the same 'id'/'tool_type'/'source' columns) "
                              "so a batch of freshly-emitted candidates gets its "
                              "tool_metadata row ready to paste alongside the tools/tool_map "
                              "rows, in one round-trip instead of pasting tools first, "
                              "rebuilding, then re-running the collector")
    parser.add_argument("--out", default="curation/state/tool_metadata.csv")
    parser.add_argument("--refresh-all", action="store_true",
                         help="re-collect for every eligible tool, not just ones missing `stars`")
    parser.add_argument("--restart", action="store_true",
                         help="ignore any checkpoint in --out and start over from row 1 "
                              "(overwrites --out instead of resuming it)")
    parser.add_argument("--sleep", type=float, default=1.0,
                         help="seconds to sleep between tools (stays polite to the third-party APIs)")
    parser.add_argument("--limit", type=int, default=None,
                         help="stop after this many tools this run (for a deliberately small batch)")
    parser.add_argument("--fields", default=None,
                         help="comma-separated subset of {keywords,sponsors,documentation,homepage} -- "
                              "cheaply backfill "
                              "ONLY these columns for tools already collected (non-blank `stars` "
                              "in --data-json), skipping every other API call (repo core beyond "
                              "topics, contributors, releases, community profile, security/"
                              "governance probes, sbom, codemeta.json, CITATION.cff, funding, "
                              "license/language resolution, OpenSSF lookups -- none of it runs). "
                              "Output is a minimal id+field(s) CSV, NOT a full tool_metadata row -- "
                              "paste it into ONLY those columns in the live sheet, matched by id, "
                              "never as a row or full-tab replacement (every other column is left "
                              "unfetched, not just unchanged, so a full-row paste would blank them "
                              "out). Not compatible with --candidates (nothing to backfill for a "
                              "tool that's never been collected at all).")
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit(
            "GITHUB_TOKEN is not set. This script needs a personal access token with "
            "public read access (no special scopes needed) -- see curation/README.md."
        )

    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })

    warnings: list = []
    unresolvable_source: list = []

    fields = None
    if args.fields:
        if args.candidates:
            raise SystemExit(
                "--fields backfill mode reads already-collected tools (non-blank `stars`) from "
                "--data-json -- it doesn't apply to --candidates, brand new tools with nothing "
                "collected yet. Run the normal full collection for those instead."
            )
        fields = {f.strip() for f in args.fields.split(",") if f.strip()}
        unknown = fields - BACKFILL_FIELDS
        if unknown:
            raise SystemExit(f"--fields only supports {sorted(BACKFILL_FIELDS)}, got unknown: {sorted(unknown)}")

    # licenseid's local SQLite index is only needed for the normal run's
    # license resolution (resolve_license()'s steps 5/6) -- --fields
    # backfill mode never calls resolve_license() at all, so loading it here
    # would just cost startup time for nothing.
    matcher = None
    if fields is None:
        try:
            matcher = AggregatedLicenseMatcher()
        except Exception as e:
            print(f"[collect] WARNING: licenseid matcher unavailable ({e}) -- license resolution "
                  f"will skip LICENSE-file text-matching and pom.xml normalization, falling straight "
                  f"through to GitHub's own detected license wherever codemeta.json and the ecosystem "
                  f"manifests don't already answer it. Run `licenseid update` to build its local "
                  f"database (see curation/README.md's Setup), then re-run.")

    if args.candidates:
        candidates_path = Path(args.candidates)
        if not candidates_path.exists():
            raise SystemExit(f"{candidates_path} not found.")
        with open(candidates_path, "r", encoding="utf-8") as f:
            tools = [{"id": row["id"], "source": row["source"]}
                     for row in csv.DictReader(f)
                     if row.get("tool_type") in ("software", "specification") and row.get("source")]
        print(f"[collect] reading tools from {candidates_path} (not yet live) "
              f"instead of {args.data_json}")
    else:
        data_path = Path(args.data_json)
        if not data_path.exists():
            raise SystemExit(f"{data_path} not found -- run `python build.py` first.")
        with open(data_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if fields is not None:
            # Already-collected tools only (never-collected ones get
            # keywords/sponsors for free the next time they go through a
            # normal run) -- and, unless --refresh-all, only ones actually
            # missing at least one requested field, so a re-run after a
            # partial paste doesn't redo work for ids already filled in live.
            tools = [t for t in data.get("tools", [])
                     if t.get("tool_type") in ("software", "specification")
                     and t.get("stars") is not None
                     and (args.refresh_all or any(_backfill_field_missing(t, f) for f in fields))]
        else:
            tools = [t for t in data.get("tools", [])
                     if t.get("tool_type") in ("software", "specification")
                     and (args.refresh_all or t.get("stars") is None)]

    out_path = Path(args.out)
    checkpointed = set() if args.restart else load_checkpointed_ids(out_path)
    if checkpointed:
        before = len(tools)
        tools = [t for t in tools if t["id"] not in checkpointed]
        print(f"[collect] resuming: {len(checkpointed)} tool(s) already in {out_path} "
              f"from an earlier run, {before - len(tools)} of them skipped")

    if args.limit is not None:
        tools = tools[: args.limit]

    remaining, rate_limit = check_rate_limit(session)
    # Rough worst case per tool: repo core (1) + contributors (1) + releases
    # (2) + community profile (1) + security probe (up to 3) + governance
    # probe (up to 5) + sbom (1) + codemeta (1) + CITATION.cff (1) +
    # FUNDING.yml (1) + pyproject.toml (1, always) = ~18 GitHub calls in the
    # common case, where GitHub's own language/license answers are trusted
    # and the rest of the package manifests are never fetched at all (see
    # `language_needs_manifests`/`license_needs_manifests` in the main
    # loop). Worst case (GitHub's language guess is blank/implausible, or
    # its license is also blank) adds the other 6 manifests (+1 conditional
    # tsconfig.json) and up to 6 LICENSE-filename probes -- ~28. Estimate
    # for the *whole run* splits the difference rather than assuming
    # worst-case for every tool, which historically way overshoots actual
    # usage. licenseid's own matching is local (its SQLite index, no
    # network per call), so it doesn't add to either estimate.
    if fields is not None:
        # keywords/homepage share one repo-core call (1 GitHub call total,
        # not one each, if both are requested -- see main()'s backfill
        # loop). Every field that reads a manifest (keywords, documentation,
        # homepage) does so via BACKFILL_MANIFEST_FILES, unioned across
        # every requested field so a shared file (e.g. pyproject.toml,
        # wanted by all three) is only counted once per tool, not once per
        # field. sponsors -> 0 GitHub calls (sponsors.ecosyste.ms only,
        # cached per owner across the run). No manifest fetch here is gated
        # behind language/license resolution the way the normal run's is,
        # since that resolution never runs in this mode.
        manifest_call_count = len(set().union(*(BACKFILL_MANIFEST_FILES.get(f, []) for f in fields)))
        calls_per_tool = manifest_call_count + (1 if ("keywords" in fields or "homepage" in fields) else 0)
        estimated_calls = len(tools) * calls_per_tool
    else:
        # Rough worst case per tool: repo core (1) + contributors (1) + releases
        # (2) + community profile (1) + security probe (up to 3) + governance
        # probe (up to 5) + sbom (1) + codemeta (1) + CITATION.cff (1) +
        # FUNDING.yml (1) + pyproject.toml (1, always) = ~18 GitHub calls in the
        # common case, where GitHub's own language/license answers are trusted
        # and the rest of the package manifests are never fetched at all (see
        # `language_needs_manifests`/`license_needs_manifests` in the main
        # loop). Worst case (GitHub's language guess is blank/implausible, or
        # its license is also blank) adds the other 6 manifests (+1 conditional
        # tsconfig.json) and up to 6 LICENSE-filename probes -- ~28. Estimate
        # for the *whole run* splits the difference rather than assuming
        # worst-case for every tool, which historically way overshoots actual
        # usage. licenseid's own matching is local (its SQLite index, no
        # network per call), so it doesn't add to either estimate.
        estimated_calls = len(tools) * 20
    if remaining >= 0:
        print(f"[collect] GitHub rate limit: {remaining}/{rate_limit} remaining "
              f"(this run needs up to ~{estimated_calls})")
        if estimated_calls > remaining:
            print(f"[collect] WARNING: estimated worst-case calls ({estimated_calls}) exceed "
                  f"remaining quota ({remaining}) -- this run may hit the rate limit partway "
                  f"through. Already-collected rows stay in {out_path} either way (written "
                  f"incrementally); re-run the same command later to pick up where it left off, "
                  f"or pass --limit to deliberately do a smaller batch now.")

    print(f"[collect] {len(tools)} software tool(s) to process this run"
          + (f" (--fields {','.join(sorted(fields))})" if fields is not None
             else " (--refresh-all)" if args.refresh_all else " (missing stars)"))

    # "YYYY-MM-DD HH:MM" (UTC, no seconds, no offset), matching every existing
    # datetime_* cell in both live sheets exactly -- see emit_candidates.py's
    # sheet_timestamp for the same convention. All three columns get the same
    # value: this script never reads the sheet's current content, only
    # site/data.json, so there's no prior datetime_added to preserve across a
    # --refresh-all re-collection -- "added" here means "last (re-)collected",
    # consistent with tool_metadata being a full-replacement paste with
    # nothing to preserve (see the module docstring).
    sheet_timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M")

    # In --fields mode, a minimal id + requested-fields header, NOT
    # OUT_FIELDNAMES -- this file is a column patch, never a full
    # tool_metadata row, so it must never carry the other columns at all
    # (blank would look like "collected, and empty," which is wrong).
    out_fieldnames = (["id"] + [f for f in OUT_FIELDNAMES if f in fields]) if fields is not None else OUT_FIELDNAMES

    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = args.restart or not out_path.exists()
    out_file = open(out_path, "w" if args.restart else "a", encoding="utf-8", newline="")
    writer = csv.DictWriter(out_file, fieldnames=out_fieldnames)
    if write_header:
        writer.writeheader()

    # owner login -> active_sponsors_count (or None), populated across the
    # whole run -- see fetch_sponsors_count(). Multiple tools under the same
    # GitHub org/user (confirmed in this catalog) share one lookup instead
    # of paying for it per tool.
    sponsors_cache: dict = {}

    # --fields backfill mode only: the union of manifest filenames every
    # requested field needs, computed once for the whole run -- e.g.
    # `--fields keywords,documentation` both want pyproject.toml, so this
    # fetches it once per tool, not once per field that happens to want it.
    backfill_manifest_files = (
        sorted(set().union(*(BACKFILL_MANIFEST_FILES.get(f, []) for f in fields)))
        if fields is not None else []
    )

    try:
        for i, tool in enumerate(tools, 1):
            repo_path = extract_repo_path(tool.get("source", ""))
            if not repo_path:
                unresolvable_source.append(tool["id"])
                continue

            if fields is not None:
                # The entire point of --fields: none of the normal run's
                # other ~18-28 calls happen here -- just what each requested
                # field actually needs. `manifests` is fetched once per tool
                # (the union computed above), then handed to whichever
                # collectors are asked for, same as the normal run's shared
                # `manifests` dict.
                row = {"id": tool["id"]}
                manifests = {filename: fetch_raw_file(session, repo_path, filename)
                             for filename in backfill_manifest_files}
                # repo core is only fetched once, shared by `keywords`
                # (topics) and `homepage` (its own last-resort fallback) --
                # neither needs it if the other isn't also requested.
                core = fetch_repo_core(session, repo_path, warnings) \
                    if ("keywords" in fields or "homepage" in fields) else {}
                if "keywords" in fields:
                    row["keywords"] = collect_keywords(core.get("topics", []), manifests, warnings, repo_path)
                if "documentation" in fields:
                    row["documentation"] = collect_documentation(manifests, warnings, repo_path)
                if "homepage" in fields:
                    row["homepage"] = collect_homepage(manifests, core.get("homepage", ""), warnings, repo_path)
                if "sponsors" in fields:
                    row["sponsors"] = fetch_sponsors_count(repo_path.split("/")[0], sponsors_cache, warnings)

                print(f"  [{i}/{len(tools)}] {tool['id']}: "
                      + " ".join(f"{f}={row.get(f) or '-'}" for f in sorted(fields)))
                writer.writerow(row)
                out_file.flush()

                if i % 20 == 0:
                    remaining, rate_limit = check_rate_limit(session)
                    if 0 <= remaining < 100:
                        print(f"[collect] stopping early: GitHub rate limit down to "
                              f"{remaining}/{rate_limit}. {out_path} has everything collected so "
                              f"far -- re-run the same command once the limit resets to continue.")
                        break

                time.sleep(args.sleep)
                continue

            core = fetch_repo_core(session, repo_path, warnings)
            default_branch = core.pop("default_branch", "main")
            topics = core.pop("topics", [])
            contributors = fetch_contributors_count(session, repo_path, warnings)
            releases = fetch_releases(session, repo_path, warnings)
            profile = fetch_community_profile(session, repo_path, warnings)
            security_url = probe_paths(session, repo_path, SECURITY_POLICY_PATHS, default_branch)
            governance_url = probe_paths(session, repo_path, GOVERNANCE_PATHS, default_branch)
            sbom_url = fetch_sbom_url(session, repo_path)
            codemeta = fetch_codemeta(session, repo_path, warnings)
            citation = fetch_citation_cff(session, repo_path, warnings)
            best_practices = fetch_openssf_best_practices(repo_path, warnings)
            scorecard = fetch_openssf_scorecard(repo_path, warnings)

            # codemeta.json is checked first for paper_url/software_heritage_id
            # (more structured than CITATION.cff's free-form preferred-citation),
            # CITATION.cff fills in if codemeta didn't have it or doesn't exist.
            paper_url = codemeta.get("paper_url") or citation.get("paper_url", "")
            swh_id = codemeta.get("software_heritage_id") or citation.get("software_heritage_id", "")

            # Two independent triggers decide whether the 6-7 ecosystem
            # package-manifest files (Cargo.toml, go.mod, package.json,
            # pom.xml, build.gradle*) are worth fetching at all for this
            # tool -- for the common case where neither fires, this saves
            # those calls entirely (pyproject.toml is always fetched
            # regardless, needed for `funding`; see fetch_package_manifests()).
            #
            # `language_needs_manifests`: GitHub's own `language` guess is
            # blank, or implausible as a real implementation language (see
            # NON_IMPLEMENTATION_LANGUAGES) -- trusting a plausible GitHub
            # answer directly, with zero extra calls, is correct far more
            # often than not; manifests are only worth the cost when that
            # trust is misplaced or there's nothing to trust at all.
            #
            # `license_needs_manifests`: codemeta.json, CITATION.cff, and
            # GitHub's own detection all came up empty -- GitHub's
            # detection is free either way (already fetched via `core`)
            # and reliable when it has an answer (see resolve_license()'s
            # docstring), so there's no reason to check manifests for a
            # license field ahead of it, only after it's also failed.
            github_language = core.get("programming_language", "")
            github_license = core.get("license", "")
            language_needs_manifests = (not github_language) or (github_language in NON_IMPLEMENTATION_LANGUAGES)
            license_needs_manifests = not (codemeta.get("license") or citation.get("license") or github_license)
            manifests = fetch_package_manifests(session, repo_path,
                                                include_all=language_needs_manifests or license_needs_manifests)

            funding = collect_funding(session, repo_path, codemeta.get("funding_candidate", ""),
                                      manifests.get("pyproject.toml"), warnings)

            license_value = resolve_license(session, repo_path, codemeta.get("license", ""),
                                            citation.get("license", ""), manifests,
                                            github_license, warnings, matcher)

            if codemeta.get("programming_language"):
                programming_language_value = codemeta["programming_language"]
            elif not language_needs_manifests:
                programming_language_value = github_language
            else:
                # GitHub's guess was blank/implausible -- every ecosystem
                # manifest actually found, combined (real polyglot support,
                # not just a single first-match guess). Genuinely "" if
                # none exist at all: a repo that's not source code in any
                # of these ecosystems (a specification/vocabulary, e.g.)
                # has no programming language, and blank says exactly
                # that -- never falls back to the just-rejected GitHub
                # guess, which would defeat the whole point of rejecting it.
                programming_language_value = "; ".join(detect_languages_from_manifests(manifests))

            keywords_value = collect_keywords(topics, manifests, warnings, repo_path)
            sponsors_value = fetch_sponsors_count(repo_path.split("/")[0], sponsors_cache, warnings)
            documentation_value = collect_documentation(manifests, warnings, repo_path)
            # `core["homepage"]` (GitHub's own field) is the last-resort
            # fallback inside collect_homepage() itself, not used directly
            # here -- `row["homepage"]` below overrides whatever `row.
            # update(core)` just set with the full priority-chain result.
            homepage_value = collect_homepage(manifests, core.get("homepage", ""), warnings, repo_path)

            print(f"  [{i}/{len(tools)}] {tool['id']}: "
                  f"stars={core.get('stars', '?')} "
                  f"license={license_value or '-'} "
                  f"lang={programming_language_value or '-'} "
                  f"scorecard={scorecard.get('openssf_scorecard_score', '-')} "
                  f"best_practices={best_practices.get('openssf_best_practices_badge_level', '-')}")

            row = {"id": tool["id"], "name": tool.get("name", ""), "source": tool.get("source", "")}
            row["datetime_added"] = sheet_timestamp
            row["datetime_checked"] = sheet_timestamp
            row["datetime_updated"] = sheet_timestamp
            row.update(core)
            row["license"] = license_value
            row["programming_language"] = programming_language_value
            row["contributors"] = contributors
            row.update(releases)
            row.update(profile)
            row["security_policy_url"] = security_url
            row["governance_url"] = governance_url
            row["sbom_url"] = sbom_url
            row["funding"] = funding
            row["funder"] = codemeta.get("funder", "")
            row["development_status"] = codemeta.get("development_status", "")
            row["keywords"] = keywords_value
            row["sponsors"] = sponsors_value
            row["documentation"] = documentation_value
            row["homepage"] = homepage_value
            row["paper_url"] = paper_url
            row["software_heritage_id"] = swh_id
            row.update(best_practices)
            row.update(scorecard)
            # Written and flushed immediately, not batched to the end -- so an
            # interruption partway through (rate limit, network, Ctrl-C, this
            # session's own tool timeout) loses at most the one in-flight row,
            # never the whole run. See load_checkpointed_ids() for the other
            # half of this: resuming a later run from here.
            writer.writerow({k: row.get(k, "") if row.get(k) is not None else "" for k in OUT_FIELDNAMES})
            out_file.flush()

            if i % 20 == 0:
                remaining, rate_limit = check_rate_limit(session)
                if 0 <= remaining < 100:
                    print(f"[collect] stopping early: GitHub rate limit down to "
                          f"{remaining}/{rate_limit}. {out_path} has everything collected so "
                          f"far -- re-run the same command once the limit resets to continue.")
                    break

            time.sleep(args.sleep)
    finally:
        out_file.close()

    total_in_file = len(load_checkpointed_ids(out_path))
    is_full_catalog_run = args.refresh_all and not args.candidates
    if fields is not None:
        print(f"\n{out_path} now has {total_in_file} row(s) total ({', '.join(sorted(fields))} "
              f"only) -- this is a COLUMN PATCH, not a tool_metadata row: paste it into ONLY the "
              f"{'/'.join(sorted(fields))} column(s) of the live sheet, matched by id (e.g. sort "
              f"both by id and paste-special just those columns). Do NOT paste as a row or full-"
              f"tab replacement -- every other column was never fetched this run, so that would "
              f"blank them out for every id in this file.")
    elif is_full_catalog_run:
        print(f"\n{out_path} now has {total_in_file} row(s) total -- review, then paste in as "
              f"a full replacement of the `tool_metadata` sheet's contents (safe: nothing there "
              f"is ever hand-edited). Use --restart on a periodic full refresh to also drop rows "
              f"for tools removed from the catalog since the last run.")
    else:
        # Either --candidates (tools not yet live at all) or the default
        # incremental mode (only tools missing `stars`, i.e. never
        # collected) -- either way this file does NOT cover every tool
        # already live in tool_metadata, so pasting it as a full replacement
        # would silently delete every row it doesn't happen to include.
        source_desc = f"from {args.candidates} (not yet live)" if args.candidates else "missing metadata until now"
        print(f"\n{out_path} now has {total_in_file} row(s) total ({source_desc}) -- review, "
              f"then APPEND these rows to the `tool_metadata` sheet alongside its existing "
              f"content. Do NOT paste as a full replacement -- that would wipe out every "
              f"already-live tool's collected data. Use --refresh-all (without --candidates) "
              f"for an actual full-catalog replacement run.")
    if unresolvable_source:
        print(f"\n{len(unresolvable_source)} tool(s) have no GitHub-style `source` URL "
              f"and need a manual look (or a GitLab/Codeberg fetch path this script doesn't have yet):")
        for tid in unresolvable_source:
            print(f"  - {tid}")
    if warnings:
        print(f"\n{len(warnings)} warning(s):")
        for w in warnings:
            print(f"  - {w}")


if __name__ == "__main__":
    main()
