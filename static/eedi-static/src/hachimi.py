from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .data_loading import EediStaticStudent, summarize_history


LEVELS = ("poor", "low", "medium", "high")
K_ID = "id"
K_NAME = "\u59d3\u540d"
K_AGE = "\u5e74\u9f84"
K_GENDER = "\u6027\u522b"
K_GRADE = "\u5e74\u7ea7"
K_DEVELOPMENT = "\u53d1\u5c55\u9636\u6bb5"
K_AGENT_NAME = "\u4ee3\u7406\u540d"
K_STRONG_SUBJECTS = "\u64c5\u957f\u79d1\u76ee"
K_WEAK_SUBJECTS = "\u8584\u5f31\u79d1\u76ee"
K_ACADEMIC_LEVEL = "\u5b66\u672f\u6c34\u5e73"
K_PERSONALITY = "\u4eba\u683c"
K_VALUES = "\u4ef7\u503c\u89c2"
K_SOCIAL = "\u793e\u4ea4\u5173\u7cfb"
K_CREATIVITY = "\u521b\u9020\u529b"
K_MENTAL_HEALTH = "\u5fc3\u7406\u5065\u5eb7"
MATH = "\u6570\u5b66"


@dataclass(frozen=True)
class HachimiPersona:
    hachimi_id: str
    raw_hachimi_persona: dict[str, Any]
    hachimi_profile_card: dict[str, Any]


@dataclass(frozen=True)
class HachimiCandidate:
    hachimi_id: str
    rank_score: float
    rank_evidence: list[str]
    rank_conflicts: list[str]
    raw_hachimi_persona: dict[str, Any]
    hachimi_profile_card: dict[str, Any]

    def to_prompt_row(self) -> dict[str, Any]:
        return {
            "hachimi_id": self.hachimi_id,
            "rank_score": self.rank_score,
            "rank_evidence": self.rank_evidence,
            "rank_conflicts": self.rank_conflicts,
            "raw_hachimi_persona": self.raw_hachimi_persona,
            "hachimi_profile_card": self.hachimi_profile_card,
        }


@dataclass(frozen=True)
class HachimiMatch:
    student_id: str
    hachimi_id: str
    match_score: float
    matcher_version: str
    candidate_hachimi_ids: list[str]
    eedi_observed_profile: dict[str, Any]
    raw_hachimi_persona: dict[str, Any]
    hachimi_profile_card: dict[str, Any]
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
    return [str(value).strip()] if str(value).strip() else []


def _compact_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _normalize_level(value: Any) -> str:
    text = str(value or "").lower()
    if "high" in text or "\u9ad8" in text or "\u524d10" in text:
        return "high"
    if "medium" in text or "\u4e2d" in text or "\u524d50" in text:
        return "medium"
    if "low" in text or "\u4f4e" in text:
        return "low"
    if "poor" in text or "\u5dee" in text or "\u540e50" in text:
        return "poor"
    return "medium"


def _math_prior(strong_subjects: list[str], weak_subjects: list[str]) -> str:
    if MATH in strong_subjects and MATH in weak_subjects:
        return "math_conflicted"
    if MATH in strong_subjects:
        return "math_strong"
    if MATH in weak_subjects:
        return "math_weak"
    return "math_neutral"


def _text_blob(row: dict[str, Any]) -> str:
    fields = [
        K_PERSONALITY,
        K_VALUES,
        K_SOCIAL,
        K_CREATIVITY,
        K_MENTAL_HEALTH,
    ]
    return "\n".join(str(row.get(field) or "") for field in fields)


def _keyword_hits(text: str, keywords: list[str]) -> list[str]:
    lowered = text.lower()
    return [keyword for keyword in keywords if keyword.lower() in lowered]


def build_hachimi_profile_card(raw_persona: dict[str, Any]) -> dict[str, Any]:
    strong_subjects = _as_list(raw_persona.get(K_STRONG_SUBJECTS))
    weak_subjects = _as_list(raw_persona.get(K_WEAK_SUBJECTS))
    source_fields = [
        key
        for key in [
            K_ID,
            K_NAME,
            K_AGE,
            K_GENDER,
            K_GRADE,
            K_DEVELOPMENT,
            K_AGENT_NAME,
            K_STRONG_SUBJECTS,
            K_WEAK_SUBJECTS,
            K_ACADEMIC_LEVEL,
            K_PERSONALITY,
            K_VALUES,
            K_SOCIAL,
            K_CREATIVITY,
            K_MENTAL_HEALTH,
        ]
        if key in raw_persona
    ]
    text = _text_blob(raw_persona)
    return {
        "hachimi_id": str(raw_persona.get(K_ID)),
        "age": raw_persona.get(K_AGE),
        "gender": raw_persona.get(K_GENDER),
        "grade": raw_persona.get(K_GRADE),
        "academic_level": _normalize_level(raw_persona.get(K_ACADEMIC_LEVEL)),
        "academic_level_text": str(raw_persona.get(K_ACADEMIC_LEVEL) or ""),
        "strong_subjects": strong_subjects,
        "weak_subjects": weak_subjects,
        "math_prior": _math_prior(strong_subjects, weak_subjects),
        "development_stage": raw_persona.get(K_DEVELOPMENT) if isinstance(raw_persona.get(K_DEVELOPMENT), dict) else {},
        "learning_style_keywords": _keyword_hits(
            text,
            [
                "\u81ea\u4fe1",
                "\u4e3b\u52a8",
                "\u4f9d\u8d56",
                "\u9000\u7f29",
                "\u590d\u76d8",
                "\u8c03\u8282",
                "\u7126\u8651",
                "\u7d27\u5f20",
                "\u4e13\u6ce8",
                "\u8010\u5fc3",
            ],
        ),
        "source_fields_included": source_fields,
    }


def load_hachimi_personas(paths: list[str | Path]) -> list[HachimiPersona]:
    personas: list[HachimiPersona] = []
    seen_ids: set[str] = set()
    for path in paths:
        source = Path(path)
        if not source.exists():
            raise FileNotFoundError(f"HACHIMI persona file not found: {source}")
        with source.open("r", encoding="utf-8") as file:
            for line_no, line in enumerate(file, start=1):
                if not line.strip():
                    continue
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError(f"HACHIMI row must be object: {source}:{line_no}")
                if K_ID not in row:
                    raise ValueError(f"HACHIMI row missing id: {source}:{line_no}")
                hachimi_id = str(row[K_ID])
                if hachimi_id in seen_ids:
                    continue
                seen_ids.add(hachimi_id)
                personas.append(
                    HachimiPersona(
                        hachimi_id=hachimi_id,
                        raw_hachimi_persona=dict(row),
                        hachimi_profile_card=build_hachimi_profile_card(row),
                    )
                )
    if not personas:
        raise ValueError("no HACHIMI personas loaded")
    return personas


def build_eedi_observed_profile(student: EediStaticStudent, age: int | None = None) -> dict[str, Any]:
    summary = summarize_history(student)
    subject_accuracy = {str(key): float(value) for key, value in summary["subject_accuracy"].items()}
    subject_counts = Counter(attempt.subject_leaf for attempt in student.history)
    sorted_weak = sorted(subject_accuracy.items(), key=lambda item: (item[1], -subject_counts[item[0]], item[0]))
    sorted_strong = sorted(subject_accuracy.items(), key=lambda item: (-item[1], -subject_counts[item[0]], item[0]))
    return {
        "student_id": student.student_id,
        "age": age if age is not None else student.age_floor,
        "age_group": student.age_group,
        "ability_level": student.ability_level,
        "ability_score_proxy": student.ability_score_proxy,
        "history_accuracy": summary["history_accuracy"],
        "history_size": summary["history_size"],
        "strong_math_areas": [subject for subject, _ in sorted_strong[:5]],
        "weak_math_areas": [subject for subject, _ in sorted_weak[:5]],
        "subject_accuracy": subject_accuracy,
        "persistence_signal": _infer_persistence(student.ability_score_proxy, summary["history_accuracy"]),
        "guessing_tendency": _infer_guessing(student.ability_score_proxy, summary["history_accuracy"]),
    }


def _infer_persistence(ability_score_proxy: float, history_accuracy: float) -> str:
    if ability_score_proxy >= 0.75 and history_accuracy >= 0.65:
        return "high"
    if ability_score_proxy <= 0.35 or history_accuracy <= 0.35:
        return "fragile"
    return "medium"


def _infer_guessing(ability_score_proxy: float, history_accuracy: float) -> str:
    if ability_score_proxy <= 0.35 and history_accuracy <= 0.4:
        return "high"
    if ability_score_proxy >= 0.75 and history_accuracy >= 0.65:
        return "low"
    return "medium"


def _level_distance(left: str, right: str) -> int:
    return abs(LEVELS.index(left) - LEVELS.index(right))


def _profile_score(observed: dict[str, Any], persona: HachimiPersona) -> tuple[float, list[str], list[str]]:
    card = persona.hachimi_profile_card
    evidence: list[str] = []
    conflicts: list[str] = []
    score = 0.0

    observed_age = observed.get("age")
    persona_age = card.get("age")
    if isinstance(observed_age, int) and isinstance(persona_age, int):
        age_gap = abs(observed_age - persona_age)
        score += max(0.0, 3.0 - age_gap)
        evidence.append(f"age_gap={age_gap}")

    ability_level = str(observed["ability_level"])
    hachimi_level = str(card["academic_level"])
    level_gap = _level_distance(ability_level, hachimi_level)
    score += max(0.0, 5.0 - 1.8 * level_gap)
    evidence.append(f"ability_level={ability_level}, hachimi_academic_level={hachimi_level}, gap={level_gap}")

    math_prior = str(card["math_prior"])
    if ability_level in {"high", "medium"} and math_prior == "math_strong":
        score += 2.0
        evidence.append("higher EEDI math performance aligns with HACHIMI math_strong prior")
    elif ability_level in {"poor", "low"} and math_prior == "math_weak":
        score += 2.0
        evidence.append("lower EEDI math performance aligns with HACHIMI math_weak prior")
    elif ability_level in {"poor", "low"} and math_prior == "math_strong":
        conflicts.append("EEDI observed math performance is weak but HACHIMI marks mathematics as strong")

    text = _text_blob(persona.raw_hachimi_persona).lower()
    observed_terms = [
        term.lower()
        for term in list(observed.get("strong_math_areas", [])) + list(observed.get("weak_math_areas", []))
        if len(str(term)) >= 4
    ]
    overlap = sum(1 for term in observed_terms if term and term in text)
    if overlap:
        score += math.log1p(overlap)
        evidence.append(f"math-area text overlap={overlap}")

    if observed.get("persistence_signal") == "high" and any(
        keyword in card.get("learning_style_keywords", []) for keyword in ["\u4e3b\u52a8", "\u8010\u5fc3", "\u590d\u76d8"]
    ):
        score += 1.0
        evidence.append("persistence signals align")
    if observed.get("guessing_tendency") == "high" and any(
        keyword in card.get("learning_style_keywords", []) for keyword in ["\u9000\u7f29", "\u4f9d\u8d56", "\u7d27\u5f20"]
    ):
        score += 1.0
        evidence.append("fragility signals align")

    return score, evidence, conflicts


def rank_hachimi_candidates(
    observed_profile: dict[str, Any],
    personas: list[HachimiPersona],
    top_k: int = 8,
) -> list[HachimiCandidate]:
    if top_k < 1:
        raise ValueError("top_k must be >= 1")
    if not personas:
        raise ValueError("personas cannot be empty")
    scored = [
        (score, persona.hachimi_id, persona, evidence, conflicts)
        for persona in personas
        for score, evidence, conflicts in [_profile_score(observed_profile, persona)]
    ]
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [
        HachimiCandidate(
            hachimi_id=persona.hachimi_id,
            rank_score=score,
            rank_evidence=evidence,
            rank_conflicts=conflicts,
            raw_hachimi_persona=persona.raw_hachimi_persona,
            hachimi_profile_card=persona.hachimi_profile_card,
        )
        for score, _, persona, evidence, conflicts in scored[:top_k]
    ]


def _string_list(value: Any, field_name: str, min_len: int = 1) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")
    result = [str(item).strip() for item in value if str(item).strip()]
    if len(result) < min_len:
        raise ValueError(f"{field_name} must contain at least {min_len} non-empty item(s)")
    return result


def _non_empty_string(value: Any, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} cannot be empty")
    return text


def select_hachimi_match_with_llm(
    observed_profile: dict[str, Any],
    candidates: list[HachimiCandidate],
    llm: Any,
) -> HachimiMatch:
    if not candidates:
        raise ValueError("candidates cannot be empty")
    candidate_by_id = {candidate.hachimi_id: candidate for candidate in candidates}
    if len(candidate_by_id) != len(candidates):
        raise ValueError("candidate hachimi ids must be unique")

    prompt = f"""
Select the best HACHIMI persona for this EEDI-static student.

Use only the EEDI observed profile built from non-test history and the candidate HACHIMI profiles below.
Do not use current test answers, current correctness, item empirical accuracy, future answers, or evaluation metrics.

Decision rule:
- EEDI observed math history is stronger evidence for math capability.
- HACHIMI is an external prior for affect, learning style, self-regulation, social expression, creativity, mental health, and response style.
- Consider the complete raw_hachimi_persona for every candidate. Do not ignore fields just because a compact card also exists.
- If EEDI and HACHIMI conflict, select the most plausible overall persona and keep the conflict explicit.

EEDI observed profile:
{_compact_json(observed_profile)}

candidate_hachimi_profiles:
{_compact_json([candidate.to_prompt_row() for candidate in candidates])}

Return JSON with:
- selected_hachimi_id: one of the candidate hachimi_id values
- match_evidence: non-empty list[str]
- conflict_evidence: list[str]. Use [] only if there is no meaningful conflict.
- fusion_rule: string describing how EEDI evidence and HACHIMI persona should be fused downstream
"""
    parsed = llm.chat_json(
        "You are a careful educational profile matching component. Return exactly one JSON object.",
        prompt,
    )
    selected_id = str(parsed.get("selected_hachimi_id", "")).strip()
    if selected_id not in candidate_by_id:
        raise ValueError(
            "selected_hachimi_id must be one of "
            f"{sorted(candidate_by_id)}, got {selected_id!r}"
        )
    selected = candidate_by_id[selected_id]
    return HachimiMatch(
        student_id=str(observed_profile["student_id"]),
        hachimi_id=selected.hachimi_id,
        match_score=selected.rank_score,
        matcher_version="llm_profile_matcher_v1",
        candidate_hachimi_ids=[candidate.hachimi_id for candidate in candidates],
        eedi_observed_profile=observed_profile,
        raw_hachimi_persona=selected.raw_hachimi_persona,
        hachimi_profile_card=selected.hachimi_profile_card,
        match_evidence=_string_list(parsed.get("match_evidence"), "match_evidence"),
        conflict_evidence=_string_list(parsed.get("conflict_evidence", []), "conflict_evidence", min_len=0),
        fusion_rule=_non_empty_string(parsed.get("fusion_rule"), "fusion_rule"),
    )


def match_hachimi_persona(observed_profile: dict[str, Any], personas: list[HachimiPersona]) -> HachimiMatch:
    candidates = rank_hachimi_candidates(observed_profile, personas, top_k=1)
    selected = candidates[0]
    return HachimiMatch(
        student_id=str(observed_profile["student_id"]),
        hachimi_id=selected.hachimi_id,
        match_score=selected.rank_score,
        matcher_version="deterministic_profile_ranker_v1",
        candidate_hachimi_ids=[selected.hachimi_id],
        eedi_observed_profile=observed_profile,
        raw_hachimi_persona=selected.raw_hachimi_persona,
        hachimi_profile_card=selected.hachimi_profile_card,
        match_evidence=selected.rank_evidence,
        conflict_evidence=selected.rank_conflicts,
        fusion_rule=(
            "Deterministic dry-run match only. Real HACHIMI matching must use "
            "select_hachimi_match_with_llm after candidate ranking."
        ),
    )


def load_hachimi_matches(path: str | Path) -> dict[str, HachimiMatch]:
    matches: dict[str, HachimiMatch] = {}
    source = Path(path)
    if not source.exists():
        return matches
    with source.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            row = json.loads(line)
            match = HachimiMatch(
                student_id=str(row["student_id"]),
                hachimi_id=str(row["hachimi_id"]),
                match_score=float(row["match_score"]),
                matcher_version=str(row.get("matcher_version", "legacy_profile_matcher")),
                candidate_hachimi_ids=[
                    str(item)
                    for item in row.get("candidate_hachimi_ids", [str(row["hachimi_id"])])
                ],
                eedi_observed_profile=dict(row["eedi_observed_profile"]),
                raw_hachimi_persona=dict(row["raw_hachimi_persona"]),
                hachimi_profile_card=dict(row["hachimi_profile_card"]),
                match_evidence=[str(item) for item in row["match_evidence"]],
                conflict_evidence=[str(item) for item in row["conflict_evidence"]],
                fusion_rule=str(row["fusion_rule"]),
            )
            matches[match.student_id] = match
    return matches
