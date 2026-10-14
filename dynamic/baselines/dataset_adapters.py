from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
EEDI_DATA_ROOT = (
    PROJECT_ROOT
    / "EEDI_data"
    / "dynamic"
    / "Question-Anchored-Tutoring-Dialogues-2k"
)
DEFAULT_EEDI_ANCHORED_DIALOGUES_PATH = EEDI_DATA_ROOT / "anchored-dialogues" / "train.csv"
DEFAULT_EEDI_QUESTION_METADATA_PATH = EEDI_DATA_ROOT / "dq-question-metadata.csv"
DEFAULT_EEDI_DIALOGUE_SUBJECTS_PATH = EEDI_DATA_ROOT / "dialogue-subjects.csv"
DEFAULT_KHAN_DATASET_PATH = PROJECT_ROOT / "dynamic" / "khan" / "CoMTA_dataset.json"

KHAN_NO_ANCHORED_QUESTION_TEXT = (
    "This Khan/CoMTA dialogue has no separate anchored question metadata. "
    "Infer the local mathematical task only from the visible dialogue history "
    "and the latest tutor turn."
)


@dataclass(frozen=True)
class DialogueTurn:
    role: str
    content: str


@dataclass(frozen=True)
class BaselineExample:
    dataset_name: str
    dialogue_id: str
    question_id: str
    intervention_id: str
    turn_idx: int
    question_text: str
    subjects: list[tuple[str, int]]
    history_before_target: list[DialogueTurn]
    gt_turn: str


def load_examples(
    dataset_name: str,
    max_dialogues: int | None = None,
    eedi_anchored_dialogues_path: str | Path = DEFAULT_EEDI_ANCHORED_DIALOGUES_PATH,
    eedi_question_metadata_path: str | Path = DEFAULT_EEDI_QUESTION_METADATA_PATH,
    eedi_dialogue_subjects_path: str | Path = DEFAULT_EEDI_DIALOGUE_SUBJECTS_PATH,
    khan_dataset_path: str | Path = DEFAULT_KHAN_DATASET_PATH,
) -> list[BaselineExample]:
    if dataset_name == "eedi_qatd2k":
        return load_eedi_turn_prediction_examples(
            anchored_dialogues_path=eedi_anchored_dialogues_path,
            question_metadata_path=eedi_question_metadata_path,
            dialogue_subjects_path=eedi_dialogue_subjects_path,
            max_dialogues=max_dialogues,
        )
    if dataset_name == "khan_comta":
        return load_khan_turn_prediction_examples(
            dataset_path=khan_dataset_path,
            max_dialogues=max_dialogues,
        )
    raise ValueError("dataset must be one of: eedi_qatd2k, khan_comta")


def load_eedi_turn_prediction_examples(
    anchored_dialogues_path: str | Path = DEFAULT_EEDI_ANCHORED_DIALOGUES_PATH,
    question_metadata_path: str | Path = DEFAULT_EEDI_QUESTION_METADATA_PATH,
    dialogue_subjects_path: str | Path = DEFAULT_EEDI_DIALOGUE_SUBJECTS_PATH,
    max_dialogues: int | None = None,
) -> list[BaselineExample]:
    anchored_path = Path(anchored_dialogues_path)
    metadata_path = Path(question_metadata_path)
    subjects_path = Path(dialogue_subjects_path)
    for path in (anchored_path, metadata_path, subjects_path):
        if not path.exists():
            raise FileNotFoundError(f"EEDI required file not found: {path}")

    data_loading = _load_eedi_data_loading_module()
    dialogues = data_loading.load_eedi_dialogues(
        anchored_dialogues_path=anchored_path,
        question_metadata_path=metadata_path,
        dialogue_subjects_path=subjects_path,
    )
    tasks, ground_truth_by_key = data_loading.build_turn_prediction_tasks(
        dialogues,
        max_dialogues=max_dialogues,
    )
    examples: list[BaselineExample] = []
    for task in tasks:
        key = (str(task.dialogue_id), int(task.target_turn_index))
        if key not in ground_truth_by_key:
            raise ValueError(f"missing EEDI gt_turn for key={key}")
        examples.append(
            BaselineExample(
                dataset_name="eedi_qatd2k",
                dialogue_id=str(task.dialogue_id),
                question_id=str(task.question_id),
                intervention_id=str(task.intervention_id),
                turn_idx=int(task.target_turn_index),
                question_text=str(task.question_text),
                subjects=[(str(name), int(level)) for name, level in task.subjects],
                history_before_target=[
                    DialogueTurn(role=str(turn.role), content=str(turn.content))
                    for turn in task.history
                ],
                gt_turn=str(ground_truth_by_key[key]),
            )
        )
    if not examples:
        raise ValueError("no EEDI baseline examples loaded")
    return examples


def load_khan_turn_prediction_examples(
    dataset_path: str | Path = DEFAULT_KHAN_DATASET_PATH,
    max_dialogues: int | None = None,
) -> list[BaselineExample]:
    path = Path(dataset_path)
    if not path.exists():
        raise FileNotFoundError(f"Khan/CoMTA required file not found: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("Khan/CoMTA dataset must be a JSON list")

    selected = raw[:max_dialogues] if max_dialogues else raw
    examples: list[BaselineExample] = []
    for dialogue_index, dialogue in enumerate(selected):
        if not isinstance(dialogue, dict):
            raise ValueError(f"Khan dialogue index={dialogue_index} is not an object")
        test_id = str(dialogue.get("test_id", dialogue_index)).strip()
        if not test_id:
            raise ValueError(f"Khan dialogue index={dialogue_index} has empty test_id")
        dialogue_id = f"khan_{test_id}"
        math_level = str(dialogue.get("math_level", "") or "").strip()
        subjects = [(f"Khan math level: {math_level}", 0)] if math_level else []
        turns = _normalize_khan_turns(dialogue.get("data"), dialogue_index)
        for turn_index, turn in enumerate(turns):
            if turn.role != "student" or turn_index == 0:
                continue
            if turns[turn_index - 1].role != "tutor":
                continue
            examples.append(
                BaselineExample(
                    dataset_name="khan_comta",
                    dialogue_id=dialogue_id,
                    question_id=test_id,
                    intervention_id="khan",
                    turn_idx=turn_index,
                    question_text=KHAN_NO_ANCHORED_QUESTION_TEXT,
                    subjects=list(subjects),
                    history_before_target=list(turns[:turn_index]),
                    gt_turn=turn.content,
                )
            )
    if not examples:
        raise ValueError("no Khan/CoMTA baseline examples loaded")
    return examples


def _load_eedi_data_loading_module() -> Any:
    module_path = PROJECT_ROOT / "dynamic" / "eedi" / "src" / "data_loading.py"
    if not module_path.exists():
        raise FileNotFoundError(f"EEDI loader not found: {module_path}")
    spec = importlib.util.spec_from_file_location(
        "dynamic_baselines_eedi_data_loading",
        module_path,
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot import EEDI data loader from: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _normalize_khan_turns(raw_turns: object, dialogue_index: int) -> list[DialogueTurn]:
    if not isinstance(raw_turns, list):
        raise ValueError(f"Khan dialogue index={dialogue_index} has no data list")
    normalized: list[DialogueTurn] = []
    for raw_turn in raw_turns:
        if not isinstance(raw_turn, dict):
            raise ValueError(f"Khan dialogue index={dialogue_index} contains non-object turn")
        raw_role = str(raw_turn.get("role", "") or "").strip()
        role = {"assistant": "tutor", "user": "student"}.get(raw_role)
        if role is None:
            raise ValueError(
                f"Khan dialogue index={dialogue_index} has unsupported role={raw_role!r}"
            )
        content = _normalize_text(raw_turn.get("content", ""))
        if not content:
            raise ValueError(f"Khan dialogue index={dialogue_index} has empty turn content")
        if normalized and normalized[-1].role == role:
            previous = normalized[-1]
            normalized[-1] = DialogueTurn(
                role=role,
                content=f"{previous.content} {content}".strip(),
            )
        else:
            normalized.append(DialogueTurn(role=role, content=content))
    return normalized


def _normalize_text(text: object) -> str:
    return " ".join(str(text or "").replace("\n", " ").split()).strip()
