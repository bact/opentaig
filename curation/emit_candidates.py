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
        "reject_category": "",            // required if verdict=="reject";
                                          // one of REJECT_CATEGORIES below
        "problem_area": "",               // optional; defaults to --problem-area
        "mappings": [                     // only for verdict=="accept"
          {"rq_no": "1", "role": "implement", "rationale": "..."},
          {"rq_no": "4", "role": "eval", "rationale": "..."}
        ]
      },
      ...
    ]

Rejections are recorded as structurally as acceptances: a closed-vocabulary
`reject_category` alongside the free-text reason, plus the licence class and
the problem area the batch was searched for. That makes "area X surfaced N
candidates, of which M were open source" a query rather than an archaeology
exercise, and lets a bad search keyword be spotted from the shape of what it
rejected. `curation/report_triage.py` does both readings.

Output:

  - `curation/candidate_tools.csv` -- new `tools` tab rows, exact live
    column order (id, tool_type, name, summary, license, homepage, source,
    documentation, funding, implement, eval, datetime_added,
    datetime_checked, datetime_updated). `implement`/`eval` here are
    RGAF-style term tags on the tool itself (per the live schema), left
    blank unless the judgment supplied them -- NOT the RQ mapping, which is
    the other file. All three timestamps are stamped with the run time,
    since a freshly emitted row was just added, checked, and updated at
    once.
  - `curation/candidate_map_updates.csv` -- `rq_no, tool_id, role,
    rationale, datetime_added, datetime_checked, datetime_updated`, one row
    per (tool, RQ) pair. Same column order as the live `tool_map` tab, so a
    human appends these rows directly -- no merging into an existing cell
    needed.
  - `curation/state/seen_repos.csv` -- appended (not overwritten) with one
    row per judged repo, accept or reject, so `dedup_candidates.py` skips
    it on future runs. Doubles as the triage record: verdict,
    reject_category, licence class, problem area, and the keyword that
    surfaced it. Licence and keyword are looked up from
    `state/search_candidates.csv` rather than re-typed, so they're recorded
    for rejects too -- which is the whole point, since the rejects are where
    the "found N, only M open source" figure comes from.

Usage:

    python curation/emit_candidates.py --judgments path/to/judgments.json
"""
from __future__ import annotations

import argparse
import csv
import datetime
import json
from pathlib import Path

from licenses import OPEN_CLASSES, classify, load_spdx_index

TOOLS_FIELDNAMES = ["id", "tool_type", "name", "summary", "license", "homepage",
                     "source", "documentation", "funding", "implement", "eval",
                     "datetime_added", "datetime_checked", "datetime_updated"]
MAP_FIELDNAMES = ["rq_no", "tool_id", "role", "rationale",
                   "datetime_added", "datetime_checked", "datetime_updated"]  # matches the live tool_map tab's header exactly
SEEN_FIELDNAMES = ["full_name", "verdict", "reject_category", "note",
                    "license_spdx_id", "license_class", "problem_area",
                    "found_via_keyword", "stars", "timestamp_utc"]

VALID_ROLES = {"implement", "eval"}

# Closed vocabulary for *why* a candidate was rejected. Free-text `note` still
# carries the specifics; this exists so rejections can be counted -- both for
# writing up "area X surfaced N candidates, of which M were open source", and
# to feed back into keyword scoping (a keyword whose hits are mostly
# `not-relevant` is a bad keyword; one that's mostly `not-a-tool-paper-artifact`
# is fishing in an academic pond and may need different phrasing).
REJECT_CATEGORIES = {
    "not-open-source": "Licence is not OSI-approved or FSF-libre (see licenses.py).",
    "not-relevant": "Off-topic, or a false-positive match on the search keyword.",
    "adversarial-purpose": "Does the opposite of what the question needs (e.g. removes watermarks).",
    "not-a-tool-linklist": "Curated 'awesome' link list or survey repo, not a usable tool.",
    "not-a-tool-dataset": "Dataset or benchmark data release, not a runnable tool.",
    "not-a-tool-paper-artifact": "Single-paper code release, not a maintained general-purpose tool.",
    "commercial-sdk": "Marketing/demo repo fronting a proprietary commercial SDK.",
    "low-substance": "Thin demo, tutorial, or student project; not maintained.",
    "out-of-scope-narrow": "Real tool in a related area, but too narrow or embedded in a larger product.",
    "redundant": "Duplicates a tool already accepted for this question.",
}


def load_existing_keys(path: Path, key_field: str) -> set:
    """Returns the set of `key_field` values already present in `path`, so a
    caller can skip rows it would otherwise append a second time."""
    if not path.exists():
        return set()
    with open(path, "r", encoding="utf-8") as f:
        return {row[key_field] for row in csv.DictReader(f)}


def load_search_metadata(path: Path) -> dict:
    """Returns {full_name: row} from search_candidates.csv, used to enrich the
    triage log with licence/stars/keyword without the judging agent having to
    re-type facts the search step already captured. Repos that reached us some
    other way (web search, a seed tab) simply won't be in here."""
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return {row["full_name"]: row for row in csv.DictReader(f)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--judgments", required=True, help="path to the judgments JSON file")
    parser.add_argument("--tools-out", default="curation/candidate_tools.csv")
    parser.add_argument("--map-out", default="curation/candidate_map_updates.csv")
    parser.add_argument("--seen-repos", default="curation/state/seen_repos.csv")
    parser.add_argument("--search-candidates", default="curation/state/search_candidates.csv",
                        help="used to look up licence/stars/keyword per repo; a repo absent "
                             "from it is recorded with whatever the judgment supplied")
    parser.add_argument("--problem-area", default="",
                        help="problem area this batch was searched for; recorded on every "
                             "triage row so per-area counts are computable later. A judgment "
                             "may override it with its own 'problem_area' key.")
    args = parser.parse_args()

    with open(args.judgments, "r", encoding="utf-8") as f:
        judgments = json.load(f)

    search_meta = load_search_metadata(Path(args.search_candidates))
    spdx = load_spdx_index()

    tool_rows, map_rows, seen_rows = [], [], []
    seen_ids = set()
    seen_repos_in_batch = set()
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    errors = []

    for j in judgments:
        repo = j.get("repo", "")
        verdict = j.get("verdict", "")
        if verdict not in ("accept", "reject"):
            errors.append(f"{repo}: verdict must be 'accept' or 'reject', got {verdict!r}")
            continue
        if repo in seen_repos_in_batch:
            errors.append(f"{repo}: duplicate repo entry in this batch")
            continue
        seen_repos_in_batch.add(repo)

        meta = search_meta.get(repo, {})
        # The judgment wins over the search row: the agent may have read the
        # LICENSE file and found something GitHub's detector missed.
        license_spdx = (j.get("license") or meta.get("license_spdx_id") or "").strip()
        license_class = classify(license_spdx, spdx)

        note = j.get("reject_reason", "") if verdict == "reject" else ""
        reject_category = j.get("reject_category", "") if verdict == "reject" else ""
        if verdict == "reject":
            if not reject_category:
                errors.append(f"{repo}: verdict=reject but no 'reject_category' given "
                              f"(one of: {', '.join(sorted(REJECT_CATEGORIES))})")
            elif reject_category not in REJECT_CATEGORIES:
                errors.append(f"{repo}: unknown reject_category {reject_category!r} "
                              f"(one of: {', '.join(sorted(REJECT_CATEGORIES))})")
            if not note:
                errors.append(f"{repo}: verdict=reject but no 'reject_reason' given")
            # Cross-check the agent against the licence data rather than trusting
            # either alone -- a mismatch means one of them needs a second look.
            if reject_category == "not-open-source" and license_class in OPEN_CLASSES:
                errors.append(f"{repo}: rejected as 'not-open-source' but its licence "
                              f"{license_spdx!r} classifies as {license_class}")

        seen_rows.append({
            "full_name": repo,
            "verdict": verdict,
            "reject_category": reject_category,
            "note": note,
            "license_spdx_id": license_spdx,
            "license_class": license_class,
            "problem_area": j.get("problem_area", args.problem_area),
            "found_via_keyword": meta.get("found_via_keyword", ""),
            "stars": meta.get("stars", ""),
            "timestamp_utc": timestamp,
        })

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
            "datetime_added": timestamp,
            "datetime_checked": timestamp,
            "datetime_updated": timestamp,
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
                errors.append(f"{repo}: rq_no {m.get('rq_no')} mapping missing a rationale")
            map_rows.append({
                "rq_no": m.get("rq_no", ""),
                "tool_id": tool_id,
                "role": role,
                "rationale": m.get("rationale", ""),
                "datetime_added": timestamp,
                "datetime_checked": timestamp,
                "datetime_updated": timestamp,
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
    already_seen = load_existing_keys(seen_path, "full_name")
    new_seen_rows = [row for row in seen_rows if row["full_name"] not in already_seen]
    skipped = len(seen_rows) - len(new_seen_rows)
    is_new = not seen_path.exists()
    with open(seen_path, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SEEN_FIELDNAMES)
        if is_new:
            writer.writeheader()
        writer.writerows(new_seen_rows)

    print(f"{len(tool_rows)} accepted tool(s) -> {tools_out}")
    print(f"{len(map_rows)} RQ mapping(s) -> {map_out}")
    print(f"{len(new_seen_rows)} repo(s) newly logged -> {seen_path}"
          + (f" ({skipped} already logged, skipped)" if skipped else ""))


if __name__ == "__main__":
    main()
