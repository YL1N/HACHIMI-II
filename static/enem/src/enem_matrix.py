from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ScienceCompetencyArea:
    competency_id: int
    short_name: str
    capability_focus: str


SCIENCE_COMPETENCIES: dict[int, ScienceCompetencyArea] = {
    1: ScienceCompetencyArea(
        competency_id=1,
        short_name="science_technology_society",
        capability_focus="science as a human and technological construction in society",
    ),
    2: ScienceCompetencyArea(
        competency_id=2,
        short_name="technology_in_context",
        capability_focus="natural-science technologies in everyday contexts",
    ),
    3: ScienceCompetencyArea(
        competency_id=3,
        short_name="environment_and_production",
        capability_focus="environmental conservation or degradation linked to production and social action",
    ),
    4: ScienceCompetencyArea(
        competency_id=4,
        short_name="life_systems_and_health",
        capability_focus="organism-environment interactions, heredity, evolution, and human health",
    ),
    5: ScienceCompetencyArea(
        competency_id=5,
        short_name="scientific_methods_and_representations",
        capability_focus="methods, procedures, models, evidence, and representations in natural sciences",
    ),
    6: ScienceCompetencyArea(
        competency_id=6,
        short_name="physics_reasoning",
        capability_focus="physics knowledge for interpreting or evaluating scientific-technological situations",
    ),
    7: ScienceCompetencyArea(
        competency_id=7,
        short_name="chemistry_reasoning",
        capability_focus="chemistry knowledge for interpreting or evaluating scientific-technological situations",
    ),
    8: ScienceCompetencyArea(
        competency_id=8,
        short_name="biology_reasoning",
        capability_focus="biology knowledge for interpreting or evaluating scientific-technological situations",
    ),
}


SCIENCE_SKILL_SUMMARIES: dict[int, str] = {
    1: "wave or oscillation phenomena and their uses",
    2: "scientific-technological solutions for communication, transport, health, or other problems",
    3: "scientific interpretations versus common-sense interpretations",
    4: "environmental intervention proposals and quality of life or biodiversity conservation",
    5: "everyday electric circuits or devices",
    6: "manuals or common technological systems",
    7: "tests, parameters, or criteria for comparing materials and products",
    8: "resource extraction, transformation, use, or recycling processes",
    9: "biogeochemical cycles, energy flow, and system changes",
    10: "environmental disturbances, pollutants, and effects on systems",
    11: "biotechnology benefits, limits, ethics, and biological structures or processes",
    12: "environmental impacts from social or economic activities",
    13: "life transmission mechanisms and living-being traits",
    14: "patterns in vital processes and organism-environment relations",
    15: "models and experiments for biological phenomena or processes",
    16: "evolution and biological patterns, processes, or taxonomy",
    17: "relations across texts, graphs, tables, mathematical relations, and symbolic language",
    18: "physical, chemical, or biological properties linked to product or system purposes",
    19: "natural-science methods or procedures for social, economic, or environmental problems",
    20: "causes or effects of motion in particles, substances, objects, or celestial bodies",
    21: "physical or chemical laws in thermodynamics or electromagnetism contexts",
    22: "radiation-matter interaction and natural, technological, biological, social, or economic implications",
    23: "energy generation, use, or transformation and ethical, environmental, social, or economic implications",
    24: "chemical codes and nomenclature for materials, substances, or transformations",
    25: "materials or substances, production steps, yields, and implications",
    26: "social, environmental, or economic implications of energy or mineral resources",
    27: "environmental intervention proposals using chemistry knowledge",
    28: "adaptive traits and organism lifestyles or distribution limits",
    29: "experiments or techniques using living beings and their implications",
    30: "individual or collective proposals for health or environmental preservation",
}


def science_skill_code(value: int | str) -> str:
    try:
        skill_id = int(str(value).strip())
    except ValueError as exc:
        raise ValueError(f"invalid ENEM science skill id: {value!r}") from exc
    if skill_id not in SCIENCE_SKILL_SUMMARIES:
        raise ValueError(f"ENEM science skill id must be 1..30, got {skill_id}")
    return f"H{skill_id}"


def science_competency_for_skill(value: int | str) -> ScienceCompetencyArea:
    skill_id = int(science_skill_code(value)[1:])
    if 1 <= skill_id <= 4:
        return SCIENCE_COMPETENCIES[1]
    if 5 <= skill_id <= 7:
        return SCIENCE_COMPETENCIES[2]
    if 8 <= skill_id <= 12:
        return SCIENCE_COMPETENCIES[3]
    if 13 <= skill_id <= 16:
        return SCIENCE_COMPETENCIES[4]
    if 17 <= skill_id <= 19:
        return SCIENCE_COMPETENCIES[5]
    if 20 <= skill_id <= 23:
        return SCIENCE_COMPETENCIES[6]
    if 24 <= skill_id <= 27:
        return SCIENCE_COMPETENCIES[7]
    return SCIENCE_COMPETENCIES[8]


def science_skill_summary(value: int | str) -> str:
    skill_id = int(science_skill_code(value)[1:])
    return SCIENCE_SKILL_SUMMARIES[skill_id]


def science_skill_payload(value: int | str) -> dict[str, Any]:
    competency = science_competency_for_skill(value)
    return {
        "skill_code": science_skill_code(value),
        "skill_summary": science_skill_summary(value),
        "competency_id": competency.competency_id,
        "competency_short_name": competency.short_name,
        "competency_focus": competency.capability_focus,
    }
