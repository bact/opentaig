#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2026 OpenTAIG authors
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Export research-question context for the tool-discovery pipeline.

Reads a built ``site/data.json`` (produced by ``python build.py``) and emits
``curation/rq_context.json``: one compact entry per research question with its
text, taxonomy, and the tool ids already mapped to it.

This is the input the discovery agent reads so it knows the **spine** (every
research question) and what is already covered -- so it maps NEW tools
*directly* to research questions, and never re-proposes a tool already
attached to a question. Deliberately compact: `tools_implement`/`tools_eval`
are bare id lists, not full tool records -- a Pass A judge re-mapping an
*existing* tool to a new RQ should look that id up directly in
`site/data.json`'s top-level `tools` array instead (the already-merged view
of both `tools` and `tool_metadata`, every field from both tabs resolved
through the precedence rule -- see "PASS A" in curation/README.md), not
duplicate that here.

Deterministic: no model, no network. It only reshapes the local
``site/data.json`` that ``build.py`` already produces (which is itself the
authoritative TAIG-sheet + map-tab join), so there is no second copy of the
join logic to drift out of sync.

Usage::

    python build.py                       # produce/refresh site/data.json first
    python curation/export_rq_context.py  # then export the RQ context

For a curation run against the *live* sheets, run ``build.py`` with the real
``config.yaml`` (the default) so ``data.json`` reflects the current sheet
state before exporting.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def rq_sort_key(rq_no: str):
    """Numeric where possible, else lexical -- RQ_No is an opaque string key
    (gaps are expected), but sorting numerically keeps the export readable."""
    try:
        return (0, int(rq_no), "")
    except (TypeError, ValueError):
        return (1, 0, str(rq_no))


def tool_ids(entries: list) -> list:
    """data.json's per-problem tools_implement/tools_eval entries carry only
    {id, name, homepage, rationale, freshness} -- we only need the ids here.
    The agent looks up a tool's full merged record (both `tools` and
    `tool_metadata`) in data.json's top-level `tools` array by id, not from
    this context file -- see the module docstring."""
    return [e["id"] for e in entries if e.get("id")]


def build_context(data: dict) -> list:
    rows = []
    for p in data.get("problems", []):
        rows.append(
            {
                "rq_no": p.get("rq_no", ""),
                "question": p.get("question", ""),
                "capacity": p.get("capacity", ""),
                "target": p.get("target", ""),
                "problem_area": p.get("problem_area", ""),
                "tools_implement": tool_ids(p.get("tools_implement", [])),
                "tools_eval": tool_ids(p.get("tools_eval", [])),
            }
        )
    rows.sort(key=lambda r: rq_sort_key(r["rq_no"]))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data", default="site/data.json", help="path to a built site/data.json"
    )
    parser.add_argument("--out", default="curation/rq_context.json", help="output path")
    args = parser.parse_args()

    data_path = Path(args.data)
    if not data_path.exists():
        raise SystemExit(
            f"{data_path} not found. Run `python build.py` first to produce it "
            "(it fetches the live sheets and writes site/data.json)."
        )

    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    rows = build_context(data)
    if not rows:
        print(f"warning: no problems found in {data_path}", file=sys.stderr)

    out = {
        "generated_from": str(data_path),
        "source_generated_at": data.get("generated_at", ""),
        "rq_count": len(rows),
        "research_questions": rows,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    mapped = sum(1 for r in rows if r["tools_implement"] or r["tools_eval"])
    print(
        f"wrote {len(rows)} research question(s) to {out_path} ({mapped} already have tools)"
    )


if __name__ == "__main__":
    main()
