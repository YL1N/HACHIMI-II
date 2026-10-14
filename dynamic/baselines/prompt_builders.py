from __future__ import annotations

import json
import re
from dataclasses import asdict
from typing import Any

from baseline_specs import BaselineSpec
from dataset_adapters import BaselineExample, DialogueTurn


def build_prompt_payload(
    example: BaselineExample,
    spec: BaselineSpec,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "question_text": example.question_text,
        "subjects": [
            {"name": subject_name, "level": subject_level}
            for subject_name, subject_level in example.subjects
        ],
        "history_before_target": [asdict(turn) for turn in example.history_before_target],
    }
    if spec.uses_profile:
        payload["coarse_student_profile"] = infer_coarse_student_profile(
            example.history_before_target
        )
    if spec.uses_memory:
        payload["short_visible_memory"] = build_short_visible_memory(
            example.history_before_target
        )
    return payload


def render_prompt(example: BaselineExample, spec: BaselineSpec) -> str:
    payload = build_prompt_payload(example, spec)
    return (
        f"System instruction:\n{spec.system_message}\n\n"
        f"Task instruction:\n{spec.instruction}\n\n"
        "Allowed input payload follows. It contains only visible information before "
        "the target student turn:\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
        "Return valid JSON only, with exactly this shape:\n"
        '{"student_reply": "<one short next student utterance>"}'
    )


def infer_coarse_student_profile(history: list[DialogueTurn]) -> dict[str, Any]:
    student_turns = [turn.content for turn in history if turn.role == "student"]
    if not student_turns:
        return {
            "prior_student_turn_count": 0,
            "observed_response_length": "none_yet",
            "observed_uncertainty": "unknown",
            "recent_student_style": "no prior student utterance is visible",
        }

    word_counts = [len(turn.split()) for turn in student_turns]
    average_words = sum(word_counts) / len(word_counts)
    uncertainty_count = sum(
        1
        for turn in student_turns
        if re.search(r"\b(idk|not sure|don't know|dont know|confused|maybe)\b", turn, re.I)
    )
    if average_words <= 4:
        length_bucket = "very_short"
    elif average_words <= 12:
        length_bucket = "short"
    else:
        length_bucket = "longer_explanatory"
    if uncertainty_count == 0:
        uncertainty = "not_observed"
    elif uncertainty_count < len(student_turns):
        uncertainty = "sometimes_observed"
    else:
        uncertainty = "often_observed"
    return {
        "prior_student_turn_count": len(student_turns),
        "observed_response_length": length_bucket,
        "observed_uncertainty": uncertainty,
        "recent_student_style": student_turns[-1][-240:],
    }


def build_short_visible_memory(history: list[DialogueTurn]) -> dict[str, Any]:
    recent_turns = history[-6:]
    recent_student_turns = [turn.content for turn in history if turn.role == "student"][-3:]
    recent_tutor_turns = [turn.content for turn in history if turn.role == "tutor"][-3:]
    return {
        "recent_turns": [asdict(turn) for turn in recent_turns],
        "recent_student_utterances": recent_student_turns,
        "recent_tutor_utterances": recent_tutor_turns,
    }


def check_basic_violations(pred_turn: str) -> dict[str, Any]:
    text = str(pred_turn or "").strip()
    violations: list[str] = []
    if not text:
        violations.append("empty_output")
    if re.search(r"(^|\n)\s*(tutor|teacher|assistant)\s*:", text, re.I):
        violations.append("tutor_role_marker")
    role_marker_count = len(
        re.findall(r"(^|\n)\s*(student|tutor|teacher|assistant|user)\s*:", text, re.I)
    )
    if role_marker_count >= 2 or "\n\n" in text:
        violations.append("multi_turn_output")
    if re.search(
        r"\b(next|later|after that|future|will reply|will say|the tutor will|teacher will)\b",
        text,
        re.I,
    ):
        violations.append("future_prediction")
    return {
        "has_violation": bool(violations),
        "violations": violations,
    }
