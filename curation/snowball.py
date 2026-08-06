#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2026 OpenTAIG authors
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Backward snowballing: mine already-known repos' READMEs for other repos
they link to (forks-from, dependencies, "see also", comparison tables), and
add the ones that pass the normal quality bar directly as candidates --
no keyword search involved.

This is the standard software-engineering-mapping-study snowballing
technique: keyword search in GitHub/Google routinely misses tools whose
README uses different jargon than the query, but a tool's own README will
usually name its closest neighbours in plain prose.

Reuses search_repos.py's filter functions (stars/pushed/archived/fork,
README-length) so a snowballed repo has to clear the exact same bar as one
found by keyword search -- it's a different *source* of candidates, not a
looser filter.

Usage:
    python curation/snowball.py --repo google/magika --repo IBM/ICX360
    python curation/snowball.py --from-candidates   # snowball every repo
                                                      # currently in
                                                      # search_candidates.csv
    python curation/snowball.py --from-candidates --max-seeds 20

Output: same two artifacts as search_repos.py --
  - curation/state/search_raw/snowball-<seed-slug>.json (per seed, the repos
    its README linked to and whether each passed the filters)
  - appended to curation/state/search_candidates.csv, found_via_keyword set
    to "snowball:<seed-repo>" for provenance
  - one row per seed appended to curation/state/search_log.csv, keyword set
    to "snowball:<seed-repo>" so it's part of the same audit trail phase-2
    keyword runs already write to (see curation/README.md's "Log every
    keyword regardless of hit count" rule -- a snowball seed that links to
    nothing new is real negative evidence too).
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

# Reuse search_repos.py's filter/IO logic rather than duplicating it.
sys.path.insert(0, str(Path(__file__).parent))
from search_repos import (  # noqa: E402
    GITHUB_API, DEFAULT_MIN_STARS, DEFAULT_PUSHED_AFTER_MONTHS, DEFAULT_MIN_README_CHARS,
    cutoff_date, fetch_readme_text, readme_content_length, to_row,
    load_existing_candidates, append_search_log, slugify,
)

# github.com/<owner>/<repo> links, excluding non-repo paths (issues, blob,
# actions, etc.) and github.com itself as a path segment.
_REPO_LINK_RE = re.compile(
    r"github\.com/([A-Za-z0-9][\w.-]*)/([A-Za-z0-9][\w.-]*?)(?:\.git)?(?:[/)\]>\s#?]|$)"
)
_NON_REPO_OWNERS = {"github", "orgs", "sponsors", "marketplace", "topics", "search", "settings", "apps"}
_NON_REPO_SUFFIXES = {"issues", "pulls", "actions", "wiki", "releases", "compare", "blob", "tree",
                       "commits", "discussions", "projects", "security", "pkgs"}


def extract_repo_links(readme_text: str, self_full_name: str) -> list[str]:
    found = []
    seen = set()
    for m in _REPO_LINK_RE.finditer(readme_text):
        owner, repo = m.group(1), m.group(2)
        if owner.lower() in _NON_REPO_OWNERS or repo.lower() in _NON_REPO_SUFFIXES:
            continue
        full_name = f"{owner}/{repo}"
        if full_name.lower() == self_full_name.lower():
            continue
        key = full_name.lower()
        if key in seen:
            continue
        seen.add(key)
        found.append(full_name)
    return found


def fetch_repo(session: requests.Session, full_name: str) -> dict | None:
    resp = session.get(f"{GITHUB_API}/repos/{full_name}", timeout=30)
    if resp.status_code != 200:
        return None
    return resp.json()


def passes_filters(item: dict, min_stars: int, pushed_after: str) -> bool:
    if item.get("archived") or item.get("fork"):
        return False
    if item.get("stargazers_count", 0) <= min_stars:
        return False
    pushed_at = item.get("pushed_at") or ""
    return pushed_at > pushed_after


def load_seed_repos_from_candidates(path: Path, limit: int | None) -> list[str]:
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        names = [row["full_name"] for row in csv.DictReader(f) if row.get("full_name")]
    return names[:limit] if limit else names


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", action="append", default=[], dest="repos",
                         help="seed repo full_name (owner/repo); repeat for multiple")
    parser.add_argument("--from-candidates", action="store_true",
                         help="use every repo currently in --out-candidates as a seed")
    parser.add_argument("--max-seeds", type=int, default=None,
                         help="cap the number of seed repos read from --from-candidates")
    parser.add_argument("--min-stars", type=int, default=DEFAULT_MIN_STARS)
    parser.add_argument("--pushed-after-months", type=int, default=DEFAULT_PUSHED_AFTER_MONTHS)
    parser.add_argument("--min-readme-chars", type=int, default=DEFAULT_MIN_README_CHARS)
    parser.add_argument("--raw-dir", default="curation/state/search_raw")
    parser.add_argument("--out-candidates", default="curation/state/search_candidates.csv")
    parser.add_argument("--log-path", default="curation/state/search_log.csv")
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("GITHUB_TOKEN is not set -- see curation/README.md's Setup section.")

    seeds = list(args.repos)
    if args.from_candidates:
        seeds += load_seed_repos_from_candidates(Path(args.out_candidates), args.max_seeds)
    if not seeds:
        raise SystemExit("no seed repos given -- pass --repo owner/repo (repeatable) or --from-candidates")

    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })

    pushed_after = cutoff_date(args.pushed_after_months)
    raw_dir = Path(args.raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    candidates = load_existing_candidates(Path(args.out_candidates))
    seen_before = set(candidates)
    log_rows = []
    run_timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")

    for seed in seeds:
        print(f"[snowball] seed {seed!r}")
        readme = fetch_readme_text(session, seed, [])
        links = extract_repo_links(readme, seed)
        print(f"  -> {len(links)} distinct repo link(s) in README")

        checked, kept = [], 0
        for full_name in links:
            if full_name in candidates:
                continue  # already a candidate from an earlier keyword/seed
            item = fetch_repo(session, full_name)
            time.sleep(0.2)
            if item is None:
                continue
            if not passes_filters(item, args.min_stars, pushed_after):
                continue
            other_readme = fetch_readme_text(session, full_name, [])
            time.sleep(0.2)
            if readme_content_length(other_readme) < args.min_readme_chars:
                continue
            row = to_row(item)
            row["found_via_keyword"] = f"snowball:{seed}"
            candidates[full_name] = row
            checked.append(row)
            kept += 1

        raw_path = raw_dir / f"snowball-{slugify(seed)}.json"
        with open(raw_path, "w", encoding="utf-8") as f:
            json.dump({"seed": seed, "links_found": links, "kept": checked}, f, indent=2)
        print(f"  -> {kept} new candidate(s) passed the filters, saved to {raw_path}")

        log_rows.append({
            "timestamp_utc": run_timestamp,
            "keyword": f"snowball:{seed}",
            "query": f"README links from {seed}",
            "raw_count": len(links),
            "new_candidates": kept,
            "min_stars": args.min_stars,
            "pushed_after_months": args.pushed_after_months,
            "min_readme_chars": args.min_readme_chars,
            "notes": "backward snowballing, not a GitHub search query",
        })

    append_search_log(Path(args.log_path), log_rows)
    print(f"logged {len(log_rows)} seed(s) to {args.log_path}")

    out_path = Path(args.out_candidates)
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        fieldnames = ["full_name", "html_url", "description", "stars", "pushed_at",
                      "language", "license_spdx_id", "homepage", "found_via_keyword"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in candidates.values():
            writer.writerow({k: row.get(k, "") for k in fieldnames})

    new_count = len(candidates) - len(seen_before)
    print(f"\nwrote {len(candidates)} total candidate(s) ({new_count} new this run) to {out_path}")


if __name__ == "__main__":
    main()
