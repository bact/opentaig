#!/usr/bin/env python3
"""Generate curation/candidate_mapping.csv: candidate RQ_No -> tool_id
mappings, derived by intersecting each tool's implement/eval term ids
(from a tools CSV, e.g. candidate_tools_from_rgaf.csv) against each
question's own mapped term ids (from a snapshot of the map tab's five
framework columns, e.g. live_map_snapshot.csv).

This is a deterministic first pass, not a final answer: term overlap
means "plausibly relevant", not "definitely relevant" -- review before
pasting anything into the live map tab's tools_implement/tools_eval
columns.

Usage:
    python curation/generate_candidate_mapping.py \\
        --map curation/live_map_snapshot.csv \\
        --tools curation/candidate_tools_from_rgaf.csv \\
        --out curation/candidate_mapping.csv
"""
from __future__ import annotations

import argparse
import collections
import csv

FRAMEWORK_COLUMNS = ["RGAF", "EUAIAct", "UNESCOAI", "ASEANAI", "CoEAI"]


def parse_ids(raw: str) -> set:
    if not raw:
        return set()
    return {p.strip() for p in raw.split(";") if p.strip()}


def rq_sort_key(rq_no: str):
    try:
        return (0, int(rq_no))
    except ValueError:
        return (1, rq_no)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--map", default="curation/live_map_snapshot.csv")
    parser.add_argument("--tools", default="curation/candidate_tools_from_rgaf.csv")
    parser.add_argument("--out", default="curation/candidate_mapping.csv")
    parser.add_argument("--out-by-rq", default="curation/candidate_mapping_by_rq.csv")
    args = parser.parse_args()

    with open(args.map, encoding="utf-8") as f:
        map_rows = list(csv.DictReader(f))
    with open(args.tools, encoding="utf-8") as f:
        tool_rows = list(csv.DictReader(f))

    rq_terms = {}
    for row in map_rows:
        rq_no = row["RQ_No"].strip()
        terms = set()
        for col in FRAMEWORK_COLUMNS:
            terms |= parse_ids(row.get(col, ""))
        rq_terms[rq_no] = terms

    tools = []
    for row in tool_rows:
        tools.append(
            {
                "id": row["id"].strip(),
                "implement": parse_ids(row.get("implement", "")),
                "eval": parse_ids(row.get("eval", "")),
            }
        )

    candidates = []
    for rq_no, terms in rq_terms.items():
        if not terms:
            continue
        for tool in tools:
            for role in ("implement", "eval"):
                shared = sorted(terms & tool[role])
                for term in shared:
                    candidates.append(
                        {"RQ_No": rq_no, "tool_id": tool["id"], "role": role, "shared_term": term}
                    )

    candidates.sort(key=lambda c: (rq_sort_key(c["RQ_No"]), c["tool_id"], c["role"], c["shared_term"]))

    with open(args.out, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["RQ_No", "tool_id", "role", "shared_term"])
        writer.writeheader()
        writer.writerows(candidates)
    print(f"wrote {len(candidates)} candidate row(s) to {args.out}")

    # Convenience pivot: one row per RQ_No, tool ids grouped by role. Easier
    # to scan than the tidy file, at the cost of dropping which specific term
    # each tool shared with the question.
    by_rq = collections.defaultdict(lambda: {"implement": set(), "eval": set()})
    for c in candidates:
        by_rq[c["RQ_No"]][c["role"]].add(c["tool_id"])

    pivot_rows = [
        {
            "RQ_No": rq,
            "candidate_tools_implement": "; ".join(sorted(by_rq[rq]["implement"])),
            "candidate_tools_eval": "; ".join(sorted(by_rq[rq]["eval"])),
        }
        for rq in sorted(by_rq, key=rq_sort_key)
    ]
    with open(args.out_by_rq, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["RQ_No", "candidate_tools_implement", "candidate_tools_eval"])
        writer.writeheader()
        writer.writerows(pivot_rows)
    print(f"wrote {len(pivot_rows)} pivoted row(s) to {args.out_by_rq}")


if __name__ == "__main__":
    main()
