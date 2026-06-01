from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass

from .llm_client import OpenAICompatClient, require_keys
from .prompts import (
    WEAK_STUDENT_PLAN_SYSTEM_PROMPT,
    WEAK_STUDENT_REALIZATION_SYSTEM_PROMPT,
)
from .weak_harness import (
    LearningAccessState,
    LocalErrorRealizationState,
    MathClaimAffordanceState,
    StudentPrior,
    SupportUptake,
    TeachingSupportPacket,
    TutorMove,
    VisibleContext,
)


PLAN_ACTION_TYPES = (
    "brief_acknowledgment",
    "clarification_request",
    "partial_attempt",
    "revision_attempt",
    "local_explanation",
)
CLAIM_CONFIDENCE_LEVELS = ("low", "medium", "high")


@dataclass(frozen=True)
class WeakTurnPlan:
    response_action: str
    local_claim: str
    claim_confidence: str
    uses_tutor_support: bool
    realizes_error: bool
    planning_rationale: list[str]


@dataclass(frozen=True)
class WeakTurnValidation:
    is_valid: bool
    sentence_count: int
    issues: list[str]


@dataclass(frozen=True)
class GeneratedWeakStudentTurn:
    pred_turn: str
    stop_dialogue: bool
    turn_rationale: list[str]
    turn_plan: WeakTurnPlan
    validation: WeakTurnValidation
    retried: bool


def generate_weak_student_turn(
    visible_context: VisibleContext,
    student_prior: StudentPrior,
    tutor_move: TutorMove,
    learning_access_state: LearningAccessState,
    support_uptake: SupportUptake,
    math_claim_affordance: MathClaimAffordanceState,
    local_error_state: LocalErrorRealizationState,
    teaching_support_packet: TeachingSupportPacket,
    llm_client: OpenAICompatClient,
) -> GeneratedWeakStudentTurn:
    initial = _generate_once(
        visible_context=visible_context,
        student_prior=student_prior,
        tutor_move=tutor_move,
        learning_access_state=learning_access_state,
        support_uptake=support_uptake,
        math_claim_affordance=math_claim_affordance,
        local_error_state=local_error_state,
        teaching_support_packet=teaching_support_packet,
        llm_client=llm_client,
        retry_note="",
    )
    validation = validate_generated_weak_turn(
        pred_turn=initial.pred_turn,
        turn_plan=initial.turn_plan,
        teaching_support_packet=teaching_support_packet,
    )
    if validation.is_valid:
        return GeneratedWeakStudentTurn(
            pred_turn=initial.pred_turn,
            stop_dialogue=initial.stop_dialogue,
            turn_rationale=initial.turn_rationale,
            turn_plan=initial.turn_plan,
            validation=validation,
            retried=False,
        )

    retried = _generate_once(
        visible_context=visible_context,
        student_prior=student_prior,
        tutor_move=tutor_move,
        learning_access_state=learning_access_state,
        support_uptake=support_uptake,
        math_claim_affordance=math_claim_affordance,
        local_error_state=local_error_state,
        teaching_support_packet=teaching_support_packet,
        llm_client=llm_client,
        retry_note=(
            "Previous output violated the packet-level protocol. "
            f"Issues: {validation.issues}."
        ),
    )
    retry_validation = validate_generated_weak_turn(
        pred_turn=retried.pred_turn,
        turn_plan=retried.turn_plan,
        teaching_support_packet=teaching_support_packet,
    )
    return GeneratedWeakStudentTurn(
        pred_turn=retried.pred_turn,
        stop_dialogue=retried.stop_dialogue,
        turn_rationale=retried.turn_rationale,
        turn_plan=retried.turn_plan,
        validation=retry_validation,
        retried=True,
    )


def validate_generated_weak_turn(
    pred_turn: str,
    turn_plan: WeakTurnPlan,
    teaching_support_packet: TeachingSupportPacket,
) -> WeakTurnValidation:
    text = pred_turn.strip()
    issues: list[str] = []
    if not text:
        issues.append("pred_turn is empty")
    sentence_count = _count_sentences(text) if text else 0
    if text and sentence_count > teaching_support_packet.max_sentences:
        issues.append(
            "pred_turn exceeds max_sentences="
            f"{teaching_support_packet.max_sentences} with sentence_count={sentence_count}"
        )
    wrong_claim_seed = str(teaching_support_packet.wrong_claim_seed or "").strip().lower()
    return WeakTurnValidation(
        is_valid=not issues,
        sentence_count=sentence_count,
        issues=issues or ["ok"],
    )


def _generate_once(
    visible_context: VisibleContext,
    student_prior: StudentPrior,
    tutor_move: TutorMove,
    learning_access_state: LearningAccessState,
    support_uptake: SupportUptake,
    math_claim_affordance: MathClaimAffordanceState,
    local_error_state: LocalErrorRealizationState,
    teaching_support_packet: TeachingSupportPacket,
    llm_client: OpenAICompatClient,
    retry_note: str,
) -> GeneratedWeakStudentTurn:
    turn_plan = _plan_once(
        visible_context=visible_context,
        student_prior=student_prior,
        tutor_move=tutor_move,
        learning_access_state=learning_access_state,
        support_uptake=support_uptake,
        math_claim_affordance=math_claim_affordance,
        local_error_state=local_error_state,
        teaching_support_packet=teaching_support_packet,
        llm_client=llm_client,
        retry_note=retry_note,
    )
    pred_turn, stop_dialogue, turn_rationale = _realize_once(
        visible_context=visible_context,
        student_prior=student_prior,
        tutor_move=tutor_move,
        learning_access_state=learning_access_state,
        support_uptake=support_uptake,
        math_claim_affordance=math_claim_affordance,
        local_error_state=local_error_state,
        teaching_support_packet=teaching_support_packet,
        turn_plan=turn_plan,
        llm_client=llm_client,
        retry_note=retry_note,
    )
    return GeneratedWeakStudentTurn(
        pred_turn=pred_turn,
        stop_dialogue=stop_dialogue,
        turn_rationale=turn_rationale,
        turn_plan=turn_plan,
        validation=WeakTurnValidation(
            is_valid=False,
            sentence_count=0,
            issues=["not validated yet"],
        ),
        retried=False,
    )


def _plan_once(
    visible_context: VisibleContext,
    student_prior: StudentPrior,
    tutor_move: TutorMove,
    learning_access_state: LearningAccessState,
    support_uptake: SupportUptake,
    math_claim_affordance: MathClaimAffordanceState,
    local_error_state: LocalErrorRealizationState,
    teaching_support_packet: TeachingSupportPacket,
    llm_client: OpenAICompatClient,
    retry_note: str,
) -> WeakTurnPlan:
    payload = {
        "visible_context": asdict(visible_context),
        "student_prior": asdict(student_prior),
        "tutor_move": asdict(tutor_move),
        "learning_access_state": asdict(learning_access_state),
        "support_uptake": asdict(support_uptake),
        "math_claim_affordance": asdict(math_claim_affordance),
        "local_error_state": asdict(local_error_state),
        "teaching_support_packet": asdict(teaching_support_packet),
        "retry_note": retry_note,
        "required_schema": {
            "response_action": list(PLAN_ACTION_TYPES),
            "local_claim": "string",
            "claim_confidence": list(CLAIM_CONFIDENCE_LEVELS),
            "uses_tutor_support": "boolean",
            "realizes_error": "boolean",
            "planning_rationale": ["string"],
        },
    }
    user_prompt = json.dumps(payload, ensure_ascii=False)
    parsed = llm_client.chat_json(
        system_prompt=WEAK_STUDENT_PLAN_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        partial_string_keys=["local_claim"],
    )
    parsed = _normalize_turn_plan_schema(parsed, teaching_support_packet)
    try:
        return _parse_turn_plan(parsed)
    except (KeyError, ValueError) as exc:
        repaired = llm_client.retry_schema_json(
            system_prompt=WEAK_STUDENT_PLAN_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            previous_reply=parsed,
            validation_error=str(exc),
            partial_string_keys=["local_claim"],
        )
        repaired = _normalize_turn_plan_schema(repaired, teaching_support_packet)
        return _parse_turn_plan(repaired)


def _realize_once(
    visible_context: VisibleContext,
    student_prior: StudentPrior,
    tutor_move: TutorMove,
    learning_access_state: LearningAccessState,
    support_uptake: SupportUptake,
    math_claim_affordance: MathClaimAffordanceState,
    local_error_state: LocalErrorRealizationState,
    teaching_support_packet: TeachingSupportPacket,
    turn_plan: WeakTurnPlan,
    llm_client: OpenAICompatClient,
    retry_note: str,
) -> tuple[str, bool, list[str]]:
    required_schema = {
        "pred_turn": "string",
        "stop_dialogue": "boolean",
        "turn_rationale": ["string"],
    }
    payload = {
        "visible_context": asdict(visible_context),
        "student_prior": asdict(student_prior),
        "tutor_move": asdict(tutor_move),
        "learning_access_state": asdict(learning_access_state),
        "support_uptake": asdict(support_uptake),
        "math_claim_affordance": asdict(math_claim_affordance),
        "local_error_state": asdict(local_error_state),
        "teaching_support_packet": asdict(teaching_support_packet),
        "turn_plan": asdict(turn_plan),
        "retry_note": retry_note,
        "required_schema": required_schema,
    }
    user_prompt = json.dumps(payload, ensure_ascii=False)
    parsed = llm_client.chat_json(
        system_prompt=WEAK_STUDENT_REALIZATION_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        partial_string_keys=["pred_turn"],
    )
    try:
        parsed = _parse_realization(parsed)
    except (KeyError, ValueError) as exc:
        repaired = llm_client.retry_schema_json(
            system_prompt=WEAK_STUDENT_REALIZATION_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            previous_reply=parsed,
            validation_error=str(exc),
            partial_string_keys=["pred_turn"],
        )
        parsed = _parse_realization(repaired)
    return (
        str(parsed["pred_turn"]).strip(),
        bool(parsed["stop_dialogue"]),
        _coerce_str_list(parsed["turn_rationale"], "turn_rationale"),
    )


def _parse_turn_plan(parsed: object) -> WeakTurnPlan:
    if isinstance(parsed, dict) and "realizes_error" not in parsed and "realizing_error" in parsed:
        parsed = dict(parsed)
        parsed["realizes_error"] = parsed["realizing_error"]
    if (
        isinstance(parsed, dict)
        and "realizes_error" not in parsed
        and "realizing_mathematical_misconception" in parsed
    ):
        parsed = dict(parsed)
        parsed["realizes_error"] = parsed["realizing_mathematical_misconception"]
    if isinstance(parsed, dict) and "realizes_error" not in parsed:
        parsed = dict(parsed)
        parsed["realizes_error"] = False
    parsed = require_keys(
        parsed,
        (
            "response_action",
            "local_claim",
            "claim_confidence",
            "uses_tutor_support",
            "realizes_error",
            "planning_rationale",
        ),
        "WeakTurnPlan",
    )
    local_claim = str(parsed["local_claim"]).strip()
    if not local_claim:
        raise ValueError("local_claim cannot be empty")
    planning_rationale = _coerce_optional_str_list(
        parsed["planning_rationale"],
        "planning_rationale",
    )
    return WeakTurnPlan(
        response_action=_coerce_enum(
            parsed["response_action"],
            PLAN_ACTION_TYPES,
            "response_action",
        ),
        local_claim=local_claim,
        claim_confidence=_coerce_enum(
            parsed["claim_confidence"],
            CLAIM_CONFIDENCE_LEVELS,
            "claim_confidence",
        ),
        uses_tutor_support=_coerce_bool(
            parsed["uses_tutor_support"],
            "uses_tutor_support",
        ),
        realizes_error=_coerce_bool(
            parsed["realizes_error"],
            "realizes_error",
        ),
        planning_rationale=planning_rationale or ["model returned no explicit planning rationale"],
    )


def _parse_realization(parsed: object) -> dict[str, object]:
    parsed = require_keys(
        parsed,
        ("pred_turn", "stop_dialogue", "turn_rationale"),
        "WeakTurnRealization",
    )
    pred_turn = str(parsed["pred_turn"]).strip()
    if not pred_turn:
        raise ValueError("pred_turn cannot be empty")
    parsed["pred_turn"] = pred_turn
    parsed["stop_dialogue"] = _coerce_bool(parsed["stop_dialogue"], "stop_dialogue")
    parsed["turn_rationale"] = _coerce_str_list(parsed["turn_rationale"], "turn_rationale")
    return parsed


def _count_sentences(text: str) -> int:
    normalized = re.sub(r"(?<=\d)\.(?=\d)", "<DECIMAL>", text)
    normalized = normalized.replace("...", ".")
    parts = [
        part.strip()
        for part in re.split(r"[.!?]+", normalized)
        if part.strip()
    ]
    return max(1, len(parts))


def _contains_focus_signal(text: str, local_focus: str) -> bool:
    focus_words = [part.strip() for part in re.split(r"[^a-z0-9]+", local_focus) if part.strip()]
    if not focus_words:
        return True
    content_words = [
        word
        for word in focus_words
        if len(word) >= 5 and word not in {"which", "count", "answer", "should"}
    ]
    if not content_words:
        return True
    return any(word in text for word in content_words[:3])


def _has_overlap(text: str, target: str) -> bool:
    target_words = [part.strip() for part in re.split(r"[^a-z0-9]+", target) if part.strip()]
    if not target_words:
        return True
    overlap = sum(1 for word in target_words if word in text)
    return overlap >= max(1, min(2, len(target_words)))


def _preserves_wrong_claim_seed(text: str, target: str) -> bool:
    target_tokens = [
        part.strip()
        for part in re.split(r"[^a-z0-9.]+", target.lower())
        if part.strip()
    ]
    if not target_tokens:
        return True
    text_tokens = {
        part.strip()
        for part in re.split(r"[^a-z0-9.]+", text.lower())
        if part.strip()
    }
    number_tokens = {
        token
        for token in target_tokens
        if re.fullmatch(r"\d+(?:\.\d+)?", token)
    }
    if number_tokens:
        return number_tokens.issubset(text_tokens)
    stopwords = {
        "a",
        "an",
        "and",
        "as",
        "be",
        "because",
        "is",
        "it",
        "of",
        "or",
        "that",
        "the",
        "then",
        "this",
        "to",
    }
    content_tokens = [token for token in target_tokens if token not in stopwords]
    if not content_tokens:
        return _has_overlap(text, target)
    unique_content_tokens = set(content_tokens)
    overlap = sum(1 for token in unique_content_tokens if token in text_tokens)
    required = max(1, (len(unique_content_tokens) * 6 + 9) // 10)
    return overlap >= required


def _response_action_matches_packet(action: str, response_space: str) -> bool:
    if action == response_space:
        return True
    compatible = {
        ("partial_attempt", "revision_attempt"),
        ("revision_attempt", "partial_attempt"),
        ("partial_attempt", "local_explanation"),
        ("local_explanation", "partial_attempt"),
        ("revision_attempt", "local_explanation"),
        ("local_explanation", "revision_attempt"),
        ("clarification_request", "brief_acknowledgment"),
        ("brief_acknowledgment", "clarification_request"),
    }
    return (action, response_space) in compatible


def _normalize_turn_plan_schema(
    parsed: object,
    teaching_support_packet: TeachingSupportPacket,
) -> object:
    if not isinstance(parsed, dict):
        return parsed
    normalized = dict(parsed)
    action = normalized.get("response_action")
    if isinstance(action, list):
        action_values = [str(item).strip() for item in action if str(item).strip()]
        if teaching_support_packet.response_space in action_values:
            normalized["response_action"] = teaching_support_packet.response_space
        elif len(action_values) == 1:
            normalized["response_action"] = action_values[0]
    if "realizes_error" not in normalized:
        normalized["realizes_error"] = (
            teaching_support_packet.local_error_presence == "codable_math_error"
        )
    rationale = normalized.get("planning_rationale")
    if isinstance(rationale, str):
        normalized["planning_rationale"] = [rationale] if rationale.strip() else []
    return normalized


def _coerce_enum(value: object, allowed: tuple[str, ...], field_name: str) -> str:
    if isinstance(value, list):
        if len(value) == len(allowed) and all(str(item).strip() in allowed for item in value):
            value = value[0]
        elif len(value) != 1:
            raise ValueError(f"{field_name} must be one of {allowed}, got {value!r}")
        value = value[0]
    text = str(value).strip()
    if text not in allowed:
        raise ValueError(f"{field_name} must be one of {allowed}, got {text!r}")
    return text


def _coerce_bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be boolean, got {type(value).__name__}: {value!r}")
    return value


def _coerce_str_list(value: object, field_name: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field_name} must be a non-empty list")
    result = [str(item).strip() for item in value if str(item).strip()]
    if not result:
        raise ValueError(f"{field_name} must contain non-empty strings")
    return result


def _coerce_optional_str_list(value: object, field_name: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")
    return [str(item).strip() for item in value if str(item).strip()]
