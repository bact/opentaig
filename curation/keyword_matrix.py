#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2026 OpenTAIG authors
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Generate candidate search keywords by combining terms across structured
dimensions (PICOC-style: Target/Action/Objective/Context), instead of
improvising flat phrases one at a time.

This is source 6 ("Domain x Artifact x Tool-type") in curation/README.md's
"Keyword expansion (phase 2)" section, generalized to any two dimensions and
made runnable -- rather than a fixed 3-column table someone reads and
manually combines.

Deterministic; no model, no network. Combines exactly TWO dimensions per run
(never three+) to respect the 2-3-word rule documented in the README: GitHub's
search API ANDs every unquoted word, and 4+ word free-text queries reliably
return zero hits even for real candidates.

Usage:
    python curation/keyword_matrix.py --list-dims
    python curation/keyword_matrix.py --dims target,action
    python curation/keyword_matrix.py --dims action,objective --limit 30
    python curation/keyword_matrix.py --dims target,action --show-tried

Feed the output straight into search_repos.py:

    python curation/keyword_matrix.py --dims target,action --limit 20 \\
        | xargs -I{} echo --keyword "{}"
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

# PICOC-adapted dimensions for this project's domain (open-source AI
# governance tooling). Kept as short (1-2 word) terms so any 2-dimension
# combination stays within the 2-3-word rule.
DIMENSIONS: dict[str, list[str]] = {
    # P/Target -- what the tool acts upon
    "target": [
        "LLM", "foundation model", "dataset", "RAG", "agent", "prompt",
        "embedding", "model weights", "training data", "generative AI",
    ],
    # I/Action -- what the tool actually does
    "action": [
        "guardrail", "scanner", "fuzzer", "auditor", "evaluator",
        "red-teaming", "watermark", "anonymizer", "validator", "shield",
        "monitor", "linter", "benchmark",
    ],
    # O/Outcome -- the governance problem it targets
    "objective": [
        "safety", "alignment", "toxicity", "hallucination", "privacy",
        "bias", "explainability", "compliance", "fairness", "robustness",
        "provenance", "drift",
    ],
    # C/Context -- environment/format/distribution shape
    "context": [
        "open source", "toolkit", "framework", "library", "CLI", "MLSecOps",
    ],
}


def load_tried(log_path: Path) -> set[str]:
    """Keywords already logged in search_log.csv (any run, hit or not)."""
    if not log_path.exists():
        return set()
    with open(log_path, "r", encoding="utf-8") as f:
        return {row["keyword"].strip().lower() for row in csv.DictReader(f) if row.get("keyword")}


def combos(dim_a: str, dim_b: str) -> list[str]:
    if dim_a not in DIMENSIONS:
        raise SystemExit(f"unknown dimension {dim_a!r}; choices: {', '.join(DIMENSIONS)}")
    if dim_b not in DIMENSIONS:
        raise SystemExit(f"unknown dimension {dim_b!r}; choices: {', '.join(DIMENSIONS)}")
    return [f"{a} {b}" for a in DIMENSIONS[dim_a] for b in DIMENSIONS[dim_b]]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dims", help="two dimension names, comma-separated, e.g. target,action")
    parser.add_argument("--list-dims", action="store_true", help="print dimension names and their terms, then exit")
    parser.add_argument("--limit", type=int, default=None, help="cap the number of phrases printed")
    parser.add_argument("--log-path", default="curation/state/search_log.csv")
    parser.add_argument("--show-tried", action="store_true",
                         help="print ALL combos, marking already-tried ones with a leading '# ', "
                              "instead of silently dropping them")
    args = parser.parse_args()

    if args.list_dims:
        for name, terms in DIMENSIONS.items():
            print(f"{name} ({len(terms)}): {', '.join(terms)}")
        return

    if not args.dims:
        raise SystemExit("--dims is required (or pass --list-dims)")
    parts = [d.strip() for d in args.dims.split(",")]
    if len(parts) != 2:
        raise SystemExit("--dims must name exactly two dimensions, e.g. --dims target,action "
                          "(never three+ -- see the 2-3-word rule in curation/README.md)")

    tried = load_tried(Path(args.log_path))
    phrases = combos(*parts)

    out = []
    for phrase in phrases:
        already = phrase.lower() in tried
        if already and not args.show_tried:
            continue
        out.append(f"# {phrase}  (already tried)" if already else phrase)

    if args.limit:
        out = out[: args.limit]

    for line in out:
        print(line)

    if not args.show_tried:
        new_count = sum(1 for p in phrases if p.lower() not in tried)
        print(f"{len(phrases)} total combos, {new_count} not yet in {args.log_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
