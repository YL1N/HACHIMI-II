from __future__ import annotations

from .cards import ResponseProtocol, TaskState, ValidationReport

SUPPORT_LEVEL_SCORE = {"L0": 0, "L1": 1, "L2": 2, "L3": 3}


def validate_answer_output(
    *,
    task_state: TaskState,
    response_protocol: ResponseProtocol,
    predicted_answer: str,
    student_response: str,
    used_support_level: str,
) -> ValidationReport:
    issues: list[str] = []
    if not predicted_answer.strip():
        issues.append("predicted_answer is empty")
    if not student_response.strip():
        issues.append("student_response is empty")

    if response_protocol.answer_mode == "option_letter_only":
        normalized = predicted_answer.strip().upper()
        if normalized not in {"A", "B", "C", "D"}:
            issues.append(f"predicted_answer is not single option letter: {predicted_answer!r}")

    if used_support_level not in SUPPORT_LEVEL_SCORE:
        issues.append(f"invalid used_support_level: {used_support_level}")
    elif SUPPORT_LEVEL_SCORE[used_support_level] > SUPPORT_LEVEL_SCORE[response_protocol.max_support_level]:
        issues.append(
            f"used_support_level exceeds budget: {used_support_level} > {response_protocol.max_support_level}"
        )

    if response_protocol.response_style == "just_answer" and len(student_response.strip().splitlines()) > 2:
        issues.append("student_response too long for just_answer mode")

    if task_state.response_format_demand == "short_fill" and len(predicted_answer) > 32:
        issues.append("predicted_answer too long for short_fill")

    return ValidationReport(
        is_valid=not issues,
        issues=issues,
    )
