#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2026 OpenTAIG authors
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Classify a GitHub-reported SPDX license id as open source or not, using
the *official* SPDX license list rather than a hand-maintained allow-list.

Why this exists: GitHub's `license.spdx_id` answers "what licence file did we
detect?", which is a different question from "is this open source?". The two
diverge in exactly the cases this project cares about -- `CC-BY-NC-4.0` is a
real SPDX id and a real licence, but it is neither OSI-approved nor FSF-libre,
so a tool carrying it is *not* open source even though the field is populated.
Conversely `NOASSERTION` means GitHub found a LICENSE file it could not match
(typically a bespoke corporate "source available" grant), which is a
meaningfully different state from having no licence at all.

The SPDX list publishes `isOsiApproved` and `isFsfLibre` per licence, so both
questions are answered from data, not opinion. The list is fetched once and
cached; it changes rarely and the cache is committed so classification is
reproducible across runs and machines.

Classes returned by `classify()`:

    osi-approved     OSI-approved (isOsiApproved). The uncontroversial case.
    free-not-osi     FSF-libre but not OSI-approved -- e.g. CC-BY-4.0, CC0-1.0.
                     Free licences, but content licences rather than software
                     ones; worth counting separately rather than lumping in.
    non-free         A known SPDX id that is neither OSI nor FSF -- e.g.
                     CC-BY-NC-4.0, Elastic-2.0, BUSL-1.1. Source is readable,
                     but the licence restricts use.
    source-available NOASSERTION -- a licence file exists but SPDX can't match
                     it. Almost always a bespoke corporate licence.
    none-declared    No licence at all. Legally the most restrictive state,
                     despite looking like the emptiest one.
    unknown          Non-empty id absent from the SPDX list (typo, or a licence
                     newer than the cached list).

Deliberately NOT collapsed into a single is_open_source() boolean: where the
line falls is a research question for whoever is writing up the results, and
baking one answer in here would quietly make that choice for them. See
`OPEN_CLASSES` for the default reading, which callers may override.

Field names (`is_osi_approved`, `is_fsf_libre`) follow the SPDX 3.0 model's
predicate naming rather than the SPDX 2.x license-list-data JSON's camelCase
(`isOsiApproved`), and match the CLI predicates (`is-osi`, `is-fsf`) in
bact/licenseid (https://github.com/bact/licenseid) -- a dedicated SPDX
license-*text*-matching tool. That project is the right call when the input
is unstructured license text (a LICENSE file, a header comment) needing
identification; here the input is already a resolved SPDX id (GitHub's
`license.spdx_id` API field), so a lookup against the same underlying SPDX
data is enough and avoids the extra dependency + local database update step.

Usage:

    from licenses import load_spdx_index, classify
    index = load_spdx_index()
    classify("CC-BY-NC-4.0", index)   # -> "non-free"
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

SPDX_URL = "https://raw.githubusercontent.com/spdx/license-list-data/main/json/licenses.json"
DEFAULT_CACHE = Path(__file__).parent / "state" / "spdx_licenses.json"

# The default reading of "open source" for aggregate counts. Callers doing a
# stricter analysis may want just {"osi-approved"}; see the module docstring.
OPEN_CLASSES = {"osi-approved", "free-not-osi"}


def load_spdx_index(cache_path: Path | str = DEFAULT_CACHE, refresh: bool = False) -> dict:
    """Returns {licenseId: {is_osi_approved, is_fsf_libre}}, fetching the SPDX
    list on first use and caching it. Pass refresh=True to re-fetch a stale
    cache. Field names follow SPDX 3.0 predicate naming, not the source JSON's
    2.x camelCase -- see the module docstring."""
    cache_path = Path(cache_path)
    if cache_path.exists() and not refresh:
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)["licenses"]

    with urllib.request.urlopen(SPDX_URL, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    index = {
        lic["licenseId"]: {
            "is_osi_approved": bool(lic.get("isOsiApproved")),
            "is_fsf_libre": bool(lic.get("isFsfLibre")),
        }
        for lic in payload["licenses"]
    }
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump({"licenseListVersion": payload.get("licenseListVersion"),
                   "licenses": index}, f, indent=1, sort_keys=True)
    return index


def classify(spdx_id: str, index: dict) -> str:
    """Maps a GitHub-reported SPDX id to one of the classes in the module
    docstring. Tolerates the deprecated short ids GitHub still returns (it
    reports `GPL-3.0`, where current SPDX prefers `GPL-3.0-only`)."""
    spdx_id = (spdx_id or "").strip()
    if not spdx_id:
        return "none-declared"
    if spdx_id == "NOASSERTION":
        return "source-available"

    entry = index.get(spdx_id)
    if entry is None:
        # GitHub still emits deprecated ids; try the modern -only/-or-later forms.
        for suffix in ("-only", "-or-later"):
            entry = index.get(spdx_id + suffix)
            if entry is not None:
                break
    if entry is None:
        return "unknown"

    if entry["is_osi_approved"]:
        return "osi-approved"
    if entry["is_fsf_libre"]:
        return "free-not-osi"
    return "non-free"


if __name__ == "__main__":
    idx = load_spdx_index()
    print(f"{len(idx)} SPDX licence ids cached at {DEFAULT_CACHE}")
    for probe in ["MIT", "Apache-2.0", "GPL-3.0", "CC-BY-NC-4.0", "CC-BY-4.0",
                  "Elastic-2.0", "NOASSERTION", "", "Definitely-Not-A-Licence"]:
        print(f"  {probe or '(empty)':<26} -> {classify(probe, idx)}")
