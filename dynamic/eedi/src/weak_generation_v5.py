from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass

from .llm_client import OpenAICompatClient, require_keys
from .prompts import WEAK_STUDENT_GENERATOR_V5_SYSTEM_PROMPT
from .weak_harness import (
    LearningAccessState,
    StudentPrior,
    SupportUptake,
    TutorMove,
    VisibleContext,
)
from .weak_harness_v5 import LearningOpportunityState, OpportunityConstraintBundle


@dataclass(frozen=True)
class WeakTurnValidationV5:
    is_valid: bool
    sentence_count: int
    issues: list[str]


@dataclass(frozen=True)
class GeneratedWeakStudentTurnV5:
    pred_turn: str
    stop_dialogue: bool
    turn_rationale: list[str]
    validation: WeakTurnValidationV5
    retried: bool


def generate_weak_student_turn_v5(
    visible_context: VisibleContext,
    student_prior: StudentPrior,
    tutor_move: TutorMove,
    learning_access_state: LearningAccessState,
    support_uptake: SupportUptake,
    learning_opportunity_state: LearningOpportunityState,
    opportunity_constraint_bundle: OpportunityConstraintBundle,
    llm_client: OpenAICompatClient,
) -> GeneratedWeakStudentTurnV5:
    initial = _realize_once(
        visible_context=visible_context,
        student_prior=student_prior,
        tutor_move=tutor_move,
        learning_access_state=learning_access_state,
        support_uptake=support_uptake,
        learning_opportunity_state=learning_opportunity_state,
        opportunity_constraint_bundle=opportunity_constraint_bundle,
        llm_client=llm_client,
        retry_note="",
    )
    validation = validate_generated_weak_turn_v5(
        pred_turn=initial.pred_turn,
        opportunity_constraint_bundle=opportunity_constraint_bundle,
    )
    if validation.is_valid:
        return GeneratedWeakStudentTurnV5(
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
        learning_opportunity_state=learning_opportunity_state,
        opportunity_constraint_bundle=opportunity_constraint_bundle,
        llm_client=llm_client,
        retry_note=(
            "Previous output violated the opportunity-constraint protocol. "
            f"Issues: {validation.issues}."
        ),
    )
    retry_validation = validate_generated_weak_turn_v5(
        pred_turn=retried.pred_turn,
        opportunity_constraint_bundle=opportunity_constraint_bundle,
    )
    return GeneratedWeakStudentTurnV5(
        pred_turn=retried.pred_turn,
        stop_dialogue=retried.stop_dialogue,
        turn_rationale=retried.turn_rationale,
        validation=retry_validation,
        retried=True,
    )


def validate_generated_weak_turn_v5(
    pred_turn: str,
    opportunity_constraint_bundle: OpportunityConstraintBundle,
) -> WeakTurnValidationV5:
    text = pred_turn.strip()
    issues: list[str] = []
    if not text:
        issues.append("pred_turn is empty")
    sentence_count = _count_sentences(text) if text else 0
    if text and sentence_count > opportunity_constraint_bundle.max_sentences:
        issues.append(
            "pred_turn exceeds max_sentences="
            f"{opportunity_constraint_bundle.max_sentences} with sentence_count={sentence_count}"
        )
    if (
        opportunity_constraint_bundle.claim_permission == "no_new_math_claim"
        and _looks_like_bare_math_answer(text)
    ):
        issues.append("pred_turn invents a new mathematical answer under no_new_math_claim")
    return WeakTurnValidationV5(
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
    learning_opportunity_state: LearningOpportunityState,
    opportunity_constraint_bundle: OpportunityConstraintBundle,
    llm_client: OpenAICompatClient,
    retry_note: str,
) -> GeneratedWeakStudentTurnV5:
    payload = {
        "visible_context": asdict(visible_context),
        "student_prior": asdict(student_prior),
        "tutor_move": asdict(tutor_move),
        "learning_access_state": asdict(learning_access_state),
        "support_uptake": asdict(support_uptake),
        "learning_opportunity_state": asdict(learning_opportunity_state),
        "opportunity_constraint_bundle": asdict(opportunity_constraint_bundle),
        "retry_note": retry_note,
        "required_schema": {
            "pred_turn": "string",
            "stop_dialogue": "boolean",
            "turn_rationale": ["string"],
        },
    }
    user_prompt = json.dumps(payload, ensure_ascii=False)
    parsed = llm_client.chat_json(
        system_prompt=WEAK_STUDENT_GENERATOR_V5_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        partial_string_keys=["pred_turn"],
    )
    try:
        parsed = _parse_realization(parsed)
    except (KeyError, ValueError) as exc:
        repaired = llm_client.retry_schema_json(
            system_prompt=WEAK_STUDENT_GENERATOR_V5_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            previous_reply=parsed,
            validation_error=str(exc),
            partial_string_keys=["pred_turn"],
        )
        parsed = _parse_realization(repaired)
    return GeneratedWeakStudentTurnV5(
        pred_turn=str(parsed["pred_turn"]).strip(),
        stop_dialogue=bool(parsed["stop_dialogue"]),
        turn_rationale=_coerce_str_list(parsed["turn_rationale"], "turn_rationale"),
        validation=WeakTurnValidationV5(
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
        "WeakTurnRealizationV5",
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
