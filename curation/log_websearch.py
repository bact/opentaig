#!/usr/bin/env python3
"""Log a web search (Google/Bing, via the agent's built-in WebSearch tool)
to the same provenance trail as every other discovery method in this
pipeline.

General web search isn't scriptable here -- there's no free, keyless search
API to call from Python (Google/Bing search APIs require paid keys), so this
stays an agent-driven step: the agent runs its own WebSearch tool call, then
records what it searched and what it found with this script, exactly the
way curation/README.md already asks for the raw-curl calibration probes
("log those too with a note distinguishing them from real script runs").

This does NOT touch search_candidates.csv -- a web search surfaces leads
(a blog post, a project homepage, a GitHub link buried in prose) that still
need to go through the normal judgment pipeline by hand; it's not a
structured API response this script could safely auto-parse into rows.

Usage:

    python curation/log_websearch.py --keyword "open source AI incident database" \\
        --hit-count 8 --new-leads 2 \\
        --note "found aiaaic.org and oecd.ai/en/incidents in top 5 results"

Appends one row to curation/state/search_log.csv with keyword prefixed
"websearch:" so it's never confused with a GitHub/registry API call when
computing paper statistics from the log.
"""
from __future__ import annotations

import argparse
import datetime
from pathlib import Path

from search_repos import append_search_log  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--keyword", required=True, help="the search query actually typed")
    parser.add_argument("--hit-count", type=int, default=0,
                         help="number of results looked at (not a total-hits count, since "
                              "general web search doesn't report one the way an API does)")
    parser.add_argument("--new-leads", type=int, default=0,
                         help="how many of those results turned into something worth judging "
                              "(a URL to follow up, not yet a candidate row)")
    parser.add_argument("--note", default="", help="free text: what was found, or why 0 leads is real negative evidence")
    parser.add_argument("--log-path", default="curation/state/search_log.csv")
    args = parser.parse_args()

    row = {
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "keyword": f"websearch:{args.keyword}",
        "query": args.keyword,
        "raw_count": args.hit_count,
        "new_candidates": args.new_leads,
        "min_stars": "n/a",
        "pushed_after_months": "n/a",
        "min_readme_chars": "n/a",
        "notes": "agent web search (WebSearch tool, not a scripted API call)"
                 + (f" -- {args.note}" if args.note else ""),
    }
    append_search_log(Path(args.log_path), [row])
    print(f"logged 1 web search to {args.log_path}: {args.keyword!r} "
          f"({args.hit_count} looked at, {args.new_leads} lead(s))")


if __name__ == "__main__":
    main()
