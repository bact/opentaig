#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2026 OpenTAIG authors
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Map each research question to the harm type(s)/specific harm(s) it helps
address, using the AIAAIC Harms Taxonomy (Abercrombie, Benbouzid, Giudici,
Golpayegani, Hernandez, Noro, Pandit, Paraschou, Pownall, Prajapati, Sayre,
Sengupta, Suriyawongkul, Thelot, Vei, Waltersdorfer -- arXiv:2407.01294),
which has 9 top-level harm types and 69 specific harms.

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

WHY THIS IS NOW A GENUINE CROSSWALK, NOT JUST EDITORIAL JUDGMENT: an earlier
version of this mapping judged each RQ against a bare harm-type label (e.g.
"Autonomy") with no supporting text at all -- HARM_DEFINITIONS below didn't
exist, and the site's `terms` tab literally said "See the taxonomy's
Appendix A for the full definition" as a placeholder for all 69 specific
harms. This version reads each RQ's own text against every specific harm's
own one-sentence definition (verbatim from the published paper), the same
way the site's other five frameworks are crosswalked against an external
authority's own clause/article text. Produced by an isolated strongest-model
judgment pass given only {all 97 RQ texts, all 69 harm definitions, the
taxonomy's own real-world example incidents per harm (from AIAAIC's "AIAAIC
harms taxonomy - v1.8" working document) for disambiguation} -- no prior
mapping, no other session context, per this project's model-tiering rule
(see curation/README.md).

VERSIONING NOTE: one harm's definition ("Sexualisation") changed materially
between the published arXiv paper (2024-07: "Sexual interest in a technology
or application") and AIAAIC's own v1.8 working document (Nov 2024: "The
non-consensual sexualisation of an individual or group using a technology or
application"). HARM_DEFINITIONS uses the v1.8 wording for that one entry
(see its inline comment) because it's the org's own more current revision
and the arXiv wording read as a near category-error against the taxonomy's
own example incidents (CSAM, deepfake sexualisation of real people). Other
harms may have similar unreviewed phrasing drift between the two documents
-- this one was caught only because it changed a mapping decision (RQ6).
Worth a full definition-by-definition reconciliation pass against v1.8 if
that matters for citation precision.

CAVEAT: still a starting point for expert review, not a validated
instrument -- judgment calls flagged in each RQ's `note`.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

# --- The taxonomy: 9 harm types, 69 specific harms (arXiv:2407.01294, Appendix A)
TAXONOMY = {
    "Autonomy": [
        "Autonomy/agency loss",
        "Impersonation/identity theft",
        "IP/copyright loss",
        "Personality rights loss",
    ],
    "Physical": [
        "Bodily injury",
        "Loss of life",
        "Personal health deterioration",
        "Property damage",
    ],
    "Psychological": [
        "Addiction",
        "Alienation/isolation",
        "Anxiety/depression",
        "Coercion/manipulation",
        "Dehumanisation/objectification",
        "Harassment/abuse/intimidation",
        "Over-reliance",
        "Radicalisation",
        "Self-harm",
        "Sexualisation",
        "Trauma",
    ],
    "Reputational": ["Defamation/libel/slander", "Loss of confidence/trust"],
    "Financial and Business": [
        "Business operations/infrastructure damage",
        "Confidentiality loss",
        "Financial/earnings loss",
        "Livelihood loss",
        "Increased competition",
        "Monopolisation",
        "Opportunity loss",
    ],
    "Human Rights and Civil Liberties": [
        "Benefits/entitlements loss",
        "Dignity loss",
        "Discrimination",
        "Loss of freedom of speech/expression",
        "Loss of freedom of assembly/association",
        "Loss of social rights and access to public services",
        "Loss of right to information",
        "Loss of right to free elections",
        "Loss of right to liberty and security",
        "Loss of right to due process",
        "Privacy loss",
    ],
    "Societal and Cultural": [
        "Breach of ethics/values/norms",
        "Cheating/plagiarism",
        "Chilling effect",
        "Cultural dispossession",
        "Damage to public health",
        "Historical revisionism",
        "Information degradation",
        "Job loss/losses",
        "Labour exploitation",
        "Loss of creativity/critical thinking",
        "Stereotyping",
        "Public service delivery deterioration",
        "Societal destabilisation",
        "Societal inequality",
        "Violence/armed conflict",
    ],
    "Political and Economic": [
        "Critical infrastructure damage",
        "Economic instability",
        "Power concentration",
        "Electoral interference",
        "Institutional trust loss",
        "Political instability",
        "Political manipulation",
    ],
    "Environmental": [
        "Biodiversity loss",
        "Carbon emissions",
        "Electronic waste",
        "Excessive energy consumption",
        "Excessive landfill",
        "Excessive water consumption",
        "Natural resource depletion",
        "Pollution",
    ],
}

AUT, PHY, PSY, REP = "Autonomy", "Physical", "Psychological", "Reputational"
FIN = "Financial and Business"
HR = "Human Rights and Civil Liberties"
SOC = "Societal and Cultural"
POL = "Political and Economic"
ENV = "Environmental"

# --- Each specific harm's own one-sentence definition (verbatim from
# arXiv:2407.01294's Appendix A, except "Sexualisation" -- see VERSIONING
# NOTE above). This is what makes the RQ mapping below a genuine crosswalk.
HARM_DEFINITIONS = {
    # --- Autonomy ---
    "Autonomy/agency loss": "Loss of an individual, group or organisation's ability to make informed decisions or pursue goals.",
    "Impersonation/identity theft": "Theft of an individual, group or organisation's identity by a third-party in order to defraud, mock or otherwise harm them.",
    "IP/copyright loss": "Misuse or abuse of an individual or organisation's intellectual property, including copyright, trademarks, and patents.",
    "Personality rights loss": "Loss of or restrictions to the rights of an individual to control the commercial use of their identity, such as name, image, likeness, or other unequivocal identifiers.",
    # --- Physical ---
    "Bodily injury": "Physical pain, injury, illness, or disease suffered by an individual or group due to the malfunction, use or misuse of a technology system.",
    "Loss of life": "Accidental or deliberate loss of life, including suicide, extinction or cessation, due to the use or misuse of a technology system.",
    "Personal health deterioration": "Physical deterioration of an individual or animal over time, increasing their risk of disease, organ failure, prolonged hospital stay or death, etc.",
    "Property damage": "Action(s) that lead directly or indirectly to the damage or destruction of tangible property eg. buildings, possessions, vehicles, robots.",
    # --- Psychological ---
    "Addiction": "Emotional or material dependence on technology or a technology system.",
    "Alienation/isolation": "An individual's or group's feeling of lack of connection with those around as a result of technology use or misuse.",
    "Anxiety/depression": "Mental health decline due to addiction, negative social interactions such as humiliation and shaming and traumatic distressing events such as online violence or rape.",
    "Coercion/manipulation": "Use of a technology system to covertly alter user beliefs and behaviour using nudging, dark patterns and/or other opaque techniques, resulting in potential erosion of privacy, addiction, anxiety/distress, etc.",
    "Dehumanisation/objectification": "Use or misuse of a technology system to depict and/or treat people as not human, less than human, or as objects.",
    "Harassment/abuse/intimidation": "Online behaviour, including sexual harassment, that makes an individual or group feel alarmed or threatened.",
    "Over-reliance": "Unfettered and/or obsessive belief in the accuracy or other quality of a technology system, resulting in addiction, anxiety, introversion, sentience, complacency, lack of critical thinking and other actual or potential negative impacts.",
    "Radicalisation": "Adoption of extreme political, social, or religious ideals and aspirations due to the nature or misuse of an algorithmic system, potentially resulting in abuse, violence, or terrorism.",
    "Self-harm": "Intentional seeking out or sharing of hurtful content about oneself that leads to, supports, or exacerbates low self-esteem and self-harm.",
    # NOTE: this harm's definition changed between the published paper
    # (arXiv:2407.01294, 2024-07: "Sexual interest in a technology or
    # application") and AIAAIC's own working document ("AIAAIC harms
    # taxonomy - v1.8", Nov 2024): "The non-consensual sexualisation of an
    # individual or group using a technology or application." The v1.8
    # wording is used here as the more current, more precise, and org's-own
    # revision -- the arXiv definition reads almost as a category error
    # (implying attraction *to* a technology) and doesn't match how the
    # taxonomy's own example incidents use the term (CSAM, deepfake
    # sexualisation of real people). Other harms may have similar
    # phrasing drift between the two documents that wasn't individually
    # verified -- this one was caught because it changed a mapping
    # decision (RQ6).
    "Sexualisation": "The non-consensual sexualisation of an individual or group using a technology or application.",
    "Trauma": "Severe and lasting emotional shock and pain caused by an extremely upsetting experience.",
    # --- Reputational ---
    "Defamation/libel/slander": "Use of a technology system to create, facilitate or amplify false perception(s) about an individual, group, or organisation.",
    "Loss of confidence/trust": "Misleading or unfair change(s) in how an individual, group, or organisation is viewed, leading to loss of ability to conduct relationships, raise capital, recruit people, etc.",
    # --- Financial and Business ---
    "Business operations/infrastructure damage": "Damage, disruption, or destruction of a business system and/or its components due to malfunction, cyberattacks, etc.",
    "Confidentiality loss": "Unauthorised sharing of sensitive, confidential information and documents such as corporate strategy and financial plans with third-parties.",
    "Financial/earnings loss": "Loss of money, income or value due to the use or misuse of a technology system.",
    "Livelihood loss": "An individual or group's loss of ability to support themselves financially or vocationally due to natural disasters, lack of demand for products/services, cost increases, etc, resulting in inability to procure food, reduced employment prospects, bankruptcy, foreclosure, homelessness, etc.",
    "Increased competition": "The inappropriate or unethical use of technology to gain market share.",
    "Monopolisation": "Abuse of market power through the control of prices, thereby limiting competition and creating unfair barriers to entry.",
    "Opportunity loss": "Loss of ability to take advantage of a financial or other opportunity, such as education, employability/securing a job.",
    # --- Human Rights and Civil Liberties ---
    "Benefits/entitlements loss": "Denial or loss of access to welfare benefits, pensions, housing, etc due to the malfunction, use or abuse of a technology system.",
    "Dignity loss": "Perceived loss of value experienced by or disrespect shown to an individual or group, resulting in self-sheltering, loss of connections and relationships, and public stigmatisation.",
    "Discrimination": "Unfair or inadequate treatment or arbitrary distinction based on a person's race, ethnicity, age, gender, sexual preference, religion, national origin, marital status, disability, language, or other protected groups.",
    "Loss of freedom of speech/expression": "Restrictions to or loss of people's right to articulate their opinions and ideas without fear of retaliation, censorship, or legal sanction.",
    "Loss of freedom of assembly/association": "Restrictions to or loss of people's right to come together and collectively express, promote, pursue, and defend their collective or shared ideas, and/or to join an association.",
    "Loss of social rights and access to public services": "Restrictions to or loss of rights to work, social security, and adequate standard of living, housing, health and education.",
    "Loss of right to information": "Restrictions to or loss of people's right to seek, receive and impart information held by public bodies.",
    "Loss of right to free elections": "Restrictions to or loss of people's right to participate in free elections at reasonable intervals by secret ballot.",
    "Loss of right to liberty and security": "Restrictions to or loss of liberty as a result of illegal or arbitrary arrest or false imprisonment.",
    "Loss of right to due process": "Restrictions to or loss of right to be treated fairly, efficiently and effectively by the administration of justice.",
    "Privacy loss": "Unwarranted exposure of an individual's private life or personal data through cyberattacks, doxxing, etc.",
    # --- Societal and Cultural ---
    "Breach of ethics/values/norms": "An actual or perceived violation or deviation from the established societal values, norms or ethical standards or principles.",
    "Cheating/plagiarism": "Use of another person's or group's words or ideas without consent and/or acknowledgement.",
    "Chilling effect": "The creation of a climate of self-censorship that deters democratic actors such as journalists, advocates and judges from speaking out.",
    "Cultural dispossession": "Intentional and/or unintentional erasure of cultural goods and values, such as ways of speaking, expressing humour, or sounds and voices that contribute to a cultural identity, or their inappropriate re-use in other cultures.",
    "Damage to public health": "Adverse impacts on the health of groups, communities or societies, including malnutrition, disease and infection conditions.",
    "Historical revisionism": "Deliberate or unintentional reinterpretation of established/orthodox historical events or accounts held by societies, communities, academics.",
    "Information degradation": "Creation or spread of false, hallucinatory, low-quality, misleading, or inaccurate information that degrades the information ecosystem and causes people to develop false or inaccurate perceptions, decisions and beliefs; or to lose trust in accurate information.",
    "Job loss/losses": "Replacement/displacement of human jobs by a technology system, leading to increased unemployment, inequality, reduced consumer spending, and social friction.",
    "Labour exploitation": "Use of under-paid and/or offshore labour to develop, manage or optimise a technology system.",
    "Loss of creativity/critical thinking": "Devaluation and/or deterioration of human creativity, artistic expression, imagination, critical thinking or problem-solving skills.",
    "Stereotyping": "Derogatory or otherwise harmful stereotyping or homogenisation of individuals, groups, societies or cultures due to the mis-representation, over-representation, under-representation, or non-representation of specific identities, groups, or perspectives.",
    "Public service delivery deterioration": "Poor performance of a public technology system due to malfunction, over-use, under-staffing etc, resulting in individuals, groups, or organisations unable to use it in a manner they can reasonably expect.",
    "Societal destabilisation": "Societal instability in the form of strikes, demonstrations and other types of civil unrest caused by loss of jobs to technology, unfair algorithmic outcomes, disinformation, etc.",
    "Societal inequality": "Increased difference in social status or wealth between individuals or groups caused or amplified by a technology system, leading to the loss of social and community wellbeing/cohesion and destabilisation.",
    "Violence/armed conflict": "Use or misuse of a technology system to incite, facilitate or conduct cyberattacks, security breaches, lethal, biological and chemical weapons development, resulting in violence and armed conflict.",
    # --- Political and Economic ---
    "Critical infrastructure damage": "Damage, disruption to or destruction of systems essential to the functioning and safety of a nation or state, including energy, transport, health, finance, and communication systems.",
    "Economic instability": "Uncontrolled fluctuations impacting the financial system, or parts thereof, due to the use or misuse of a technology system, or set of systems.",
    "Power concentration": "Amplification of concentration of economic and/or political wealth and power, potentially resulting in increased inequality and instability.",
    "Electoral interference": "Generation of false or misleading information that can interrupt or mislead voters and/or undermine trust in electoral processes.",
    "Institutional trust loss": "Erosion of trust in public institutions and weakened checks and balances due to mis/disinformation, influence operations, over-dependence on technology, etc.",
    "Political instability": "Political polarisation or unrest caused by increased inequality, job losses, over-dependence on technology making societies vulnerable to systemic failures, etc, arising from or amplified by the use or misuse of a technology system.",
    "Political manipulation": "Use or misuse of personal data to target individuals' interests, personalities and vulnerabilities with tailored political messages via micro-advertising or deepfakes/synthetic media.",
    # --- Environmental ---
    "Biodiversity loss": "Over-expansion of technology infrastructure, or inadequate alignment of technology with sustainable practices, leading to deforestation, habitat destruction, and fragmentation and loss of biodiversity.",
    "Carbon emissions": "Release of carbon dioxide, nitric oxide and other gases, increasing carbon emissions, exacerbating climate change, and negatively impacting local communities.",
    "Electronic waste": "Electrical or electronic equipment that is waste, including all components, sub-assemblies and consumables that are part of the equipment at the time the equipment becomes waste.",
    "Excessive energy consumption": "Excessive energy use, leading to energy bottlenecks and shortages for communities, organisations, and businesses.",
    "Excessive landfill": "Excessive disposal of electrical or electronic equipment leading to ecological/biodiversity damage, and disrupting the livelihoods and eroding the rights of local communities.",
    "Excessive water consumption": "Excessive use of water to cool data centres and for other purposes, leading to water restrictions or shortages for local communities or businesses.",
    "Natural resource depletion": "Extraction of minerals, metals, rare earths, and fossil fuels that deplete natural resources and increase carbon emissions.",
    "Pollution": "Actual or potential pollution to the air, ground, noise, or water caused by a technology system.",
}


MAPPING = {
    "1": (
        "direct",
        [
            (HR, ["Privacy loss"]),
            (AUT, ["IP/copyright loss"]),
            (SOC, ["Information degradation"]),
        ],
        '"Problematic data" at web scale is concretely personal data, unlicensed copyrighted works, and low-quality/false text; scaling detection is what prevents each from entering training corpora.',
    ),
    "2": (
        "direct",
        [(AUT, ["IP/copyright loss"])],
        '"Prevent training on unlicensed data" is a verbatim match for misuse of an individual or organisation\'s copyright.',
    ),
    "3": ("direct", [(AUT, ["IP/copyright loss"])], ""),
    "4": (
        "direct",
        [
            (HR, ["Privacy loss"]),
            (AUT, ["IP/copyright loss"]),
            (SOC, ["Information degradation"]),
        ],
        "Same target harms as RQ1; the contribution is doing the detection under restricted access.",
    ),
    "5": (
        "direct",
        [(SOC, ["Information degradation"]), (HR, ["Privacy loss"])],
        "Contamination with problematic samples (poisoned or otherwise harmful text) degrades what the trained system then outputs; personal data is the other canonical contaminant.",
    ),
    "6": (
        "direct",
        [
            (SOC, ["Violence/armed conflict"]),
            (HR, ["Privacy loss"]),
            (PSY, ["Sexualisation"]),
        ],
        "Removal-without-signposting framing covers hazardous content (weapons/attack material) and personal data; also covers non-consensual sexual content (e.g. CSAM) in corpora under AIAAIC v1.8's revised Sexualisation definition (non-consensual sexualisation via a technology), which differs from the arXiv paper's older wording.",
    ),
    "7": (
        "direct",
        [
            (AUT, ["IP/copyright loss", "Personality rights loss"]),
            (HR, ["Privacy loss"]),
        ],
        "Licence/metadata reporting is the mechanism by which copyright, personal data and likeness/voice-consent claims over training material can be traced and honoured.",
    ),
    "8": (
        "enabling",
        [(HR, ["Privacy loss"]), (AUT, ["IP/copyright loss"]), (SOC, ["Stereotyping"])],
        "Generic audit infrastructure, but the harms large-dataset audits actually surface are personal data, unlicensed material, and representational skew.",
    ),
    "9": (
        "direct",
        [(SOC, ["Stereotyping"]), (HR, ["Discrimination"])],
        '"Persistent bias" as a macro-scale dataset property is precisely over-/under-/non-representation of groups, which then yields unfair treatment on protected attributes.',
    ),
    "10": (
        "enabling",
        [(AUT, ["IP/copyright loss"]), (HR, ["Privacy loss"]), (SOC, ["Stereotyping"])],
        '"Suitability for training" is judged mainly on licensing, personal data, and representational composition.',
    ),
    "11": (
        "direct",
        [(SOC, ["Information degradation", "Stereotyping"])],
        "Links problematic training data to degraded and skewed downstream outputs.",
    ),
    "12": (
        "enabling",
        [
            (AUT, ["IP/copyright loss"]),
            (SOC, ["Cheating/plagiarism", "Information degradation"]),
        ],
        "Training-data attribution is the technical basis for copyright claims and for acknowledging whose words/ideas a generation reproduces, and for tracing hallucinations back to their source data.",
    ),
    "13": (
        "enabling",
        [(SOC, ["Violence/armed conflict"]), (POL, ["Power concentration"])],
        "Chip-specification thresholds are the foundation of compute controls, whose stated purpose is limiting uplift to dangerous capabilities and unchecked concentration of frontier capability.",
    ),
    "14": (
        "enabling",
        [(POL, ["Power concentration"]), (SOC, ["Violence/armed conflict"])],
        "Governability of compute is what keeps frontier capability from concentrating and from being diverted to weapons/attack development.",
    ),
    "15": (
        "enabling",
        [(SOC, ["Violence/armed conflict"]), (POL, ["Power concentration"])],
        "Establishes whether distributed small-cluster training can evade compute-based controls.",
    ),
    "16": (
        "enabling",
        [(SOC, ["Violence/armed conflict"]), (POL, ["Power concentration"])],
        "Detecting decentralised training closes the main evasion route for the same controls.",
    ),
    "17": (
        "direct",
        [(SOC, ["Violence/armed conflict"]), (FIN, ["Confidentiality loss"])],
        'The RQ explicitly conditions detection on "retaining developer privacy", which is the taxonomy\'s Confidentiality loss (corporate/strategic information), not personal Privacy loss.',
    ),
    "18": (
        "enabling",
        [(SOC, ["Violence/armed conflict"])],
        "Workload classification is the measurement substrate for compute-governance regimes aimed at unsanctioned frontier training.",
    ),
    "19": (
        "enabling",
        [],
        "Genuinely harm-agnostic: evaluation thoroughness and blindspot discovery apply identically to every harm in the taxonomy, so naming any subset would be arbitrary.",
    ),
    "20": (
        "enabling",
        [(PSY, ["Over-reliance"]), (SOC, ["Information degradation"])],
        "Contaminated benchmarks inflate apparent capability/safety, producing exactly the unwarranted belief in system quality and complacency that Over-reliance describes.",
    ),
    "21": (
        "enabling",
        [(PSY, ["Over-reliance"])],
        "The RQ's stated object is a model's \"limitations and weaknesses\"; making those legible is the counter to unfettered belief in system accuracy.",
    ),
    "22": (
        "enabling",
        [
            (SOC, ["Violence/armed conflict", "Information degradation"]),
            (PSY, ["Harassment/abuse/intimidation"]),
        ],
        "Red-teaming at scale is targeted at the standard misuse categories: attack/weapons uplift, disinformation generation, and abusive content.",
    ),
    "23": (
        "enabling",
        [
            (SOC, ["Violence/armed conflict"]),
            (POL, ["Critical infrastructure damage"]),
            (AUT, ["Autonomy/agency loss"]),
        ],
        "Agent evaluation targets autonomous action risks: cyber/attack capability, disruption of essential systems, and humans losing effective control over decisions taken on their behalf.",
    ),
    "24": (
        "enabling",
        [
            (POL, ["Economic instability", "Critical infrastructure damage"]),
            (SOC, ["Violence/armed conflict"]),
        ],
        "Interacting-agent networks are the case where emergent collective behaviour hits markets and essential systems, not just individual users.",
    ),
    "25": (
        "enabling",
        [(SOC, ["Societal destabilisation", "Societal inequality", "Job loss/losses"])],
        '"Downstream societal impacts" maps to the taxonomy\'s societal tier; these three are the impacts impact-assessment work most often instruments.',
    ),
    "26": (
        "direct",
        [(HR, ["Discrimination"]), (SOC, ["Stereotyping"])],
        "Language is an explicitly protected attribute in the Discrimination definition, so evaluation coverage gaps across languages/modalities are themselves the mechanism by which unequal and skewed treatment goes unmeasured.",
    ),
    "27": (
        "enabling",
        [(PSY, ["Over-reliance"]), (SOC, ["Information degradation"])],
        "Invalid benchmarks produce false beliefs about what a system can safely do.",
    ),
    "28": (
        "enabling",
        [],
        "Simulation-environment fidelity is a cross-cutting evaluation-methodology question with no specific harm attached.",
    ),
    "29": ("direct", [(HR, ["Privacy loss"]), (FIN, ["Confidentiality loss"])], ""),
    "30": ("direct", [(HR, ["Privacy loss"])], ""),
    "31": (
        "enabling",
        [(PSY, ["Over-reliance"]), (SOC, ["Information degradation"])],
        "Protects the integrity of the measurements on which safety claims rest.",
    ),
    "32": (
        "enabling",
        [(PSY, ["Over-reliance"]), (SOC, ["Information degradation"])],
        "Same evaluation-integrity target as RQ31, approached from the hosting side.",
    ),
    "33": (
        "direct",
        [(SOC, ["Societal inequality"]), (POL, ["Power concentration"])],
        '"Fairly and equitably between users" targets differential access to compute as an amplifier of status/wealth gaps and of concentrated capability.',
    ),
    "34": (
        "direct",
        [(FIN, ["Monopolisation"]), (POL, ["Power concentration"])],
        "Interoperability of public compute is the direct counter to lock-in and unfair barriers to entry.",
    ),
    "35": (
        "enabling",
        [(SOC, ["Public service delivery deterioration", "Violence/armed conflict"])],
        "Assurance over publicly funded compute guards both against waste/misallocation of a public system and against diversion of subsidised compute to prohibited uses.",
    ),
    "36": (
        "enabling",
        [(HR, ["Discrimination", "Privacy loss"]), (SOC, ["Information degradation"])],
        "Access-tier methodology is generic, but the harms third-party audits are actually commissioned to find are unfair treatment, personal-data exposure, and inaccurate output.",
    ),
    "37": (
        "direct",
        [(SOC, ["Violence/armed conflict", "Information degradation"])],
        '"Risks of misuse" of released models resolves to attack/weapons uplift and mass generation of false content.',
    ),
    "38": (
        "direct",
        [(AUT, ["IP/copyright loss"]), (FIN, ["Confidentiality loss"])],
        "Model theft/duplication is misappropriation of the developer's IP and of confidential technical assets.",
    ),
    "39": (
        "direct",
        [(FIN, ["Confidentiality loss"]), (AUT, ["IP/copyright loss"])],
        'The "commercial concerns" side of the trade-off is exactly the confidentiality and IP interest the taxonomy names.',
    ),
    "40": ("direct", [(HR, ["Privacy loss"])], ""),
    "41": (
        "enabling",
        [(HR, ["Privacy loss"])],
        "Allocating data-access duties along the value chain determines who is accountable for exposure of user data.",
    ),
    "42": (
        "direct",
        [(HR, ["Privacy loss"]), (FIN, ["Confidentiality loss"])],
        '"Without revealing individual user identities or sensitive information" matches both the personal and the confidential-information harms.',
    ),
    "43": (
        "direct",
        [(HR, ["Privacy loss"]), (FIN, ["Confidentiality loss"])],
        "MPC across value-chain entities protects both data subjects and each party's commercially sensitive holdings.",
    ),
    "44": (
        "direct",
        [(AUT, ["IP/copyright loss"]), (HR, ["Privacy loss"])],
        "Dataset-membership verification is the evidentiary basis for both copyright claims and data-subject claims against a model.",
    ),
    "45": (
        "direct",
        [(HR, ["Privacy loss"]), (AUT, ["IP/copyright loss"])],
        '"Does not include certain information" is in practice personal data or licensed material.',
    ),
    "46": (
        "direct",
        [(HR, ["Privacy loss"]), (AUT, ["IP/copyright loss"])],
        "Membership inference repurposed as an audit tool serves the same two claims as RQ44.",
    ),
    "47": ("direct", [(AUT, ["IP/copyright loss"])], ""),
    "48": (
        "direct",
        [(SOC, ["Violence/armed conflict"]), (POL, ["Power concentration"])],
        "Chip-location verification exists to enforce export controls against diversion to hostile military/attack use.",
    ),
    "49": (
        "direct",
        [(SOC, ["Violence/armed conflict"])],
        "Anti-spoofing hardens the same export-control enforcement.",
    ),
    "50": (
        "enabling",
        [(SOC, ["Violence/armed conflict"]), (FIN, ["Confidentiality loss"])],
        "TEE attestation supports compute-use verification while shielding the attested workload's contents from the verifier.",
    ),
    "51": (
        "enabling",
        [(SOC, ["Violence/armed conflict"])],
        "Alternative route to the same compute-usage verification goal.",
    ),
    "52": (
        "direct",
        [
            (HR, ["Privacy loss"]),
            (FIN, ["Confidentiality loss"]),
            (SOC, ["Chilling effect"]),
        ],
        'This RQ is explicitly about the governance mechanism\'s own misuse potential -- "unnecessarily-broad surveillance" -- so it targets exposure of personal and corporate information and the self-censorship such monitoring induces.',
    ),
    "53": (
        "enabling",
        [(SOC, ["Violence/armed conflict"])],
        "Overhead reduction is what makes the compute-verification regime deployable at cluster scale; no harm of its own.",
    ),
    "54": (
        "enabling",
        [],
        '"Model properties" is left unspecified in the RQ text, so any harm list would be invented rather than grounded.',
    ),
    "55": (
        "direct",
        [
            (SOC, ["Violence/armed conflict", "Information degradation"]),
            (PSY, ["Self-harm"]),
        ],
        "Per-query risk assessment against safety requirements targets the canonical refusal categories: attack/weapons assistance, false information, and self-harm-related content.",
    ),
    "56": (
        "enabling",
        [(POL, ["Institutional trust loss"])],
        "Model registries are an oversight instrument; the harm they guard against is erosion of the checks and balances that make public scrutiny of AI meaningful.",
    ),
    "57": (
        "direct",
        [(AUT, ["IP/copyright loss"])],
        "Model ownership is the IP interest at stake.",
    ),
    "58": (
        "direct",
        [(AUT, ["IP/copyright loss"])],
        "Spoofing-resistance protects the same ownership claim from false assertion.",
    ),
    "59": (
        "enabling",
        [(POL, ["Institutional trust loss"]), (REP, ["Loss of confidence/trust"])],
        "End-to-end audit registries underpin both public-institutional oversight and the ability of counterparties to trust a supplier's claims.",
    ),
    "61": (
        "direct",
        [(PSY, ["Over-reliance"]), (REP, ["Loss of confidence/trust"])],
        "Presentation to users is about calibrating user belief in a system's verified status -- too much yields complacency, too little or misleading presentation yields unwarranted distrust.",
    ),
    "62": (
        "direct",
        [(FIN, ["Confidentiality loss"]), (AUT, ["IP/copyright loss"])],
        'ZK proofs are proposed precisely so compliance can be demonstrated "without directly disclosing architectural details".',
    ),
    "63": (
        "enabling",
        [(POL, ["Institutional trust loss"]), (REP, ["Loss of confidence/trust"])],
        "Guards against the audited-model/deployed-model swap, which would hollow out every downstream assurance.",
    ),
    "64": (
        "enabling",
        [(SOC, ["Violence/armed conflict", "Information degradation"])],
        "Verifying that safety measures are actually live at deployment protects the misuse categories those measures exist to block.",
    ),
    "65": (
        "direct",
        [
            (SOC, ["Information degradation"]),
            (AUT, ["Impersonation/identity theft"]),
            (POL, ["Electoral interference"]),
        ],
        "Robust watermarking is the provenance signal against synthetic false content, deepfake impersonation, and voter-targeted fabrication.",
    ),
    "66": (
        "direct",
        [(SOC, ["Information degradation"]), (AUT, ["Impersonation/identity theft"])],
        "Metadata-level provenance serves the same synthetic-content harms as RQ65.",
    ),
    "67": (
        "direct",
        [
            (SOC, ["Information degradation", "Cheating/plagiarism"]),
            (POL, ["Electoral interference"]),
        ],
        "Detector robustness governs whether synthetic disinformation, election fabrication, and unacknowledged AI-authored work can be identified at all.",
    ),
    "68": (
        "direct",
        [
            (SOC, ["Information degradation", "Cheating/plagiarism"]),
            (REP, ["Defamation/libel/slander"]),
        ],
        "This RQ is about detector false positives on genuine-but-edited material; the AIAAIC precedent (AI detectors falsely accusing students) shows the harm is a false accusation about a person's work, not just ecosystem noise.",
    ),
    "69": (
        "direct",
        [(HR, ["Privacy loss"]), (FIN, ["Confidentiality loss"])],
        "Training-data extraction exposes memorised personal data and confidential documents.",
    ),
    "70": ("direct", [(HR, ["Privacy loss"]), (FIN, ["Confidentiality loss"])], ""),
    "71": (
        "direct",
        [
            (AUT, ["IP/copyright loss"]),
            (
                FIN,
                ["Confidentiality loss", "Business operations/infrastructure damage"],
            ),
        ],
        "Cluster-level hardware security protects weights as IP, the confidential material they encode, and the cluster itself as a business system against cyberattack.",
    ),
    "72": (
        "direct",
        [(AUT, ["IP/copyright loss"]), (SOC, ["Violence/armed conflict"])],
        "On-chip licence enforcement is simultaneously an IP-protection mechanism and a use-restriction mechanism against unapproved deployment.",
    ),
    "73": (
        "enabling",
        [
            (FIN, ["Business operations/infrastructure damage"]),
            (SOC, ["Violence/armed conflict"]),
        ],
        "Secure firmware update prevents attackers from subverting the on-chip governance layer that the other compute-security RQs depend on.",
    ),
    "74": (
        "direct",
        [(FIN, ["Confidentiality loss"]), (AUT, ["IP/copyright loss"])],
        "TEE security on accelerators is what keeps processed data and weights from third-party exposure.",
    ),
    "75": (
        "enabling",
        [(AUT, ["IP/copyright loss"]), (SOC, ["Violence/armed conflict"])],
        "Anti-tamper protects weights physically and keeps diverted/repurposed accelerators from silently escaping controls.",
    ),
    "76": (
        "enabling",
        [(AUT, ["IP/copyright loss"]), (SOC, ["Violence/armed conflict"])],
        "Same target as RQ75, assessed empirically.",
    ),
    "77": (
        "enabling",
        [(AUT, ["IP/copyright loss"]), (SOC, ["Violence/armed conflict"])],
        "Self-destruct on tamper is a last-resort protection of weights and of the control regime; the property damage it causes is intended, not a harm the research addresses.",
    ),
    "78": (
        "direct",
        [(SOC, ["Violence/armed conflict"]), (POL, ["Power concentration"])],
        "Preventing unsanctioned frontier training is aimed at capability uplift for attack/weapons work and at unchecked capability concentration.",
    ),
    "79": (
        "direct",
        [(SOC, ["Violence/armed conflict"]), (POL, ["Power concentration"])],
        "Conditional export enforcement is the same control regime applied at the border.",
    ),
    "80": (
        "direct",
        [
            (AUT, ["IP/copyright loss"]),
            (FIN, ["Confidentiality loss"]),
            (SOC, ["Violence/armed conflict"]),
        ],
        "Weight theft is both an IP/confidentiality loss for the developer and the fastest route by which a safeguarded model reaches an actor who will strip its safeguards.",
    ),
    "81": (
        "direct",
        [(AUT, ["IP/copyright loss"]), (FIN, ["Confidentiality loss"])],
        "",
    ),
    "82": (
        "enabling",
        [(POL, ["Power concentration"]), (SOC, ["Violence/armed conflict"])],
        "Shared governance mechanisms exist so no single party holds unilateral control over a high-capability model.",
    ),
    "83": (
        "direct",
        [(HR, ["Privacy loss"]), (AUT, ["IP/copyright loss"])],
        "Unlearning/disgorgement is the remedy demanded in data-subject erasure and copyright-infringement cases; evaluating it determines whether that remedy is real.",
    ),
    "84": (
        "direct",
        [(SOC, ["Information degradation"]), (HR, ["Privacy loss"])],
        "Collateral removal of untargeted concepts degrades the model's factual output quality, which is the cost side of an otherwise privacy/IP-motivated intervention.",
    ),
    "85": (
        "direct",
        [(HR, ["Privacy loss", "Discrimination"]), (AUT, ["IP/copyright loss"])],
        "Discrimination is included because language is a protected attribute in its definition: unlearning that works only in high-resource languages delivers the erasure remedy unequally.",
    ),
    "86": (
        "enabling",
        [
            (SOC, ["Violence/armed conflict"]),
            (FIN, ["Business operations/infrastructure damage"]),
        ],
        "Adversarial-attack detection at deployment guards against both the safeguard-bypass route to dangerous outputs and the disruption of the deployed system itself.",
    ),
    "87": (
        "enabling",
        [
            (SOC, ["Violence/armed conflict"]),
            (FIN, ["Business operations/infrastructure damage"]),
        ],
        "Response-side counterpart to RQ86.",
    ),
    "88": (
        "direct",
        [(SOC, ["Violence/armed conflict", "Information degradation"])],
        'Fine-tuning for "malicious tasks" is the standard safeguard-stripping pathway to attack-capable and disinformation-optimised models.',
    ),
    "89": (
        "direct",
        [(SOC, ["Violence/armed conflict"]), (POL, ["Critical infrastructure damage"])],
        '"Dual-use capabilities" in this literature means CBRN and offensive-cyber assistance.',
    ),
    "90": (
        "direct",
        [(SOC, ["Violence/armed conflict"]), (POL, ["Critical infrastructure damage"])],
        "Identity-gating is the access-control counterpart to RQ89's detection.",
    ),
    "91": (
        "enabling",
        [],
        "Asks which properties should be regulatory targets at all; deliberately harm-agnostic across the whole taxonomy.",
    ),
    "92": (
        "enabling",
        [],
        "Standardisation methodology applying to any safety or reliability requirement, hence to any harm.",
    ),
    "93": (
        "enabling",
        [],
        "Post-deployment correction is a remediation capability that applies to whichever harm the discovered flaw happens to produce.",
    ),
    "94": (
        "enabling",
        [],
        "This is the meta-question that the harm taxonomy itself answers; mapping it to a subset of harms would be circular.",
    ),
    "95": (
        "enabling",
        [],
        "Domain-comparative risk question spanning the full taxonomy.",
    ),
    "96": (
        "enabling",
        [],
        "Forecasting methodology with no harm-specific commitment in the question text.",
    ),
    "97": (
        "direct",
        [
            (
                ENV,
                [
                    "Carbon emissions",
                    "Excessive energy consumption",
                    "Excessive water consumption",
                    "Electronic waste",
                ],
            )
        ],
        "Names environmental impact explicitly; these four are the environmental harms that reporting/disclosure requirements can actually capture (as against upstream extraction and pollution, which the RQ does not reach).",
    ),
    "98": (
        "direct",
        [
            (
                ENV,
                [
                    "Carbon emissions",
                    "Excessive energy consumption",
                    "Excessive water consumption",
                    "Electronic waste",
                ],
            )
        ],
        "Measurement-side counterpart to RQ97.",
    ),
}


def main() -> None:
    ctx = json.load(open("curation/rq_context.json"))["research_questions"]
    rqs = {r["rq_no"]: r for r in ctx}

    missing = set(rqs) - set(MAPPING)
    extra = set(MAPPING) - set(rqs)
    if missing or extra:
        print(
            f"WARNING unmapped RQs: {sorted(missing)}; unknown RQs in mapping: {sorted(extra)}"
        )

    out = Path("curation/aiaaic_taxonomy_mapping.csv")
    rows = []
    for rq_no, r in sorted(rqs.items(), key=lambda kv: int(kv[0])):
        kind, harms, note = MAPPING.get(rq_no, ("unmapped", [], ""))
        n_tools = len(r["tools_implement"]) + len(r["tools_eval"])
        rows.append(
            {
                "rq_no": rq_no,
                "problem_area": r["problem_area"],
                "question": r["question"],
                "n_tools": n_tools,
                "mapping_kind": kind,
                "harm_types": " | ".join(h for h, _ in harms) or "(cross-cutting)",
                "specific_harms": " | ".join(s for _, ss in harms for s in ss),
                "note": note,
            }
        )
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

    print(
        f"{'HARM TYPE':<34} {'RQs':>4} {'dir':>4} {'enab':>5} {'tooled':>7} {'zero':>5}"
    )
    print("-" * 64)
    for h in TAXONOMY:
        d = sorted(set(by_type[h]["direct"]), key=int)
        e = sorted(set(by_type[h]["enabling"]), key=int)
        allrq = sorted(set(d) | set(e), key=int)
        tooled = [
            q
            for q in allrq
            if len(rqs[q]["tools_implement"]) + len(rqs[q]["tools_eval"]) > 0
        ]
        zero = [q for q in allrq if q not in tooled]
        print(
            f"{h:<34} {len(allrq):>4} {len(d):>4} {len(e):>5} {len(tooled):>7} {len(zero):>5}"
        )

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
    print(
        f"\n{total_uncovered}/{n_all} specific harms have no RQ; "
        f"{n_all - total_uncovered}/{n_all} have at least one."
    )


if __name__ == "__main__":
    main()
