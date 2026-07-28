#!/usr/bin/env python3
"""One-time migration: populate the reject_category / license_class /
problem_area / found_via_keyword / stars columns added to
`state/seen_repos.csv` after the first 144 rows were already written by
earlier emit_candidates.py runs (before it recorded any of that).

This is a **best-effort reconstruction**, not a re-judgment:

- `license_class` / `found_via_keyword` / `stars` come from
  `state/search_candidates.csv`, joined on `full_name` -- exact, not a
  guess, for the 111/144 rows that went through `search_repos.py`.
- The 32 RGAF-seed rows didn't go through `search_repos.py` (they came from
  a blog post via `tools_rgaf_seed`), so `found_via_keyword`/`stars` stay
  blank for them -- there's no metadata to backfill those two from, and
  inventing them would misrepresent the record. `license_spdx_id` is
  still recoverable though: the 29 accepted ones are already live in the
  `tools` tab with a human-verified licence, joined here via
  `site/data.json`'s `source` URL (run `python build.py` first so that
  file is current). The 3 rejected ones aren't in `tools` -- those were
  looked up directly via the GitHub API on 2026-07-28 and are hardcoded in
  `RGAF_REJECT_LICENSES` below, since it's a fixed, closed set of 3 that
  will never grow.
- `problem_area` is inferred from which timestamp cluster a row falls in
  (four batches, four clearly separated `timestamp_utc` values -- see
  BATCH_AREAS below.) The RGAF-seed batch spans many different RQs per
  tool, so it's tagged `rgaf-seed-triage` rather than a single area.
- `reject_category` is regex-matched against the existing free-text `note`
  against the same closed vocabulary emit_candidates.py now validates
  going forward (REJECT_CATEGORIES). This is inherently approximate --
  the note was written as prose, not with a category in mind -- so this
  script prints every row whose note didn't confidently match a category,
  for a manual look, rather than silently guessing.

Only ever needs to run once. Kept in the repo (rather than deleted after
running) so the reconstruction is itself auditable -- a future reader can
see exactly how the historical categories were derived instead of finding
opaque values with no explanation.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from emit_candidates import SEEN_FIELDNAMES
from licenses import classify, load_spdx_index

SEEN_PATH = Path("curation/state/seen_repos.csv")
CANDIDATES_PATH = Path("curation/state/search_candidates.csv")
SITE_DATA_PATH = Path("site/data.json")

REPO_PATH_RE = re.compile(r"github\.com[:/]+([^/]+/[^/.]+?)(?:\.git)?/?$", re.IGNORECASE)

# The 3 rgaf-seed-triage rejects: not in the `tools` tab (rejected, so never
# merged), so there's no site/data.json row to join against. Looked up
# directly via `curl -H "Authorization: Bearer $GITHUB_TOKEN"
# api.github.com/repos/<full_name>` on 2026-07-28 -- see the module
# docstring. A fixed, closed set; will never need a new entry.
RGAF_REJECT_LICENSES = {
    "mlflow/mlflow": "Apache-2.0",
    "SonySemiconductorSolutions/mct-model-optimization": "Apache-2.0",
    "intel/neural-compressor": "Apache-2.0",
}


def load_tools_licenses_by_repo(path: Path) -> dict:
    """Returns {repo_path_lowercased: license_spdx_id} for every tool live in
    the `tools` tab, by extracting 'org/repo' from each tool's `source` URL.
    Used to backfill licence for rgaf-seed-triage accepts, which are exactly
    the tools that made it into this catalog."""
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    by_repo = {}
    for tool in data.get("tools", []):
        m = REPO_PATH_RE.search(tool.get("source", "") or "")
        if m:
            by_repo[m.group(1).lower()] = tool.get("license", "")
    return by_repo

# Timestamp -> (problem_area, source note). Four batches, identified by
# their shared timestamp_utc (all rows written by one emit_candidates.py
# run share the run's timestamp).
BATCH_AREAS = {
    "2026-07-24T17:43:42+00:00": "Identification of Problematic Data",  # RQ1-6, first search_repos.py batch
    "2026-07-28T06:52:16+00:00": "rgaf-seed-triage",  # tools_rgaf_seed, spans many RQs -- see docstring
    "2026-07-28T12:58:33+00:00": "Verification of AI-generated Content",  # RQ65-68
    "2026-07-28T13:43:57+00:00": "Verifiable Audits",  # RQ59-64
}

# (category, regex) pairs, checked in order -- first match wins. Mirrors
# REJECT_CATEGORIES in emit_candidates.py; kept as a local, ordered list here
# because backfill needs priority between overlapping patterns (e.g. a note
# can mention both "off-topic" and "thin" -- off-topic is the more specific,
# more useful signal so it's checked first).
CATEGORY_PATTERNS = [
    ("not-open-source", r"licen[cs]e|Source Access Grant|proprietary"),
    ("adversarial-purpose", r"adversarial|removes watermark|strips|evade|wrong side"),
    ("not-a-tool-linklist", r"awesome-list|curated (link|paper) list"),
    ("not-a-tool-dataset", r"dataset (repository|release|paper)|benchmark dataset"),
    ("not-a-tool-paper-artifact", r"single-paper|research code release|research artifact|"
                                   r"research-notebook|whitepaper|paper release|"
                                   r"mathematical formulations|circuit designs"),
    ("commercial-sdk", r"commercial-sdk"),
    ("not-relevant", r"off-topic|false positive|unrelated|different (problem area|domain)|"
                      r"not an audit or provenance registry"),
    ("low-substance", r"low-substance|student/tutorial|tutorial repo|hackathon|vague|"
                       r"not clearly maintained|thin"),
    ("redundant", r"redundant"),
]


def categorize(note: str) -> str | None:
    for category, pattern in CATEGORY_PATTERNS:
        if re.search(pattern, note, re.IGNORECASE):
            return category
    return None


def main() -> None:
    with open(SEEN_PATH, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    with open(CANDIDATES_PATH, "r", encoding="utf-8") as f:
        cand_meta = {r["full_name"]: r for r in csv.DictReader(f)}

    tools_licenses = load_tools_licenses_by_repo(SITE_DATA_PATH)

    spdx = load_spdx_index()
    unmatched = []

    for row in rows:
        if row.get("license_class"):
            continue  # already backfilled or written post-migration; leave alone

        meta = cand_meta.get(row["full_name"], {})
        license_spdx = (meta.get("license_spdx_id", "")
                         or tools_licenses.get(row["full_name"].lower(), "")
                         or RGAF_REJECT_LICENSES.get(row["full_name"], ""))
        row["license_spdx_id"] = license_spdx
        row["license_class"] = classify(license_spdx, spdx)
        row["found_via_keyword"] = meta.get("found_via_keyword", "")
        row["stars"] = meta.get("stars", "")
        row["problem_area"] = BATCH_AREAS.get(row["timestamp_utc"], "")

        if row["verdict"] == "reject":
            cat = categorize(row.get("note", ""))
            if cat is None:
                cat = "out-of-scope-narrow"  # the residual bucket -- see CATEGORY_PATTERNS
                unmatched.append(row["full_name"])
            row["reject_category"] = cat
        else:
            row["reject_category"] = ""

    with open(SEEN_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SEEN_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Backfilled {len(rows)} row(s) in {SEEN_PATH}")
    if unmatched:
        print(f"\n{len(unmatched)} reject(s) fell back to 'out-of-scope-narrow' "
              f"(no regex pattern matched their note -- worth a manual look):")
        for name in unmatched:
            print(f"  - {name}")


if __name__ == "__main__":
    main()
