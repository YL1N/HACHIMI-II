from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

from .dialogue_context import DialogueContextState
from .evaluation_eedi import write_jsonl
from .tutor_turn_profile import TutorTurnProfile


@dataclass(frozen=True)
class PopulationCalibrationExemplar:
    dialogue_id: str
    question_id: str
    intervention_id: str
    turn_idx: int
    subjects: list[tuple[str, int]]
    history_turn_count: int
    latest_tutor_turn: str
    last_student_turn: str
    tutor_profile: dict[str, object]
    has_codable_math_error: bool
    knowledge_type: str | None
    error_locus: str | None
    error_mechanism: str | None
    error_evidence: list[str]


@dataclass(frozen=True)
class PopulationCalibrationSummary:
    calibration_mode: str
    n_retrieved: int
    retrieved_exemplar_keys: list[str]
    codable_error_rate: float
    top_knowledge_types: list[str]
    top_error_loci: list[str]
    top_error_mechanisms: list[str]
    prior_summary_lines: list[str]
    caution_lines: list[str]


def write_population_calibration_bank(
    output_path: str | Path,
    exemplars: list[PopulationCalibrationExemplar],
) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [asdict(exemplar) for exemplar in exemplars]
    write_jsonl(path, rows)


def load_population_calibration_bank(
    path: str | Path,
) -> list[PopulationCalibrationExemplar]:
    bank_path = Path(path)
    if not bank_path.exists():
        raise FileNotFoundError(f"population calibration bank not found: {bank_path}")
    exemplars: list[PopulationCalibrationExemplar] = []
    with bank_path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            raw = json.loads(stripped)
            if not isinstance(raw, dict):
                raise ValueError(f"{bank_path} line {line_no} must be a JSON object")
            exemplars.append(_parse_population_calibration_exemplar(raw, bank_path, line_no))
    if not exemplars:
        raise ValueError(f"population calibration bank is empty: {bank_path}")
    return exemplars


def build_population_calibration_summary(
    context: DialogueContextState,
    tutor_profile: TutorTurnProfile,
    exemplar_bank: list[PopulationCalibrationExemplar],
    top_k: int,
) -> PopulationCalibrationSummary | None:
    if top_k <= 0 or not exemplar_bank:
        return None
    ranked = sorted(
        exemplar_bank,
        key=lambda exemplar: _retrieval_sort_key(exemplar, context, tutor_profile),
        reverse=True,
    )
    retrieved = ranked[:top_k]
    if not retrieved:
        return None

    codable_error_count = sum(1 for exemplar in retrieved if exemplar.has_codable_math_error)
    knowledge_counter = Counter(
        exemplar.knowledge_type
        for exemplar in retrieved
        if exemplar.knowledge_type is not None
    )
    locus_counter = Counter(
        exemplar.error_locus
        for exemplar in retrieved
        if exemplar.error_locus is not None
    )
    mechanism_counter = Counter(
        exemplar.error_mechanism
        for exemplar in retrieved
        if exemplar.error_mechanism is not None
    )
    top_knowledge_types = [str(item) for item, _ in knowledge_counter.most_common(3)]
    top_error_loci = [str(item) for item, _ in locus_counter.most_common(3)]
    top_error_mechanisms = [str(item) for item, _ in mechanism_counter.most_common(3)]

    prior_summary_lines = [
        (
            f"Retrieved {len(retrieved)} calibration exemplars for the current tutor move "
            f"on local object: {tutor_profile.elicited_object_description}."
        ),
        (
            f"Among retrieved exemplars, codable math errors appear in "
            f"{codable_error_count}/{len(retrieved)} cases."
        ),
    ]
    if top_knowledge_types:
        prior_summary_lines.append(
            "Most common knowledge-type priors in similar local situations: "
            + ", ".join(top_knowledge_types)
            + "."
        )
    if top_error_loci:
        prior_summary_lines.append(
            "Most common error-locus priors in similar local situations: "
            + ", ".join(top_error_loci)
            + "."
        )
    if top_error_mechanisms:
        prior_summary_lines.append(
            "Most common error-mechanism priors in similar local situations: "
            + ", ".join(top_error_mechanisms)
            + "."
        )
    caution_lines = [
        "Use this summary only as a group prior for similar students and similar local tutor moves.",
        "Do not treat the retrieved exemplars as an answer script for the current turn.",
        "Current-turn visible context and current tutor support still override generic group tendencies.",
        "Do not lock the current student into one fixed wording style, hesitation style, or one fixed local reaction path.",
    ]

    return PopulationCalibrationSummary(
        calibration_mode="retrieved_group_prior",
        n_retrieved=len(retrieved),
        retrieved_exemplar_keys=[_exemplar_key(exemplar) for exemplar in retrieved],
        codable_error_rate=(codable_error_count / len(retrieved)),
        top_knowledge_types=top_knowledge_types,
        top_error_loci=top_error_loci,
        top_error_mechanisms=top_error_mechanisms,
        prior_summary_lines=prior_summary_lines,
        caution_lines=caution_lines,
    )


def population_calibration_summary_to_dict(
    summary: PopulationCalibrationSummary | None,
) -> dict[str, object] | None:
    if summary is None:
        return None
    return asdict(summary)


def _parse_population_calibration_exemplar(
    raw: dict[str, object],
    path: Path,
    line_no: int,
) -> PopulationCalibrationExemplar:
    required = {
        "dialogue_id",
        "question_id",
        "intervention_id",
        "turn_idx",
        "subjects",
        "history_turn_count",
        "latest_tutor_turn",
        "last_student_turn",
        "tutor_profile",
        "has_codable_math_error",
        "knowledge_type",
        "error_locus",
        "error_mechanism",
        "error_evidence",
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
    tutor_profile = raw["tutor_profile"]
    if not isinstance(tutor_profile, dict):
        raise ValueError(f"{path} line {line_no} tutor_profile must be a dict")
    error_evidence = raw["error_evidence"]
    if not isinstance(error_evidence, list) or not error_evidence:
        raise ValueError(f"{path} line {line_no} error_evidence must be a non-empty list")
    has_codable_math_error = raw["has_codable_math_error"]
    if not isinstance(has_codable_math_error, bool):
        raise ValueError(f"{path} line {line_no} has_codable_math_error must be bool")
    return PopulationCalibrationExemplar(
        dialogue_id=str(raw["dialogue_id"]).strip(),
        question_id=str(raw["question_id"]).strip(),
        intervention_id=str(raw["intervention_id"]).strip(),
        turn_idx=int(raw["turn_idx"]),
        subjects=subjects,
        history_turn_count=int(raw["history_turn_count"]),
        latest_tutor_turn=str(raw["latest_tutor_turn"]).strip(),
        last_student_turn=str(raw["last_student_turn"]).strip(),
        tutor_profile={str(key): value for key, value in tutor_profile.items()},
        has_codable_math_error=has_codable_math_error,
        knowledge_type=_nullable_text(raw["knowledge_type"]),
        error_locus=_nullable_text(raw["error_locus"]),
        error_mechanism=_nullable_text(raw["error_mechanism"]),
        error_evidence=[str(item).strip() for item in error_evidence if str(item).strip()],
    )


def _retrieval_sort_key(
    exemplar: PopulationCalibrationExemplar,
    context: DialogueContextState,
    tutor_profile: TutorTurnProfile,
) -> tuple[float, float, float, float, float, float]:
    exemplar_profile = exemplar.tutor_profile
    support_type_match = float(
        str(exemplar_profile.get("support_type", "")) == tutor_profile.support_type
    )
    process_match = float(
        str(exemplar_profile.get("elicited_response_process", ""))
        == tutor_profile.elicited_response_process
    )
    target_type_match = float(
        str(exemplar_profile.get("elicited_response_target_type", ""))
        == tutor_profile.elicited_response_target_type
    )
    intervention_match = float(
        str(exemplar_profile.get("target_of_intervention", ""))
        == tutor_profile.target_of_intervention
    )
    subject_overlap = _subject_overlap_ratio(exemplar.subjects, context.subjects)
    object_overlap = _token_overlap_ratio(
        str(exemplar_profile.get("elicited_object_description", "")),
        tutor_profile.elicited_object_description,
    )
    return (
        support_type_match,
        process_match,
        target_type_match,
        intervention_match + subject_overlap,
        object_overlap,
        -abs(exemplar.history_turn_count - context.turn_count_so_far),
    )


def _subject_overlap_ratio(
    left: list[tuple[str, int]],
    right: list[tuple[str, int]],
) -> float:
    left_set = {str(name).strip().lower() for name, _ in left}
    right_set = {str(name).strip().lower() for name, _ in right}
    if not left_set or not right_set:
        return 0.0
    overlap = len(left_set & right_set)
    union = len(left_set | right_set)
    return overlap / union if union else 0.0


def _token_overlap_ratio(left: str, right: str) -> float:
    left_tokens = set(_tokenize(left))
    right_tokens = set(_tokenize(right))
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = len(left_tokens & right_tokens)
    union = len(left_tokens | right_tokens)
    return overlap / union if union else 0.0


def _tokenize(text: str) -> list[str]:
    token_text = str(text or "").lower()
    return [token for token in token_text.replace("/", " ").replace("-", " ").split() if token]


def _exemplar_key(exemplar: PopulationCalibrationExemplar) -> str:
    return f"{exemplar.dialogue_id}:{exemplar.turn_idx}"


def _nullable_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
