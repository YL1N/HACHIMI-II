from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass

from .llm_client import OpenAICompatClient, require_keys
from .prompts import WEAK_STUDENT_SURFACE_REALIZER_V4_SYSTEM_PROMPT
from .weak_harness import (
    LearningAccessState,
    StudentPrior,
    SupportUptake,
    TutorMove,
    VisibleContext,
)
from .weak_harness_v4 import MediatedTurnPlanState, TeachingSupportPacketV4


@dataclass(frozen=True)
class WeakTurnValidationV4:
    is_valid: bool
    sentence_count: int
    issues: list[str]


@dataclass(frozen=True)
class GeneratedWeakStudentTurnV4:
    pred_turn: str
    stop_dialogue: bool
    turn_rationale: list[str]
    validation: WeakTurnValidationV4
    retried: bool


def generate_weak_student_turn_v4(
    visible_context: VisibleContext,
    student_prior: StudentPrior,
    tutor_move: TutorMove,
    learning_access_state: LearningAccessState,
    support_uptake: SupportUptake,
    mediated_turn_plan: MediatedTurnPlanState,
    teaching_support_packet: TeachingSupportPacketV4,
    llm_client: OpenAICompatClient,
) -> GeneratedWeakStudentTurnV4:
    initial = _realize_once(
        visible_context=visible_context,
        student_prior=student_prior,
        tutor_move=tutor_move,
        learning_access_state=learning_access_state,
        support_uptake=support_uptake,
        mediated_turn_plan=mediated_turn_plan,
        teaching_support_packet=teaching_support_packet,
        llm_client=llm_client,
        retry_note="",
    )
    validation = validate_generated_weak_turn_v4(
        pred_turn=initial.pred_turn,
        mediated_turn_plan=mediated_turn_plan,
        teaching_support_packet=teaching_support_packet,
    )
    if validation.is_valid:
        return GeneratedWeakStudentTurnV4(
            pred_turn=initial.pred_turn,
            stop_dialogue=initial.stop_dialogue,
            turn_rationale=initial.turn_rationale,
            validation=validation,
            retried=False,
        )

    retried = _realize_once(
        visible_context=visible_context,
        student_prior=student_prior,
        tutor_move=tutor_move,
        learning_access_state=learning_access_state,
        support_uptake=support_uptake,
        mediated_turn_plan=mediated_turn_plan,
        teaching_support_packet=teaching_support_packet,
        llm_client=llm_client,
        retry_note=(
            "Previous output violated the packet-level protocol. "
            f"Issues: {validation.issues}."
        ),
    )
    retry_validation = validate_generated_weak_turn_v4(
        pred_turn=retried.pred_turn,
        mediated_turn_plan=mediated_turn_plan,
        teaching_support_packet=teaching_support_packet,
    )
    return GeneratedWeakStudentTurnV4(
        pred_turn=retried.pred_turn,
        stop_dialogue=retried.stop_dialogue,
        turn_rationale=retried.turn_rationale,
        validation=retry_validation,
        retried=True,
    )


def validate_generated_weak_turn_v4(
    pred_turn: str,
    mediated_turn_plan: MediatedTurnPlanState,
    teaching_support_packet: TeachingSupportPacketV4,
) -> WeakTurnValidationV4:
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
    lowered = text.lower()
    if mediated_turn_plan.content_mode == "support_consistent_claim":
        if not _preserves_kernel(lowered, teaching_support_packet.support_consistent_claim_seed or ""):
            issues.append("pred_turn does not preserve support_consistent_claim_seed")
    elif mediated_turn_plan.content_mode == "misconception_consistent_claim":
        if not _preserves_kernel(lowered, teaching_support_packet.wrong_claim_seed or ""):
            issues.append("pred_turn does not preserve wrong_claim_seed")
    elif (
        mediated_turn_plan.content_mode == "no_claim"
        and teaching_support_packet.claim_requirement == "no_claim"
        and _looks_like_bare_math_answer(text)
    ):
        issues.append("pred_turn invents a math answer in a no_claim turn")
    return WeakTurnValidationV4(
        is_valid=not issues,
        sentence_count=sentence_count,
        issues=issues or ["ok"],
    )


def _realize_once(
    visible_context: VisibleContext,
    student_prior: StudentPrior,
    tutor_move: TutorMove,
    learning_access_state: LearningAccessState,
    support_uptake: SupportUptake,
    mediated_turn_plan: MediatedTurnPlanState,
    teaching_support_packet: TeachingSupportPacketV4,
    llm_client: OpenAICompatClient,
    retry_note: str,
) -> GeneratedWeakStudentTurnV4:
    payload = {
        "visible_context": asdict(visible_context),
        "student_prior": asdict(student_prior),
        "tutor_move": asdict(tutor_move),
        "learning_access_state": asdict(learning_access_state),
        "support_uptake": asdict(support_uptake),
        "mediated_turn_plan": asdict(mediated_turn_plan),
        "teaching_support_packet": asdict(teaching_support_packet),
        "retry_note": retry_note,
        "required_schema": {
            "pred_turn": "string",
            "stop_dialogue": "boolean",
            "turn_rationale": ["string"],
        },
    }
    user_prompt = json.dumps(payload, ensure_ascii=False)
    parsed = llm_client.chat_json(
        system_prompt=WEAK_STUDENT_SURFACE_REALIZER_V4_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        partial_string_keys=["pred_turn"],
    )
    try:
        parsed = _parse_realization(parsed)
    except (KeyError, ValueError) as exc:
        repaired = llm_client.retry_schema_json(
            system_prompt=WEAK_STUDENT_SURFACE_REALIZER_V4_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            previous_reply=parsed,
            validation_error=str(exc),
            partial_string_keys=["pred_turn"],
        )
        parsed = _parse_realization(repaired)
    return GeneratedWeakStudentTurnV4(
        pred_turn=str(parsed["pred_turn"]).strip(),
        stop_dialogue=bool(parsed["stop_dialogue"]),
        turn_rationale=_coerce_str_list(parsed["turn_rationale"], "turn_rationale"),
        validation=WeakTurnValidationV4(
            is_valid=False,
            sentence_count=0,
            issues=["not validated yet"],
        ),
        retried=False,
    )


def _parse_realization(parsed: object) -> dict[str, object]:
    parsed = require_keys(
        parsed,
        ("pred_turn", "stop_dialogue", "turn_rationale"),
        "WeakTurnRealizationV4",
    )
    pred_turn = str(parsed["pred_turn"]).strip()
    if not pred_turn:
        raise ValueError("pred_turn cannot be empty")
    if not isinstance(parsed["stop_dialogue"], bool):
        raise ValueError("stop_dialogue must be boolean")
    parsed["pred_turn"] = pred_turn
    parsed["turn_rationale"] = _coerce_str_list(parsed["turn_rationale"], "turn_rationale")
    return parsed


def _count_sentences(text: str) -> int:
    normalized = re.sub(r"(?<=\d)\.(?=\d)", "<DECIMAL>", text)
    normalized = normalized.replace("...", ".")
    parts = [part.strip() for part in re.split(r"[.!?]+", normalized) if part.strip()]
    return max(1, len(parts))


def _preserves_kernel(text: str, target: str) -> bool:
    target_tokens = [
        part.strip()
        for part in re.split(r"[^a-z0-9.]+", str(target).lower())
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
        token for token in target_tokens if re.fullmatch(r"\d+(?:\.\d+)?", token)
    }
    if number_tokens:
        return number_tokens.issubset(text_tokens)
    option_tokens = {
        token for token in target_tokens if token in {"a", "b", "c", "d"}
    }
    if option_tokens and option_tokens.issubset(text_tokens):
        if "option" in target_tokens:
            return True
        non_option_tokens = [
            token
            for token in target_tokens
            if token not in option_tokens and token not in {"the", "option"}
        ]
        if not non_option_tokens:
            return True
        overlap = sum(1 for token in set(non_option_tokens) if token in text_tokens)
        return overlap >= 1
    stopwords = {
        "a",
        "an",
        "and",
        "as",
        "be",
        "because",
        "by",
        "for",
        "i",
        "is",
        "it",
        "of",
        "or",
        "that",
        "the",
        "this",
        "to",
        "we",
    }
    content_tokens = [token for token in target_tokens if token not in stopwords]
    if not content_tokens:
        return True
    overlap = sum(1 for token in set(content_tokens) if token in text_tokens)
    required = max(1, (len(set(content_tokens)) * 6 + 9) // 10)
    return overlap >= required


def _looks_like_bare_math_answer(text: str) -> bool:
    stripped = text.strip()
    if re.fullmatch(r"[A-Da-d]", stripped):
        return True
    if re.fullmatch(r"[-+]?\d+(?:[.,]\d+)?", stripped):
        return True
    math_symbol_count = sum(
        1 for char in stripped if char in {"=", "+", "-", "*", "/", "%", "^", ":"}
    )
    return math_symbol_count >= 2 and len(stripped.split()) <= 8


def _coerce_str_list(value: object, field_name: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field_name} must be a non-empty list")
    result = [str(item).strip() for item in value if str(item).strip()]
    if not result:
        raise ValueError(f"{field_name} must contain non-empty strings")
    return result
