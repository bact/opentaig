#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2026 OpenTAIG authors
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Emit the three pasteable CSVs that add the AIAAIC Harms Taxonomy to
the site as a sixth framework.

The site already has the machinery for this: `frameworks:` in config.yaml is a
list of {key, column}, term definitions live in the `terms` tab, framework
metadata in the `framework` tab, and per-RQ mappings in the `map` tab. Adding a
framework is therefore a data change plus four lines of config -- **no code
changes**. This script emits the data half, reading the column headers straight
out of config.yaml so the output pastes in without reformatting.

Outputs (all in curation/, gitignored -- unlike candidate_tools.csv /
candidate_map_updates.csv, these carry no agent judgment of their own, only a
deterministic projection of aiaaic_taxonomy_mapping.py's MAPPING data through
config.yaml's column headers. Delete freely; re-run this script to regenerate
byte-for-byte, modulo the timestamp columns):
  - candidate_framework_aiaaic.csv  -> 1 row for the `framework` tab
  - candidate_terms_aiaaic.csv      -> N rows for the `terms` tab
  - candidate_map_aiaaic.csv        -> 97 rows: rq_no + the new `aiaaic` column

This is a one-time addition (the taxonomy has 9 harm types, not an ongoing
curation feed), already merged into the live sheet as of 2026-07-29. Re-run
only if the mapping in aiaaic_taxonomy_mapping.py changes, the RQ catalog
changes, or you switch `--granularity`/`--include`.

Then in config.yaml, under `frameworks:`, add:

    - key: aiaaic
      column: "aiaaic"

Granularity (`--granularity`):
  type      (default) the 9 top-level harm types. Recommended: this is the
            level the RQ->harm judgment is actually defensible at, and it
            keeps the chip row readable.
  specific  all 69 specific harms. Sharper, but the specific harms in the
            mapping were chosen as *illustrations* of why a type applies, not
            as an exhaustive per-harm claim -- don't publish at this level
            without re-reviewing each row.

Scope (`--include`):
  qualified (default) every RQ gets at least one chip, and the direct/enabling
            distinction survives via two sentinel terms. A blank cell would be
            read as "no harm identified", which is wrong for two different
            reasons at once: 11 RQs are genuinely method-level, while 34 have
            harms mapped but only as enabling infrastructure. So:
              - direct RQs      -> harm type chips alone
              - enabling RQs    -> harm type chips + `aiaaic-indirect`
              - cross-cutting   -> `aiaaic-crosscutting` alone
  direct    only direct harm chips; enabling RQs collapse to `aiaaic-indirect`
            and cross-cutting ones to `aiaaic-crosscutting`.
  all       direct and enabling harms chipped identically, no qualifier. Loses
            the distinction -- implies an RQ targets a harm it only supports.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import importlib.util
import json
from pathlib import Path

import yaml

HARM_TYPE_DEFS = {
    "Autonomy": "Loss of or restrictions to the ability or rights of an individual, group or entity to make decisions and control their identity and/or output.",
    "Physical": "Physical injury to an individual or group, or damage to physical property.",
    "Psychological": "Direct or indirect impairment of the emotional and psychological mental health of an individual, organisation, or society.",
    "Reputational": "Damage to the reputation of an individual, group or organisation.",
    "Financial and Business": "Use or misuse of a technology system in a manner that damages the financial interests of an individual or group, or which causes strategic, operational, legal or financial harm to a business or other organisation.",
    "Human Rights and Civil Liberties": "Use or misuse of a technology system in a manner that compromises fundamental human rights and freedoms.",
    "Societal and Cultural": "Harms affecting the functioning of societies, communities and economies caused directly or indirectly by the use or misuse technology systems.",
    "Political and Economic": "Manipulation of political beliefs, damage to political institutions and the effective delivery of government services.",
    "Environmental": "Damage to the environment directly or indirectly caused by a technology system or set of systems.",
}

TYPE_SLUG = {
    "Autonomy": "autonomy",
    "Physical": "physical",
    "Psychological": "psychological",
    "Reputational": "reputational",
    "Financial and Business": "financial",
    "Human Rights and Civil Liberties": "humanrights",
    "Societal and Cultural": "societal",
    "Political and Economic": "political",
    "Environmental": "environmental",
}

# Sentinel terms -- not harm types, but needed so a blank map cell never has
# to be read as "no harm identified" when the real state is "not judged" or
# "supports addressing a harm without targeting it". Rendered as chips with
# their own distinct styling (see .chip-aiaaic-indirect etc. in style.css) so
# they read visually as different in kind from a harm-type chip, not just a
# 10th harm type.
SENTINEL_DEFS = {
    "crosscutting": (
        "Cross-cutting (method-level)",
        "This question is about a research method or evaluation property "
        "(e.g. measurement thoroughness, mechanistic understanding) that "
        "applies regardless of which harm is being investigated -- not "
        "mapped to a specific harm type.",
    ),
    "indirect": (
        "Supports harm mitigation (indirect)",
        "This question provides infrastructure, methodology, or verification "
        "capability that a harm-mitigation effort would need, without itself "
        "targeting the harm(s) shown here. Distinguished from a direct "
        "mapping so 'this RQ has a harm chip' is not read as 'this RQ's "
        "own text is about that harm.'",
    ),
}

PAPER_URL = "https://arxiv.org/abs/2407.01294"


def slugify(text: str) -> str:
    out = []
    for ch in text.lower():
        out.append(ch if ch.isalnum() else "-")
    return "-".join(p for p in "".join(out).split("-") if p)


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--granularity", choices=["type", "specific"], default="type")
    ap.add_argument(
        "--include", choices=["qualified", "direct", "all"], default="qualified"
    )
    ap.add_argument("--framework-key", default="aiaaic")
    args = ap.parse_args()

    cfg = yaml.safe_load(open("config.yaml"))
    tcol = cfg["columns"]["terms"]
    fcol = cfg["columns"]["framework"]

    spec = importlib.util.spec_from_file_location(
        "hm", "curation/aiaaic_taxonomy_mapping.py"
    )
    hm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hm)

    ctx = json.load(open("curation/rq_context.json"))["research_questions"]
    rq_order = [r["rq_no"] for r in sorted(ctx, key=lambda r: int(r["rq_no"]))]

    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M")
    key = args.framework_key

    def stamp(row: dict) -> dict:
        for c in ("datetime_added", "datetime_checked", "datetime_updated"):
            if c in tcol:
                row[tcol[c]] = now
        return row

    # ---- framework tab row ------------------------------------------------
    fw_row = {
        fcol["id"]: key,
        fcol["name"]: "AIAAIC Harms Taxonomy",
        fcol["fullname"]: (
            "A Collaborative, Human-Centred Taxonomy of AI, "
            "Algorithmic, and Automation Harms"
        ),
        fcol["summary"]: (
            "Nine harm types and 69 specific harms, developed by an independent working "
            "group via expert consultation and crowdsourced annotation testing over the "
            "AIAAIC Repository. Used here as a coverage-completeness check: each "
            "question's own text is read against each harm's own definition, the same "
            "way the site's other frameworks are crosswalked against an external "
            "authority's own text -- but AIAAIC itself never mapped these specific "
            "research questions, so it's our own crosswalk against their taxonomy, not "
            "an AIAAIC-authored one."
        ),
        fcol["homepage"]: PAPER_URL,
    }
    if "source" in fcol:
        fw_row[fcol["source"]] = PAPER_URL
    for c in ("datetime_added", "datetime_checked", "datetime_updated"):
        if c in fcol:
            fw_row[fcol[c]] = now

    Path("curation/candidate_framework_aiaaic.csv").write_text("")
    with open(
        "curation/candidate_framework_aiaaic.csv", "w", newline="", encoding="utf-8"
    ) as f:
        w = csv.DictWriter(f, fieldnames=list(fw_row))
        w.writeheader()
        w.writerow(fw_row)

    # ---- terms tab rows ---------------------------------------------------
    term_rows = []
    if args.granularity == "type":
        for htype, definition in HARM_TYPE_DEFS.items():
            term_rows.append(
                stamp(
                    {
                        tcol["id"]: f"{key}-{TYPE_SLUG[htype]}",
                        tcol["framework"]: key,
                        tcol["name"]: htype,
                        tcol["summary"]: definition,
                        tcol["url"]: PAPER_URL,
                    }
                )
            )
        if args.include == "qualified":
            for slug, (name, definition) in SENTINEL_DEFS.items():
                term_rows.append(
                    stamp(
                        {
                            tcol["id"]: f"{key}-{slug}",
                            tcol["framework"]: key,
                            tcol["name"]: name,
                            tcol["summary"]: definition,
                            tcol["url"]: "",
                        }
                    )
                )
    else:
        for htype, specifics in hm.TAXONOMY.items():
            for s in specifics:
                term_rows.append(
                    stamp(
                        {
                            tcol["id"]: f"{key}-{TYPE_SLUG[htype]}-{slugify(s)}",
                            tcol["framework"]: key,
                            tcol["name"]: s,
                            tcol["summary"]: f"{htype}: {hm.HARM_DEFINITIONS[s]}",
                            tcol["url"]: PAPER_URL,
                        }
                    )
                )
        if args.include == "qualified":
            for slug, (name, definition) in SENTINEL_DEFS.items():
                term_rows.append(
                    stamp(
                        {
                            tcol["id"]: f"{key}-{slug}",
                            tcol["framework"]: key,
                            tcol["name"]: name,
                            tcol["summary"]: definition,
                            tcol["url"]: "",
                        }
                    )
                )

    with open(
        "curation/candidate_terms_aiaaic.csv", "w", newline="", encoding="utf-8"
    ) as f:
        w = csv.DictWriter(f, fieldnames=list(term_rows[0]))
        w.writeheader()
        w.writerows(term_rows)

    # ---- map tab column ---------------------------------------------------
    # Three states per RQ, matching hm.MAPPING's own kind field:
    #   "direct"    -> harm chips alone (the RQ's text targets this harm)
    #   "enabling"  -> harm chips (--include all|qualified only), qualified
    #                  by `aiaaic-indirect` so it isn't read as a direct claim
    #   no harms    -> `aiaaic-crosscutting` (--include qualified only)
    map_rows = []
    n_direct = n_indirect = n_crosscutting = n_blank = 0
    for rq_no in rq_order:
        kind, harms, _note = hm.MAPPING.get(rq_no, ("unmapped", [], ""))
        ids = []
        if harms and (args.include in ("all", "qualified") or kind == "direct"):
            for htype, specifics in harms:
                if args.granularity == "type":
                    ids.append(f"{key}-{TYPE_SLUG[htype]}")
                else:
                    ids.extend(
                        f"{key}-{TYPE_SLUG[htype]}-{slugify(s)}" for s in specifics
                    )
            if kind == "enabling" and args.include == "qualified":
                ids.append(f"{key}-indirect")
        elif not harms and args.include == "qualified":
            ids.append(f"{key}-crosscutting")

        ids = list(dict.fromkeys(ids))  # de-dup, preserve order
        if not ids:
            n_blank += 1
        elif f"{key}-crosscutting" in ids:
            n_crosscutting += 1
        elif f"{key}-indirect" in ids:
            n_indirect += 1
        else:
            n_direct += 1
        map_rows.append({"rq_no": rq_no, key: ";".join(ids)})

    with open(
        "curation/candidate_map_aiaaic.csv", "w", newline="", encoding="utf-8"
    ) as f:
        w = csv.DictWriter(f, fieldnames=["rq_no", key])
        w.writeheader()
        w.writerows(map_rows)

    print(f"granularity={args.granularity}  include={args.include}")
    print("  framework rows : 1   -> curation/candidate_framework_aiaaic.csv")
    print(
        f"  term rows      : {len(term_rows):<3} -> curation/candidate_terms_aiaaic.csv"
    )
    print(f"  map rows       : {len(map_rows):<3} -> curation/candidate_map_aiaaic.csv")
    print(f"    direct harm chip(s)      : {n_direct}")
    print(f"    indirect (enabling)      : {n_indirect}")
    print(f"    crosscutting sentinel    : {n_crosscutting}")
    print(f"    blank (--include direct only, enabling RQs dropped) : {n_blank}")
    print(
        f'\nThen add to config.yaml under `frameworks:`:\n\n    - key: {key}\n      column: "{key}"'
    )


if __name__ == "__main__":
    main()
