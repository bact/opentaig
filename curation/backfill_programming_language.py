#!/usr/bin/env python3
"""Retrospective fill for the `programming_language` column added to the
`tools` tab after the initial ~130 tools were already catalogued.

Read-only against the live sheet: this only ever *reads* `site/data.json`
(the last local `python build.py` output) and the real GitHub API, and
writes a review CSV -- it never touches the Google Sheet. A human copies
the `programming_language` value into the matching `id` row in the live
`tools` tab by hand (or via a one-time VLOOKUP-then-paste-values in the
sheet), the same review-before-merge shape as `candidate_tools.csv`.

Uses the real GitHub REST API (`/repos/{owner}/{repo}`), so like
search_repos.py it needs a `GITHUB_TOKEN` env var and unrestricted network
access to `api.github.com`. A Claude Code session whose only GitHub
credential is an auto-injected, repo-scoped token will get a 403 ("sessions
are bound to their configured repositories") -- but `export
GITHUB_TOKEN=$(gh auth token)` works fine when the environment has its own
independent `gh auth login` session (verify with `gh auth status` first).
See curation/README.md's "Running locally" section.

Only considers `tool_type` "software" rows with a GitHub `source` URL and a
currently-blank `programming_language` -- "specification" rows have no
source code to have a language, and a non-GitHub `source` (rare) can't be
looked up by this script and is listed separately for manual lookup.

The sheet's `programming_language` column accepts a semicolon-separated list
for genuinely polyglot tools (e.g. "Python; Rust"), but GitHub's repo
`language` field only ever reports one dominant-by-bytes language -- this
script always writes a single value per row. Add a second language by hand
in the sheet afterwards if the tool warrants it; don't infer one here.

Usage:

    python build.py   # refresh site/data.json against the live sheet first
    export GITHUB_TOKEN=ghp_...
    python curation/backfill_programming_language.py
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import time
from pathlib import Path

import requests

GITHUB_API = "https://api.github.com"
REPO_PATH_RE = re.compile(r"github\.com[:/]+([^/]+/[^/.]+?)(?:\.git)?/?$", re.IGNORECASE)

OUT_FIELDNAMES = ["id", "name", "source", "programming_language"]


def extract_repo_path(source_url: str) -> str | None:
    m = REPO_PATH_RE.search(source_url or "")
    return m.group(1) if m else None


def fetch_language(session: requests.Session, repo_path: str, warnings: list) -> str:
    """GitHub's own repo-level `language` field -- the dominant language by
    byte count, same source search_repos.py already logs for freshly
    discovered candidates. Returns "" on any failure (404/renamed/private/
    rate-limited) rather than raising, since a single unreachable repo
    shouldn't abort the whole batch."""
    try:
        resp = session.get(f"{GITHUB_API}/repos/{repo_path}", timeout=30)
        if resp.status_code == 403 and "rate limit" in resp.text.lower():
            reset = resp.headers.get("X-RateLimit-Reset")
            warnings.append(f"rate limited on {repo_path}; resets at {reset}")
            return ""
        if resp.status_code != 200:
            warnings.append(f"{repo_path}: GitHub API returned {resp.status_code}")
            return ""
        return resp.json().get("language") or ""
    except requests.RequestException as e:
        warnings.append(f"{repo_path}: request failed ({e})")
        return ""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-json", default="site/data.json",
                         help="local build output to read the live tool catalog from")
    parser.add_argument("--out", default="curation/state/programming_language_backfill.csv")
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit(
            "GITHUB_TOKEN is not set. This script needs a personal access token with "
            "public read access (no special scopes needed) -- see curation/README.md."
        )

    data_path = Path(args.data_json)
    if not data_path.exists():
        raise SystemExit(f"{data_path} not found -- run `python build.py` first.")
    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })

    warnings: list = []
    unresolvable_source: list = []
    rows = []

    tools = [t for t in data.get("tools", [])
             if t.get("tool_type") == "software" and not t.get("programming_languages")]
    print(f"[backfill] {len(tools)} software tool(s) missing programming_language")

    for i, tool in enumerate(tools, 1):
        repo_path = extract_repo_path(tool.get("source", ""))
        if not repo_path:
            unresolvable_source.append(tool["id"])
            continue
        language = fetch_language(session, repo_path, warnings)
        print(f"  [{i}/{len(tools)}] {tool['id']}: {language or '(none found)'}")
        if language:
            rows.append({
                "id": tool["id"],
                "name": tool.get("name", ""),
                "source": tool.get("source", ""),
                "programming_language": language,
            })
        time.sleep(0.5)  # stay well inside the unauthenticated/authenticated core rate limit

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUT_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWrote {len(rows)} row(s) to {out_path} -- review, then paste "
          f"programming_language values into the matching `id` rows in the live sheet.")
    if unresolvable_source:
        print(f"\n{len(unresolvable_source)} tool(s) have no GitHub-style `source` URL "
              f"and need a manual look:")
        for tid in unresolvable_source:
            print(f"  - {tid}")
    if warnings:
        print(f"\n{len(warnings)} warning(s):")
        for w in warnings:
            print(f"  - {w}")


if __name__ == "__main__":
    main()
