#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2026 OpenTAIG authors
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Quasi-Gold-Standard (QGS) validation: test whether a candidate keyword
list actually finds repos you already know are relevant, before spending a
real search-and-triage pass on it.

Pick 5-10 repos already accepted into the catalog (ideally spanning several
problem areas) as the QGS set. Run this against a batch of proposed
keywords: it reports per-keyword and per-QGS-repo recall, so a keyword
angle that misses most of the QGS can be caught before it's used for real.

This is a calibration tool, NOT a discovery run: it does not touch
search_candidates.csv. It does append to search_log.csv (same provenance
rule as everywhere else in this pipeline -- see curation/README.md's "Log
every keyword regardless of hit count"), with a note marking the rows as
QGS validation so they're not mistaken for real discovery runs when
computing paper statistics.

Usage:
    python curation/validate_qgs.py \\
        --qgs google/magika --qgs IBM/ICX360 --qgs leondz/garak \\
        --keyword "LLM guardrail" --keyword "prompt injection scanner"

    python curation/validate_qgs.py --qgs-file curation/state/qgs.txt \\
        --keyword-file curation/state/candidate_keywords.txt
"""
from __future__ import annotations

import argparse
import datetime
import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from search_repos import (  # noqa: E402
    build_query, search_repositories, cutoff_date,
    DEFAULT_MIN_STARS, DEFAULT_PUSHED_AFTER_MONTHS, append_search_log,
)


def read_lines(path: str) -> list[str]:
    with open(path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--qgs", action="append", default=[], dest="qgs",
                         help="known-relevant repo full_name (owner/repo); repeat for multiple")
    parser.add_argument("--qgs-file", help="file of owner/repo, one per line (# comments ok)")
    parser.add_argument("--keyword", action="append", default=[], dest="keywords",
                         help="candidate keyword to test; repeat for multiple")
    parser.add_argument("--keyword-file", help="file of keywords, one per line (# comments ok)")
    parser.add_argument("--min-stars", type=int, default=DEFAULT_MIN_STARS)
    parser.add_argument("--pushed-after-months", type=int, default=DEFAULT_PUSHED_AFTER_MONTHS)
    parser.add_argument("--max-pages", type=int, default=3,
                         help="pages of 100 to fetch per keyword (default 3, higher than "
                             "search_repos.py's default 1, since recall needs deeper coverage "
                             "than a real discovery run would bother fetching)")
    parser.add_argument("--log-path", default="curation/state/search_log.csv",
                         help="set to /dev/null to skip logging this calibration run")
    args = parser.parse_args()

    qgs = list(args.qgs) + (read_lines(args.qgs_file) if args.qgs_file else [])
    keywords = list(args.keywords) + (read_lines(args.keyword_file) if args.keyword_file else [])
    if not qgs:
        raise SystemExit("no QGS repos given -- pass --qgs owner/repo (repeatable) or --qgs-file")
    if not keywords:
        raise SystemExit("no keywords given -- pass --keyword ... (repeatable) or --keyword-file")

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("GITHUB_TOKEN is not set -- see curation/README.md's Setup section.")
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })

    pushed_after = cutoff_date(args.pushed_after_months)
    found_by: dict[str, set[str]] = {r: set() for r in qgs}  # qgs repo -> keywords that found it
    log_rows = []
    run_timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    warnings: list = []

    for keyword in keywords:
        query = build_query(keyword, args.min_stars, pushed_after)
        items = search_repositories(session, query, warnings, max_pages=args.max_pages)
        hit_names = {item.get("full_name", "").lower() for item in items}
        for repo in qgs:
            if repo.lower() in hit_names:
                found_by[repo].add(keyword)
        print(f"[qgs] {keyword!r} -> {len(items)} hit(s)")
        log_rows.append({
            "timestamp_utc": run_timestamp,
            "keyword": keyword,
            "query": query,
            "raw_count": len(items),
            "new_candidates": 0,
            "min_stars": args.min_stars,
            "pushed_after_months": args.pushed_after_months,
            "min_readme_chars": "skipped",
            "notes": "qgs-validation: calibration probe, not a discovery run, "
                     "search_candidates.csv not touched",
        })

    print("\n--- QGS recall ---")
    covered = 0
    for repo in qgs:
        kws = found_by[repo]
        status = ", ".join(sorted(kws)) if kws else "NOT FOUND by any keyword"
        print(f"  {repo}: {status}")
        if kws:
            covered += 1
    sensitivity = covered / len(qgs) if qgs else 0.0
    print(f"\nquasi-sensitivity: {covered}/{len(qgs)} = {sensitivity:.0%}")
    if sensitivity < 1.0:
        print("Repos not found by any keyword above need their README vocabulary mined "
              "for a better phrase -- see curation/README.md source 1 (mine vocabulary "
              "from accepted tools) -- before this keyword batch is used for a real run.")

    if args.log_path != "/dev/null":
        append_search_log(Path(args.log_path), log_rows)
        print(f"\nlogged {len(log_rows)} calibration probe(s) to {args.log_path}")
    if warnings:
        print(f"\n{len(warnings)} warning(s):", file=sys.stderr)
        for w in warnings:
            print(f"  - {w}", file=sys.stderr)


if __name__ == "__main__":
    main()
