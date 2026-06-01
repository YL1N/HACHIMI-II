from __future__ import annotations

import json
import math
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .data_loading import EnemStaticStudent, summarize_history
from .llm_client import OpenAICompatClient


TARGET_DOMAIN_TERMS = (
    "自然科学",
    "科学",
    "物理",
    "化学",
    "生物",
    "science",
    "physics",
    "chemistry",
    "biology",
    "ciências",
    "física",
    "química",
    "biologia",
)


@dataclass(frozen=True)
class HachimiPersona:
    hachimi_id: str
    raw_persona: dict[str, Any]
    hachimi_profile_card: dict[str, Any]


@dataclass(frozen=True)
class HachimiCandidate:
    hachimi_id: str
    raw_persona: dict[str, Any]
    hachimi_profile_card: dict[str, Any]
    score: float
    evidence: list[str]
    conflict_evidence: list[str]


@dataclass(frozen=True)
class HachimiMatch:
    student_id: str
    hachimi_id: str
    matcher_version: str
    candidate_hachimi_ids: list[str]
    hachimi_profile_card: dict[str, Any]
    raw_hachimi_persona: dict[str, Any]
    match_evidence: list[str]
    conflict_evidence: list[str]
    fusion_rule: str

    def to_row(self) -> dict[str, Any]:
        return asdict(self)


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value is None:
        return []
    text = str(value).strip()
    return [text] if text else []


def _find_first_key(raw: dict[str, Any], fragments: list[str]) -> str | None:
    for key in raw:
        lowered = str(key).lower()
        if any(fragment.lower() in lowered for fragment in fragments):
            return key
    return None


def _extract_profile_card(raw: dict[str, Any]) -> dict[str, Any]:
    id_value = raw.get("id") or raw.get("student_id") or raw.get("hachimi_id") or raw.get("ID")
    strong_key = _find_first_key(raw, ["擅", "强", "strong"])
    weak_key = _find_first_key(raw, ["弱", "薄", "weak"])
    level_key = _find_first_key(raw, ["水平", "level", "academic"])
    grade_key = _find_first_key(raw, ["年级", "grade"])
    age_key = _find_first_key(raw, ["年龄", "age"])
    text_fields = {
        str(key): value
        for key, value in raw.items()
        if isinstance(value, str) and len(value.strip()) > 20
    }
    return {
        "hachimi_id": str(id_value),
        "grade": str(raw.get(grade_key, "")) if grade_key else "",
        "age": raw.get(age_key) if age_key else None,
        "academic_level": str(raw.get(level_key, "")) if level_key else "",
        "strong_subjects": _as_list(raw.get(strong_key)) if strong_key else [],
        "weak_subjects": _as_list(raw.get(weak_key)) if weak_key else [],
        "long_text_field_names": list(text_fields)[:8],
        "long_text_snippets": {key: str(value)[:240] for key, value in list(text_fields.items())[:4]},
    }


def load_hachimi_personas(paths: list[Path]) -> list[HachimiPersona]:
    personas: list[HachimiPersona] = []
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(f"HACHIMI persona file not found: {path}")
        with path.open("r", encoding="utf-8") as file:
            for line_no, line in enumerate(file, start=1):
                if not line.strip():
                    continue
                raw = json.loads(line)
                if not isinstance(raw, dict):
                    raise ValueError(f"HACHIMI row must be object: {path}:{line_no}")
                card = _extract_profile_card(raw)
                hachimi_id = str(card.get("hachimi_id") or f"{path.name}:{line_no}")
                personas.append(HachimiPersona(hachimi_id=hachimi_id, raw_persona=raw, hachimi_profile_card=card))
    if not personas:
        raise ValueError("no HACHIMI personas loaded")
    return personas


def load_hachimi_matches(path: Path) -> dict[str, HachimiMatch]:
    if not path.exists():
        return {}
    matches: dict[str, HachimiMatch] = {}
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            row = json.loads(line)
            match = HachimiMatch(**row)
            matches[match.student_id] = match
    return matches


def build_enem_observed_profile(student: EnemStaticStudent) -> dict[str, Any]:
    summary = summarize_history(student)
    competency_accuracy = dict(summary["competency_accuracy"])
    sorted_weak = sorted(competency_accuracy.items(), key=lambda item: (item[1], item[0]))
    sorted_strong = sorted(competency_accuracy.items(), key=lambda item: (-item[1], item[0]))
    return {
        "student_id": student.student_id,
        "target_dataset": "ENEM_2024",
        "target_area": student.target_area,
        "ability_level": student.ability_level,
        "ability_score_proxy": student.ability_score_proxy,
        "history_accuracy": summary["history_accuracy"],
        "strong_science_areas": [name for name, _ in sorted_strong[:5]],
        "weak_science_areas": [name for name, _ in sorted_weak[:5]],
        "competency_accuracy": competency_accuracy,
        "answer_counts": summary["answer_counts"],
        "blank_or_invalid_count": summary["blank_or_invalid_count"],
    }


def _domain_prior(card: dict[str, Any]) -> str:
    strong_text = " ".join(str(value) for value in card.get("strong_subjects", []))
    weak_text = " ".join(str(value) for value in card.get("weak_subjects", []))
    strong_has = any(term.lower() in strong_text.lower() for term in TARGET_DOMAIN_TERMS)
    weak_has = any(term.lower() in weak_text.lower() for term in TARGET_DOMAIN_TERMS)
    if strong_has and weak_has:
        return "science_conflicted"
    if strong_has:
        return "science_strong"
    if weak_has:
        return "science_weak"
    return "science_neutral"


def _level_distance(observed_level: str, card_level: str) -> int:
    order = ["poor", "low", "medium", "high"]
    text = card_level.lower()
    if any(token in text for token in ["差", "poor", "low", "weak", "后"]):
        card = "poor"
    elif any(token in text for token in ["中", "medium", "average"]):
        card = "medium"
    elif any(token in text for token in ["高", "优", "good", "high", "strong"]):
        card = "high"
    else:
        card = "medium"
    return abs(order.index(observed_level) - order.index(card))


def rank_hachimi_candidates(
    observed_profile: dict[str, Any],
    personas: list[HachimiPersona],
    top_k: int = 8,
) -> list[HachimiCandidate]:
    observed_level = str(observed_profile["ability_level"])
    observed_terms = " ".join(
        list(observed_profile.get("strong_science_areas", []))
        + list(observed_profile.get("weak_science_areas", []))
    ).lower()
    candidates: list[HachimiCandidate] = []
    for persona in personas:
        card = persona.hachimi_profile_card
        evidence: list[str] = []
        conflicts: list[str] = []
        score = 0.0
        gap = _level_distance(observed_level, str(card.get("academic_level") or ""))
        score -= gap
        evidence.append(f"ability_level_gap={gap}")

        prior = _domain_prior(card)
        evidence.append(f"target_domain_prior={prior}")
        if observed_level in {"medium", "high"} and prior == "science_strong":
            score += 1.5
        elif observed_level in {"poor", "low"} and prior == "science_weak":
            score += 1.0
        elif observed_level in {"poor", "low"} and prior == "science_strong":
            conflicts.append("ENEM observed science history is weak but HACHIMI marks target science as strong")
            score -= 0.5

        persona_terms = " ".join(
            [str(value) for value in card.get("strong_subjects", [])]
            + [str(value) for value in card.get("weak_subjects", [])]
        ).lower()
        overlap = sum(1 for token in set(observed_terms.split("_")) if token and token in persona_terms)
        if overlap:
            score += math.log1p(overlap)
            evidence.append(f"science-area text overlap={overlap}")
        candidates.append(
            HachimiCandidate(
                hachimi_id=persona.hachimi_id,
                raw_persona=persona.raw_persona,
                hachimi_profile_card=card,
                score=score,
                evidence=evidence,
                conflict_evidence=conflicts,
            )
        )
    candidates.sort(key=lambda item: (-item.score, item.hachimi_id))
    return candidates[:top_k]


def select_hachimi_match_with_llm(
    observed_profile: dict[str, Any],
    candidates: list[HachimiCandidate],
    llm: OpenAICompatClient,
) -> HachimiMatch:
    if not candidates:
        raise ValueError("candidates cannot be empty")
    payload = {
        "observed_enem_profile": observed_profile,
        "candidate_hachimi_profiles": [
            {
                "hachimi_id": candidate.hachimi_id,
                "rule_score": candidate.score,
                "rule_evidence": candidate.evidence,
                "rule_conflicts": candidate.conflict_evidence,
                "hachimi_profile_card": candidate.hachimi_profile_card,
                "raw_hachimi_persona": candidate.raw_persona,
            }
            for candidate in candidates
        ],
        "fusion_rule": (
            "ENEM observed science calibration history is primary for science capability. "
            "HACHIMI fills learning-style, affective, self-regulation, and response-expression gaps. "
            "If HACHIMI conflicts with ENEM evidence, keep the conflict visible."
        ),
    }
    parsed = llm.chat_json(
        system_prompt=(
            "Select the best HACHIMI persona match for an ENEM natural-science student simulation. "
            "Return exactly one JSON object. Do not use hidden test answers."
        ),
        user_prompt=json.dumps(payload, ensure_ascii=False),
    )
    selected_id = str(parsed.get("selected_hachimi_id") or "").strip()
    by_id = {candidate.hachimi_id: candidate for candidate in candidates}
    if selected_id not in by_id:
        raise ValueError(f"selected_hachimi_id={selected_id!r} not in candidates")
    selected = by_id[selected_id]
    return HachimiMatch(
        student_id=str(observed_profile["student_id"]),
        hachimi_id=selected.hachimi_id,
        matcher_version="enem_llm_profile_matcher_v1",
        candidate_hachimi_ids=[candidate.hachimi_id for candidate in candidates],
        hachimi_profile_card=selected.hachimi_profile_card,
        raw_hachimi_persona=selected.raw_persona,
        match_evidence=[str(item) for item in parsed.get("match_evidence", selected.evidence)],
        conflict_evidence=[str(item) for item in parsed.get("conflict_evidence", selected.conflict_evidence)],
        fusion_rule=str(parsed.get("fusion_rule") or payload["fusion_rule"]),
    )


def deterministic_hachimi_match(
    student: EnemStaticStudent,
    personas: list[HachimiPersona],
) -> HachimiMatch:
    observed = build_enem_observed_profile(student)
    candidates = rank_hachimi_candidates(observed, personas, top_k=1)
    selected = candidates[0]
    return HachimiMatch(
        student_id=student.student_id,
        hachimi_id=selected.hachimi_id,
        matcher_version="enem_rule_ranker_only_for_dry_run",
        candidate_hachimi_ids=[selected.hachimi_id],
        hachimi_profile_card=selected.hachimi_profile_card,
        raw_hachimi_persona=selected.raw_persona,
        match_evidence=selected.evidence,
        conflict_evidence=selected.conflict_evidence,
        fusion_rule="dry-run rule-ranked HACHIMI match; real runs should use LLM final matching",
    )
