from __future__ import annotations

from dataclasses import asdict, dataclass

from .data_loading import DialogueTurn, TurnPredictionTask


@dataclass(frozen=True)
class DialogueContextState:
    dialogue_id: str
    question_id: str
    intervention_id: str
    question_text: str
    subjects: list[tuple[str, int]]
    turns_so_far: list[dict[str, str]]
    latest_tutor_turn: str
    last_student_turn: str
    turn_count_so_far: int


def build_dialogue_context_state(task: TurnPredictionTask) -> DialogueContextState:
    latest_tutor_turn = ""
    last_student_turn = ""
    for turn in reversed(task.history):
        if turn.role == "tutor" and not latest_tutor_turn:
            latest_tutor_turn = turn.content
        if turn.role == "student" and not last_student_turn:
            last_student_turn = turn.content
        if latest_tutor_turn and last_student_turn:
            break
    return DialogueContextState(
        dialogue_id=task.dialogue_id,
        question_id=task.question_id,
        intervention_id=task.intervention_id,
        question_text=task.question_text,
        subjects=list(task.subjects),
        turns_so_far=[asdict(turn) for turn in task.history],
        latest_tutor_turn=latest_tutor_turn,
        last_student_turn=last_student_turn,
        turn_count_so_far=len(task.history),
    )


def format_history_text(history: list[DialogueTurn]) -> str:
    lines = []
    for idx, turn in enumerate(history, start=1):
        role = "Tutor" if turn.role == "tutor" else "Student"
        lines.append(f"Turn {idx} ({role}): {turn.content}")
    return "\n".join(lines)
