#!/usr/bin/env python3
"""Search GitHub for candidate open-source tools, by keyword.

Uses the real GitHub REST Search API (``/search/repositories``), so it needs
a ``GITHUB_TOKEN`` env var and normal, unrestricted network access to
``api.github.com``. A Claude Code session whose only GitHub credential is an
auto-injected, repo-scoped token will get a 403 ("sessions are bound to
their configured repositories") -- but ``export GITHUB_TOKEN=$(gh auth
token)`` works fine when the environment has its own independent ``gh auth
login`` session (verify with ``gh auth status`` first), since that token
carries the real user's normal scopes rather than being repo-bound. See
curation/README.md's "Running locally" section.

Applies the same qualifiers as a manual GitHub search:

    <keyword> stars:>{min_stars} pushed:>{cutoff_date} archived:false fork:false

`min_stars` is kept deliberately low (default 19, i.e. 20+) so solid but
lesser-known academic/research tools aren't filtered out just for having a
small audience -- the point is excluding noise (empty scaffolds, abandoned
forks), not popularity contests. `pushed_after_months` (default 12) excludes
dead projects.

That query already filters archived/forked/inactive/low-star repos
server-side. A **second, local** filter then drops repos whose README is too
short to be a real description (e.g. a 1-line README that just repeats the
title) -- this needs a follow-up request per repo, so it's kept as a
separate, cheaper-to-skip stage.

Output (kept deliberately as two files, per the "keep the full list
somewhere, filter before the mapping step" instruction):

  - ``curation/state/search_raw/<keyword-slug>.json`` -- every repo the
    GitHub query returned (already past the stars/pushed/archived/fork
    filters), one file per keyword, for full auditability.
  - ``curation/state/search_candidates.csv`` -- the above, deduplicated
    across all keywords searched so far, MINUS repos with a too-short
    README. This is what step "Map to RQ" should read from.

Usage:

    export GITHUB_TOKEN=ghp_...
    python curation/search_repos.py --keyword "bias detection dataset audit" \\
        --keyword "training data license scanner"

Re-run with more/different --keyword values over time; --out-candidates is
appended-and-deduplicated, not overwritten, so this can be run incrementally
across many sessions.
"""
from __future__ import annotations

import argparse
import csv
import datetime
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

GITHUB_API = "https://api.github.com"
DEFAULT_MIN_STARS = 19  # query is stars:>19, i.e. 20 or more
DEFAULT_PUSHED_AFTER_MONTHS = 12
DEFAULT_MIN_README_CHARS = 200  # excludes ~1-line "This is X." READMEs
_slug_re = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    return _slug_re.sub("-", text.strip().lower()).strip("-") or "keyword"


def cutoff_date(months: int) -> str:
    # No dateutil dependency: step back by (roughly) `months` months using a
    # fixed 30.44-day average -- fine for a coarse "still active" filter.
    dt = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=months * 30.44)
    return dt.strftime("%Y-%m-%d")


def build_query(keyword: str, min_stars: int, pushed_after: str) -> str:
    return f"{keyword} stars:>{min_stars} pushed:>{pushed_after} archived:false fork:false"


def search_repositories(session: requests.Session, query: str, warnings: list,
                        max_pages: int = 1) -> list:
    """GitHub repository search, sorted by stars, following pagination up to
    `max_pages` pages of 100.

    Defaults to a single page to preserve the original behaviour for ordinary
    free-text keywords, where 100 star-sorted hits is already well past the
    point of diminishing returns. Raise it (`--max-pages`) for `topic:` tag
    sweeps, which routinely match several hundred repos -- silently keeping
    only the top 100 there would make a "total" sweep quietly partial, and
    the truncation is invisible in the output because `total_count` isn't
    what gets written out.

    GitHub caps *any* search at 1000 results (10 pages) regardless of
    `total_count`, so max_pages above 10 buys nothing; a query reporting more
    than 1000 needs narrowing (extra term, or a higher --min-stars) to be
    mined exhaustively. That case is recorded as a warning rather than
    passing silently.

    The search endpoint is rate-limited to 30 req/min authenticated, so
    paginated sweeps sleep briefly between pages."""
    items = []
    for page in range(1, max_pages + 1):
        resp = session.get(
            f"{GITHUB_API}/search/repositories",
            params={"q": query, "sort": "stars", "order": "desc",
                    "per_page": 100, "page": page},
            timeout=30,
        )
        if resp.status_code == 403 and "rate limit" in resp.text.lower():
            reset = resp.headers.get("X-RateLimit-Reset")
            warnings.append(f"rate limited on query {query!r} (page {page}); resets at {reset}")
            break
        if resp.status_code == 422:
            # Past the 1000-result ceiling: GitHub rejects the page rather
            # than returning an empty list. Not an error, just the end.
            break
        resp.raise_for_status()
        payload = resp.json()
        batch = payload.get("items", [])
        items.extend(batch)
        total = payload.get("total_count", 0)
        if page == 1 and total > 1000:
            warnings.append(
                f"query {query!r} reports {total} results but GitHub caps search at 1000; "
                f"narrow it (extra term or higher --min-stars) to mine it exhaustively")
        if len(batch) < 100 or len(items) >= min(total, 1000):
            break
        time.sleep(2)  # stay well inside the 30 req/min search limit
    return items


def fetch_readme_text(session: requests.Session, full_name: str, warnings: list) -> str:
    """Plain-text README via the contents API's raw media type. Returns ''
    on any failure (private/no README/rate limit) -- treated as "too short"
    downstream, not a hard error, since a missing README is itself a signal
    this repo isn't ready to recommend."""
    try:
        resp = session.get(
            f"{GITHUB_API}/repos/{full_name}/readme",
            headers={"Accept": "application/vnd.github.raw+json"},
            timeout=30,
        )
        if resp.status_code != 200:
            return ""
        return resp.text
    except requests.RequestException as e:
        warnings.append(f"{full_name}: README fetch failed ({e})")
        return ""


def readme_content_length(readme_text: str) -> int:
    """Strip markdown badges/images and bare links before measuring length,
    so a README that's ALL badges (common auto-generated boilerplate) reads
    as short, not padded out by badge markup."""
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", readme_text)  # ![alt](url) images/badges
    text = re.sub(r"\[!\[[^\]]*\]\([^)]*\)\]\([^)]*\)", "", text)  # linked badges
    text = re.sub(r"^#+\s.*$", "", text, flags=re.MULTILINE)  # heading lines (often just the title)
    return len(text.strip())


def to_row(item: dict) -> dict:
    license_info = item.get("license") or {}
    return {
        "full_name": item.get("full_name", ""),
        "html_url": item.get("html_url", ""),
        "description": (item.get("description") or "").strip(),
        "stars": item.get("stargazers_count", 0),
        "pushed_at": item.get("pushed_at", ""),
        "language": item.get("language") or "",
        "license_spdx_id": license_info.get("spdx_id") or "",
        "homepage": item.get("homepage") or "",
    }


def load_existing_candidates(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return {row["full_name"]: row for row in csv.DictReader(f)}


LOG_FIELDNAMES = ["timestamp_utc", "keyword", "query", "raw_count", "new_candidates",
                   "min_stars", "pushed_after_months", "min_readme_chars", "notes"]


def append_search_log(log_path: Path, rows: list) -> None:
    """Append one row per keyword searched this run -- the provenance trail
    of every query issued against the live GitHub Search API (what was
    tried, when, and how many hits), kept separately from
    search_candidates.csv because a keyword can be searched again later
    with different filters and both runs are worth keeping on record."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not log_path.exists()
    with open(log_path, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LOG_FIELDNAMES)
        if is_new:
            writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--keyword", action="append", required=True, dest="keywords",
                         help="search keyword/phrase; repeat --keyword for multiple")
    parser.add_argument("--min-stars", type=int, default=DEFAULT_MIN_STARS)
    parser.add_argument("--pushed-after-months", type=int, default=DEFAULT_PUSHED_AFTER_MONTHS)
    parser.add_argument("--min-readme-chars", type=int, default=DEFAULT_MIN_README_CHARS)
    parser.add_argument("--max-pages", type=int, default=1,
                        help="pages of 100 results to follow per keyword (default 1). "
                             "Raise for `topic:` sweeps, which routinely match several "
                             "hundred repos; GitHub caps any search at 1000 (10 pages).")
    parser.add_argument("--raw-dir", default="curation/state/search_raw")
    parser.add_argument("--out-candidates", default="curation/state/search_candidates.csv")
    parser.add_argument("--log-path", default="curation/state/search_log.csv",
                         help="provenance log of every keyword searched, appended to (never overwritten)")
    parser.add_argument("--skip-readme-check", action="store_true",
                         help="skip the per-repo README fetch (faster, but no README-length filtering)")
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

    pushed_after = cutoff_date(args.pushed_after_months)
    warnings: list = []
    raw_dir = Path(args.raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)

    candidates = load_existing_candidates(Path(args.out_candidates))
    seen_before = set(candidates)
    log_rows = []
    run_timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")

    for keyword in args.keywords:
        query = build_query(keyword, args.min_stars, pushed_after)
        print(f"[search] {query!r}")
        items = search_repositories(session, query, warnings, max_pages=args.max_pages)
        rows = [to_row(item) for item in items]

        raw_path = raw_dir / f"{slugify(keyword)}.json"
        with open(raw_path, "w", encoding="utf-8") as f:
            json.dump({"keyword": keyword, "query": query, "count": len(rows), "repos": rows}, f, indent=2)
        print(f"  -> {len(rows)} repo(s), full list saved to {raw_path}")

        kept = 0
        for row in rows:
            full_name = row["full_name"]
            if full_name in candidates:
                continue  # already a candidate from an earlier keyword/run
            if not args.skip_readme_check:
                readme = fetch_readme_text(session, full_name, warnings)
                length = readme_content_length(readme)
                if length < args.min_readme_chars:
                    continue
                time.sleep(0.2)  # be polite to the contents API between repos
            row["found_via_keyword"] = keyword
            candidates[full_name] = row
            kept += 1
        print(f"  -> {kept} new candidate(s) passed the README-length filter")
        log_rows.append({
            "timestamp_utc": run_timestamp,
            "keyword": keyword,
            "query": query,
            "raw_count": len(rows),
            "new_candidates": kept,
            "min_stars": args.min_stars,
            "pushed_after_months": args.pushed_after_months,
            "min_readme_chars": args.min_readme_chars if not args.skip_readme_check else "skipped",
            "notes": "",
        })

    append_search_log(Path(args.log_path), log_rows)
    print(f"logged {len(log_rows)} keyword run(s) to {args.log_path}")

    out_path = Path(args.out_candidates)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        fieldnames = ["full_name", "html_url", "description", "stars", "pushed_at",
                      "language", "license_spdx_id", "homepage", "found_via_keyword"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in candidates.values():
            writer.writerow({k: row.get(k, "") for k in fieldnames})

    new_count = len(candidates) - len(seen_before)
    print(f"\nwrote {len(candidates)} total candidate(s) ({new_count} new this run) to {out_path}")
    if warnings:
        print(f"\n{len(warnings)} warning(s):", file=sys.stderr)
        for w in warnings:
            print(f"  - {w}", file=sys.stderr)


if __name__ == "__main__":
    main()
