#!/usr/bin/env python3
"""Map each research question to the harm type(s) it helps address, using the
Collaborative Harms Taxonomy (Abercrombie, Benbouzid, Giudici, Golpayegani,
Hernandez, Noro, Pandit, Paraschou, Pownall, Prajapati, Sayre, Sengupta,
Suriyawongkul, Thelot, Vei, Waltersdorfer -- arXiv:2407.01294), which has 9
top-level harm types and 69 specific harms.

Purpose: a **coverage-completeness check on the research agenda itself**, which
is a different question from "which RQs have tools". Reading the RQ catalog
against an independent, human-centred harm taxonomy answers: *which harms does
technical AI governance research not ask about at all?* Cross-referenced with
tool coverage it separates three states:

  1. harm addressed by RQs, and tooled          -- healthy
  2. harm addressed by RQs, but no tools        -- recognised, untooled
  3. harm not addressed by any RQ               -- outside the agenda entirely

State 3 is invisible to any analysis that starts from the RQ catalog, because
the catalog defines its own scope. That's the point of checking it against an
externally-derived taxonomy.

Mapping direction: RQ -> harm(s) the research would help **prevent, detect,
measure, or remediate**. Not "harms this RQ could cause".

`kind` distinguishes:
  - "direct"   -- the RQ names or clearly targets this harm
  - "enabling" -- the RQ provides infrastructure/method that supports
                  addressing it, without naming it (e.g. evaluation
                  methodology RQs). Counted separately so the headline
                  numbers aren't inflated by cross-cutting method RQs.

CAVEAT: this mapping is agent-produced from the RQ text and the taxonomy's own
definitions. It is a starting point for expert review, not a validated
instrument. Judgment calls flagged in `note`.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

# --- The taxonomy: 9 harm types, 69 specific harms (arXiv:2407.01294, Appendix A)
TAXONOMY = {
    "Autonomy": [
        "Autonomy/agency loss", "Impersonation/identity theft", "IP/copyright loss",
        "Personality rights loss"],
    "Physical": [
        "Bodily injury", "Loss of life", "Personal health deterioration", "Property damage"],
    "Psychological": [
        "Addiction", "Alienation/isolation", "Anxiety/depression", "Coercion/manipulation",
        "Dehumanisation/objectification", "Harassment/abuse/intimidation", "Over-reliance",
        "Radicalisation", "Self-harm", "Sexualisation", "Trauma"],
    "Reputational": [
        "Defamation/libel/slander", "Loss of confidence/trust"],
    "Financial and Business": [
        "Business operations/infrastructure damage", "Confidentiality loss",
        "Financial/earnings loss", "Livelihood loss", "Increased competition",
        "Monopolisation", "Opportunity loss"],
    "Human Rights and Civil Liberties": [
        "Benefits/entitlements loss", "Dignity loss", "Discrimination",
        "Loss of freedom of speech/expression", "Loss of freedom of assembly/association",
        "Loss of social rights and access to public services", "Loss of right to information",
        "Loss of right to free elections", "Loss of right to liberty and security",
        "Loss of right to due process", "Privacy loss"],
    "Societal and Cultural": [
        "Breach of ethics/values/norms", "Cheating/plagiarism", "Chilling effect",
        "Cultural dispossession", "Damage to public health", "Historical revisionism",
        "Information degradation", "Job loss/losses", "Labour exploitation",
        "Loss of creativity/critical thinking", "Stereotyping",
        "Public service delivery deterioration", "Societal destabilisation",
        "Societal inequality", "Violence/armed conflict"],
    "Political and Economic": [
        "Critical infrastructure damage", "Economic instability", "Power concentration",
        "Electoral interference", "Institutional trust loss", "Political instability",
        "Political manipulation"],
    "Environmental": [
        "Biodiversity loss", "Carbon emissions", "Electronic waste",
        "Excessive energy consumption", "Excessive landfill", "Excessive water consumption",
        "Natural resource depletion", "Pollution"],
}

AUT, PHY, PSY, REP = "Autonomy", "Physical", "Psychological", "Reputational"
FIN = "Financial and Business"
HR = "Human Rights and Civil Liberties"
SOC = "Societal and Cultural"
POL = "Political and Economic"
ENV = "Environmental"

# rq_no -> (kind, [(harm_type, [specific harms])], note)
MAPPING = {
    # --- Identification of Problematic Data -------------------------------
    "1": ("direct", [(SOC, ["Information degradation", "Stereotyping"]),
                     (HR, ["Discrimination", "Privacy loss"]),
                     (PSY, ["Harassment/abuse/intimidation"])],
          "Problematic data = toxic/biased/PII/illegal; spans all three."),
    "2": ("direct", [(AUT, ["IP/copyright loss"])], ""),
    "3": ("direct", [(AUT, ["IP/copyright loss"])], ""),
    "4": ("direct", [(SOC, ["Information degradation", "Stereotyping"]),
                     (HR, ["Discrimination", "Privacy loss"])], ""),
    "5": ("direct", [(SOC, ["Information degradation"]), (HR, ["Discrimination"])], ""),
    "6": ("direct", [(SOC, ["Information degradation"]), (HR, ["Privacy loss"]),
                     (PSY, ["Harassment/abuse/intimidation"])], ""),
    # --- Infrastructure and Metadata --------------------------------------
    "7": ("direct", [(AUT, ["IP/copyright loss"]), (HR, ["Privacy loss"])], ""),
    "8": ("enabling", [(HR, ["Discrimination", "Privacy loss"]), (SOC, ["Stereotyping"])],
          "Audit infrastructure: enables detection of whatever the auditor looks for."),
    "9": ("direct", [(HR, ["Discrimination"]), (SOC, ["Stereotyping", "Societal inequality"])], ""),
    "10": ("direct", [(AUT, ["IP/copyright loss"]), (HR, ["Privacy loss", "Discrimination"])], ""),
    # --- Attribution of Model Behavior to Data ----------------------------
    "11": ("enabling", [(HR, ["Discrimination"]), (SOC, ["Information degradation"])], ""),
    "12": ("enabling", [(AUT, ["IP/copyright loss"]), (HR, ["Discrimination"])],
           "Attribution underpins both copyright claims and bias accountability."),
    # --- Compute: chip/cluster specs, workloads ---------------------------
    "13": ("enabling", [(POL, ["Power concentration"])], "Compute governability precondition."),
    "14": ("enabling", [(POL, ["Power concentration"])], ""),
    "15": ("enabling", [(POL, ["Power concentration"])], ""),
    "16": ("enabling", [(POL, ["Power concentration"]), (SOC, ["Violence/armed conflict"])],
           "Decentralised training detection = evasion of compute controls."),
    "17": ("enabling", [(POL, ["Power concentration"]), (HR, ["Privacy loss"])],
           "RQ explicitly balances detection against developer privacy."),
    "18": ("enabling", [(POL, ["Power concentration"])], ""),
    # --- Evaluations ------------------------------------------------------
    "19": ("enabling", [], "Cross-cutting: evaluation thoroughness applies to any harm."),
    "20": ("enabling", [(REP, ["Loss of confidence/trust"]), (PSY, ["Over-reliance"])],
           "Contamination inflates capability claims -> misplaced trust/over-reliance."),
    "21": ("enabling", [], "Cross-cutting: mechanistic understanding is harm-agnostic."),
    "22": ("enabling", [(SOC, ["Violence/armed conflict"]),
                        (PSY, ["Harassment/abuse/intimidation"])],
           "Red-teaming surfaces misuse harms; scope depends on the probes used."),
    "23": ("enabling", [], "Cross-cutting agent evaluation."),
    "24": ("enabling", [(FIN, ["Business operations/infrastructure damage"]),
                        (POL, ["Economic instability"])],
           "Multi-agent failure modes are most cited in market/infrastructure terms."),
    "25": ("direct", [(SOC, ["Societal destabilisation", "Societal inequality", "Job loss/losses"]),
                      (POL, ["Political instability"])],
           "The one RQ that names societal impact as its object."),
    "26": ("direct", [(SOC, ["Cultural dispossession", "Stereotyping"]),
                      (HR, ["Discrimination"])],
           "Cross-lingual/modal scope is explicitly about non-dominant groups."),
    "27": ("enabling", [(REP, ["Loss of confidence/trust"]), (PSY, ["Over-reliance"])],
           "Construct validity failure -> unwarranted confidence in a benchmark."),
    "28": ("enabling", [], "Cross-cutting simulation fidelity."),
    # --- Privacy-preserving access ----------------------------------------
    "29": ("direct", [(HR, ["Privacy loss"])], ""),
    "30": ("direct", [(HR, ["Privacy loss"])], ""),
    "31": ("enabling", [(REP, ["Loss of confidence/trust"])], "Evaluation integrity."),
    "32": ("enabling", [(REP, ["Loss of confidence/trust"])], "Evaluation integrity."),
    # --- Compute inequities -----------------------------------------------
    "33": ("direct", [(SOC, ["Societal inequality"]), (FIN, ["Opportunity loss"]),
                      (POL, ["Power concentration"])], ""),
    "34": ("direct", [(SOC, ["Societal inequality"]), (FIN, ["Opportunity loss"])], ""),
    "35": ("enabling", [(POL, ["Power concentration"])], ""),
    # --- Third-party model access -----------------------------------------
    "36": ("enabling", [], "Cross-cutting auditing methodology."),
    "37": ("direct", [(SOC, ["Violence/armed conflict"]),
                      (PSY, ["Harassment/abuse/intimidation"])],
           "'Risks of misuse' -- taxonomy's misuse harms are mostly these two."),
    "38": ("direct", [(FIN, ["Confidentiality loss"]), (AUT, ["IP/copyright loss"])], ""),
    "39": ("direct", [(FIN, ["Confidentiality loss"])], ""),
    # --- Downstream user logs ---------------------------------------------
    "40": ("direct", [(HR, ["Privacy loss"])], ""),
    "41": ("direct", [(HR, ["Privacy loss", "Loss of right to information"])], ""),
    "42": ("direct", [(HR, ["Privacy loss"])], ""),
    "43": ("direct", [(HR, ["Privacy loss"])], ""),
    # --- Verification of training data ------------------------------------
    "44": ("direct", [(AUT, ["IP/copyright loss"]), (HR, ["Privacy loss"])], ""),
    "45": ("direct", [(HR, ["Privacy loss"]), (AUT, ["IP/copyright loss"])], ""),
    "46": ("direct", [(HR, ["Privacy loss"]), (AUT, ["IP/copyright loss"])], ""),
    "47": ("direct", [(AUT, ["IP/copyright loss"])], ""),
    # --- Chip location / compute workload verification --------------------
    "48": ("enabling", [(POL, ["Power concentration"]), (SOC, ["Violence/armed conflict"])],
           "Export-control enforcement."),
    "49": ("enabling", [(POL, ["Power concentration"]), (SOC, ["Violence/armed conflict"])], ""),
    "50": ("enabling", [(POL, ["Power concentration"])], ""),
    "51": ("enabling", [(POL, ["Power concentration"])], ""),
    "52": ("direct", [(HR, ["Privacy loss", "Loss of right to liberty and security"])],
           "RQ explicitly names surveillance misuse as the harm to avoid."),
    "53": ("enabling", [(POL, ["Power concentration"])], ""),
    # --- Verification of model properties / dynamic systems ---------------
    "54": ("enabling", [], "Cross-cutting property verification."),
    "55": ("direct", [(PSY, ["Harassment/abuse/intimidation", "Self-harm"]),
                      (SOC, ["Violence/armed conflict"])],
           "Runtime risk assessment of a response = content-harm gating."),
    "56": ("enabling", [(REP, ["Loss of confidence/trust"])], ""),
    # --- Proof of learning -------------------------------------------------
    "57": ("direct", [(AUT, ["IP/copyright loss"]), (FIN, ["Confidentiality loss"])], ""),
    "58": ("direct", [(AUT, ["IP/copyright loss"]), (FIN, ["Confidentiality loss"])], ""),
    # --- Verifiable audits -------------------------------------------------
    "59": ("enabling", [(REP, ["Loss of confidence/trust"])], ""),
    "61": ("direct", [(REP, ["Loss of confidence/trust"]),
                      (HR, ["Loss of right to information"])],
           "Presentation-to-users is the taxonomy's 'right to information' territory."),
    "62": ("enabling", [(FIN, ["Confidentiality loss"]), (REP, ["Loss of confidence/trust"])], ""),
    "63": ("enabling", [(REP, ["Loss of confidence/trust"])], ""),
    "64": ("enabling", [(REP, ["Loss of confidence/trust"])], ""),
    # --- Verification of AI-generated content ------------------------------
    "65": ("direct", [(SOC, ["Information degradation"]),
                      (AUT, ["Impersonation/identity theft", "Personality rights loss"]),
                      (POL, ["Electoral interference", "Political manipulation"])], ""),
    "66": ("direct", [(SOC, ["Information degradation"]),
                      (AUT, ["Impersonation/identity theft", "Personality rights loss"]),
                      (POL, ["Electoral interference", "Political manipulation"])], ""),
    "67": ("direct", [(SOC, ["Information degradation"]),
                      (AUT, ["Impersonation/identity theft"]),
                      (POL, ["Electoral interference", "Political manipulation"])], ""),
    "68": ("direct", [(SOC, ["Information degradation", "Historical revisionism"]),
                      (AUT, ["Personality rights loss"])],
           "Edited-genuine-image case is where historical revisionism actually lands."),
    # --- Training data extraction -----------------------------------------
    "69": ("direct", [(HR, ["Privacy loss"]), (FIN, ["Confidentiality loss"])], ""),
    "70": ("direct", [(HR, ["Privacy loss"]), (FIN, ["Confidentiality loss"])], ""),
    # --- Hardware-based IP security / anti-tamper / usage restrictions ----
    "71": ("direct", [(FIN, ["Confidentiality loss"]), (AUT, ["IP/copyright loss"])], ""),
    "72": ("direct", [(FIN, ["Confidentiality loss"]), (AUT, ["IP/copyright loss"])], ""),
    "73": ("enabling", [(FIN, ["Confidentiality loss"])], ""),
    "74": ("enabling", [(FIN, ["Confidentiality loss"])], ""),
    "75": ("enabling", [(FIN, ["Confidentiality loss"]), (AUT, ["IP/copyright loss"])], ""),
    "76": ("enabling", [(FIN, ["Confidentiality loss"])], ""),
    "77": ("enabling", [(FIN, ["Confidentiality loss"])], ""),
    "78": ("direct", [(POL, ["Power concentration"]), (SOC, ["Violence/armed conflict"])], ""),
    "79": ("direct", [(POL, ["Power concentration"]), (SOC, ["Violence/armed conflict"])], ""),
    # --- Model theft --------------------------------------------------------
    "80": ("direct", [(FIN, ["Confidentiality loss", "Business operations/infrastructure damage"]),
                      (AUT, ["IP/copyright loss"])], ""),
    "81": ("direct", [(FIN, ["Confidentiality loss"]), (AUT, ["IP/copyright loss"])], ""),
    # --- Shared model governance -------------------------------------------
    "82": ("direct", [(POL, ["Power concentration"])], ""),
    # --- Unlearning / disgorgement -----------------------------------------
    "83": ("direct", [(HR, ["Privacy loss"]), (AUT, ["IP/copyright loss"])],
           "Unlearning is the technical substrate of erasure/disgorgement rights."),
    "84": ("direct", [(HR, ["Privacy loss"]), (AUT, ["IP/copyright loss"])], ""),
    "85": ("direct", [(HR, ["Privacy loss"]), (AUT, ["IP/copyright loss"])], ""),
    # --- Adversarial attacks -------------------------------------------------
    "86": ("enabling", [(FIN, ["Business operations/infrastructure damage"]),
                        (PHY, ["Bodily injury"])],
           "Physical link is indirect: adversarial attacks on safety-critical systems."),
    "87": ("enabling", [(FIN, ["Business operations/infrastructure damage"]),
                        (PHY, ["Bodily injury"])], ""),
    # --- Modification-resistant models / dual-use --------------------------
    "88": ("direct", [(SOC, ["Violence/armed conflict"]),
                      (PSY, ["Harassment/abuse/intimidation"])], ""),
    "89": ("direct", [(SOC, ["Violence/armed conflict"]), (PHY, ["Loss of life"])],
           "Dual-use capability = CBRN/cyber; the clearest Physical-harm link in the catalog."),
    "90": ("direct", [(SOC, ["Violence/armed conflict"]), (PHY, ["Loss of life"])], ""),
    # --- Governance translation ---------------------------------------------
    "91": ("enabling", [], "Cross-cutting: 'which properties indicate risk' is harm-agnostic."),
    "92": ("enabling", [], "Cross-cutting standardisation."),
    # --- Deployment corrections ----------------------------------------------
    "93": ("enabling", [(REP, ["Loss of confidence/trust"])],
           "Post-deployment remediation applies to whatever flaw was found."),
    # --- Understanding risks / forecasting -----------------------------------
    "94": ("enabling", [], "Cross-cutting risk enumeration -- in principle spans all 9 types."),
    "95": ("enabling", [], "Cross-cutting domain differentiation."),
    "96": ("enabling", [], "Cross-cutting forecasting."),
    # --- Environmental --------------------------------------------------------
    "97": ("direct", [(ENV, ["Carbon emissions", "Excessive energy consumption"])],
           "RQ says 'environmental impact' generically; tools measure energy/carbon only."),
    "98": ("direct", [(ENV, ["Carbon emissions", "Excessive energy consumption"])],
           "Same: the other 6 environmental harms are not operationalised by any tool."),
}


def main() -> None:
    ctx = json.load(open("curation/rq_context.json"))["research_questions"]
    rqs = {r["rq_no"]: r for r in ctx}

    missing = set(rqs) - set(MAPPING)
    extra = set(MAPPING) - set(rqs)
    if missing or extra:
        print(f"WARNING unmapped RQs: {sorted(missing)}; unknown RQs in mapping: {sorted(extra)}")

    out = Path("curation/harm_taxonomy_mapping.csv")
    rows = []
    for rq_no, r in sorted(rqs.items(), key=lambda kv: int(kv[0])):
        kind, harms, note = MAPPING.get(rq_no, ("unmapped", [], ""))
        n_tools = len(r["tools_implement"]) + len(r["tools_eval"])
        rows.append({
            "rq_no": rq_no,
            "problem_area": r["problem_area"],
            "question": r["question"],
            "n_tools": n_tools,
            "mapping_kind": kind,
            "harm_types": " | ".join(h for h, _ in harms) or "(cross-cutting)",
            "specific_harms": " | ".join(s for _, ss in harms for s in ss),
            "note": note,
        })
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows -> {out}\n")

    # ---- Reverse view: harm type -> RQ and tool coverage -------------------
    by_type = defaultdict(lambda: {"direct": [], "enabling": []})
    for rq_no, (kind, harms, _) in MAPPING.items():
        for h, _s in harms:
            by_type[h][kind].append(rq_no)

    print(f"{'HARM TYPE':<34} {'RQs':>4} {'dir':>4} {'enab':>5} {'tooled':>7} {'zero':>5}")
    print("-" * 64)
    for h in TAXONOMY:
        d = sorted(set(by_type[h]["direct"]), key=int)
        e = sorted(set(by_type[h]["enabling"]), key=int)
        allrq = sorted(set(d) | set(e), key=int)
        tooled = [q for q in allrq
                  if len(rqs[q]["tools_implement"]) + len(rqs[q]["tools_eval"]) > 0]
        zero = [q for q in allrq if q not in tooled]
        print(f"{h:<34} {len(allrq):>4} {len(d):>4} {len(e):>5} {len(tooled):>7} {len(zero):>5}")

    # ---- Sharpest check: which of the 69 specific harms have NO RQ? --------
    covered = set()
    for _rq, (_k, harms, _n) in MAPPING.items():
        for _h, ss in harms:
            covered.update(ss)

    print("\n\nSPECIFIC HARMS WITH NO RQ ADDRESSING THEM")
    print("=" * 64)
    total_uncovered = 0
    for h, specifics in TAXONOMY.items():
        gaps = [s for s in specifics if s not in covered]
        total_uncovered += len(gaps)
        if gaps:
            print(f"\n{h}  ({len(gaps)}/{len(specifics)} uncovered)")
            for s in gaps:
                print(f"    - {s}")
    n_all = sum(len(v) for v in TAXONOMY.values())
    print(f"\n{total_uncovered}/{n_all} specific harms have no RQ; "
          f"{n_all - total_uncovered}/{n_all} have at least one.")


if __name__ == "__main__":
    main()
