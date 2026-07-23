#!/usr/bin/env python3
"""Build script for OpenTAIG.

Fetches the "Questions" and "Tools" tabs of a Google Sheet as CSV, normalizes
them into a set of open-problem records, and renders a static site with
Jinja2 templates. Designed to be run once per generation (manually, or on a
schedule via GitHub Actions) -- there are no runtime calls back to the sheet.

Usage:
    python build.py [--config config.yaml] [--frameworks frameworks.yaml]

For local development without network access, set a `file:` path under
`data.questions` / `data.tools` in config.yaml to read from a local CSV
instead of fetching from Google Sheets.
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
    question: str
    capacity: str
    target: str
    mappings: dict  # fw_key -> list[str]
    tools: list  # list[Tool]
    order: int


# --------------------------------------------------------------------------
# Loading config / data
# --------------------------------------------------------------------------

def load_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def fetch_source(source_cfg: dict, sheet_id: str, label: str, warnings: list) -> str:
    """Return CSV text for a data source, preferring a local `file` override."""
    file_path = source_cfg.get("file")
    if file_path:
        p = Path(file_path)
        print(f"[data] {label}: reading local file {p}")
        with open(p, "r", encoding="utf-8-sig") as f:
            return f.read()

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
        # Strip whitespace from header keys defensively (Google Sheets export
        # is well-behaved here, but stray leading/trailing spaces in a header
        # cell would otherwise silently break column lookups).
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
    """Split a mapping cell into a list of terms.

    Primary format: semicolon-separated values, e.g.
      "Robust, Reliable & Safe; Transparent & Explainable"
    Fallback: comma-separated legacy cells are parsed via longest-match
    against `vocab` (if supplied), since canonical terms may themselves
    contain commas.
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


def parse_tool_ids(raw: Optional[str], warnings: list, context: str) -> list:
    if raw is None:
        return []
    raw = raw.strip()
    if raw.lower() in UNMAPPED_TOKENS:
        return []
    if ";" in raw:
        parts = raw.split(";")
    else:
        parts = raw.split(",")
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
# Build problems
# --------------------------------------------------------------------------

def load_seed_taxonomy(path: Optional[Path]) -> dict:
    if not path or not path.exists():
        return {}
    seed = {}
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            q = (row.get("question") or "").strip()
            if not q:
                continue
            seed[q] = {
                "capacity": (row.get("capacity") or "").strip(),
                "target": (row.get("target") or "").strip(),
            }
    return seed


def build_problems(
    rows: list,
    colmap: dict,
    framework_defs: list,
    vocab: dict,
    tool_catalog: dict,
    seed_taxonomy: dict,
    uncategorized_label: str,
    warnings: list,
) -> list:
    problems = []
    seen_slugs = {}
    for i, row in enumerate(rows):
        question = (row.get(colmap["question"]) or "").strip()
        if not question:
            continue

        capacity = (row.get(colmap["capacity"]) or "").strip()
        target = (row.get(colmap["target"]) or "").strip()
        if not capacity or not target:
            seed = seed_taxonomy.get(question)
            if seed:
                capacity = capacity or seed.get("capacity", "")
                target = target or seed.get("target", "")
        capacity = capacity or uncategorized_label
        target = target or uncategorized_label

        mappings = {}
        for fw in framework_defs:
            raw = row.get(fw["column"])
            context = f"questions row {i + 2} [{fw['column']}]"
            mappings[fw["key"]] = split_multi(raw, vocab.get(fw["key"]), warnings, context)

        tool_ids = parse_tool_ids(row.get(colmap["tools"]), warnings, f"questions row {i + 2} [Tools]")
        tools = []
        for tid in tool_ids:
            tool = tool_catalog.get(tid)
            if tool is None:
                warnings.append(
                    f"questions row {i + 2}: tool id {tid!r} not found in the Tools tab "
                    f"(check for typos or a missing catalog entry)"
                )
                continue
            tools.append(tool)

        slug = stable_slug(question)
        if slug in seen_slugs:
            warnings.append(f"questions row {i + 2}: slug collision with row {seen_slugs[slug]} (duplicate question?)")
        seen_slugs[slug] = i + 2

        problems.append(
            Problem(
                slug=slug,
                question=question,
                capacity=capacity,
                target=target,
                mappings=mappings,
                tools=tools,
                order=i,
            )
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


def group_by_taxonomy(problems: list, capacities_order: list, targets_order: list, uncategorized_label: str) -> list:
    capacities_present = {p.capacity for p in problems}
    cap_order = ordered_present(capacities_present, capacities_order, uncategorized_label)

    groups = []
    for cap in cap_order:
        cap_problems = [p for p in problems if p.capacity == cap]
        targets_present = {p.target for p in cap_problems}
        tgt_order = ordered_present(targets_present, targets_order, uncategorized_label)
        subgroups = []
        for tgt in tgt_order:
            sub_problems = sorted((p for p in cap_problems if p.target == tgt), key=lambda p: p.order)
            subgroups.append({"name": tgt, "problems": sub_problems, "count": len(sub_problems)})
        groups.append({"name": cap, "subgroups": subgroups, "count": len(cap_problems)})
    return groups


def build_tools_index(problems: list, tool_catalog: dict) -> list:
    usage = {tid: [] for tid in tool_catalog}
    for p in problems:
        for t in p.tools:
            usage.setdefault(t.id, [])
            usage[t.id].append(p)
    entries = []
    for tid, tool in tool_catalog.items():
        entries.append({"tool": tool, "problems": usage.get(tid, [])})
    entries.sort(key=lambda e: e["tool"].name.lower())
    return entries


def build_frameworks_index(problems: list, framework_defs: list) -> dict:
    """fw_key -> {term: {"problems": [...], "slug": str}}, insertion-ordered by first appearance."""
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
                    s = base
                    n = 2
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
        "question": p.question,
        "capacity": p.capacity,
        "target": p.target,
        "mappings": p.mappings,
        "tools": [{"id": t.id, "name": t.name, "homepage": t.homepage} for t in p.tools],
    }


def render_site(
    out_dir: Path,
    config: dict,
    framework_defs: list,
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

    facet_terms = {key: sorted(terms.keys(), key=str.lower) for key, terms in frameworks_index.items()}
    capacities_list = [g["name"] for g in groups]
    targets_present = {p.target for p in problems}
    targets_list = ordered_present(
        targets_present, config["taxonomy"]["targets"], config["taxonomy"]["uncategorized_label"]
    )

    site_ctx = {
        "site": config["site"],
        "generated_at": generated_at,
        "frameworks": framework_defs,
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

    # Home
    write(out_dir / "index.html", "index.html", root="", groups=groups, active="home")

    # Problem detail pages
    for p in problems:
        write(out_dir / "problems" / f"{p.slug}.html", "problem.html", root="../", problem=p, active="problem")

    # Tools
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

    # Frameworks
    write(
        out_dir / "frameworks" / "index.html",
        "frameworks_index.html",
        root="../",
        frameworks_index=frameworks_index,
        active="frameworks",
    )
    for fw in framework_defs:
        key = fw["key"]
        for term, data in frameworks_index.get(key, {}).items():
            write(
                out_dir / "frameworks" / key / f"{data['slug']}.html",
                "framework_term.html",
                root="../../",
                framework=fw,
                term=term,
                problems=data["problems"],
                active="frameworks",
            )

    # data.json (baked snapshot, not required by app.js but kept for reuse/transparency)
    data_json = {
        "generated_at": generated_at,
        "problems": [problem_to_public_dict(p) for p in problems],
        "tools": [dataclasses.asdict(t) for t in tool_catalog.values()],
    }
    (out_dir / "data.json").write_text(json.dumps(data_json, indent=2), encoding="utf-8")

    # Static assets
    assets_src = Path(__file__).parent / "assets"
    shutil.copytree(assets_src, out_dir / "assets")

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

    sheet_id = config["data"]["sheet_id"]
    questions_csv = fetch_source(config["data"]["questions"], sheet_id, "questions", warnings)
    tools_csv = fetch_source(config["data"]["tools"], sheet_id, "tools", warnings)

    questions_rows = parse_csv_text(questions_csv)
    tools_rows = parse_csv_text(tools_csv)

    colmap = config["columns"]
    tool_catalog = build_tool_catalog(tools_rows, colmap["tools"], warnings)

    seed_path = config["taxonomy"].get("seed_file")
    seed_taxonomy = load_seed_taxonomy(Path(seed_path) if seed_path else None)

    framework_defs = config["frameworks"]
    problems = build_problems(
        questions_rows,
        colmap["questions"],
        framework_defs,
        vocab,
        tool_catalog,
        seed_taxonomy,
        config["taxonomy"]["uncategorized_label"],
        warnings,
    )

    if not problems:
        raise SystemExit(
            "No problems parsed from the Questions tab. Check that the sheet has a "
            f"'{colmap['questions']['question']}' column with data, and that the gid in "
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
