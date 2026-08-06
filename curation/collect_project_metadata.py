#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2026 OpenTAIG authors
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Collect project-quality / community-health metadata for the
`tool_metadata` tab -- a separate spreadsheet from the main OpenTAIG one,
100% written by this script, joined onto `tools` by `id` at build time (see
"tools / tool_metadata precedence" in build.py and docs/data-schema.md).
GitHub-only for now (GitLab/Codeberg would need their own fetch functions;
no tool in the catalog is hosted there yet, so they aren't built
speculatively -- see the module docstring bottom for what that would take).

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

Sources -- one repo costs ~12-18 GitHub API calls (varies with how many
security/governance path probes short-circuit) + 2 third-party calls, all
confirmed by hand against real repos before this script was written, not
assumed from documentation:

  - `GET /repos/{owner}/{repo}` -> stars (`stargazers_count`), forks
    (`forks_count`), watchers (`subscribers_count` -- NOT `watchers_count`,
    which has been a silent alias for `stargazers_count` since GitHub folded
    "Watch" into "Star"), open_issues_count (`open_issues_count`; GitHub
    conflates open PRs into this count, a known quirk, not a bug in this
    script), last_commit_date (`pushed_at`, date part only),
    programming_language (`language`, the same single dominant-by-bytes
    field `backfill_programming_language.py` used to fetch on its own),
    and `default_branch` (needed by several probes below).
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

Both third-party calls (bestpractices.dev, scorecard.dev) are made with a
**plain, unauthenticated request** -- never through the GitHub-authed
session, so the GITHUB_TOKEN header is never sent to a third-party host.
The same is true of every GitHub *contents* fetch used for YAML/TOML/JSON
parsing below -- they go through the normal authed `session`, since they're
still github.com, just returned as base64-decoded raw content via the
`vnd.github.raw+json` media type rather than JSON-wrapped.

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

`dependents_count` is deliberately NOT collected here -- GitHub's "Used by"
dependency-graph count has no public API, only an HTML page
(`/network/dependents`), and this script doesn't scrape it: fragile against
markup changes, and bulk-scraping a GitHub HTML page for data with no API
sits in ToS gray territory that a one-off manual check in a browser doesn't.
Leave that column for manual spot-checks.

Same GITHUB_TOKEN / session requirement as search_repos.py -- see that
script's docstring, or curation/README.md's "Setup" section, for the
`gh auth token` vs repo-scoped-token distinction.

By default, only considers `tool_type` "software" rows with a GitHub
`source` URL and no `stars` value yet (i.e. never collected) -- pass
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
limit (`/rate_limit`) before starting, with a rough worst-case call estimate
for the run (~18 GitHub calls/tool), and re-checks every 20 tools --
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
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import time
import tomllib
from pathlib import Path
from urllib.parse import quote

import requests
import yaml

GITHUB_API = "https://api.github.com"
BESTPRACTICES_API = "https://www.bestpractices.dev/projects.json"
SCORECARD_API = "https://api.scorecard.dev/projects"
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

OUT_FIELDNAMES = [
    "id", "name", "source", "programming_language",
    "stars", "forks", "watchers", "contributors",
    "open_issues_count", "releases_count", "latest_release_date", "last_commit_date",
    "readme_url", "license_url", "code_of_conduct_url", "contributing_url",
    "security_policy_url", "governance_url", "sbom_url",
    "funding", "funder", "development_status", "paper_url", "software_heritage_id",
    "openssf_best_practices_url", "openssf_best_practices_badge_level",
    "openssf_scorecard_url", "openssf_scorecard_score",
    "openssf_scorecard_branch_protection", "openssf_scorecard_code_review",
    "openssf_scorecard_maintained", "openssf_scorecard_vulnerabilities",
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
        return {
            "stars": data.get("stargazers_count"),
            "forks": data.get("forks_count"),
            "watchers": data.get("subscribers_count"),
            "open_issues_count": data.get("open_issues_count"),
            "last_commit_date": (data.get("pushed_at") or "")[:10],
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


def pyproject_funding_url(text: str, warnings: list, repo_path: str) -> str:
    try:
        data = tomllib.loads(text)
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
        warnings.append(f"{repo_path}: pyproject.toml failed to parse ({e})")
        return ""
    urls = (data.get("project") or {}).get("urls") or {}
    # PyPA well-known labels match case/punctuation-insensitively (spec:
    # packaging.python.org/en/latest/specifications/well-known-project-urls)
    # -- confirmed against real projects using both "funding" (pandas) and
    # "Funding" (pytest).
    for label, url in urls.items():
        if re.sub(r"[^a-z0-9]", "", label.lower()) == "funding":
            return url
    return ""


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


def collect_funding(session: requests.Session, repo_path: str,
                    codemeta_candidate: str, warnings: list) -> str:
    """Always computes and returns whatever it finds -- this script writes
    unconditionally to `tool_metadata`, which is 100% machine-owned;
    "should this override a curated value" is resolved later, in build.py,
    by the tools/tool_metadata precedence rule, not here. Tries
    FUNDING.yml, then pyproject.toml's `Funding` project URL, then
    codemeta.json's own `funding` field (only if URL-shaped); first hit
    wins, but every candidate found is logged so a human can see what was
    passed over."""
    candidates = []
    funding_yml = fetch_raw_file(session, repo_path, ".github/FUNDING.yml")
    if funding_yml:
        candidates.extend(funding_yml_urls(funding_yml, warnings, repo_path))

    pyproject = fetch_raw_file(session, repo_path, "pyproject.toml")
    if pyproject:
        url = pyproject_funding_url(pyproject, warnings, repo_path)
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-json", default="site/data.json",
                         help="local build output to read the live tool catalog from")
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
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit(
            "GITHUB_TOKEN is not set. This script needs a personal access token with "
            "public read access (no special scopes needed) -- see curation/README.md."
        )

    data_path = Path(args.data_json)
    if not data_path.exists():
        raise SystemExit(f"{data_path} not found -- run `python build.py` first.")
    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })

    warnings: list = []
    unresolvable_source: list = []

    tools = [t for t in data.get("tools", [])
             if t.get("tool_type") == "software"
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
    # FUNDING.yml (1) + pyproject.toml (1) = ~18 GitHub calls.
    estimated_calls = len(tools) * 18
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
          + (" (--refresh-all)" if args.refresh_all else " (missing stars)"))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = args.restart or not out_path.exists()
    out_file = open(out_path, "w" if args.restart else "a", encoding="utf-8", newline="")
    writer = csv.DictWriter(out_file, fieldnames=OUT_FIELDNAMES)
    if write_header:
        writer.writeheader()

    try:
        for i, tool in enumerate(tools, 1):
            repo_path = extract_repo_path(tool.get("source", ""))
            if not repo_path:
                unresolvable_source.append(tool["id"])
                continue

            core = fetch_repo_core(session, repo_path, warnings)
            default_branch = core.pop("default_branch", "main")
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

            funding = collect_funding(session, repo_path,
                                      codemeta.get("funding_candidate", ""), warnings)

            print(f"  [{i}/{len(tools)}] {tool['id']}: "
                  f"stars={core.get('stars', '?')} "
                  f"scorecard={scorecard.get('openssf_scorecard_score', '-')} "
                  f"best_practices={best_practices.get('openssf_best_practices_badge_level', '-')}")

            row = {"id": tool["id"], "name": tool.get("name", ""), "source": tool.get("source", "")}
            row.update(core)
            row["contributors"] = contributors
            row.update(releases)
            row.update(profile)
            row["security_policy_url"] = security_url
            row["governance_url"] = governance_url
            row["sbom_url"] = sbom_url
            row["funding"] = funding
            row["funder"] = codemeta.get("funder", "")
            row["development_status"] = codemeta.get("development_status", "")
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
    print(f"\n{out_path} now has {total_in_file} row(s) total -- review, then paste in as "
          f"a full replacement of the `tool_metadata` sheet's contents (safe: nothing there "
          f"is ever hand-edited). Use --restart on a periodic full refresh to also drop rows "
          f"for tools removed from the catalog since the last run.")
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
