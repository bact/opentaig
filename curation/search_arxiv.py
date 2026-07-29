#!/usr/bin/env python3
"""Search arXiv for papers whose abstract/comments advertise a code release,
and resolve any GitHub link found to a real candidate repo -- the last
unscripted source in curation/README.md's "Keyword expansion" list (source
10's arXiv bullet).

Many governance-relevant tools start life as a paper artifact (TextAttack,
ART, ...) rather than a standalone GitHub-first project, so they rank low or
never appear in a GitHub-native search. arXiv's own search only returns
papers, not resolved code -- this script closes that gap: it queries the
public Atom API (no auth, no scraping), pulls every `github.com/owner/repo`
link out of each hit's abstract/summary and comment field, and runs each
through the exact same filters as search_repos.py/snowball.py (stars/
pushed/archived/fork + README length) before it counts as a candidate.

**Judge these extra carefully against `not-a-tool-paper-artifact`** (see
curation/README.md's "Rejection tracking" table) -- the category exists to
reject one-off replication scripts, not maintained tools that happen to
have a paper. A repo that's still actively pushed/starred well after the
paper's publication date is reasonable evidence it's the latter.

Usage:

    python curation/search_arxiv.py --keyword "LLM auditing" \\
        --keyword "model evaluation toolkit"

Logged to curation/state/search_log.csv (keyword = "arxiv:<term>") and
appended to curation/state/search_candidates.csv, same as the other
discovery scripts.

NOTE: `export.arxiv.org/api/query` could not be reached from the sandbox
this script was written in (the bare host answers, but that specific path
timed out every time -- possibly a network policy quirk of that
environment, not arXiv itself). This is arXiv's documented, stable public
API and the request logic mirrors search_repos.py's proven GitHub calls, but
it has NOT been exercised against a real response here -- run it once
locally and sanity-check the output before relying on it.
"""
from __future__ import annotations

import argparse
import csv
import datetime
import os
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import quote

import requests

sys.path.insert(0, str(Path(__file__).parent))
from search_repos import (  # noqa: E402
    DEFAULT_MIN_STARS, DEFAULT_PUSHED_AFTER_MONTHS, DEFAULT_MIN_README_CHARS,
    cutoff_date, fetch_readme_text, readme_content_length,
    load_existing_candidates, append_search_log,
)
from snowball import fetch_repo, passes_filters, extract_repo_links  # noqa: E402

ARXIV_API = "https://export.arxiv.org/api/query"
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


def search_arxiv(term: str, max_results: int, warnings: list) -> list[dict]:
    """One page of arXiv's Atom search API, parsed into plain dicts."""
    url = f"{ARXIV_API}?search_query=all:{quote(term)}&start=0&max_results={max_results}"
    try:
        resp = requests.get(url, timeout=30)
    except requests.RequestException as e:
        warnings.append(f"arxiv search {term!r} failed: {e}")
        return []
    if resp.status_code != 200:
        warnings.append(f"arxiv search {term!r} failed: HTTP {resp.status_code}")
        return []
    root = ET.fromstring(resp.text)
    entries = []
    for entry in root.findall("atom:entry", ATOM_NS):
        summary = (entry.findtext("atom:summary", default="", namespaces=ATOM_NS) or "").strip()
        comment = (entry.findtext("arxiv:comment", default="", namespaces=ATOM_NS) or "").strip()
        entries.append({
            "id": entry.findtext("atom:id", default="", namespaces=ATOM_NS),
            "title": " ".join((entry.findtext("atom:title", default="", namespaces=ATOM_NS) or "").split()),
            "summary": summary,
            "comment": comment,
        })
    return entries


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--keyword", action="append", required=True, dest="keywords",
                         help="arXiv search term; repeat --keyword for multiple")
    parser.add_argument("--max-results", type=int, default=20, help="papers to fetch per keyword")
    parser.add_argument("--min-stars", type=int, default=DEFAULT_MIN_STARS)
    parser.add_argument("--pushed-after-months", type=int, default=DEFAULT_PUSHED_AFTER_MONTHS)
    parser.add_argument("--min-readme-chars", type=int, default=DEFAULT_MIN_README_CHARS)
    parser.add_argument("--out-candidates", default="curation/state/search_candidates.csv")
    parser.add_argument("--log-path", default="curation/state/search_log.csv")
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("GITHUB_TOKEN is not set -- extracted links are resolved to GitHub repos "
                          "and need the GitHub API. See curation/README.md's Setup section.")
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    pushed_after = cutoff_date(args.pushed_after_months)

    candidates = load_existing_candidates(Path(args.out_candidates))
    seen_before = set(candidates)
    warnings: list = []
    log_rows = []
    run_timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")

    for term in args.keywords:
        label = f"arxiv:{term}"
        print(f"[arxiv] {label!r}")
        papers = search_arxiv(term, args.max_results, warnings)
        time.sleep(3)  # arXiv asks for >=3s between API requests

        found_links = 0
        kept = 0
        for paper in papers:
            text = f"{paper['summary']} {paper['comment']}"
            links = extract_repo_links(text, self_full_name="")
            found_links += len(links)
            for full_name in links:
                if full_name in candidates:
                    continue
                item = fetch_repo(session, full_name)
                time.sleep(0.2)
                if item is None or not passes_filters(item, args.min_stars, pushed_after):
                    continue
                readme = fetch_readme_text(session, full_name, warnings)
                time.sleep(0.2)
                if readme_content_length(readme) < args.min_readme_chars:
                    continue
                candidates[full_name] = {
                    "full_name": full_name,
                    "html_url": item.get("html_url", ""),
                    "description": (item.get("description") or paper["title"]).strip(),
                    "stars": item.get("stargazers_count", 0),
                    "pushed_at": item.get("pushed_at", ""),
                    "language": item.get("language") or "",
                    "license_spdx_id": (item.get("license") or {}).get("spdx_id") or "",
                    "homepage": item.get("homepage") or "",
                    "found_via_keyword": f"{label} (paper: {paper['id']})",
                }
                kept += 1

        print(f"  -> {len(papers)} paper(s), {found_links} github link(s) extracted, "
              f"{kept} new candidate(s) kept")
        log_rows.append({
            "timestamp_utc": run_timestamp,
            "keyword": label,
            "query": term,
            "raw_count": len(papers),
            "new_candidates": kept,
            "min_stars": args.min_stars,
            "pushed_after_months": args.pushed_after_months,
            "min_readme_chars": args.min_readme_chars,
            "notes": "arXiv abstract/comment link extraction, not a GitHub search",
        })

    append_search_log(Path(args.log_path), log_rows)
    print(f"logged {len(log_rows)} keyword run(s) to {args.log_path}")

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
    if warnings:
        print(f"\n{len(warnings)} warning(s):", file=sys.stderr)
        for w in warnings:
            print(f"  - {w}", file=sys.stderr)


if __name__ == "__main__":
    main()
