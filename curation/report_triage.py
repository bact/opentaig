#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2026 OpenTAIG authors
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Turn `state/seen_repos.csv` into the two counts a methodology write-up
actually needs: candidates found per problem area, and how many of those
were open source. Deterministic; no model, no network (licence classes are
already baked into seen_repos.csv by emit_candidates.py at judgment time).

Only reads data that's already been recorded -- this does no new judging.
Rows from before the reject_category/license_class columns existed will show
up as blank/"(unrecorded)"; that's a real gap in the historical record, not
a bug here, and it's reported as its own line rather than silently dropped.

Usage:

    python curation/report_triage.py
    python curation/report_triage.py --by keyword
    python curation/report_triage.py --seen-repos curation/state/seen_repos.csv
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path

from licenses import OPEN_CLASSES


def load_rows(path: Path) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def report_by(rows: list[dict], group_field: str) -> None:
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        key = r.get(group_field) or "(unrecorded)"
        groups[key].append(r)

    print(f"{'group':<45} {'found':>6} {'accepted':>9} {'open-src':>9} {'rejected':>9}")
    print("-" * 82)
    for key in sorted(groups, key=lambda k: -len(groups[k])):
        grp = groups[key]
        accepted = [r for r in grp if r["verdict"] == "accept"]
        rejected = [r for r in grp if r["verdict"] == "reject"]
        open_src = [r for r in grp if r.get("license_class") in OPEN_CLASSES]
        print(f"{key:<45} {len(grp):>6} {len(accepted):>9} {len(open_src):>9} {len(rejected):>9}")


def report_reject_categories(rows: list[dict]) -> None:
    rejected = [r for r in rows if r["verdict"] == "reject"]
    counts = Counter(r.get("reject_category") or "(unrecorded)" for r in rejected)
    print(f"\n{len(rejected)} total rejection(s), by category:")
    for cat, n in counts.most_common():
        print(f"  {n:>4}  {cat}")


def report_license_classes(rows: list[dict]) -> None:
    counts = Counter(r.get("license_class") or "(unrecorded)" for r in rows)
    total = len(rows)
    open_n = sum(n for cls, n in counts.items() if cls in OPEN_CLASSES)
    print(f"\n{total} total judged repo(s), by licence class "
          f"({open_n} open source: {sorted(OPEN_CLASSES)}):")
    for cls, n in counts.most_common():
        marker = "*" if cls in OPEN_CLASSES else " "
        print(f"  {marker} {n:>4}  {cls}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seen-repos", default="curation/state/seen_repos.csv")
    parser.add_argument("--by", choices=["problem_area", "keyword"], default="problem_area",
                        help="group the found/accepted/open-source/rejected table by this field "
                             "(default: problem_area; 'keyword' uses found_via_keyword)")
    args = parser.parse_args()

    path = Path(args.seen_repos)
    if not path.exists():
        raise SystemExit(f"{path} not found")
    rows = load_rows(path)
    if not rows:
        raise SystemExit(f"{path} has no rows")

    group_field = "problem_area" if args.by == "problem_area" else "found_via_keyword"
    report_by(rows, group_field)
    report_reject_categories(rows)
    report_license_classes(rows)


if __name__ == "__main__":
    main()
