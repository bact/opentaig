#!/usr/bin/env python3
"""Turn judged candidates (step 4 extract + step 5 map-to-RQ, both done by
an agent) into the two review CSVs a human pastes into the live sheet, and
record every judged repo -- accepted or rejected -- so future dedup runs
don't re-surface it.

Deterministic; no model, no network. Input is a JSON file of judgments (see
`--judgments`), one object per candidate repo:

    [
      {
        "repo": "org/name",              // GitHub "org/repo", required
        "id": "kebab-case-id",            // required only if verdict=="accept"
        "tool_type": "software",
        "name": "Display Name",
        "summary": "one-line summary, distilled from the README",
        "license": "MIT",                 // leave "" rather than guess
        "homepage": "https://...",
        "source": "https://github.com/org/name.git",
        "documentation": "",
        "funding": "",
        "verdict": "accept",              // or "reject"
        "reject_reason": "",              // required if verdict=="reject"
        "mappings": [                     // only for verdict=="accept"
          {"rq_no": "1", "role": "implement", "rationale": "..."},
          {"rq_no": "4", "role": "eval", "rationale": "..."}
        ]
      },
      ...
    ]

Output:

  - `curation/candidate_tools.csv` -- new `tools` tab rows, exact live
    column order (id, tool_type, name, summary, license, homepage, source,
    documentation, funding, implement, eval). `implement`/`eval` here are
    RGAF-style term tags on the tool itself (per the live schema), left
    blank unless the judgment supplied them -- NOT the RQ mapping, which is
    the other file.
  - `curation/candidate_map_updates.csv` -- `RQ_No, tool_id, role,
    rationale`, one row per (tool, RQ) pair, for a human to merge into the
    map tab's existing `tools_implement`/`tools_eval` semicolon lists.
  - `curation/state/seen_repos.csv` -- appended (not overwritten) with one
    row per judged repo, accept or reject, so `dedup_candidates.py` skips
    it on future runs.

Usage:

    python curation/emit_candidates.py --judgments path/to/judgments.json
"""
from __future__ import annotations

import argparse
import csv
import datetime
import json
from pathlib import Path

TOOLS_FIELDNAMES = ["id", "tool_type", "name", "summary", "license", "homepage",
                     "source", "documentation", "funding", "implement", "eval"]
MAP_FIELDNAMES = ["RQ_No", "tool_id", "role", "rationale"]
SEEN_FIELDNAMES = ["full_name", "verdict", "timestamp_utc", "note"]

VALID_ROLES = {"implement", "eval"}


def load_existing_rows(path: Path, key_field: str) -> tuple:
    """Returns (fieldnames_or_None, list_of_existing_rows) for append-and-dedup."""
    if not path.exists():
        return None, []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return reader.fieldnames, list(reader)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--judgments", required=True, help="path to the judgments JSON file")
    parser.add_argument("--tools-out", default="curation/candidate_tools.csv")
    parser.add_argument("--map-out", default="curation/candidate_map_updates.csv")
    parser.add_argument("--seen-repos", default="curation/state/seen_repos.csv")
    args = parser.parse_args()

    with open(args.judgments, "r", encoding="utf-8") as f:
        judgments = json.load(f)

    tool_rows, map_rows, seen_rows = [], [], []
    seen_ids = set()
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    errors = []

    for j in judgments:
        repo = j.get("repo", "")
        verdict = j.get("verdict", "")
        if verdict not in ("accept", "reject"):
            errors.append(f"{repo}: verdict must be 'accept' or 'reject', got {verdict!r}")
            continue

        note = j.get("reject_reason", "") if verdict == "reject" else ""
        seen_rows.append({"full_name": repo, "verdict": verdict, "timestamp_utc": timestamp, "note": note})

        if verdict == "reject":
            continue

        tool_id = j.get("id", "")
        if not tool_id:
            errors.append(f"{repo}: verdict=accept but no 'id' given")
            continue
        if tool_id in seen_ids:
            errors.append(f"{repo}: duplicate tool id {tool_id!r} in this batch")
            continue
        seen_ids.add(tool_id)

        tool_rows.append({
            "id": tool_id,
            "tool_type": j.get("tool_type", "software"),
            "name": j.get("name", tool_id),
            "summary": j.get("summary", ""),
            "license": j.get("license", ""),
            "homepage": j.get("homepage", ""),
            "source": j.get("source", ""),
            "documentation": j.get("documentation", ""),
            "funding": j.get("funding", ""),
            "implement": j.get("implement", ""),
            "eval": j.get("eval", ""),
        })

        mappings = j.get("mappings", [])
        if not mappings:
            errors.append(f"{repo}: verdict=accept but no RQ mappings given")
        for m in mappings:
            role = m.get("role", "")
            if role not in VALID_ROLES:
                errors.append(f"{repo}: mapping role must be 'implement' or 'eval', got {role!r}")
                continue
            if not m.get("rationale"):
                errors.append(f"{repo}: RQ_No {m.get('rq_no')} mapping missing a rationale")
            map_rows.append({
                "RQ_No": m.get("rq_no", ""),
                "tool_id": tool_id,
                "role": role,
                "rationale": m.get("rationale", ""),
            })

    if errors:
        print("Errors -- fix the judgments file and re-run (nothing was written):")
        for e in errors:
            print(f"  - {e}")
        raise SystemExit(1)

    tools_out = Path(args.tools_out)
    tools_out.parent.mkdir(parents=True, exist_ok=True)
    with open(tools_out, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=TOOLS_FIELDNAMES)
        writer.writeheader()
        writer.writerows(tool_rows)

    map_out = Path(args.map_out)
    with open(map_out, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=MAP_FIELDNAMES)
        writer.writeheader()
        writer.writerows(map_rows)

    seen_path = Path(args.seen_repos)
    seen_path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not seen_path.exists()
    with open(seen_path, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SEEN_FIELDNAMES)
        if is_new:
            writer.writeheader()
        writer.writerows(seen_rows)

    print(f"{len(tool_rows)} accepted tool(s) -> {tools_out}")
    print(f"{len(map_rows)} RQ mapping(s) -> {map_out}")
    print(f"{len(seen_rows)} repo(s) logged (accept+reject) -> {seen_path}")


if __name__ == "__main__":
    main()
