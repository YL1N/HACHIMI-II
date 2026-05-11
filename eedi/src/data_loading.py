from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DialogueTurn:
    role: str
    content: str


@dataclass(frozen=True)
class EediDialogue:
    dialogue_id: str
    question_id: str
    intervention_id: str
    question_text: str
    subjects: list[tuple[str, int]]
    turns: list[DialogueTurn]


@dataclass(frozen=True)
class TurnPredictionTask:
    dialogue_id: str
    question_id: str
    intervention_id: str
    question_text: str
    subjects: list[tuple[str, int]]
    history: list[DialogueTurn]
    target_turn_index: int


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"csv not found: {path}")
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _normalize_message(text: str) -> str:
    return " ".join(str(text or "").replace("\n", " ").split()).strip()


def _load_subjects_map(path: Path) -> dict[str, list[tuple[str, int]]]:
    rows = _read_csv_rows(path)
    result: dict[str, list[tuple[str, int]]] = {}
    for row in rows:
        intervention_id = str(row["InterventionId"]).strip()
        subject_name = str(row["SubjectName"]).strip()
        level_text = str(row["SubjectLevel"]).strip()
        if not intervention_id or not subject_name or not level_text:
            continue
        level = int(level_text)
        result.setdefault(intervention_id, []).append((subject_name, level))
    return result


def _load_question_text_map(path: Path) -> dict[tuple[str, str], str]:
    rows = _read_csv_rows(path)
    grouped: dict[tuple[str, str], list[tuple[int, str, str]]] = {}
    for row in rows:
        key = (
            str(row["QuestionId_DQ"]).strip(),
            str(row["InterventionId"]).strip(),
        )
        sequence = int(str(row["Sequence"]).strip())
        label = str(row["Label"]).strip()
        text = _normalize_message(row["Text"])
        grouped.setdefault(key, []).append((sequence, label, text))

    result: dict[tuple[str, str], str] = {}
    for key, items in grouped.items():
        ordered = sorted(items, key=lambda item: item[0])
        pieces = [f"{label}: {text}" for _, label, text in ordered if text]
        result[key] = "\n".join(pieces).strip()
    return result


def load_eedi_dialogues(
    anchored_dialogues_path: str | Path,
    question_metadata_path: str | Path,
    dialogue_subjects_path: str | Path,
) -> list[EediDialogue]:
    turns_rows = _read_csv_rows(Path(anchored_dialogues_path))
    question_map = _load_question_text_map(Path(question_metadata_path))
    subjects_map = _load_subjects_map(Path(dialogue_subjects_path))

    grouped_rows: dict[tuple[str, str], list[dict[str, str]]] = {}
    for row in turns_rows:
        key = (
            str(row["QuestionId_DQ"]).strip(),
            str(row["InterventionId"]).strip(),
        )
        grouped_rows.setdefault(key, []).append(row)

    dialogues: list[EediDialogue] = []
    for (question_id, intervention_id), rows in grouped_rows.items():
        ordered_rows = sorted(
            rows,
            key=lambda row: int(str(row["MessageSequence"]).strip()),
        )
        turns: list[DialogueTurn] = []
        for row in ordered_rows:
            role = "tutor" if str(row["IsTutor"]).strip() == "1" else "student"
            content = _normalize_message(row["MessageString"])
            if not content:
                continue
            if turns and turns[-1].role == role:
                turns[-1] = DialogueTurn(
                    role=role,
                    content=f"{turns[-1].content} {content}".strip(),
                )
                continue
            turns.append(DialogueTurn(role=role, content=content))
        if not turns:
            continue
        question_text = question_map.get((question_id, intervention_id), "").strip()
        if not question_text:
            raise ValueError(
                "missing question text for "
                f"question_id={question_id} intervention_id={intervention_id}"
            )
        dialogues.append(
            EediDialogue(
                dialogue_id=f"{question_id}_{intervention_id}",
                question_id=question_id,
                intervention_id=intervention_id,
                question_text=question_text,
                subjects=subjects_map.get(intervention_id, []),
                turns=turns,
            )
        )
    if not dialogues:
        raise ValueError("no EEDI dialogues loaded")
    return dialogues


def build_turn_prediction_tasks(
    dialogues: list[EediDialogue],
    max_dialogues: int | None = None,
) -> tuple[list[TurnPredictionTask], dict[tuple[str, int], str]]:
    selected_dialogues = dialogues[:max_dialogues] if max_dialogues else dialogues
    tasks: list[TurnPredictionTask] = []
    ground_truth_by_key: dict[tuple[str, int], str] = {}
    for dialogue in selected_dialogues:
        for turn_index, turn in enumerate(dialogue.turns):
            if turn.role != "student":
                continue
            history = dialogue.turns[:turn_index]
            if not history:
                continue
            tasks.append(
                TurnPredictionTask(
                    dialogue_id=dialogue.dialogue_id,
                    question_id=dialogue.question_id,
                    intervention_id=dialogue.intervention_id,
                    question_text=dialogue.question_text,
                    subjects=list(dialogue.subjects),
                    history=list(history),
                    target_turn_index=turn_index,
                )
            )
            ground_truth_by_key[(dialogue.dialogue_id, turn_index)] = turn.content
    if not tasks:
        raise ValueError("no turn-level student prediction tasks built")
    return tasks, ground_truth_by_key
