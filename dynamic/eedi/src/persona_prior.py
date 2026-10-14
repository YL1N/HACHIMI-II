"""HACHIMI-1M persona matching for the dialogue pipeline (Appendix A).

  1. Observed profile: the visible dialogue is summarized into a profile with
     grade or age, ability level, past performance, strong and weak subjects,
     response style, uncertainty, and help-seeking.
  2. Candidate retrieval: a candidate pool is drawn from the persona bank on
     coarse fields (grade or age range, academic level, subjects, and
     learning-style tags).
  3. Rule-based ranking: candidates are scored on grade compatibility,
     agreement of ability level, overlap of strong and weak subjects, and
     similarity of learning behavior, and the top-k are kept.
  4. Reranking: the backbone compares the observed profile with the full
     descriptions of the top-k candidates and selects one persona.
  5. Validity check: near-duplicate candidates are removed, and the selected
     persona is checked for membership in the candidate pool and completeness
     of its fields.
  6. Fusion: the selected persona is summarized into the persona prior that
     the student model merges with the observed evidence.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .dialogue_context import DialogueContextState
from .evaluation_eedi import write_jsonl
from .tutor_turn_profile import TutorTurnProfile


LEVELS = ("poor", "low", "medium", "high")
COARSE_FIELD_COUNT = 4
GRADE_OR_AGE_RANGE = 2
NEAR_DUPLICATE_THRESHOLD = 0.9
REQUIRED_PERSONA_FIELDS = (
    "persona_id",
    "grade_or_age",
    "academic_level",
    "persona_description",
)

_POSITIVE_FEEDBACK = re.compile(
    r"\b(correct|well done|that['’]?s right|exactly|good job|great|perfect|"
    r"spot on|brilliant|excellent)\b"
)
_CORRECTIVE_FEEDBACK = re.compile(
    r"\b(incorrect|not quite|not correct|not right|not exactly|"
    r"isn['’]?t (?:quite )?(?:right|correct)|try again|"
    r"have another (?:go|look|try)|mistake)\b"
)
_UNCERTAINTY = re.compile(
    r"\b(i think|maybe|not sure|i guess|i don['’]?t know|idk|dunno|probably|"
    r"perhaps)\b|\?\s*$"
)
_HELP_SEEKING = re.compile(
    r"\b(help|hint|explain|confused|stuck|i don['’]?t (?:understand|get)|"
    r"how do (?:i|you|we)|what do (?:i|you|we)|can you|could you|show me)\b"
)
_GRADE_OR_AGE_MENTION = re.compile(
    r"\b(?:year|grade)\s*\d{1,2}\b|\b\d{1,2}\s*years?\s*old\b"
)
_BEHAVIOR_KEYWORDS = {
    ("help_seeking", "high"): ("help", "guidance", "support", "reliance", "依赖", "求助"),
    ("uncertainty", "high"): ("anxious", "hesitant", "unsure", "nervous", "焦虑", "紧张", "退缩"),
    ("uncertainty", "low"): ("confident", "independent", "自信", "主动"),
    ("response_style", "extended"): ("reflective", "explain", "verbal", "复盘", "表达"),
    ("response_style", "fragment"): ("quiet", "brief", "passive", "内向", "被动"),
}


@dataclass(frozen=True)
class HachimiPersona:
    persona_id: str
    grade_or_age: str
    academic_level: str
    subjects: list[tuple[str, int]]
    learning_style_tags: list[str]
    self_efficacy_description: str
    motivation_description: str
    confidence_description: str
    interactional_style: str
    persona_description: str


@dataclass(frozen=True)
class RankedCandidate:
    persona: HachimiPersona
    rank_score: float
    rank_evidence: list[str]


@dataclass(frozen=True)
class PersonaPriorSummary:
    matching_mode: str
    n_matched: int
    matched_persona_ids: list[str]
    selected_persona_id: str
    learning_tendency_priors: list[str]
    interactional_style_priors: list[str]
    prior_summary_lines: list[str]
    caution_lines: list[str]
    match_evidence: list[str]
    conflict_evidence: list[str]
    fusion_rule: str


def write_persona_bank(
    output_path: str | Path,
    personas: list[HachimiPersona],
) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [asdict(persona) for persona in personas]
    write_jsonl(path, rows)


def load_persona_bank(
    path: str | Path,
) -> list[HachimiPersona]:
    bank_path = Path(path)
    if not bank_path.exists():
        raise FileNotFoundError(f"HACHIMI-1M persona bank not found: {bank_path}")
    personas: list[HachimiPersona] = []
    with bank_path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            raw = json.loads(stripped)
            if not isinstance(raw, dict):
                raise ValueError(f"{bank_path} line {line_no} must be a JSON object")
            personas.append(_parse_persona(raw, bank_path, line_no))
    if not personas:
        raise ValueError(f"persona bank is empty: {bank_path}")
    return personas


def build_persona_prior_summary(
    context: DialogueContextState,
    tutor_profile: TutorTurnProfile,
    persona_bank: list[HachimiPersona],
    top_k: int,
    llm_client: Any = None,
    exclude_dialogue_id: str | None = None,
) -> PersonaPriorSummary | None:
    if top_k <= 0 or not persona_bank:
        return None

    # Step 1: observed profile
    observed = _build_observed_profile(context)

    # Step 2: candidate retrieval on coarse fields
    pool = persona_bank
    if exclude_dialogue_id is not None:
        pool = [p for p in persona_bank if p.persona_id != exclude_dialogue_id]
    if not pool:
        return None
    pool = _retrieve_candidates(pool, observed, min_size=top_k)

    # Step 3: rule-based ranking
    scored = [
        RankedCandidate(
            persona=persona,
            rank_score=score,
            rank_evidence=evidence,
        )
        for persona in pool
        for score, evidence in [_rule_based_ranking_score(persona, observed)]
    ]
    scored.sort(key=lambda c: (-c.rank_score, c.persona.persona_id))
    candidates = scored[:top_k]

    # Step 4: backbone reranking
    if llm_client is not None and len(candidates) > 1:
        selected, match_evidence, conflict_evidence, fusion_rule = (
            _backbone_rerank(observed, candidates, llm_client)
        )
    else:
        selected = candidates[0]
        match_evidence = selected.rank_evidence
        conflict_evidence = []
        fusion_rule = "rule_ranked_top1"

    # Step 5: validity check
    selected, candidates = _validity_check(selected, candidates)

    # Step 6: fusion into the persona prior summary
    learning_tendencies = _extract_learning_tendencies(selected.persona)
    interactional_styles = _extract_interactional_styles(selected.persona)

    prior_summary_lines = [
        (
            f"Matched {len(candidates)} HACHIMI-1M candidates for the current learner "
            f"on subjects: {', '.join(s for s, _ in context.subjects)}; "
            f"selected persona {selected.persona.persona_id}."
        ),
    ]
    if learning_tendencies:
        prior_summary_lines.append(
            "Learning tendency priors from selected persona: "
            + "; ".join(learning_tendencies)
            + "."
        )
    if interactional_styles:
        prior_summary_lines.append(
            "Interactional style prior: " + interactional_styles[0] + "."
        )
    caution_lines = [
        "Use this summary only as a persona prior for the current learner.",
        "Do not treat matched personas as answer scripts for the current turn.",
        "Generation-visible evidence and current task context override persona priors.",
        "Do not lock the learner into a single fixed response pattern from the matched personas.",
    ]

    return PersonaPriorSummary(
        matching_mode="hachimi_1m_persona_matching",
        n_matched=len(candidates),
        matched_persona_ids=[c.persona.persona_id for c in candidates],
        selected_persona_id=selected.persona.persona_id,
        learning_tendency_priors=learning_tendencies,
        interactional_style_priors=interactional_styles,
        prior_summary_lines=prior_summary_lines,
        caution_lines=caution_lines,
        match_evidence=match_evidence,
        conflict_evidence=conflict_evidence,
        fusion_rule=fusion_rule,
    )


def persona_prior_summary_to_dict(
    summary: PersonaPriorSummary | None,
) -> dict[str, object] | None:
    if summary is None:
        return None
    return asdict(summary)


# ── Step 1: observed profile ──────────────────────────────────────────────


def _build_observed_profile(context: DialogueContextState) -> dict[str, Any]:
    turns = context.turns_so_far
    student_turns = [
        str(t.get("content", "")) for t in turns if t.get("role") == "student"
    ]

    # Past performance is read from the tutor's feedback on earlier student turns.
    positive = corrective = 0
    for previous, current in zip(turns, turns[1:]):
        if previous.get("role") != "student" or current.get("role") != "tutor":
            continue
        feedback = str(current.get("content", "")).lower()
        if _CORRECTIVE_FEEDBACK.search(feedback):
            corrective += 1
        elif _POSITIVE_FEEDBACK.search(feedback):
            positive += 1
    judged = positive + corrective
    share_positive = positive / judged if judged else None
    ability_level = _performance_to_level(share_positive)

    subjects = [name for name, _ in context.subjects]
    word_counts = [len(turn.split()) for turn in student_turns]
    avg_words = sum(word_counts) / len(word_counts) if word_counts else None

    return {
        "dialogue_id": context.dialogue_id,
        "question_id": context.question_id,
        "grade_or_age": _extract_grade_or_age(context),
        "ability_level": ability_level,
        "past_performance": {
            "positive_feedback": positive,
            "corrective_feedback": corrective,
            "share_positive": share_positive,
        },
        "subjects": subjects,
        "strong_subjects": subjects if ability_level in ("medium", "high") else [],
        "weak_subjects": subjects if ability_level in ("poor", "low") else [],
        "response_style": _response_style(avg_words),
        "uncertainty": _signal_level(student_turns, _UNCERTAINTY),
        "help_seeking": _signal_level(student_turns, _HELP_SEEKING),
        "student_turn_count": len(student_turns),
        "turn_count": context.turn_count_so_far,
        "latest_tutor_turn": context.latest_tutor_turn,
        "last_student_turn": context.last_student_turn,
    }


def _extract_grade_or_age(context: DialogueContextState) -> str | None:
    texts = [context.question_text] + [
        str(t.get("content", "")) for t in context.turns_so_far
    ]
    for text in texts:
        found = _GRADE_OR_AGE_MENTION.search(str(text).lower())
        if found:
            return found.group()
    return None


def _performance_to_level(share_positive: float | None) -> str | None:
    if share_positive is None:
        return None
    if share_positive >= 0.75:
        return "high"
    if share_positive >= 0.5:
        return "medium"
    if share_positive >= 0.25:
        return "low"
    return "poor"


def _response_style(avg_words: float | None) -> str | None:
    if avg_words is None:
        return None
    if avg_words <= 3:
        return "fragment"
    if avg_words <= 12:
        return "short"
    return "extended"


def _signal_level(student_turns: list[str], pattern: re.Pattern[str]) -> str | None:
    if not student_turns:
        return None
    share = sum(1 for turn in student_turns if pattern.search(turn.lower())) / len(
        student_turns
    )
    if share >= 0.5:
        return "high"
    if share >= 0.2:
        return "medium"
    return "low"


def _observed_behavior_keywords(observed: dict[str, Any]) -> tuple[str, ...]:
    keywords: list[str] = []
    for signal in ("help_seeking", "uncertainty", "response_style"):
        keywords.extend(_BEHAVIOR_KEYWORDS.get((signal, observed.get(signal)), ()))
    return tuple(keywords)


# ── Step 2: candidate retrieval ───────────────────────────────────────────


def _retrieve_candidates(
    pool: list[HachimiPersona],
    observed: dict[str, Any],
    min_size: int,
) -> list[HachimiPersona]:
    counted = [(persona, _coarse_field_matches(persona, observed)) for persona in pool]
    for required in range(COARSE_FIELD_COUNT, 0, -1):
        retrieved = [persona for persona, matches in counted if matches >= required]
        if len(retrieved) >= min_size:
            return retrieved
    return list(pool)


def _coarse_field_matches(persona: HachimiPersona, observed: dict[str, Any]) -> int:
    # A field that is unknown on either side does not exclude the persona.
    observed_age = _parse_age(observed.get("grade_or_age"))
    persona_age = _parse_age(persona.grade_or_age)
    grade_match = (
        observed_age is None
        or persona_age is None
        or abs(observed_age - persona_age) <= GRADE_OR_AGE_RANGE
    )

    observed_level = observed.get("ability_level")
    persona_level = _normalize_level(persona.academic_level)
    level_match = (
        observed_level is None
        or persona_level is None
        or _level_distance(observed_level, persona_level) <= 1
    )

    subject_match = (
        not observed.get("subjects")
        or not persona.subjects
        or _subject_overlap(observed["subjects"], persona) > 0
    )

    behavior_keywords = _observed_behavior_keywords(observed)
    tags_text = " ".join(persona.learning_style_tags).lower()
    tag_match = (
        not behavior_keywords
        or not tags_text
        or any(keyword in tags_text for keyword in behavior_keywords)
    )

    return sum((grade_match, level_match, subject_match, tag_match))


# ── Step 3: rule-based ranking ────────────────────────────────────────────


def _rule_based_ranking_score(
    persona: HachimiPersona,
    observed: dict[str, Any],
) -> tuple[float, list[str]]:
    score = 0.0
    evidence: list[str] = []

    # Grade compatibility
    observed_age = _parse_age(observed.get("grade_or_age"))
    persona_age = _parse_age(persona.grade_or_age)
    if observed_age is not None and persona_age is not None:
        age_gap = abs(observed_age - persona_age)
        score += max(0.0, 3.0 - age_gap)
        evidence.append(f"grade_or_age_gap={age_gap}")

    # Agreement of ability level
    observed_level = observed.get("ability_level")
    persona_level = _normalize_level(persona.academic_level)
    if observed_level is not None and persona_level is not None:
        level_gap = _level_distance(observed_level, persona_level)
        score += max(0.0, 5.0 - 1.8 * level_gap)
        evidence.append(
            f"ability_level={observed_level}, "
            f"persona_academic_level={persona_level}, gap={level_gap}"
        )

    # Overlap of strong and weak subjects
    subject_field = next(
        (f for f in ("strong_subjects", "weak_subjects") if observed.get(f)),
        "subjects",
    )
    subject_ratio = _subject_overlap(observed.get(subject_field, []), persona)
    if subject_ratio:
        score += 3.0 * subject_ratio
        evidence.append(f"{subject_field}_overlap={subject_ratio:.2f}")

    # Similarity of learning behavior
    behavior_text = " ".join(
        [
            *persona.learning_style_tags,
            persona.self_efficacy_description,
            persona.motivation_description,
            persona.confidence_description,
            persona.interactional_style,
        ]
    ).lower()
    aligned = [
        keyword
        for keyword in _observed_behavior_keywords(observed)
        if keyword in behavior_text
    ]
    if aligned:
        score += min(len(aligned), 3)
        evidence.append("learning_behavior_alignment=" + ",".join(aligned))

    if not evidence:
        evidence.append("no_matching_signals")

    return score, evidence


def _parse_age(value: object) -> int | None:
    text = str(value or "").strip().lower()
    number = re.search(r"\d{1,2}", text)
    if not number:
        return None
    parsed = int(number.group())
    # A grade or year-group number is converted to an approximate age.
    if re.search(r"grade|年级|year(?!s?\s*old)", text):
        return parsed + 5
    return parsed


def _normalize_level(value: object) -> str | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    if "high" in text or "高" in text or "前10" in text:
        return "high"
    if "medium" in text or "中" in text or "前50" in text:
        return "medium"
    if "low" in text or "低" in text:
        return "low"
    if "poor" in text or "差" in text or "后50" in text:
        return "poor"
    return "medium"


def _level_distance(left: str, right: str) -> int:
    return abs(LEVELS.index(left) - LEVELS.index(right))


def _subject_key(name: object) -> str:
    text = str(name or "").strip().lower()
    if "math" in text or "数学" in text:
        return "math"
    return text


def _subject_overlap(subject_names: list[str], persona: HachimiPersona) -> float:
    observed_keys = {_subject_key(name) for name in subject_names} - {""}
    persona_keys = {_subject_key(name) for name, _ in persona.subjects} - {""}
    if not observed_keys or not persona_keys:
        return 0.0
    return len(observed_keys & persona_keys) / len(observed_keys | persona_keys)


# ── Step 4: backbone reranking ────────────────────────────────────────────


_RERANK_SYSTEM_PROMPT = (
    "You are an educational profile matching component. "
    "Select the best HACHIMI-1M persona for this dialogue learner. "
    "Return exactly one JSON object."
)


def _backbone_rerank(
    observed: dict[str, Any],
    candidates: list[RankedCandidate],
    llm_client: Any,
    max_attempts: int = 3,
) -> tuple[RankedCandidate, list[str], list[str], str]:
    candidate_by_id = {c.persona.persona_id: c for c in candidates}

    candidate_rows = []
    for c in candidates:
        candidate_rows.append({
            "persona_id": c.persona.persona_id,
            "grade_or_age": c.persona.grade_or_age,
            "academic_level": c.persona.academic_level,
            "subjects": c.persona.subjects,
            "learning_style_tags": c.persona.learning_style_tags,
            "self_efficacy": c.persona.self_efficacy_description,
            "motivation": c.persona.motivation_description,
            "confidence": c.persona.confidence_description,
            "interactional_style": c.persona.interactional_style,
            "persona_description": c.persona.persona_description,
            "rule_rank_score": c.rank_score,
            "rule_rank_evidence": c.rank_evidence,
        })

    prompt = (
        "Select the best HACHIMI persona for this dialogue learner.\n\n"
        "Decision rule:\n"
        "- The dialogue history is the primary evidence for learning behavior.\n"
        "- HACHIMI is an external prior for motivation, confidence, learning "
        "habits, self-efficacy, and interaction style.\n"
        "- Consider the full persona description for every candidate.\n"
        "- If the dialogue evidence and a persona conflict, select the most "
        "plausible overall persona and keep the conflict explicit.\n\n"
        f"Dialogue observed profile:\n{json.dumps(observed, ensure_ascii=False)}\n\n"
        f"Candidate personas (rule-ranked):\n{json.dumps(candidate_rows, ensure_ascii=False)}\n\n"
        "Return JSON with:\n"
        "- selected_persona_id: one of the candidate persona_id values\n"
        "- match_evidence: non-empty list[str]\n"
        "- conflict_evidence: list[str] ([] if no meaningful conflict)\n"
        "- fusion_rule: string describing how dialogue evidence and persona "
        "should be fused downstream"
    )

    last_error: Exception | None = None
    for _ in range(max_attempts):
        try:
            parsed = llm_client.chat_json(
                system_prompt=_RERANK_SYSTEM_PROMPT,
                user_prompt=prompt,
            )
            selected_id = str(parsed.get("selected_persona_id", "")).strip()
            if selected_id not in candidate_by_id:
                raise ValueError(
                    f"selected_persona_id must be one of "
                    f"{sorted(candidate_by_id)}, got {selected_id!r}"
                )
            match_evidence = parsed.get("match_evidence", [])
            if not isinstance(match_evidence, list) or not match_evidence:
                raise ValueError("match_evidence must be a non-empty list")
            match_evidence = [str(e).strip() for e in match_evidence if str(e).strip()]
            conflict_evidence = parsed.get("conflict_evidence", [])
            if not isinstance(conflict_evidence, list):
                conflict_evidence = []
            conflict_evidence = [str(e).strip() for e in conflict_evidence if str(e).strip()]
            fusion_rule = str(parsed.get("fusion_rule", "")).strip()
            if not fusion_rule:
                fusion_rule = "backbone_reranked"
            return (
                candidate_by_id[selected_id],
                match_evidence,
                conflict_evidence,
                fusion_rule,
            )
        except Exception as exc:
            last_error = exc

    fallback = candidates[0]
    return (
        fallback,
        fallback.rank_evidence + [f"rerank_fallback: {last_error}"],
        [],
        "rerank_failed_fallback_to_rule_top1",
    )


# ── Step 5: validity check ───────────────────────────────────────────────


def _validity_check(
    selected: RankedCandidate,
    candidates: list[RankedCandidate],
) -> tuple[RankedCandidate, list[RankedCandidate]]:
    rank = {}
    for position, candidate in enumerate(candidates):
        rank.setdefault(candidate.persona.persona_id, position)

    # Membership in the candidate pool
    if selected.persona.persona_id not in rank:
        selected = candidates[0]

    # Near-duplicate removal; the selected persona is always kept.
    kept: list[RankedCandidate] = [selected]
    for candidate in candidates:
        if any(_is_near_duplicate(candidate.persona, k.persona) for k in kept):
            continue
        kept.append(candidate)
    kept.sort(key=lambda c: rank[c.persona.persona_id])

    # Completeness of the selected persona's fields
    if not _is_complete(selected.persona):
        selected = next((c for c in kept if _is_complete(c.persona)), selected)

    return selected, kept


def _is_complete(persona: HachimiPersona) -> bool:
    return all(
        str(getattr(persona, field, "") or "").strip()
        for field in REQUIRED_PERSONA_FIELDS
    )


def _is_near_duplicate(left: HachimiPersona, right: HachimiPersona) -> bool:
    if left.persona_id == right.persona_id:
        return True
    left_shingles = _char_shingles(_persona_text(left))
    right_shingles = _char_shingles(_persona_text(right))
    if not left_shingles or not right_shingles:
        return False
    similarity = len(left_shingles & right_shingles) / len(left_shingles | right_shingles)
    return similarity >= NEAR_DUPLICATE_THRESHOLD


def _persona_text(persona: HachimiPersona) -> str:
    return " ".join(
        [
            persona.persona_description,
            persona.self_efficacy_description,
            persona.motivation_description,
            persona.confidence_description,
            persona.interactional_style,
        ]
    )


def _char_shingles(text: str, size: int = 3) -> set[str]:
    normalized = " ".join(str(text or "").lower().split())
    return {normalized[i : i + size] for i in range(len(normalized) - size + 1)}


# ── Step 6: fusion helpers ────────────────────────────────────────────────


def _extract_learning_tendencies(persona: HachimiPersona) -> list[str]:
    tendencies: list[str] = []
    for field in ("self_efficacy_description", "motivation_description", "confidence_description"):
        value = getattr(persona, field, "")
        if value and value.strip():
            tendencies.append(value.strip())
    return tendencies[:3]


def _extract_interactional_styles(persona: HachimiPersona) -> list[str]:
    if persona.interactional_style and persona.interactional_style.strip():
        return [persona.interactional_style.strip()]
    return []


# ── Parsing ───────────────────────────────────────────────────────────────


def _parse_persona(
    raw: dict[str, object],
    path: Path,
    line_no: int,
) -> HachimiPersona:
    required = {
        "persona_id",
        "grade_or_age",
        "academic_level",
        "subjects",
        "learning_style_tags",
        "self_efficacy_description",
        "motivation_description",
        "confidence_description",
        "interactional_style",
        "persona_description",
    }
    missing = sorted(required - set(raw))
    if missing:
        raise ValueError(f"{path} line {line_no} missing keys: {missing}")
    subjects_raw = raw["subjects"]
    if not isinstance(subjects_raw, list):
        raise ValueError(f"{path} line {line_no} subjects must be a list")
    subjects: list[tuple[str, int]] = []
    for item in subjects_raw:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            subjects.append((str(item[0]).strip(), int(item[1])))
        else:
            raise ValueError(f"{path} line {line_no} invalid subject item: {item!r}")
    learning_style_tags = raw["learning_style_tags"]
    if not isinstance(learning_style_tags, list):
        raise ValueError(f"{path} line {line_no} learning_style_tags must be a list")
    return HachimiPersona(
        persona_id=str(raw["persona_id"]).strip(),
        grade_or_age=str(raw["grade_or_age"]).strip(),
        academic_level=str(raw["academic_level"]).strip(),
        subjects=subjects,
        learning_style_tags=[str(t).strip() for t in learning_style_tags],
        self_efficacy_description=str(raw["self_efficacy_description"]).strip(),
        motivation_description=str(raw["motivation_description"]).strip(),
        confidence_description=str(raw["confidence_description"]).strip(),
        interactional_style=str(raw["interactional_style"]).strip(),
        persona_description=str(raw["persona_description"]).strip(),
    )
