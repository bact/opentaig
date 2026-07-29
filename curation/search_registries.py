#!/usr/bin/env python3
"""Search non-GitHub registries for candidate tools -- source 10 in
curation/README.md's "Keyword expansion (phase 2)" list. GitHub's own search
index is what search_repos.py mines; a tool can rank low there (or never
even be pushed as its own top-level repo) while still being prominent on the
registry its actual users install from.

Two registries, both with a real public JSON search API (no auth, no
scraping):

  - **npm** (`--registry npm`) -- registry.npmjs.org's official search API.
    Each hit's `repository` field is resolved back to a `github.com/owner/repo`
    URL and run through the *same* filters as search_repos.py (stars/pushed/
    archived/fork + README length), via the shared helpers in snowball.py --
    so an npm-sourced candidate clears the identical bar, just discovered
    through a different index. Rows land in the normal
    curation/state/search_candidates.csv with an `npm/<pkg>` note.
  - **Hugging Face** (`--registry huggingface-spaces` /
    `--registry huggingface-models`) -- huggingface.co's public search API.
    Most Spaces/Models aren't mirrored to a top-level GitHub repo, so these
    are kept as their own candidate rows (`full_name` = `hf:<id>`,
    `html_url` = the HF page, `stars` = likes as a rough popularity proxy).
    No README-length filter is applied here (HF model/dataset cards use a
    different format); read the card directly at the judgment step instead.

**PyPI has no working public search API** -- its old XML-RPC `search()`
method was retired in 2018, and PyPI's search *page*
(`https://pypi.org/search/?q=...`) returned a bot-detection "Client
Challenge" page (Fastly), not results, when this was checked live -- so it
can't be scraped either. Use GitHub's own search instead
(`search_repos.py`, optionally with `language:python`); nearly every
PyPI-published tool worth including also has a GitHub repo.

Usage:

    python curation/search_registries.py --registry npm --keyword "LLM guardrail"
    python curation/search_registries.py --registry huggingface-spaces --keyword "fairness"
    python curation/search_registries.py --registry huggingface-models --keyword "toxicity classifier"

Logged to curation/state/search_log.csv (keyword = "<registry>:<term>") and
appended to curation/state/search_candidates.csv, same as search_repos.py
and snowball.py, so it's part of the same audit trail.
"""
from __future__ import annotations

import argparse
import csv
import datetime
import os
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from search_repos import (  # noqa: E402
    DEFAULT_MIN_STARS, DEFAULT_PUSHED_AFTER_MONTHS, DEFAULT_MIN_README_CHARS,
    cutoff_date, fetch_readme_text, readme_content_length,
    load_existing_candidates, append_search_log,
)
from snowball import fetch_repo, passes_filters, extract_repo_links  # noqa: E402

NPM_SEARCH_API = "https://registry.npmjs.org/-/v1/search"
HF_API = "https://huggingface.co/api"


def npm_repo_from_links(links: dict) -> str | None:
    """npm's `links.repository` is a git+https/git+ssh URL, sometimes with a
    trailing `.git`, `#subdir`, etc. Pull the owner/repo out of it."""
    repo_url = links.get("repository") or links.get("homepage") or ""
    if "github.com" not in repo_url:
        return None
    hits = extract_repo_links(repo_url, self_full_name="")
    return hits[0] if hits else None


def search_npm(term: str, size: int, warnings: list) -> list[dict]:
    resp = requests.get(NPM_SEARCH_API, params={"text": term, "size": size}, timeout=30)
    if resp.status_code != 200:
        warnings.append(f"npm search {term!r} failed: HTTP {resp.status_code}")
        return []
    return resp.json().get("objects", [])


def search_huggingface(kind: str, term: str, size: int, warnings: list) -> list[dict]:
    endpoint = "spaces" if kind == "huggingface-spaces" else "models"
    resp = requests.get(f"{HF_API}/{endpoint}", params={"search": term, "limit": size}, timeout=30)
    if resp.status_code != 200:
        warnings.append(f"huggingface {endpoint} search {term!r} failed: HTTP {resp.status_code}")
        return []
    return resp.json()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--registry", required=True,
                         choices=["npm", "huggingface-spaces", "huggingface-models"])
    parser.add_argument("--keyword", action="append", required=True, dest="keywords",
                         help="search term; repeat --keyword for multiple")
    parser.add_argument("--size", type=int, default=20, help="results to fetch per keyword")
    parser.add_argument("--min-stars", type=int, default=DEFAULT_MIN_STARS,
                         help="npm only -- resolved GitHub repos still need to clear this bar")
    parser.add_argument("--pushed-after-months", type=int, default=DEFAULT_PUSHED_AFTER_MONTHS)
    parser.add_argument("--min-readme-chars", type=int, default=DEFAULT_MIN_README_CHARS,
                         help="npm only")
    parser.add_argument("--out-candidates", default="curation/state/search_candidates.csv")
    parser.add_argument("--log-path", default="curation/state/search_log.csv")
    args = parser.parse_args()

    candidates = load_existing_candidates(Path(args.out_candidates))
    seen_before = set(candidates)
    warnings: list = []
    log_rows = []
    run_timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")

    session = None
    pushed_after = None
    if args.registry == "npm":
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            raise SystemExit("GITHUB_TOKEN is not set -- npm hits are resolved to GitHub repos "
                              "and need the GitHub API. See curation/README.md's Setup section.")
        session = requests.Session()
        session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        pushed_after = cutoff_date(args.pushed_after_months)

    for term in args.keywords:
        label = f"{args.registry}:{term}"
        print(f"[registry] {label!r}")
        kept = 0
        raw_count = 0

        if args.registry == "npm":
            hits = search_npm(term, args.size, warnings)
            raw_count = len(hits)
            for hit in hits:
                pkg = hit.get("package", {})
                full_name = npm_repo_from_links(pkg.get("links", {}))
                if not full_name or full_name in candidates:
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
                    "description": (item.get("description") or pkg.get("description") or "").strip(),
                    "stars": item.get("stargazers_count", 0),
                    "pushed_at": item.get("pushed_at", ""),
                    "language": item.get("language") or "",
                    "license_spdx_id": (item.get("license") or {}).get("spdx_id") or pkg.get("license", ""),
                    "homepage": item.get("homepage") or "",
                    "found_via_keyword": label,
                }
                kept += 1
        else:
            hits = search_huggingface(args.registry, term, args.size, warnings)
            raw_count = len(hits)
            for hit in hits:
                hf_id = hit.get("id") or hit.get("modelId")
                if not hf_id:
                    continue
                kind_path = "spaces" if args.registry == "huggingface-spaces" else "models"
                full_name = f"hf:{hf_id}"
                if full_name in candidates:
                    continue
                candidates[full_name] = {
                    "full_name": full_name,
                    "html_url": f"https://huggingface.co/{kind_path}/{hf_id}",
                    "description": "",  # not in the search response; read the card at judgment time
                    "stars": hit.get("likes", 0),
                    "pushed_at": hit.get("lastModified", "") or hit.get("createdAt", ""),
                    "language": "",
                    "license_spdx_id": "",  # not in the search response; check the model/space card
                    "homepage": f"https://huggingface.co/{kind_path}/{hf_id}",
                    "found_via_keyword": label,
                }
                kept += 1

        print(f"  -> {raw_count} hit(s), {kept} new candidate(s) kept")
        log_rows.append({
            "timestamp_utc": run_timestamp,
            "keyword": label,
            "query": term,
            "raw_count": raw_count,
            "new_candidates": kept,
            "min_stars": args.min_stars if args.registry == "npm" else "n/a",
            "pushed_after_months": args.pushed_after_months if args.registry == "npm" else "n/a",
            "min_readme_chars": args.min_readme_chars if args.registry == "npm" else "n/a (registry API, no README check)",
            "notes": f"non-GitHub registry search ({args.registry})",
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
