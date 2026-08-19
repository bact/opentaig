#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2026 OpenTAIG authors
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Drop candidates that are already accounted for, before the expensive
judgment steps (extract + map to RQ) run on them.

Two sources of "already accounted for":

  1. Already live in the `tools` tab -- matched by GitHub repo path (e.g.
     `org/repo`) extracted from each tool's `source` URL, since that's the
     only field guaranteed to point at the actual repo.
  2. Already judged in a previous curation run -- `curation/state/seen_repos.csv`,
     a running log of every repo a human has already accepted or rejected.
     Re-showing a previously-rejected repo just because a later keyword
     also matched it wastes review time.

Deterministic; no model, no network (reads only local files already
produced by `build.py` and `search_repos.py`).

Output is a *separate* file, `curation/state/candidates_to_review.csv` --
`search_candidates.csv` stays untouched as the full audit trail (see
curation/README.md).

Usage:

    python build.py   # refresh site/data.json first, so the live-tools
                       # dedup check is against current data
    python curation/dedup_candidates.py
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

REPO_PATH_RE = re.compile(r"github\.com[:/]+([^/]+/[^/.]+?)(?:\.git)?/?$")


def repo_path(url: str) -> str:
    """Extract 'org/repo' from a GitHub URL, lowercased for comparison.
    Returns '' if the URL doesn't look like a GitHub repo (e.g. a spec doc
    or non-GitHub homepage) -- such tools simply never match a candidate."""
    if not url:
        return ""
    m = REPO_PATH_RE.search(url.strip())
    return m.group(1).lower() if m else ""


def load_live_tool_repo_paths(data_json: Path) -> set:
    if not data_json.exists():
        return set()
    with open(data_json, "r", encoding="utf-8") as f:
        data = json.load(f)
    paths = set()
    for tool in data.get("tools", []):
        for field in ("source", "homepage"):
            p = repo_path(tool.get(field, ""))
            if p:
                paths.add(p)
    return paths


def load_seen_repos(seen_path: Path) -> dict:
    if not seen_path.exists():
        return {}
    with open(seen_path, "r", encoding="utf-8") as f:
        return {row["full_name"].lower(): row for row in csv.DictReader(f)}


def main() -> None:
    csv.field_size_limit(sys.maxsize)
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--candidates", default="curation/state/search_candidates.csv")
    parser.add_argument("--data-json", default="site/data.json")
    parser.add_argument("--seen-repos", default="curation/state/seen_repos.csv")
    parser.add_argument("--out", default="curation/state/candidates_to_review.csv")
    args = parser.parse_args()

    candidates_path = Path(args.candidates)
    if not candidates_path.exists():
        raise SystemExit(f"{candidates_path} not found -- run search_repos.py first.")

    with open(candidates_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        candidates = list(reader)

    live_paths = load_live_tool_repo_paths(Path(args.data_json))
    seen = load_seen_repos(Path(args.seen_repos))

    kept, dropped_live, dropped_seen = [], 0, 0
    for row in candidates:
        path = repo_path(row["html_url"])
        if path in live_paths:
            dropped_live += 1
            continue
        seen_row = seen.get(path)
        if seen_row:
            dropped_seen += 1
            continue
        kept.append(row)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(kept)

    print(f"{len(candidates)} candidate(s) in {candidates_path}")
    print(f"  -> {dropped_live} already in the live tools tab")
    print(f"  -> {dropped_seen} already judged in {args.seen_repos}")
    print(f"  -> {len(kept)} to review, written to {out_path}")


if __name__ == "__main__":
    main()
