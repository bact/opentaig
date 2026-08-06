#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2026 OpenTAIG authors
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Build script for OpenTAIG.

Generates a static site from THREE decoupled Google Sheets: the upstream
TAIG sheet, joined by research question number (rq_no, the problem number
in the TAIG paper); our own OpenTAIG sheet; and a separate tool_metadata
sheet, joined onto tools by id.

  * "taig"     -- upstream TAIG paper data (question text + taxonomy +
                 citations + expertise). The spine of the site.
  * "mapping"  -- our framework/regulation mappings, keyed by rq_no. Cells
                 hold semicolon-separated ids referencing the "terms"
                 catalog below, not free text.
  * "tool_map" -- our research-question-to-tool mappings: one row per
                 (rq_no, tool_id, role) pairing plus a rationale, rather
                 than a semicolon list, so a tool can answer more than one
                 RQ and each pairing can carry its own explanation.
  * "tools"    -- our open-source tool catalog (a tab in the OpenTAIG
                 sheet). Identity fields (name/license/homepage/...) plus
                 an optional human override for every project-quality/
                 community-health field also in "tool_metadata" below --
                 see apply_tool_metadata()/resolve_metadata_field().
  * "tool_metadata" -- auto-collected project-quality/community-health data
                 per tool (a separate spreadsheet from OpenTAIG, so a future
                 write-automation credential can be scoped to touch only
                 this one), 100% written by
                 curation/collect_project_metadata.py. Joined onto "tools"
                 by id; never hand-edited.
  * "terms"    -- our RGAF/EU_AI_Act/UNESCO/ASEAN/CoE term catalog (a tab in
                 the OpenTAIG sheet), one shared tab across all frameworks,
                 with globally-unique namespaced ids (e.g. `euaiact-a8`).

Renders the site with Jinja2. Designed to run once per generation (manually,
or on a schedule via GitHub Actions) -- there are no runtime calls back to the
sheets.

Usage:
    python build.py [--config config.yaml]

For local development without network access, set a `file:` path under any
`data.*` source in config.yaml to read from a local CSV instead of fetching
from Google Sheets.
"""
from __future__ import annotations

import argparse
import csv
import dataclasses
import datetime
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
class Freshness:
    """Row-level bookkeeping, present on every OUR-owned tab (mapping,
    tool_map, tools, terms, framework): when a row was first added, when it
    was last reviewed for staleness, and when its content last actually
    changed (a review that finds nothing new updates only `checked`, not
    `updated`). Purely informational -- no build logic reads these yet, they
    exist so a future scheduler/crawler can decide what needs re-fetching."""
    added: str = ""
    checked: str = ""
    updated: str = ""


@dataclasses.dataclass
class Tool:
    id: str
    slug: str
    name: str
    tool_type: str = ""
    summary: str = ""
    license: str = ""
    homepage: str = ""
    source: str = ""
    documentation: str = ""
    # `tools`' own freshness -- when this row was discovered/last hand-
    # edited. Distinct from `metadata_freshness` below: the two tabs carry
    # independent datetimes, one for curation, one for auto-collection --
    # never merged into a single value, same reasoning as Problem's
    # `mapping_freshness` staying separate from each RQ's own freshness.
    freshness: Freshness = dataclasses.field(default_factory=Freshness)
    # `tool_metadata`'s own freshness -- when collect_project_metadata.py
    # last (re-)collected this tool. Blank Freshness() if the tool has no
    # tool_metadata row yet (never collected).
    metadata_freshness: Freshness = dataclasses.field(default_factory=Freshness)
    # Every field below is resolved by apply_tool_metadata() from BOTH the
    # `tools` tab (a human override, or the literal token "none" to force
    # blank) and the `tool_metadata` tab (collect_project_metadata.py's
    # output) -- see METADATA_FIELDS / resolve_metadata_field() above.
    # Never set directly by build_tool_catalog(). A collection-time
    # snapshot, not a live value; GitHub-only for now.
    programming_languages: list = dataclasses.field(default_factory=list)  # list[str]
    funding: str = ""
    funder: str = ""
    stars: Optional[int] = None
    forks: Optional[int] = None
    watchers: Optional[int] = None
    contributors: Optional[int] = None
    open_issues_count: Optional[int] = None
    releases_count: Optional[int] = None
    latest_release_date: str = ""
    last_commit_date: str = ""
    readme_url: str = ""
    license_url: str = ""
    code_of_conduct_url: str = ""
    contributing_url: str = ""
    security_policy_url: str = ""
    governance_url: str = ""
    sbom_url: str = ""
    dependents_count: Optional[int] = None  # not auto-collected; manual-entry only
    development_status: str = ""
    paper_url: str = ""
    software_heritage_id: str = ""
    openssf_best_practices_url: str = ""
    openssf_best_practices_badge_level: str = ""
    openssf_scorecard_url: str = ""
    openssf_scorecard_score: Optional[float] = None
    # 0-10; -1 means Scorecard couldn't evaluate that check, not a real
    # score -- see collect_project_metadata.py's docstring.
    openssf_scorecard_branch_protection: Optional[float] = None
    openssf_scorecard_code_review: Optional[float] = None
    openssf_scorecard_maintained: Optional[float] = None
    openssf_scorecard_vulnerabilities: Optional[float] = None


@dataclasses.dataclass
class ToolRationale:
    """A single (tool, why-it-answers-this-RQ) pairing -- one row from the
    tool_map tab, resolved against the tool catalog. Distinct from Tool
    itself because the same Tool can appear under different RQs with a
    different rationale each time, so the rationale can't live on Tool."""
    tool: "Tool"
    rationale: str = ""
    freshness: Freshness = dataclasses.field(default_factory=Freshness)


@dataclasses.dataclass
class Term:
    id: str
    framework: str
    name: str
    summary: str = ""
    url: str = ""
    freshness: Freshness = dataclasses.field(default_factory=Freshness)


@dataclasses.dataclass
class Problem:
    slug: str
    rq_no: str
    question: str
    capacity: str
    target: str
    problem_area: str
    section_number: str
    mappings: dict  # facet_key -> list[Term] (5 frameworks) or list[str] ("expertise")
    existing_work: list  # list[str]
    new_work: list  # list[str]
    tools_implement: list  # list[ToolRationale]
    tools_eval: list  # list[ToolRationale]
    search_text: str  # precomputed lowercased text for the client-side search box
    order: int
    mapping_freshness: Freshness = dataclasses.field(default_factory=Freshness)  # from the `mapping` tab's row for this rq_no


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


def parse_optional_int(value: Optional[str], context: str, warnings: list) -> Optional[int]:
    """Blank -> None (most tools don't have this collected yet); anything
    non-blank that isn't a plain integer is a warning, not a crash -- a
    stray "~1,200" or "N/A" pasted by hand shouldn't break the whole build."""
    text = clean(value)
    if not text:
        return None
    try:
        return int(text.replace(",", ""))
    except ValueError:
        warnings.append(f"{context}: expected an integer, got {text!r} -- ignoring")
        return None


def parse_optional_float(value: Optional[str], context: str, warnings: list) -> Optional[float]:
    text = clean(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        warnings.append(f"{context}: expected a number, got {text!r} -- ignoring")
        return None


# --------------------------------------------------------------------------
# tools / tool_metadata precedence
#
# Every project-quality/community-health field is collectible by
# collect_project_metadata.py into the `tool_metadata` tab, but can also be
# hand-set directly in `tools` -- e.g. to correct a bad auto-collected value,
# or to fill in `dependents_count`, which is never auto-collected at all. One
# uniform rule for all of them, applied per field, not per tool:
#
#   - a non-blank `tools` cell always wins, parsed as that field's own type
#   - the literal token "none" (case-insensitive) in `tools` means
#     "explicitly reviewed and suppressed" -- final value is blank/None,
#     NOT the tool_metadata value. This is what lets a human say "I know the
#     collector found something here, and I want nothing shown" -- an empty
#     `tools` cell alone can't express that, since it's indistinguishable
#     from "never reviewed" and would otherwise just fall through.
#   - a blank `tools` cell (anything else, including truly empty) falls
#     through to `tool_metadata`'s collected value
#
# This makes `tool_metadata` 100% machine-owned -- a collection run can
# safely overwrite the whole tab, since no hand edit ever lives there; every
# override, for any field, always goes in `tools` instead.
METADATA_INT_FIELDS = {"stars", "forks", "watchers", "contributors",
                        "open_issues_count", "releases_count", "dependents_count"}
METADATA_FLOAT_FIELDS = {"openssf_scorecard_score", "openssf_scorecard_branch_protection",
                          "openssf_scorecard_code_review", "openssf_scorecard_maintained",
                          "openssf_scorecard_vulnerabilities"}
METADATA_LIST_FIELDS = {"programming_language"}  # semicolon list; resolved as a whole raw string, split by the caller
NONE_TOKEN = "none"

# Every project-quality/community-health field, in the order they're laid
# out in both the `tools` and `tool_metadata` tabs. Deliberately excludes
# identity columns (id, tool_type, name, summary, license, homepage, source,
# documentation) and freshness columns, which are `tools`-only with no
# tool_metadata counterpart or precedence logic.
METADATA_FIELDS = [
    "programming_language", "funding", "funder",
    "stars", "forks", "watchers", "contributors",
    "last_commit_date", "open_issues_count", "releases_count", "latest_release_date",
    "readme_url", "license_url", "governance_url", "contributing_url",
    "code_of_conduct_url", "security_policy_url", "sbom_url",
    "dependents_count", "paper_url",
    "openssf_best_practices_url", "openssf_best_practices_badge_level",
    "openssf_scorecard_url", "openssf_scorecard_score",
    "openssf_scorecard_branch_protection", "openssf_scorecard_code_review",
    "openssf_scorecard_maintained", "openssf_scorecard_vulnerabilities",
    "development_status", "software_heritage_id",
]


def resolve_metadata_field(tools_raw: Optional[str], metadata_raw: Optional[str],
                            field: str, context: str, warnings: list):
    """One field, one tool: apply the tools/tool_metadata precedence rule
    described above and return the correctly-typed final value (str, or
    Optional[int]/Optional[float] per METADATA_INT_FIELDS/METADATA_FLOAT_FIELDS).
    `programming_language` (METADATA_LIST_FIELDS) is returned as the winning
    *raw* string, not yet split -- the caller runs it through
    split_simple_list() itself, same as any other programming_language cell."""
    tools_text = clean(tools_raw)
    if tools_text.lower() == NONE_TOKEN:
        winning_raw = ""
    elif tools_text:
        winning_raw = tools_text
    else:
        winning_raw = clean(metadata_raw)

    if field in METADATA_INT_FIELDS:
        return parse_optional_int(winning_raw, context, warnings)
    if field in METADATA_FLOAT_FIELDS:
        return parse_optional_float(winning_raw, context, warnings)
    return winning_raw


def fetch_source(source_cfg: dict, label: str, warnings: list) -> str:
    """Return CSV text for a data source, preferring a local `file` override.

    Prefers `sheet_name` (the tab's visible name) over `gid` (the tab's
    opaque numeric id) when both are absent-or-present, since a tab name is
    stable and human-verifiable, whereas a wrong/stale gid produces a bare
    "400 Bad Request" from Google's export endpoint with no clue why.
    """
    file_path = source_cfg.get("file")
    if file_path:
        p = Path(file_path)
        print(f"[data] {label}: reading local file {p}")
        with open(p, "r", encoding="utf-8-sig") as f:
            return f.read()

    sheet_id = source_cfg["sheet_id"]
    sheet_name = source_cfg.get("sheet_name")
    if sheet_name:
        from urllib.parse import quote

        url = (
            f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq"
            f"?tqx=out:csv&sheet={quote(sheet_name)}"
        )
    else:
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
        "Is the sheet shared as 'Anyone with the link'? Is the sheet_name/gid correct? "
        "A '400 Bad Request' here almost always means the tab name or gid doesn't "
        "match any tab in the spreadsheet -- open the tab and check its exact name."
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


def parse_id_list(raw: Optional[str]) -> list:
    """Split a cell of semicolon- (or comma-, as fallback) separated ids.
    Used for both the Tools column and the five framework columns, now that
    all of them hold pure id references rather than free text."""
    if raw is None:
        return []
    raw = raw.strip()
    if raw.lower() in UNMAPPED_TOKENS:
        return []
    parts = raw.split(";") if ";" in raw else raw.split(",")
    return [p.strip() for p in parts if p.strip()]


def parse_freshness(row: dict, colmap: dict, warnings: list, context: str) -> "Freshness":
    """Read the `datetime_added`/`datetime_checked`/`datetime_updated` trio
    present on every OUR-owned tab. Every row is expected to carry all three
    -- warn (don't fail) if any is blank, so a straggler row that predates
    or skipped the freshness bookkeeping gets surfaced for cleanup rather
    than silently passing through. Free-text passthrough, not parsed into a
    datetime: the build has no logic that compares or sorts them, it just
    carries them into data.json for a future scheduler to read."""
    fresh = Freshness(
        added=(row.get(colmap.get("datetime_added", "")) or "").strip(),
        checked=(row.get(colmap.get("datetime_checked", "")) or "").strip(),
        updated=(row.get(colmap.get("datetime_updated", "")) or "").strip(),
    )
    missing = [name for name, value in
               (("datetime_added", fresh.added), ("datetime_checked", fresh.checked), ("datetime_updated", fresh.updated))
               if not value]
    if missing:
        warnings.append(f"{context}: missing {', '.join(missing)} (every row is expected to carry all three)")
    return fresh


# --------------------------------------------------------------------------
# Slugs
# --------------------------------------------------------------------------

_slug_re = re.compile(r"[^a-z0-9]+")


def slugify(text: str, max_len: int = 60) -> str:
    base = _slug_re.sub("-", text.strip().lower()).strip("-")
    base = base[:max_len].rstrip("-")
    return base or "item"


def stable_slug(rq_no: str, text: str) -> str:
    """RQ number prefix + slug. The RQ number is the sheet's own stable
    identifier -- readable, sorts naturally, and never changes if the
    question wording is edited (unlike a text-derived hash)."""
    return f"{safe_id_for_path(rq_no)}-{slugify(text)}"


def safe_id_for_path(tool_id: str) -> str:
    return _slug_re.sub("-", tool_id.strip().lower()).strip("-") or "tool"


# --------------------------------------------------------------------------
# Build tool catalog
# --------------------------------------------------------------------------

def build_tool_catalog(rows: list, colmap: dict, warnings: list) -> tuple:
    """Return ({id: Tool}, {id: raw row dict}). Only identity fields (id,
    tool_type, name, summary, license, homepage, source, documentation) and
    freshness are set on the Tool here -- every project-quality/community-
    health field (including the raw, not-yet-typed `programming_language`/
    `funding`/`funder` cells) is resolved afterward by apply_tool_metadata(),
    against both this tab and `tool_metadata`. The raw row dict returned
    alongside the catalog is what that merge reads `tools`' own cells from."""
    catalog = {}
    raw_rows = {}
    for i, row in enumerate(rows):
        raw_id = (row.get(colmap["id"]) or "").strip()
        if not raw_id:
            continue
        if raw_id in catalog:
            warnings.append(f"tools row {i + 2}: duplicate tool id {raw_id!r}, overwriting earlier entry")

        ctx = f"tools row {i + 2} ({raw_id!r})"
        catalog[raw_id] = Tool(
            id=raw_id,
            slug=safe_id_for_path(raw_id),
            name=(row.get(colmap["name"]) or "").strip() or raw_id,
            tool_type=(row.get(colmap["tool_type"]) or "").strip(),
            summary=(row.get(colmap["summary"]) or "").strip(),
            license=(row.get(colmap["license"]) or "").strip(),
            homepage=(row.get(colmap["homepage"]) or "").strip(),
            source=(row.get(colmap["source"]) or "").strip(),
            documentation=(row.get(colmap["documentation"]) or "").strip(),
            freshness=parse_freshness(row, colmap, warnings, ctx),
        )
        raw_rows[raw_id] = row
    return catalog, raw_rows


def apply_tool_metadata(tool_catalog: dict, tools_raw_rows: dict, metadata_rows: list,
                        colmap_tools: dict, colmap_metadata: dict, warnings: list) -> None:
    """Resolve every field in METADATA_FIELDS for every tool, per the
    tools/tool_metadata precedence rule documented above
    resolve_metadata_field(), and set it on the matching Tool in place.

    Runs for every tool in `tool_catalog`, not just ones with a
    `tool_metadata` row -- a `tools`-tab override (or an explicit "none")
    still applies even for a tool the collector hasn't reached yet; it just
    resolves against an empty metadata side."""
    metadata_by_id = {}
    for i, row in enumerate(metadata_rows):
        raw_id = (row.get(colmap_metadata["id"]) or "").strip()
        if not raw_id:
            continue
        if raw_id not in tool_catalog:
            warnings.append(
                f"tool_metadata row {i + 2}: id {raw_id!r} not found in the tools tab "
                f"(orphaned metadata row -- typo, or the tool was since removed)"
            )
            continue
        if raw_id in metadata_by_id:
            warnings.append(f"tool_metadata row {i + 2}: duplicate tool id {raw_id!r}, overwriting earlier entry")
        metadata_by_id[raw_id] = row

    for raw_id, tool in tool_catalog.items():
        tools_row = tools_raw_rows.get(raw_id, {})
        metadata_row = metadata_by_id.get(raw_id, {})
        ctx = f"tool {raw_id!r}"

        for field in METADATA_FIELDS:
            tools_col = colmap_tools.get(field)
            metadata_col = colmap_metadata.get(field)
            tools_raw = tools_row.get(tools_col) if tools_col else None
            metadata_raw = metadata_row.get(metadata_col) if metadata_col else None
            value = resolve_metadata_field(tools_raw, metadata_raw, field, f"{ctx} [{field}]", warnings)
            if field in METADATA_LIST_FIELDS:
                tool.programming_languages = split_simple_list(value)
            else:
                setattr(tool, field, value)

        # tool_metadata's own freshness, kept separate from `tools`' --
        # blank Freshness() if this tool has no tool_metadata row yet.
        if metadata_row:
            tool.metadata_freshness = parse_freshness(metadata_row, colmap_metadata, warnings,
                                                       f"tool_metadata ({raw_id!r})")


# --------------------------------------------------------------------------
# Build terms catalog (RGAF/EU_AI_Act/UNESCO/ASEAN/CoE terms, one shared tab)
# --------------------------------------------------------------------------

def build_terms_catalog(rows: list, colmap: dict, warnings: list) -> dict:
    """Return {id: Term} from the "terms" tab. Ids are expected to be
    globally unique via a namespaced convention (e.g. `euaiact-a8` vs.
    `coeai-a8`), so a flat dict is sufficient -- no per-framework scoping
    needed for the lookup itself."""
    catalog = {}
    for i, row in enumerate(rows):
        raw_id = (row.get(colmap["id"]) or "").strip()
        if not raw_id:
            continue
        if raw_id in catalog:
            warnings.append(f"terms row {i + 2}: duplicate term id {raw_id!r}, overwriting earlier entry")
        catalog[raw_id] = Term(
            id=raw_id,
            framework=(row.get(colmap["framework"]) or "").strip(),
            name=(row.get(colmap["name"]) or "").strip() or raw_id,
            summary=(row.get(colmap["summary"]) or "").strip(),
            url=(row.get(colmap["url"]) or "").strip(),
            freshness=parse_freshness(row, colmap, warnings, f"terms row {i + 2} ({raw_id!r})"),
        )
    return catalog


# --------------------------------------------------------------------------
# Build framework catalog (descriptive metadata, one row per framework key)
# --------------------------------------------------------------------------

def build_framework_catalog(rows: list, colmap: dict, warnings: list) -> dict:
    """Return {id: {name, fullname, summary, homepage, source, group}} from
    the "framework" tab -- mirrors build_tool_catalog/build_terms_catalog
    (flat dict by id, duplicate-id warning)."""
    catalog = {}
    for i, row in enumerate(rows):
        raw_id = (row.get(colmap["id"]) or "").strip()
        if not raw_id:
            continue
        if raw_id in catalog:
            warnings.append(f"framework row {i + 2}: duplicate framework id {raw_id!r}, overwriting earlier entry")
        catalog[raw_id] = {
            "name": (row.get(colmap["name"]) or "").strip(),
            "fullname": (row.get(colmap["fullname"]) or "").strip(),
            "summary": (row.get(colmap["summary"]) or "").strip(),
            "homepage": (row.get(colmap["homepage"]) or "").strip(),
            "source": (row.get(colmap["source"]) or "").strip(),
            "group": (row.get(colmap["group"]) or "").strip(),
            "freshness": parse_freshness(row, colmap, warnings, f"framework row {i + 2} ({raw_id!r})"),
        }
    return catalog


def merge_framework_defs(frameworks_config: list, framework_catalog: dict, warnings: list) -> list:
    """Merge each `frameworks:` config entry (key, column -- the build
    wiring) with its descriptive metadata from the "framework" tab. `label`
    is the tab's `name`; `doc_url` is the tab's `source`, falling back to
    `homepage` if `source` is blank (some frameworks, e.g. unescoai, only
    have a homepage on file)."""
    merged = []
    for fw in frameworks_config:
        key = fw["key"]
        info = framework_catalog.get(key)
        if info is None:
            warnings.append(
                f"framework {key!r}: no matching row in the framework tab "
                f"(falling back to the key itself as label, no doc_url)"
            )
            info = {"name": "", "fullname": "", "summary": "", "homepage": "", "source": "", "group": "",
                    "freshness": Freshness()}
        merged.append(
            {
                "key": key,
                "column": fw["column"],
                "label": info["name"] or key,
                "fullname": info["fullname"],
                "summary": info["summary"],
                "group": info["group"],
                "doc_url": info["source"] or info["homepage"],
                "homepage": info["homepage"],
                "freshness": info["freshness"],
            }
        )
    configured_keys = {fw["key"] for fw in frameworks_config}
    for fw_id in framework_catalog:
        if fw_id not in configured_keys:
            warnings.append(
                f"framework tab: id {fw_id!r} has no matching entry in config.yaml's "
                f"`frameworks:` list (orphaned metadata, not wired to any mapping column)"
            )
    return merged


# --------------------------------------------------------------------------
# Build mapping index (rq_no -> our annotations)
# --------------------------------------------------------------------------

def build_mapping_index(rows: list, colmap: dict, framework_defs: list, warnings: list) -> dict:
    """Return {rq_no: {fw_key: [term_ids...], ...}} from the mapping tab. The
    mapping tab's own question-text column is intentionally ignored. Cells
    are plain id lists (';'-separated) -- resolution against the terms
    catalog happens in build_problems. Tool mappings are NOT here -- see
    build_tool_role_index / the tool_map tab."""
    index = {}
    for i, row in enumerate(rows):
        rq_no = (row.get(colmap["rq_no"]) or "").strip()
        if not rq_no:
            # A wholly blank trailing row is common in exports; only warn if the
            # row actually carries mapping content that will be silently lost.
            has_content = any((row.get(fw["column"]) or "").strip() for fw in framework_defs)
            if has_content:
                warnings.append(f"mapping row {i + 2}: blank rq_no but has mapping content; row ignored")
            continue
        if rq_no in index:
            warnings.append(f"mapping row {i + 2}: duplicate rq_no {rq_no!r}, keeping last")
        entry = {"freshness": parse_freshness(row, colmap, warnings, f"mapping row {i + 2} (rq_no {rq_no!r})")}
        for fw in framework_defs:
            entry[fw["key"]] = parse_id_list(row.get(fw["column"]))
        index[rq_no] = entry
    return index


# --------------------------------------------------------------------------
# Build tool-role index (rq_no -> tool pairings, tool_map tab)
# --------------------------------------------------------------------------

VALID_TOOL_ROLES = {"implement", "eval"}


def build_tool_role_index(rows: list, colmap: dict, warnings: list) -> dict:
    """Return {rq_no: {"implement": [(tool_id, rationale, freshness), ...], "eval": [...]}}
    from the tool_map tab -- one row per (rq_no, tool_id, role) pairing, long
    format rather than a semicolon list, so a rationale has somewhere to
    live and adding a pairing never means hand-editing an existing cell.
    Resolution against the tool catalog happens in build_problems, same
    deferred-resolution pattern as build_mapping_index."""
    index: dict = {}
    seen_pairs = set()
    for i, row in enumerate(rows):
        rq_no = (row.get(colmap["rq_no"]) or "").strip()
        tool_id = (row.get(colmap["tool_id"]) or "").strip()
        role = (row.get(colmap["role"]) or "").strip()
        rationale = (row.get(colmap["rationale"]) or "").strip()
        if not rq_no and not tool_id and not role:
            continue  # blank trailing row
        if not rq_no or not tool_id:
            warnings.append(f"tool_map row {i + 2}: missing rq_no or tool_id; row ignored")
            continue
        if role not in VALID_TOOL_ROLES:
            warnings.append(
                f"tool_map row {i + 2}: role {role!r} must be exactly 'implement' or 'eval'; row ignored"
            )
            continue
        pair_key = (rq_no, tool_id, role)
        if pair_key in seen_pairs:
            warnings.append(f"tool_map row {i + 2}: duplicate ({rq_no}, {tool_id}, {role}) pairing; row ignored")
            continue
        seen_pairs.add(pair_key)
        entry = index.setdefault(rq_no, {"implement": [], "eval": []})
        context = f"tool_map row {i + 2} (rq_no {rq_no!r}, tool_id {tool_id!r})"
        entry[role].append((tool_id, rationale, parse_freshness(row, colmap, warnings, context)))
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
    tool_role_index: dict,
    tool_catalog: dict,
    terms_catalog: dict,
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
            fw_key = fw["key"]
            term_ids = (mapping or {}).get(fw_key, [])
            terms = []
            for tid in term_ids:
                term = terms_catalog.get(tid)
                if term is None:
                    warnings.append(
                        f"RQ {rq_no}: term id {tid!r} referenced in [{fw['column']}] not found "
                        f"in the terms tab (check for typos or a missing catalog entry)"
                    )
                    continue
                if term.framework and term.framework != fw_key:
                    warnings.append(
                        f"RQ {rq_no}: term id {tid!r} referenced in [{fw['column']}] belongs to "
                        f"framework {term.framework!r} in the terms tab, not {fw_key!r} -- "
                        f"likely pasted into the wrong column"
                    )
                terms.append(term)
            mappings[fw_key] = terms
        mappings[expertise_key] = expertise

        tool_pairs = tool_role_index.get(rq_no) if rq_no else None
        if tool_pairs is not None:
            used_rqnos.add(rq_no)

        def resolve_tools(role: str) -> list:
            resolved = []
            for tid, rationale, pair_freshness in (tool_pairs or {}).get(role, []):
                tool = tool_catalog.get(tid)
                if tool is None:
                    warnings.append(
                        f"RQ {rq_no}: tool id {tid!r} referenced in tool_map [{role}] not found "
                        f"in the Tools tab (check for typos or a missing catalog entry)"
                    )
                    continue
                resolved.append(ToolRationale(tool=tool, rationale=rationale, freshness=pair_freshness))
            return resolved

        tools_implement = resolve_tools("implement")
        tools_eval = resolve_tools("eval")

        slug = stable_slug(rq_no, question)
        if slug in seen_slugs:
            warnings.append(f"TAIG row {i + 2}: slug collision with row {seen_slugs[slug]} (duplicate question?)")
        seen_slugs[slug] = i + 2

        search_parts = [question, problem_area]
        for fw in framework_defs:
            search_parts.extend(t.name for t in mappings[fw["key"]])
        search_parts.extend(expertise)
        search_parts.extend(t.tool.name for t in tools_implement)
        search_parts.extend(t.tool.name for t in tools_eval)
        search_text = " ".join(search_parts).lower()

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
                tools_implement=tools_implement,
                tools_eval=tools_eval,
                search_text=search_text,
                order=i,
                mapping_freshness=(mapping or {}).get("freshness", Freshness()),
            )
        )

    # Surface orphaned annotations: mapping/tool_map rows whose rq_no matched no TAIG row.
    for rq_no in mapping_index:
        if rq_no not in used_rqnos:
            warnings.append(
                f"mapping RQ {rq_no!r}: no matching row in the TAIG sheet "
                f"(orphaned annotation -- typo, or question removed/renumbered upstream)"
            )
    for rq_no in tool_role_index:
        if rq_no not in used_rqnos:
            warnings.append(
                f"tool_map RQ {rq_no!r}: no matching row in the TAIG sheet "
                f"(orphaned tool pairing -- typo, or question removed/renumbered upstream)"
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
    """Capacity -> Target -> Problem Area -> [problems]. Each capacity/target
    group carries a `slug` (its name, slugified) so templates can anchor-link
    into a specific cell -- e.g. from the matrix overview on the Landscape
    and Tools pages -- without recomputing the slug themselves."""
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
            target_groups.append({"name": tgt, "slug": slugify(tgt), "areas": area_groups, "count": len(tgt_problems)})
        groups.append({"name": cap, "slug": slugify(cap), "targets": target_groups, "count": len(cap_problems)})
    return groups


def flatten_groups(groups: list) -> list:
    """Problems in the same order they're rendered on the problems-listing
    page (Capacity -> Target -> Problem Area), for prev/next navigation on
    the problem-detail page -- distinct from `Problem.order` (raw sheet
    row order), which doesn't necessarily match the on-page grouping."""
    flat = []
    for g in groups:
        for tgt in g["targets"]:
            for area in tgt["areas"]:
                flat.extend(area["problems"])
    return flat


CROSSCUTTING_TARGET = "All"


def build_matrix(problems: list, capacities_order: list, targets_order: list) -> list:
    """Capacity x Target coverage matrix for the Landscape page's overview
    grid, and the per-RQ data the compact mini-heatmap (atop the Explorer/
    problems and Tools listing pages) buckets by tool count. Iterates the
    full configured taxonomy, not just combinations actually present in the
    data, so the grid shape stays stable regardless of current coverage. A
    capacity whose only target is "All" (Operationalisation, Ecosystem
    Monitoring) renders as one wide cross-cutting cell instead of 4 columns.

    Each block also carries `rq_cells`: one entry per problem in that cell,
    in sheet order, with its own tool_count/has_tool -- the Landscape page's
    per-cell binary blocks and the mini-heatmap's per-RQ, count-bucketed
    squares both read from this instead of a separate data pass.
    """
    core_targets = [t for t in targets_order if t != CROSSCUTTING_TARGET]
    cells: dict = {}
    for p in problems:
        cell = cells.setdefault((p.capacity, p.target), {"total": 0, "covered": 0, "areas": [], "rq_cells": []})
        cell["total"] += 1
        tool_count = len(p.tools_implement) + len(p.tools_eval)
        if tool_count:
            cell["covered"] += 1
        if p.problem_area not in cell["areas"]:
            cell["areas"].append(p.problem_area)
        cell["rq_cells"].append({
            "rq_no": p.rq_no, "slug": p.slug, "question": p.question,
            "tool_count": tool_count, "has_tool": tool_count > 0,
        })

    empty_cell = {"total": 0, "covered": 0, "areas": [], "rq_cells": []}
    rows = []
    for cap in capacities_order:
        cap_targets = {tgt for (c, tgt) in cells if c == cap}
        crosscutting = bool(cap_targets) and cap_targets <= {CROSSCUTTING_TARGET}
        if crosscutting:
            cell = cells.get((cap, CROSSCUTTING_TARGET), empty_cell)
            blocks = [{
                "target": CROSSCUTTING_TARGET, "target_slug": slugify(CROSSCUTTING_TARGET),
                "span": len(core_targets), **cell,
            }]
        else:
            blocks = []
            for tgt in core_targets:
                cell = cells.get((cap, tgt), empty_cell)
                blocks.append({"target": tgt, "target_slug": slugify(tgt), "span": 1, **cell})
        rows.append({"capacity": cap, "capacity_slug": slugify(cap), "blocks": blocks})
    return rows


def first_words(text: str, max_chars: int = 75) -> str:
    """As many whole words as fit within `max_chars`, ellipsized -- the short
    problem-question label on a tool's preview chip, where the full question
    would overflow it. Breaks on a word boundary, never mid-word, even if
    that means landing under the limit rather than right at it."""
    if len(text) <= max_chars:
        return text
    words = text.split()
    kept = []
    length = 0
    for word in words:
        added_length = len(word) + (1 if kept else 0)  # +1 for the joining space
        if length + added_length > max_chars:
            break
        kept.append(word)
        length += added_length
    if not kept:
        kept = [words[0]]  # first word alone exceeds max_chars -- show it whole anyway
    return " ".join(kept) + "..."


def _rq_sort_key(p) -> tuple:
    """Numeric rq_no sorts before any non-numeric one, and never gets
    compared to a str directly (mixed int/str comparison raises)."""
    try:
        return (0, int(p.rq_no))
    except ValueError:
        return (1, p.rq_no)


def select_highlighted_problems(tool_id: str, problems_for_tool: list, max_shown: int = 3) -> tuple:
    """Pick up to `max_shown` problems to preview on a tool's card. Prefers a
    mix of Implement/Evaluate roles and distinct Capacity x Target
    combinations over just the first N by number, so the preview doesn't
    read as one narrow slice of what the tool does. Returns
    (chosen_in_rq_order, how_many_left_out).
    """
    candidates = []
    for p in problems_for_tool:
        roles = set()
        if any(pairing.tool.id == tool_id for pairing in p.tools_implement):
            roles.add("implement")
        if any(pairing.tool.id == tool_id for pairing in p.tools_eval):
            roles.add("eval")
        if roles:
            candidates.append((p, roles))
    candidates.sort(key=lambda c: _rq_sort_key(c[0]))

    if len(candidates) <= max_shown:
        return [c[0] for c in candidates], 0

    selected = []
    used_cap_target = set()
    role_counts = {"implement": 0, "eval": 0}
    pool = list(candidates)
    while pool and len(selected) < max_shown:
        def score(c):
            p, roles = c
            dup = 1 if (p.capacity, p.target) in used_cap_target else 0
            if "implement" in roles and "eval" in roles:
                role_gap = 0
            elif "implement" in roles:
                role_gap = 0 if role_counts["implement"] <= role_counts["eval"] else 1
            else:
                role_gap = 0 if role_counts["eval"] <= role_counts["implement"] else 1
            return (dup, role_gap)
        pool.sort(key=lambda c: (score(c), _rq_sort_key(c[0])))
        p, roles = pool.pop(0)
        selected.append((p, roles))
        used_cap_target.add((p.capacity, p.target))
        for r in roles:
            role_counts[r] += 1

    selected.sort(key=lambda c: _rq_sort_key(c[0]))
    return [c[0] for c in selected], len(candidates) - len(selected)


def build_tools_index(problems: list, tool_catalog: dict) -> list:
    usage = {tid: [] for tid in tool_catalog}
    for p in problems:
        for pairing in list(p.tools_implement) + list(p.tools_eval):
            tid = pairing.tool.id
            usage.setdefault(tid, [])
            if p not in usage[tid]:
                usage[tid].append(p)
    entries = []
    for tid, tool in tool_catalog.items():
        tool_problems = usage.get(tid, [])
        highlighted, more_count = select_highlighted_problems(tid, tool_problems)
        entries.append({
            "tool": tool,
            "problems": tool_problems,
            "highlighted_problems": [
                {"rq_no": p.rq_no, "slug": p.slug, "label": first_words(p.question)}
                for p in highlighted
            ],
            "more_count": more_count,
        })
    entries.sort(key=lambda e: e["tool"].name.lower())
    return entries


def format_csl_author(author: dict) -> str:
    """CSL-JSON author -> one display name. `literal` covers organizations
    and phrases like "et al." that aren't a real person's name."""
    if "literal" in author:
        return author["literal"]
    return author.get("family", "").strip()


def format_csl_date(issued: dict) -> str:
    parts = (issued or {}).get("date-parts") or [[]]
    year = parts[0][0] if parts[0] else ""
    return str(year)


def load_references(path: Path) -> list:
    """Load a CSL-JSON array (see
    https://github.com/citation-style-language/schema) and render each item
    to a simple {citation, url} pair for the References page. Not a full
    CSL formatter -- just enough to produce "Authors, Year. Title." """
    items = json.loads(path.read_text(encoding="utf-8"))
    references = []
    for item in items:
        authors = [format_csl_author(a) for a in item.get("author", [])]
        authors = [a for a in authors if a]
        year = format_csl_date(item.get("issued"))
        title = (item.get("title") or "").strip()
        lead = ", ".join(authors + ([year] if year else []))
        citation = f"{lead}. {title}." if lead else f"{title}."
        references.append(
            {
                "citation": citation,
                "lead": lead,
                "title": title,
                "url": item.get("URL", "")
            }
        )
    return references


def build_frameworks_index(problems: list, framework_defs: list, terms_catalog: dict) -> dict:
    """fw_key -> {term_id: {"term": Term, "problems": [...]}}, in the terms
    tab's own row order (sheet order). Only the regulatory frameworks get
    browse pages -- expertise does not (it is filter + chips only)."""
    usage = {}
    for p in problems:
        for fw in framework_defs:
            for term in p.mappings.get(fw["key"], []):
                usage.setdefault(term.id, []).append(p)

    index = {}
    for fw in framework_defs:
        key = fw["key"]
        index[key] = {
            term_id: {"term": term, "problems": usage.get(term_id, [])}
            for term_id, term in terms_catalog.items()
            if term.framework == key
        }
    return index


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

def problem_to_public_dict(p: Problem, expertise_key: str) -> dict:
    mappings_out = {}
    for key, value in p.mappings.items():
        if key == expertise_key:
            mappings_out[key] = value  # plain list[str]
        else:
            mappings_out[key] = [
                {"id": t.id, "name": t.name, "url": t.url, "freshness": dataclasses.asdict(t.freshness)}
                for t in value
            ]
    return {
        "slug": p.slug,
        "rq_no": p.rq_no,
        "question": p.question,
        "capacity": p.capacity,
        "target": p.target,
        "problem_area": p.problem_area,
        "section_number": p.section_number,
        "mappings": mappings_out,
        "existing_work": p.existing_work,
        "new_work": p.new_work,
        "mapping_freshness": dataclasses.asdict(p.mapping_freshness),
        "tools_implement": [
            {"id": t.tool.id, "name": t.tool.name, "homepage": t.tool.homepage, "rationale": t.rationale,
             "freshness": dataclasses.asdict(t.freshness)}
            for t in p.tools_implement
        ],
        "tools_eval": [
            {"id": t.tool.id, "name": t.tool.name, "homepage": t.tool.homepage, "rationale": t.rationale,
             "freshness": dataclasses.asdict(t.freshness)}
            for t in p.tools_eval
        ],
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
        facet_terms[key] = sorted((data["term"].name for data in terms.values()), key=str.lower)
    expertise_terms = sorted({t for p in problems for t in p.mappings.get(expertise_key, [])}, key=str.lower)
    facet_terms[expertise_key] = expertise_terms

    capacities_list = [g["name"] for g in groups]

    matrix = build_matrix(problems, config["taxonomy"]["capacities"], config["taxonomy"]["targets"])
    capacity_blurbs = config["taxonomy"].get("capacity_blurbs", {})
    targets_core = [t for t in config["taxonomy"]["targets"] if t != CROSSCUTTING_TARGET]

    site_ctx = {
        "site": config["site"],
        "generated_at": generated_at,
        "frameworks": framework_defs,
        "expertise": expertise_def,
        "facets": facet_defs,
        "facet_terms": facet_terms,
        "capacities_list": capacities_list,
        "problem_count": len(problems),
        "tool_count": len(tool_catalog),
        "references": load_references(Path(__file__).parent / "data" / "references.json"),
        "matrix": matrix,
        "capacity_blurbs": capacity_blurbs,
        "targets_core": targets_core,
    }

    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    (out_dir / "problems").mkdir()
    (out_dir / "tools").mkdir()
    (out_dir / "frameworks").mkdir()
    for fw in framework_defs:
        (out_dir / "frameworks" / fw["key"]).mkdir()
    (out_dir / "references").mkdir()

    def write(path: Path, template_name: str, **ctx):
        path.parent.mkdir(parents=True, exist_ok=True)
        tmpl = env.get_template(template_name)
        path.write_text(tmpl.render(**site_ctx, **ctx), encoding="utf-8")

    # Tools with zero tool_map rows -- not wrong data, just not curated yet
    # (or genuinely unaddressed by any of the 97 RQs). Surfaced on the
    # problems-listing page as a special "RQ #0" card rather than silently
    # vanishing from the open-problems view; they still list normally on the
    # tools index.
    orphan_tools = sorted((e["tool"] for e in tools_index if not e["problems"]), key=lambda t: t.name.lower())

    # / is the Landscape overview (capacity x target matrix); the problem
    # listing itself ("Explorer") lives at /problems/, each problem at
    # /problems/<rq_no>-<slug>/ -- a directory with its own index.html, for a
    # clean trailing-slash URL rather than a bare .html file.
    write(out_dir / "index.html", "landscape.html", root="", active="landscape")
    write(
        out_dir / "problems" / "index.html", "problems_index.html", root="../",
        groups=groups, orphan_tools=orphan_tools, active="problems",
    )

    flat_problems = flatten_groups(groups)
    for i, p in enumerate(flat_problems):
        write(
            out_dir / "problems" / p.slug / "index.html", "problem.html", root="../../",
            problem=p,
            prev=flat_problems[i - 1] if i > 0 else None,
            next=flat_problems[i + 1] if i + 1 < len(flat_problems) else None,
            active="problem",
        )

    # Short-alias redirect: /problems/<rq_no>/ -> /problems/<rq_no>-<slug>/,
    # so a problem can be linked by number alone without knowing its current
    # slug. rq_dir uses the same sanitizing as the slug's own prefix
    # (safe_id_for_path), so it always matches the directory p.slug already
    # starts with.
    for p in flat_problems:
        rq_dir = safe_id_for_path(p.rq_no)
        write(
            out_dir / "problems" / rq_dir / "index.html", "problem_redirect.html",
            rq_no=p.rq_no, target=f"../{p.slug}/",
        )

    # Same directory-per-item pattern for tools: /tools/ listing,
    # /tools/<tool-id>/ detail.
    write(out_dir / "tools" / "index.html", "tools_index.html", root="../", entries=tools_index, active="tools")
    for entry in tools_index:
        tool = entry["tool"]
        write(
            out_dir / "tools" / tool.slug / "index.html",
            "tool.html",
            root="../../",
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
        for term_id, data in frameworks_index.get(fw["key"], {}).items():
            write(
                out_dir / "frameworks" / fw["key"] / f"{safe_id_for_path(term_id)}.html",
                "framework_term.html",
                root="../../",
                framework=fw,
                term=data["term"],
                problems=data["problems"],
                active="frameworks",
            )

    write(out_dir / "references" / "index.html", "references.html", root="../", active="references")

    data_json = {
        "generated_at": generated_at,
        "problems": [problem_to_public_dict(p, expertise_key) for p in problems],
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
    args = parser.parse_args()

    config = load_yaml(Path(args.config))
    warnings: list = []

    taig_csv = fetch_source(config["data"]["taig"], "taig", warnings)
    mapping_csv = fetch_source(config["data"]["mapping"], "mapping", warnings)
    tool_map_csv = fetch_source(config["data"]["tool_map"], "tool_map", warnings)
    tools_csv = fetch_source(config["data"]["tools"], "tools", warnings)
    tool_metadata_csv = fetch_source(config["data"]["tool_metadata"], "tool_metadata", warnings)
    terms_csv = fetch_source(config["data"]["terms"], "terms", warnings)
    framework_csv = fetch_source(config["data"]["framework"], "framework", warnings)

    taig_rows = parse_csv_text(taig_csv)
    mapping_rows = parse_csv_text(mapping_csv)
    tool_map_rows = parse_csv_text(tool_map_csv)
    tools_rows = parse_csv_text(tools_csv)
    tool_metadata_rows = parse_csv_text(tool_metadata_csv)
    terms_rows = parse_csv_text(terms_csv)
    framework_rows = parse_csv_text(framework_csv)

    colmap = config["columns"]
    framework_catalog = build_framework_catalog(framework_rows, colmap["framework"], warnings)
    framework_defs = merge_framework_defs(config["frameworks"], framework_catalog, warnings)
    expertise_def = config["expertise"]
    expertise_key = expertise_def["key"]
    facet_defs = list(framework_defs) + [expertise_def]

    terms_catalog = build_terms_catalog(terms_rows, colmap["terms"], warnings)
    tool_catalog, tools_raw_rows = build_tool_catalog(tools_rows, colmap["tools"], warnings)
    apply_tool_metadata(tool_catalog, tools_raw_rows, tool_metadata_rows,
                        colmap["tools"], colmap["tool_metadata"], warnings)
    mapping_index = build_mapping_index(mapping_rows, colmap["mapping"], framework_defs, warnings)
    tool_role_index = build_tool_role_index(tool_map_rows, colmap["tool_map"], warnings)

    problems = build_problems(
        taig_rows,
        colmap["taig"],
        framework_defs,
        expertise_key,
        mapping_index,
        tool_role_index,
        tool_catalog,
        terms_catalog,
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
    frameworks_index = build_frameworks_index(problems, framework_defs, terms_catalog)

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
        warnings,
        generated_at,
    )

    print(f"\n[build] wrote {len(problems)} problems, {len(tool_catalog)} tools to {out_dir}/")


if __name__ == "__main__":
    main()
