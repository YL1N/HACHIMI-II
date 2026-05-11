from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass

from .llm_client import OpenAICompatClient, require_keys
from .prompts import WEAK_STUDENT_GENERATOR_V52_SYSTEM_PROMPT
from .weak_harness import (
    LearningAccessState,
    StudentPrior,
    SupportUptake,
    TutorMove,
    VisibleContext,
)
from .weak_harness_v5 import LearningOpportunityState
from .weak_harness_v52 import (
    ClaimRealizationFrame,
    LocalBeliefStateV52,
    OpportunityConstraintBundleV52,
    StudentResponsePolicyStateV52,
    SupportTransformationStateV52,
)


@dataclass(frozen=True)
class WeakTurnValidationV52:
    is_valid: bool
    sentence_count: int
    issues: list[str]


@dataclass(frozen=True)
class GeneratedWeakStudentTurnV52:
    pred_turn: str
    stop_dialogue: bool
    turn_rationale: list[str]
    validation: WeakTurnValidationV52
    retried: bool


def generate_weak_student_turn_v52(
    visible_context: VisibleContext,
    student_prior: StudentPrior,
    tutor_move: TutorMove,
    learning_access_state: LearningAccessState,
    support_uptake: SupportUptake,
    learning_opportunity_state: LearningOpportunityState,
    student_response_policy: StudentResponsePolicyStateV52,
    local_belief_state: LocalBeliefStateV52,
    support_transformation_state: SupportTransformationStateV52,
    claim_realization_frame: ClaimRealizationFrame,
    opportunity_constraint_bundle_v52: OpportunityConstraintBundleV52,
    llm_client: OpenAICompatClient,
) -> GeneratedWeakStudentTurnV52:
    initial = _realize_once(
        visible_context=visible_context,
        student_prior=student_prior,
        tutor_move=tutor_move,
        learning_access_state=learning_access_state,
        support_uptake=support_uptake,
        learning_opportunity_state=learning_opportunity_state,
        student_response_policy=student_response_policy,
        local_belief_state=local_belief_state,
        support_transformation_state=support_transformation_state,
        claim_realization_frame=claim_realization_frame,
        opportunity_constraint_bundle_v52=opportunity_constraint_bundle_v52,
        llm_client=llm_client,
        retry_note="",
    )
    validation = validate_generated_weak_turn_v52(
        pred_turn=initial.pred_turn,
        bundle=opportunity_constraint_bundle_v52,
    )
    if validation.is_valid:
        return GeneratedWeakStudentTurnV52(
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
        student_response_policy=student_response_policy,
        local_belief_state=local_belief_state,
        support_transformation_state=support_transformation_state,
        claim_realization_frame=claim_realization_frame,
        opportunity_constraint_bundle_v52=opportunity_constraint_bundle_v52,
        llm_client=llm_client,
        retry_note=(
            "Previous output violated the v5.2 constraint bundle. "
            f"Issues: {validation.issues}."
        ),
    )
    retry_validation = validate_generated_weak_turn_v52(
        pred_turn=retried.pred_turn,
        bundle=opportunity_constraint_bundle_v52,
    )
    return GeneratedWeakStudentTurnV52(
        pred_turn=retried.pred_turn,
        stop_dialogue=retried.stop_dialogue,
        turn_rationale=retried.turn_rationale,
        validation=retry_validation,
        retried=True,
    )


def validate_generated_weak_turn_v52(
    pred_turn: str,
    bundle: OpportunityConstraintBundleV52,
) -> WeakTurnValidationV52:
    text = pred_turn.strip()
    issues: list[str] = []
    if not text:
        issues.append("pred_turn is empty")
    sentence_count = _count_sentences(text) if text else 0
    if text and sentence_count > bundle.max_sentences:
        issues.append(
            "pred_turn exceeds max_sentences="
            f"{bundle.max_sentences} with sentence_count={sentence_count}"
        )
    if (
        bundle.claim_state == "no_claim"
        and bundle.response_space not in {"brief_acknowledgment", "clarification_request"}
        and _looks_like_bare_math_answer(text)
    ):
        issues.append("pred_turn invents a new mathematical answer when claim_state is no_claim")
    if (
        bundle.claim_state != "no_claim"
        and bundle.anchor_mode == "stay_with_visible_belief"
        and bundle.preserve_prior_commitment
        and local_surface_breaks_visible_belief(text, bundle)
    ):
        issues.append("pred_turn breaks visible belief continuity too abruptly")
    return WeakTurnValidationV52(
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
    student_response_policy: StudentResponsePolicyStateV52,
    local_belief_state: LocalBeliefStateV52,
    support_transformation_state: SupportTransformationStateV52,
    claim_realization_frame: ClaimRealizationFrame,
    opportunity_constraint_bundle_v52: OpportunityConstraintBundleV52,
    llm_client: OpenAICompatClient,
    retry_note: str,
) -> GeneratedWeakStudentTurnV52:
    payload = {
        "visible_context": asdict(visible_context),
        "student_prior": asdict(student_prior),
        "tutor_move": asdict(tutor_move),
        "learning_access_state": asdict(learning_access_state),
        "support_uptake": asdict(support_uptake),
        "learning_opportunity_state": asdict(learning_opportunity_state),
        "student_response_policy": asdict(student_response_policy),
        "local_belief_state": asdict(local_belief_state),
        "support_transformation_state": asdict(support_transformation_state),
        "claim_realization_frame": asdict(claim_realization_frame),
        "opportunity_constraint_bundle_v52": asdict(opportunity_constraint_bundle_v52),
        "retry_note": retry_note,
        "required_schema": {
            "pred_turn": "string",
            "stop_dialogue": "boolean",
            "turn_rationale": ["string"],
        },
    }
    user_prompt = json.dumps(payload, ensure_ascii=False)
    parsed = llm_client.chat_json(
        system_prompt=WEAK_STUDENT_GENERATOR_V52_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        partial_string_keys=["pred_turn"],
    )
    try:
        parsed = _parse_realization(parsed)
    except (KeyError, ValueError) as exc:
        repaired = llm_client.retry_schema_json(
            system_prompt=WEAK_STUDENT_GENERATOR_V52_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            previous_reply=parsed,
            validation_error=str(exc),
            partial_string_keys=["pred_turn"],
        )
        parsed = _parse_realization(repaired)
    return GeneratedWeakStudentTurnV52(
        pred_turn=str(parsed["pred_turn"]).strip(),
        stop_dialogue=bool(parsed["stop_dialogue"]),
        turn_rationale=_coerce_str_list(parsed["turn_rationale"], "turn_rationale"),
        validation=WeakTurnValidationV52(
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
        "WeakTurnRealizationV52",
    )
    pred_turn = str(parsed["pred_turn"]).strip()
    if not pred_turn:
        raise ValueError("pred_turn cannot be empty")
    if not isinstance(parsed["stop_dialogue"], bool):
        raise ValueError("stop_dialogue must be boolean")
    parsed["pred_turn"] = pred_turn
    parsed["turn_rationale"] = _coerce_optional_str_list(
        parsed["turn_rationale"],
        "turn_rationale",
    ) or ["The weak actor followed the compiled v5.2 frame."]
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


def local_surface_breaks_visible_belief(
    text: str,
    bundle: OpportunityConstraintBundleV52,
) -> bool:
    stripped = text.strip().lower()
    if bundle.claim_state == "no_claim":
        return False
    if bundle.anchor_mode != "stay_with_visible_belief":
        return False
    if not bundle.allowed_content_sources:
        return False
    seed_words = set()
    for source in bundle.allowed_content_sources:
        for part in re.findall(r"[A-Za-z0-9]+", source.lower()):
            if len(part) >= 2:
                seed_words.add(part)
    if not seed_words:
        return False
    overlap = sum(1 for word in seed_words if word in stripped)
    return overlap == 0


def _coerce_str_list(value: object, field_name: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field_name} must be a non-empty list")
    result = [str(item).strip() for item in value if str(item).strip()]
    if not result:
        raise ValueError(f"{field_name} must contain non-empty strings")
    return result


def _coerce_optional_str_list(value: object, field_name: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")
    return [str(item).strip() for item in value if str(item).strip()]
