#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2026 OpenTAIG authors
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

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
        "license": "",                     // leave "" -- collect_project_metadata.py
                                          // auto-collects this from the GitHub repo
                                          // API's own SPDX detection into
                                          // tool_metadata now, same override
                                          // precedence as stars/programming_language.
                                          // Only set this if the judgment used a
                                          // higher-confidence source GitHub's own
                                          // detector wouldn't have (a dedicated
                                          // license-scan tool, or a human/AI judge
                                          // actually reading the LICENSE file text,
                                          // e.g. to correct a NOASSERTION or a
                                          // GitHub misdetection) -- not just repeating
                                          // what the repo API already reports.
        "programming_language": "Python", // semicolon-separated if more than
                                          // one, e.g. "Python; Rust"; leave
                                          // "" for tool_type "specification"
        "homepage": "",                   // auto-collected into tool_metadata now, same
                                          // as documentation/license/programming_language
                                          // -- only set for a genuine judgment call the
                                          // collector can't make (wrong/stale auto value,
                                          // or the real site lives somewhere no manifest
                                          // names)
        "source": "https://github.com/org/name.git",
        "documentation": "",              // same as homepage -- leave blank, auto-collected
        "funding": "",
        "verdict": "accept",              // or "reject"
        "reject_reason": "",              // required if verdict=="reject"
        "reject_category": "",            // required if verdict=="reject";
                                          // one of REJECT_CATEGORIES below
        "problem_area": "",               // optional; defaults to --problem-area
        "no_rq_mapping_reason": "",       // set instead of "mappings" when the tool is a
                                          // real accept but doesn't fit any RQ in the
                                          // current taxonomy -- it's added with zero
                                          // tool_map rows and surfaces under "Pending
                                          // mapping" on the site's problems index (see
                                          // build.py's orphan_tools) rather than being
                                          // held back for lack of a place to put it
        "mappings": [                     // required for verdict=="accept" unless
                                          // "no_rq_mapping_reason" is set instead
          {"rq_no": "1", "role": "implement", "rationale": "..."},
          {"rq_no": "4", "role": "eval", "rationale": "..."}
        ],
        "checked_no_match": [             // optional; RQs this tool was also
                                          // read against and ruled out --
                                          // NOT the same as not having been
                                          // considered at all. Only for
                                          // verdict=="accept" (needs a
                                          // tool `id` to key against). Plain
                                          // rq_no strings, or
                                          // {"rq_no": "34", "note": "..."}
                                          // if the reasoning is worth a line.
          "34", {"rq_no": "41", "note": "risk taxonomy fits but no tool-level mechanism match"}
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

Output. All three files are **appended, not overwritten** -- running this
script across several batches in a session accumulates candidates from all
of them, so a human reviewing/merging only has to open+paste each file
once, not once per batch (the previous overwrite-per-run behaviour meant a
batch's output was silently destroyed by the next batch's run unless it was
copied out first):

  - `curation/candidate_tools.csv` -- new `tools` tab rows, matching the
    live tab's *current* actual column order (see the comment above
    `TOOLS_FIELDNAMES` -- nothing enforces the two staying in sync, so
    re-check against the live header if a paste ever looks misaligned):
    id, tool_type, name, summary, license, programming_language, homepage,
    source, documentation, funding, funder, paper_url, dependents,
    datetime_added, datetime_checked, datetime_updated, keywords, stars,
    forks, watchers, contributors, sponsors, last_commit_date,
    open_issues_count, releases_count, latest_release_date, readme_url,
    license_url, governance_url, contributing_url, code_of_conduct_url,
    security_policy_url, sbom_url, openssf_best_practices_url,
    openssf_best_practices_badge_level, openssf_scorecard_url,
    openssf_scorecard_score, openssf_scorecard_branch_protection,
    openssf_scorecard_code_review, openssf_scorecard_maintained,
    openssf_scorecard_vulnerabilities, development_status,
    software_heritage_id. `dependents` is `tools`-only, never
    auto-collected (no public API for GitHub's dependency-graph count) --
    fill it in by hand if a candidate is worth spot-checking.
    `programming_language`, `funding`, `funder`, and
    every project-quality/community-health column (stars through
    openssf_scorecard_vulnerabilities) are all overrides in `tools` now,
    not the primary source -- `tool_metadata` (a separate sheet,
    collect_project_metadata.py's output) is, and build.py resolves one
    from the other (see "tools / tool_metadata precedence" in
    docs/data-schema.md). Leave them blank here by design rather than
    having the judging agent guess at star counts or OpenSSF scan status
    -- run `collect_project_metadata.py` after this tool is live and
    `site/data.json` is rebuilt; it'll pick up this new id automatically.
    Only set one of these fields here if the judgment genuinely needs to
    force a value the collector would get wrong (the literal token "none"
    forces blank instead of falling through to tool_metadata). All three timestamps are stamped with the run time,
    since a freshly emitted row was just added, checked, and updated at
    once -- formatted "YYYY-MM-DD HH:MM" (UTC, no seconds, no offset) to
    match every existing datetime_* cell in the live sheet exactly, so
    pasting a batch in doesn't require reformatting. Deduplicated on `id`
    across runs -- re-running the same judgments file twice doesn't
    duplicate a row. Also skipped entirely (no row emitted at all) if `id`
    is already present in the live `tools` tab, per `--data-json`
    (site/data.json, i.e. `python build.py` output) -- this is what makes
    pass-A re-mapping safe: judging an *already-accepted* tool against a
    *new* RQ must emit only the new `tool_map` row below, never a second
    `tools` row for a tool that's already live.
  - `curation/candidate_map_updates.csv` -- `rq_no, tool_id, role,
    rationale, datetime_added, datetime_checked, datetime_updated`, one row
    per (tool, RQ) pair. Same column order as the live `tool_map` tab, so a
    human appends these rows directly -- no merging into an existing cell
    needed. Deduplicated on `(rq_no, tool_id, role)` across runs.
  - `curation/state/seen_repos.csv` -- appended (not overwritten) with one
    row per judged repo, accept or reject, so `dedup_candidates.py` skips
    it on future runs. Doubles as the triage record: verdict,
    reject_category, licence class, problem area, and the keyword that
    surfaced it. Licence and keyword are looked up from
    `state/search_candidates.csv` rather than re-typed, so they're recorded
    for rejects too -- which is the whole point, since the rejects are where
    the "found N, only M open source" figure comes from. Deduplicated on
    `full_name` across runs.
  - `curation/state/pass_a_checked.csv` -- `tool_id, rq_no, verdict, note,
    timestamp_utc`, one row per (tool, RQ) pairing actually *considered*
    during a Pass A re-mapping batch (see curation/README.md's "Pass A"
    starter prompt), regardless of outcome: `verdict` is "match" for every
    RQ in `mappings` above and "no_match" for every entry in
    `checked_no_match`. This is the only place a *negative* Pass A result is
    recorded anywhere -- `tool_map` only ever holds accepted mappings, so
    without this file there is no way to tell "already checked, no match"
    apart from "never checked at all", and a fresh Pass A run would silently
    re-derive the same negative conclusions instead of covering new ground.
    Never pasted into the live sheet -- like `seen_repos.csv`, this is
    process/provenance data, not site content. Deduplicated on
    `(tool_id, rq_no)` across runs, so re-running a judgments file, or a
    later batch re-considering an already-checked pair, doesn't duplicate a
    row (first verdict recorded wins; if a pair is later genuinely accepted
    after an earlier "no_match", the real status still lives in `tool_map`
    -- this ledger only answers "has this pair been looked at", not "what's
    the current truth").

**After merging accepted rows into the live sheet, clear (empty, keeping
just the header row) `candidate_tools.csv` and `candidate_map_updates.csv`**
-- otherwise already-merged rows keep accumulating alongside genuinely new
ones and the file stops being a clean "what's pending review" list. They're
safe to clear: nothing reads them back except a human pasting them in, and
`state/seen_repos.csv` (never cleared) is what actually prevents a merged
tool from being re-proposed.

Usage:

    python curation/emit_candidates.py --judgments path/to/judgments.json
"""
from __future__ import annotations

import argparse
import csv
import datetime
import json
import sys
from pathlib import Path

from licenses import OPEN_CLASSES, classify, load_spdx_index

csv.field_size_limit(sys.maxsize)

# Column order matches the live `tools` tab's *current* actual order, which
# is independent of build.py (a plain DictReader match by name, order-
# agnostic) and only matters for the "paste without reformatting" promise
# below -- re-check against the live header if this ever seems to produce a
# misaligned paste, since nothing enforces the two staying in sync.
TOOLS_FIELDNAMES = ["id", "tool_type", "name", "summary", "license", "programming_language",
                     "homepage", "source", "documentation", "funding", "funder", "paper_url",
                     "dependents",
                     "datetime_added", "datetime_checked", "datetime_updated",
                     "keywords",
                     "stars", "forks", "watchers", "contributors", "sponsors", "last_commit_date",
                     "open_issues_count", "releases_count", "latest_release_date",
                     "readme_url", "license_url", "governance_url", "contributing_url",
                     "code_of_conduct_url", "security_policy_url", "sbom_url",
                     "openssf_best_practices_url", "openssf_best_practices_badge_level",
                     "openssf_scorecard_url", "openssf_scorecard_score",
                     "openssf_scorecard_branch_protection", "openssf_scorecard_code_review",
                     "openssf_scorecard_maintained", "openssf_scorecard_vulnerabilities",
                     "development_status", "software_heritage_id"]
MAP_FIELDNAMES = ["rq_no", "tool_id", "role", "rationale",
                   "datetime_added", "datetime_checked", "datetime_updated"]  # matches the live tool_map tab's header exactly
SEEN_FIELDNAMES = ["full_name", "verdict", "reject_category", "note",
                    "license_spdx_id", "license_class", "problem_area",
                    "found_via_keyword", "stars", "timestamp_utc"]
PASS_A_FIELDNAMES = ["tool_id", "rq_no", "verdict", "note", "timestamp_utc"]

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


def load_existing_keys_multi(path: Path, key_fields: list) -> set:
    """Same as `load_existing_keys`, for a composite key (e.g. the
    (rq_no, tool_id, role) triple that makes a `tool_map` row unique)."""
    if not path.exists():
        return set()
    with open(path, "r", encoding="utf-8") as f:
        return {tuple(row[field] for field in key_fields) for row in csv.DictReader(f)}


def append_rows(path: Path, fieldnames: list, rows: list, key_fields: list) -> tuple:
    """Appends `rows` to the CSV at `path`, writing a header only if the file
    is new, and skipping any row whose `key_fields` already appear in the
    file -- so running the same batch twice (or several batches across a
    session) accumulates rather than duplicates. Returns (written, skipped)
    counts."""
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = load_existing_keys_multi(path, key_fields)
    new_rows = [r for r in rows if tuple(r[f] for f in key_fields) not in existing]
    skipped = len(rows) - len(new_rows)
    is_new = not path.exists()
    with open(path, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if is_new:
            writer.writeheader()
        writer.writerows(new_rows)
    return len(new_rows), skipped


def load_live_tool_ids(data_json: Path) -> set:
    """Returns the `id` of every tool already in the live `tools` tab (via
    site/data.json, which build.py generates from it). Pass A re-judges
    already-accepted tools against RQs they aren't yet mapped to -- their
    `tools` row must not be re-emitted, only the new `tool_map` row(s)."""
    if not data_json.exists():
        return set()
    with open(data_json, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {tool["id"] for tool in data.get("tools", [])}


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
    parser.add_argument("--pass-a-out", default="curation/state/pass_a_checked.csv",
                        help="ledger of every (tool_id, rq_no) pairing considered, match or not")
    parser.add_argument("--search-candidates", default="curation/state/search_candidates.csv",
                        help="used to look up licence/stars/keyword per repo; a repo absent "
                             "from it is recorded with whatever the judgment supplied")
    parser.add_argument("--data-json", default="site/data.json",
                        help="used to detect tool ids already live in the `tools` tab, so "
                             "pass-A re-mappings of an existing tool don't re-emit its `tools` "
                             "row -- only its new `tool_map` row(s). Run `python build.py` "
                             "first so this reflects the current live sheet.")
    parser.add_argument("--problem-area", default="",
                        help="problem area this batch was searched for; recorded on every "
                             "triage row so per-area counts are computable later. A judgment "
                             "may override it with its own 'problem_area' key.")
    args = parser.parse_args()

    with open(args.judgments, "r", encoding="utf-8") as f:
        judgments = json.load(f)

    search_meta = load_search_metadata(Path(args.search_candidates))
    live_tool_ids = load_live_tool_ids(Path(args.data_json))
    spdx = load_spdx_index()

    tool_rows, map_rows, seen_rows, pass_a_rows = [], [], [], []
    seen_ids = set()
    live_tools_skipped = 0
    seen_repos_in_batch = set()
    now = datetime.datetime.now(datetime.timezone.utc)
    # seen_repos.csv is our own audit log, never pasted into the sheet, so it
    # keeps full ISO precision. candidate_tools.csv / candidate_map_updates.csv
    # get pasted directly into sheet cells, and every existing datetime_* cell
    # in the live sheet uses "YYYY-MM-DD HH:MM" (UTC, no seconds, no offset) --
    # matching that means a human can paste without reformatting, which is the
    # difference between the timestamp columns actually getting filled in and
    # quietly getting skipped (as happened to the previous batch).
    timestamp = now.isoformat(timespec="seconds")
    sheet_timestamp = now.strftime("%Y-%m-%d %H:%M")
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

        if tool_id in live_tool_ids:
            # Pass A: re-mapping a tool that's already in the live `tools`
            # tab. Only its new tool_map row(s) belong in the output --
            # re-emitting the tools row would duplicate it once pasted in.
            live_tools_skipped += 1
        else:
            tool_rows.append({
                "id": tool_id,
                "tool_type": j.get("tool_type", "software"),
                "name": j.get("name", tool_id),
                "summary": j.get("summary", ""),
                "license": j.get("license", ""),
                "programming_language": j.get("programming_language", ""),
                "homepage": j.get("homepage", ""),
                "source": j.get("source", ""),
                "documentation": j.get("documentation", ""),
                "funding": j.get("funding", ""),
                # Project-quality/community-health columns: left blank here by
                # design -- run curation/collect_project_metadata.py after this
                # tool is merged into the live sheet and site/data.json is
                # rebuilt, rather than having the judging agent try to guess
                # star counts or OpenSSF scan status by hand. Still listed in
                # TOOLS_FIELDNAMES so the emitted row's columns line up with
                # the live tab's, for a clean paste.
                "stars": j.get("stars", ""),
                "forks": j.get("forks", ""),
                "watchers": j.get("watchers", ""),
                "contributors": j.get("contributors", ""),
                "sponsors": j.get("sponsors", ""),
                "keywords": j.get("keywords", ""),
                "open_issues_count": j.get("open_issues_count", ""),
                "releases_count": j.get("releases_count", ""),
                "latest_release_date": j.get("latest_release_date", ""),
                "last_commit_date": j.get("last_commit_date", ""),
                "readme_url": j.get("readme_url", ""),
                "license_url": j.get("license_url", ""),
                "code_of_conduct_url": j.get("code_of_conduct_url", ""),
                "contributing_url": j.get("contributing_url", ""),
                "security_policy_url": j.get("security_policy_url", ""),
                "governance_url": j.get("governance_url", ""),
                "sbom_url": j.get("sbom_url", ""),
                "funder": j.get("funder", ""),
                "development_status": j.get("development_status", ""),
                "paper_url": j.get("paper_url", ""),
                "dependents": j.get("dependents", ""),
                "software_heritage_id": j.get("software_heritage_id", ""),
                "openssf_best_practices_url": j.get("openssf_best_practices_url", ""),
                "openssf_best_practices_badge_level": j.get("openssf_best_practices_badge_level", ""),
                "openssf_scorecard_url": j.get("openssf_scorecard_url", ""),
                "openssf_scorecard_score": j.get("openssf_scorecard_score", ""),
                "openssf_scorecard_branch_protection": j.get("openssf_scorecard_branch_protection", ""),
                "openssf_scorecard_code_review": j.get("openssf_scorecard_code_review", ""),
                "openssf_scorecard_maintained": j.get("openssf_scorecard_maintained", ""),
                "openssf_scorecard_vulnerabilities": j.get("openssf_scorecard_vulnerabilities", ""),
                "datetime_added": sheet_timestamp,
                "datetime_checked": sheet_timestamp,
                "datetime_updated": sheet_timestamp,
            })

        mappings = j.get("mappings", [])
        if not mappings and not j.get("no_rq_mapping_reason"):
            errors.append(f"{repo}: verdict=accept but no RQ mappings given (if this is "
                           f"deliberate -- a real tool with no matching RQ in the current "
                           f"taxonomy yet -- set 'no_rq_mapping_reason' explaining why; it'll "
                           f"land on the site's 'Pending mapping' list instead of an RQ page)")
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
                "datetime_added": sheet_timestamp,
                "datetime_checked": sheet_timestamp,
                "datetime_updated": sheet_timestamp,
            })
            pass_a_rows.append({
                "tool_id": tool_id,
                "rq_no": m.get("rq_no", ""),
                "verdict": "match",
                "note": "",
                "timestamp_utc": timestamp,
            })

        for entry in j.get("checked_no_match", []):
            rq_no = entry if isinstance(entry, str) else entry.get("rq_no", "")
            note = "" if isinstance(entry, str) else entry.get("note", "")
            if not rq_no:
                errors.append(f"{repo}: checked_no_match entry missing rq_no")
                continue
            pass_a_rows.append({
                "tool_id": tool_id,
                "rq_no": rq_no,
                "verdict": "no_match",
                "note": note,
                "timestamp_utc": timestamp,
            })

    if errors:
        print("Errors -- fix the judgments file and re-run (nothing was written):")
        for e in errors:
            print(f"  - {e}")
        raise SystemExit(1)

    tools_out = Path(args.tools_out)
    tools_written, tools_skipped = append_rows(tools_out, TOOLS_FIELDNAMES, tool_rows, ["id"])

    map_out = Path(args.map_out)
    map_written, map_skipped = append_rows(map_out, MAP_FIELDNAMES, map_rows, ["rq_no", "tool_id", "role"])

    seen_path = Path(args.seen_repos)
    seen_written, seen_skipped = append_rows(seen_path, SEEN_FIELDNAMES, seen_rows, ["full_name"])

    pass_a_path = Path(args.pass_a_out)
    pass_a_written, pass_a_skipped = append_rows(pass_a_path, PASS_A_FIELDNAMES, pass_a_rows, ["tool_id", "rq_no"])

    pending_mapping_count = sum(1 for j in judgments
                                 if j.get("verdict") == "accept" and not j.get("mappings"))
    print(f"{tools_written} accepted tool(s) -> {tools_out}"
          + (f" ({tools_skipped} already present, skipped)" if tools_skipped else "")
          + (f" ({live_tools_skipped} already live in tools tab, tools-row skipped)" if live_tools_skipped else "")
          + (f" ({pending_mapping_count} with no RQ mapping -- will show under 'Pending mapping' on the site)"
             if pending_mapping_count else ""))
    print(f"{map_written} RQ mapping(s) -> {map_out}"
          + (f" ({map_skipped} already present, skipped)" if map_skipped else ""))
    print(f"{seen_written} repo(s) newly logged -> {seen_path}"
          + (f" ({seen_skipped} already logged, skipped)" if seen_skipped else ""))
    if pass_a_rows:
        print(f"{pass_a_written} (tool, RQ) pairing(s) logged -> {pass_a_path}"
              + (f" ({pass_a_skipped} already present, skipped)" if pass_a_skipped else ""))


if __name__ == "__main__":
    main()
