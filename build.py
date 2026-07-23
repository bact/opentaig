#!/usr/bin/env python3
"""Build script for OpenTAIG.

Generates a static site from TWO decoupled Google Sheets, joined by research
question number (RQ_No):

  * "taig"    -- upstream TAIG paper data (question text + taxonomy +
                 citations + expertise). The spine of the site.
  * "mapping" -- our framework/regulation mappings + tool ids, keyed by RQ_No.
  * "tools"   -- our open-source tool catalog (a tab in the mapping sheet).

Renders the site with Jinja2. Designed to run once per generation (manually,
or on a schedule via GitHub Actions) -- there are no runtime calls back to the
sheets.

Usage:
    python build.py [--config config.yaml] [--frameworks frameworks.yaml]

For local development without network access, set a `file:` path under any
`data.*` source in config.yaml to read from a local CSV instead of fetching
from Google Sheets.
"""
from __future__ import annotations

import argparse
import csv
import dataclasses
import datetime
import hashlib
import io
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Optional

import requests
import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

UNMAPPED_TOKENS = {"", "unmapped", "n/a", "none"}


# --------------------------------------------------------------------------
# Data model
# --------------------------------------------------------------------------

@dataclasses.dataclass
class Tool:
    id: str
    slug: str
    name: str
    summary: str = ""
    license: str = ""
    homepage: str = ""
    source: str = ""
    documentation: str = ""
    funding: str = ""


@dataclasses.dataclass
class Problem:
    slug: str
    rq_no: str
    question: str
    capacity: str
    target: str
    problem_area: str
    section_number: str
    mappings: dict  # facet_key -> list[str] (5 frameworks + "expertise")
    existing_work: list  # list[str]
    new_work: list  # list[str]
    tools: list  # list[Tool]
    order: int


# --------------------------------------------------------------------------
# Loading config / data
# --------------------------------------------------------------------------

def load_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def clean(value: Optional[str]) -> str:
    """Strip surrounding whitespace and collapse stray newlines that Google
    Sheets sometimes leaves inside a cell (e.g. "Data\n")."""
    if value is None:
        return ""
    return " ".join(value.split()).strip()


def fetch_source(source_cfg: dict, label: str, warnings: list) -> str:
    """Return CSV text for a data source, preferring a local `file` override."""
    file_path = source_cfg.get("file")
    if file_path:
        p = Path(file_path)
        print(f"[data] {label}: reading local file {p}")
        with open(p, "r", encoding="utf-8-sig") as f:
            return f.read()

    sheet_id = source_cfg["sheet_id"]
    gid = source_cfg.get("gid", 0)
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
    print(f"[data] {label}: fetching {url}")
    last_err = None
    for attempt in range(1, 4):
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            resp.encoding = "utf-8-sig"
            return resp.text
        except requests.RequestException as e:  # pragma: no cover - network
            last_err = e
            print(f"[data] {label}: attempt {attempt} failed ({e})", file=sys.stderr)
    raise SystemExit(
        f"Failed to fetch {label} from {url} after 3 attempts: {last_err}\n"
        "Is the sheet shared as 'Anyone with the link'? Is the gid correct?"
    )


def parse_csv_text(text: str) -> list:
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for row in reader:
        # Strip whitespace from header keys defensively (a stray leading/
        # trailing space in a header cell would otherwise break lookups).
        rows.append({(k or "").strip(): v for k, v in row.items()})
    return rows


# --------------------------------------------------------------------------
# Cell parsing
# --------------------------------------------------------------------------

def greedy_vocab_match(raw: str, vocab: list) -> tuple:
    """Greedily match known terms (longest first) at the start of `raw`,
    consuming a following comma/space between matches. Returns
    (matched_terms, leftover_text)."""
    vocab_sorted = sorted(vocab, key=len, reverse=True)
    remaining = raw.strip()
    matched = []
    changed = True
    while remaining and changed:
        changed = False
        for term in vocab_sorted:
            if remaining.startswith(term):
                matched.append(term)
                remaining = remaining[len(term):].lstrip(" ,")
                changed = True
                break
    return matched, remaining


def split_multi(raw: Optional[str], vocab: Optional[list], warnings: list, context: str) -> list:
    """Split a framework mapping cell into a list of terms.

    Primary format: semicolon-separated values. Fallback: comma-separated
    legacy cells are parsed via longest-match against `vocab` (if supplied),
    since canonical terms may themselves contain commas (e.g.
    "Article 15 (Accuracy, robustness and cybersecurity)").
    """
    if raw is None:
        return []
    raw = raw.strip()
    if raw.lower() in UNMAPPED_TOKENS:
        return []

    if ";" in raw:
        parts = [p.strip() for p in raw.split(";")]
        return [p for p in parts if p and p.lower() not in UNMAPPED_TOKENS]

    if "," in raw:
        if vocab:
            matched, leftover = greedy_vocab_match(raw, vocab)
            leftover = leftover.strip(" ,")
            if leftover:
                warnings.append(
                    f"{context}: could not fully match comma-separated cell against known "
                    f"vocabulary; leftover={leftover!r} raw={raw!r}. Consider switching this "
                    f"cell to semicolon-separated values."
                )
                matched.extend(p.strip() for p in leftover.split(",") if p.strip())
            return [t for t in matched if t.lower() not in UNMAPPED_TOKENS]
        warnings.append(
            f"{context}: comma-separated cell with no vocabulary fallback available "
            f"(raw={raw!r}); splitting naively on comma, which may break multi-word terms."
        )
        return [p.strip() for p in raw.split(",") if p.strip() and p.strip().lower() not in UNMAPPED_TOKENS]

    return [raw]


def split_simple_list(raw: Optional[str]) -> list:
    """Split a cell on either ';' or ',' -- for values whose individual terms
    have no internal punctuation (e.g. expertise tags like 'ML Theory')."""
    if raw is None:
        return []
    raw = raw.strip()
    if raw.lower() in UNMAPPED_TOKENS:
        return []
    parts = re.split(r"[;,]", raw)
    return [p.strip() for p in parts if p.strip() and p.strip().lower() not in UNMAPPED_TOKENS]


def split_semicolon(raw: Optional[str]) -> list:
    """Split a cell on ';' only -- for citation lists where commas appear
    inside individual author lists (e.g. 'Li et al., 2024; Wei et al., 2024')."""
    if raw is None:
        return []
    raw = raw.strip()
    if raw.lower() in UNMAPPED_TOKENS:
        return []
    return [p.strip() for p in raw.split(";") if p.strip()]


def parse_tool_ids(raw: Optional[str], warnings: list, context: str) -> list:
    if raw is None:
        return []
    raw = raw.strip()
    if raw.lower() in UNMAPPED_TOKENS:
        return []
    parts = raw.split(";") if ";" in raw else raw.split(",")
    return [p.strip() for p in parts if p.strip()]


# --------------------------------------------------------------------------
# Slugs
# --------------------------------------------------------------------------

_slug_re = re.compile(r"[^a-z0-9]+")


def slugify(text: str, max_len: int = 60) -> str:
    base = _slug_re.sub("-", text.strip().lower()).strip("-")
    base = base[:max_len].rstrip("-")
    return base or "item"


def stable_slug(text: str) -> str:
    """Slug + short stable hash suffix, so two problems that reduce to the
    same slug prefix never collide, and the URL stays stable across builds."""
    h = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
    return f"{slugify(text)}-{h}"


def safe_id_for_path(tool_id: str) -> str:
    return _slug_re.sub("-", tool_id.strip().lower()).strip("-") or "tool"


# --------------------------------------------------------------------------
# Build tool catalog
# --------------------------------------------------------------------------

def build_tool_catalog(rows: list, colmap: dict, warnings: list) -> dict:
    catalog = {}
    for i, row in enumerate(rows):
        raw_id = (row.get(colmap["id"]) or "").strip()
        if not raw_id:
            continue
        if raw_id in catalog:
            warnings.append(f"tools row {i + 2}: duplicate tool id {raw_id!r}, overwriting earlier entry")
        catalog[raw_id] = Tool(
            id=raw_id,
            slug=safe_id_for_path(raw_id),
            name=(row.get(colmap["name"]) or "").strip() or raw_id,
            summary=(row.get(colmap["summary"]) or "").strip(),
            license=(row.get(colmap["license"]) or "").strip(),
            homepage=(row.get(colmap["homepage"]) or "").strip(),
            source=(row.get(colmap["source"]) or "").strip(),
            documentation=(row.get(colmap["documentation"]) or "").strip(),
            funding=(row.get(colmap["funding"]) or "").strip(),
        )
    return catalog


# --------------------------------------------------------------------------
# Build mapping index (RQ_No -> our annotations)
# --------------------------------------------------------------------------

def build_mapping_index(rows: list, colmap: dict, framework_defs: list, vocab: dict, warnings: list) -> dict:
    """Return {rq_no: {fw_key: [...], ..., "tool_ids": [...]}} from the mapping
    tab. The mapping tab's own question-text column is intentionally ignored."""
    index = {}
    for i, row in enumerate(rows):
        rq_no = (row.get(colmap["rq_no"]) or "").strip()
        if not rq_no:
            # A wholly blank trailing row is common in exports; only warn if the
            # row actually carries mapping content that will be silently lost.
            has_content = any((row.get(fw["column"]) or "").strip() for fw in framework_defs) or \
                (row.get(colmap["tools"]) or "").strip()
            if has_content:
                warnings.append(f"mapping row {i + 2}: blank RQ_No but has mapping content; row ignored")
            continue
        if rq_no in index:
            warnings.append(f"mapping row {i + 2}: duplicate RQ_No {rq_no!r}, keeping last")
        entry = {}
        for fw in framework_defs:
            raw = row.get(fw["column"])
            context = f"mapping RQ {rq_no} [{fw['column']}]"
            entry[fw["key"]] = split_multi(raw, vocab.get(fw["key"]), warnings, context)
        entry["tool_ids"] = parse_tool_ids(row.get(colmap["tools"]), warnings, f"mapping RQ {rq_no} [Tools]")
        index[rq_no] = entry
    return index


# --------------------------------------------------------------------------
# Build problems (TAIG sheet is the spine)
# --------------------------------------------------------------------------

def build_problems(
    taig_rows: list,
    colmap: dict,
    framework_defs: list,
    expertise_key: str,
    mapping_index: dict,
    tool_catalog: dict,
    uncategorized_label: str,
    warnings: list,
) -> list:
    problems = []
    seen_slugs = {}
    used_rqnos = set()

    for i, row in enumerate(taig_rows):
        question = clean(row.get(colmap["question"]))
        if not question:
            continue

        rq_no = clean(row.get(colmap["question_number"]))
        capacity = clean(row.get(colmap["capacity"])) or uncategorized_label
        target = clean(row.get(colmap["target"])) or uncategorized_label
        problem_area = clean(row.get(colmap["problem_area"])) or uncategorized_label
        section_number = clean(row.get(colmap["section_number"]))
        existing_work = split_semicolon(row.get(colmap["existing_work"]))
        new_work = split_semicolon(row.get(colmap["new_work"]))
        expertise = split_simple_list(row.get(colmap["relevant_expertise"]))

        mapping = mapping_index.get(rq_no) if rq_no else None
        if mapping is not None:
            used_rqnos.add(rq_no)

        mappings = {}
        for fw in framework_defs:
            mappings[fw["key"]] = (mapping or {}).get(fw["key"], [])
        mappings[expertise_key] = expertise

        tool_ids = (mapping or {}).get("tool_ids", [])
        tools = []
        for tid in tool_ids:
            tool = tool_catalog.get(tid)
            if tool is None:
                warnings.append(
                    f"RQ {rq_no}: tool id {tid!r} not found in the Tools tab "
                    f"(check for typos or a missing catalog entry)"
                )
                continue
            tools.append(tool)

        slug = stable_slug(question)
        if slug in seen_slugs:
            warnings.append(f"TAIG row {i + 2}: slug collision with row {seen_slugs[slug]} (duplicate question?)")
        seen_slugs[slug] = i + 2

        problems.append(
            Problem(
                slug=slug,
                rq_no=rq_no,
                question=question,
                capacity=capacity,
                target=target,
                problem_area=problem_area,
                section_number=section_number,
                mappings=mappings,
                existing_work=existing_work,
                new_work=new_work,
                tools=tools,
                order=i,
            )
        )

    # Surface orphaned annotations: mapping rows whose RQ_No matched no TAIG row.
    for rq_no in mapping_index:
        if rq_no not in used_rqnos:
            warnings.append(
                f"mapping RQ {rq_no!r}: no matching row in the TAIG sheet "
                f"(orphaned annotation -- typo, or question removed/renumbered upstream)"
            )
    return problems


# --------------------------------------------------------------------------
# Grouping / indexes
# --------------------------------------------------------------------------

def ordered_present(values_present: set, configured_order: list, uncategorized_label: str) -> list:
    ordered = [v for v in configured_order if v in values_present]
    extras = sorted(v for v in values_present if v not in configured_order and v != uncategorized_label)
    ordered.extend(extras)
    if uncategorized_label in values_present:
        ordered.append(uncategorized_label)
    return ordered


def order_by_first_appearance(problems: list) -> list:
    """Problem-area names in the order they first appear in the (section-
    ordered) TAIG sheet."""
    first = {}
    for p in sorted(problems, key=lambda p: p.order):
        first.setdefault(p.problem_area, p.order)
    return sorted(first, key=lambda name: first[name])


def group_by_taxonomy(problems: list, capacities_order: list, targets_order: list, uncategorized_label: str) -> list:
    """Capacity -> Target -> Problem Area -> [problems]."""
    capacities_present = {p.capacity for p in problems}
    cap_order = ordered_present(capacities_present, capacities_order, uncategorized_label)

    groups = []
    for cap in cap_order:
        cap_problems = [p for p in problems if p.capacity == cap]
        targets_present = {p.target for p in cap_problems}
        tgt_order = ordered_present(targets_present, targets_order, uncategorized_label)
        target_groups = []
        for tgt in tgt_order:
            tgt_problems = [p for p in cap_problems if p.target == tgt]
            area_groups = []
            for area in order_by_first_appearance(tgt_problems):
                area_problems = sorted(
                    (p for p in tgt_problems if p.problem_area == area), key=lambda p: p.order
                )
                area_groups.append({"name": area, "problems": area_problems, "count": len(area_problems)})
            target_groups.append({"name": tgt, "areas": area_groups, "count": len(tgt_problems)})
        groups.append({"name": cap, "targets": target_groups, "count": len(cap_problems)})
    return groups


def build_tools_index(problems: list, tool_catalog: dict) -> list:
    usage = {tid: [] for tid in tool_catalog}
    for p in problems:
        for t in p.tools:
            usage.setdefault(t.id, [])
            usage[t.id].append(p)
    entries = [{"tool": tool, "problems": usage.get(tid, [])} for tid, tool in tool_catalog.items()]
    entries.sort(key=lambda e: e["tool"].name.lower())
    return entries


def build_frameworks_index(problems: list, framework_defs: list) -> tuple:
    """fw_key -> {term: {"problems": [...], "slug": str}}, in first-appearance
    order. Only the regulatory frameworks get browse pages -- expertise does
    not (it is filter + chips only)."""
    index = {}
    term_slugs = {}
    for fw in framework_defs:
        key = fw["key"]
        terms = {}
        used_slugs = set()
        for p in problems:
            for term in p.mappings.get(key, []):
                if term not in terms:
                    base = slugify(term, max_len=50)
                    s, n = base, 2
                    while s in used_slugs:
                        s = f"{base}-{n}"
                        n += 1
                    used_slugs.add(s)
                    terms[term] = {"slug": s, "problems": []}
                terms[term]["problems"].append(p)
        index[key] = terms
        term_slugs[key] = {term: data["slug"] for term, data in terms.items()}
    return index, term_slugs


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

def problem_to_public_dict(p: Problem) -> dict:
    return {
        "slug": p.slug,
        "rq_no": p.rq_no,
        "question": p.question,
        "capacity": p.capacity,
        "target": p.target,
        "problem_area": p.problem_area,
        "section_number": p.section_number,
        "mappings": p.mappings,
        "existing_work": p.existing_work,
        "new_work": p.new_work,
        "tools": [{"id": t.id, "name": t.name, "homepage": t.homepage} for t in p.tools],
    }


def render_site(
    out_dir: Path,
    config: dict,
    framework_defs: list,
    expertise_def: dict,
    facet_defs: list,
    problems: list,
    groups: list,
    tool_catalog: dict,
    tools_index: list,
    frameworks_index: dict,
    term_slugs: dict,
    warnings: list,
    generated_at: str,
) -> None:
    templates_dir = Path(__file__).parent / "templates"
    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )

    expertise_key = expertise_def["key"]
    facet_terms = {}
    for key, terms in frameworks_index.items():
        facet_terms[key] = sorted(terms.keys(), key=str.lower)
    expertise_terms = sorted({t for p in problems for t in p.mappings.get(expertise_key, [])}, key=str.lower)
    facet_terms[expertise_key] = expertise_terms

    capacities_list = [g["name"] for g in groups]
    targets_present = {p.target for p in problems}
    targets_list = ordered_present(
        targets_present, config["taxonomy"]["targets"], config["taxonomy"]["uncategorized_label"]
    )

    site_ctx = {
        "site": config["site"],
        "generated_at": generated_at,
        "frameworks": framework_defs,
        "expertise": expertise_def,
        "facets": facet_defs,
        "term_slugs": term_slugs,
        "facet_terms": facet_terms,
        "capacities_list": capacities_list,
        "targets_list": targets_list,
        "problem_count": len(problems),
        "tool_count": len(tool_catalog),
    }

    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    (out_dir / "problems").mkdir()
    (out_dir / "tools").mkdir()
    (out_dir / "frameworks").mkdir()
    for fw in framework_defs:
        (out_dir / "frameworks" / fw["key"]).mkdir()

    def write(path: Path, template_name: str, **ctx):
        tmpl = env.get_template(template_name)
        path.write_text(tmpl.render(**site_ctx, **ctx), encoding="utf-8")

    write(out_dir / "index.html", "index.html", root="", groups=groups, active="home")

    for p in problems:
        write(out_dir / "problems" / f"{p.slug}.html", "problem.html", root="../", problem=p, active="problem")

    write(out_dir / "tools" / "index.html", "tools_index.html", root="../", entries=tools_index, active="tools")
    for entry in tools_index:
        tool = entry["tool"]
        write(
            out_dir / "tools" / f"{tool.slug}.html",
            "tool.html",
            root="../",
            tool=tool,
            problems=entry["problems"],
            active="tools",
        )

    write(
        out_dir / "frameworks" / "index.html",
        "frameworks_index.html",
        root="../",
        frameworks_index=frameworks_index,
        active="frameworks",
    )
    for fw in framework_defs:
        for term, data in frameworks_index.get(fw["key"], {}).items():
            write(
                out_dir / "frameworks" / fw["key"] / f"{data['slug']}.html",
                "framework_term.html",
                root="../../",
                framework=fw,
                term=term,
                problems=data["problems"],
                active="frameworks",
            )

    data_json = {
        "generated_at": generated_at,
        "problems": [problem_to_public_dict(p) for p in problems],
        "tools": [dataclasses.asdict(t) for t in tool_catalog.values()],
    }
    (out_dir / "data.json").write_text(json.dumps(data_json, indent=2), encoding="utf-8")

    shutil.copytree(Path(__file__).parent / "assets", out_dir / "assets")
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")

    if warnings:
        print(f"\n[build] {len(warnings)} warning(s):", file=sys.stderr)
        for w in warnings:
            print(f"  - {w}", file=sys.stderr)


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--frameworks", default="frameworks.yaml")
    args = parser.parse_args()

    config = load_yaml(Path(args.config))
    vocab = load_yaml(Path(args.frameworks)) or {}
    warnings: list = []

    taig_csv = fetch_source(config["data"]["taig"], "taig", warnings)
    mapping_csv = fetch_source(config["data"]["mapping"], "mapping", warnings)
    tools_csv = fetch_source(config["data"]["tools"], "tools", warnings)

    taig_rows = parse_csv_text(taig_csv)
    mapping_rows = parse_csv_text(mapping_csv)
    tools_rows = parse_csv_text(tools_csv)

    colmap = config["columns"]
    framework_defs = config["frameworks"]
    expertise_def = config["expertise"]
    expertise_key = expertise_def["key"]
    facet_defs = list(framework_defs) + [expertise_def]

    tool_catalog = build_tool_catalog(tools_rows, colmap["tools"], warnings)
    mapping_index = build_mapping_index(mapping_rows, colmap["mapping"], framework_defs, vocab, warnings)

    problems = build_problems(
        taig_rows,
        colmap["taig"],
        framework_defs,
        expertise_key,
        mapping_index,
        tool_catalog,
        config["taxonomy"]["uncategorized_label"],
        warnings,
    )

    if not problems:
        raise SystemExit(
            "No problems parsed from the TAIG sheet. Check that it has a "
            f"'{colmap['taig']['question']}' column with data and that the gid in "
            "config.yaml points at the right tab."
        )

    groups = group_by_taxonomy(
        problems,
        config["taxonomy"]["capacities"],
        config["taxonomy"]["targets"],
        config["taxonomy"]["uncategorized_label"],
    )
    tools_index = build_tools_index(problems, tool_catalog)
    frameworks_index, term_slugs = build_frameworks_index(problems, framework_defs)

    generated_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    out_dir = Path(config["output_dir"])
    render_site(
        out_dir,
        config,
        framework_defs,
        expertise_def,
        facet_defs,
        problems,
        groups,
        tool_catalog,
        tools_index,
        frameworks_index,
        term_slugs,
        warnings,
        generated_at,
    )

    print(f"\n[build] wrote {len(problems)} problems, {len(tool_catalog)} tools to {out_dir}/")


if __name__ == "__main__":
    main()
