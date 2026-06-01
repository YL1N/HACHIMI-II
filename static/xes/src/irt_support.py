from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from .data_loading import LEVEL_NAMES, QuestionRecord, load_questions


@dataclass(frozen=True)
class IRTSupportSettings:
    min_item_response_count: int = 300
    min_student_unique_items: int = 50
    min_level_response_count: int = 20
    max_level_share: float = 0.45
    max_distribution_l1: float = 0.30
    include_image_questions: bool = False


@dataclass(frozen=True)
class StudentAbilityBanding:
    thresholds: dict[str, float]
    student_score: dict[str, float]
    student_level: dict[str, str]
    global_level_counts: dict[str, int]


@dataclass(frozen=True)
class IRTItemDiagnostic:
    question_id: str
    total: int
    correct: int
    accuracy: float
    level_counts: dict[str, int]
    level_accuracy: dict[str, float | None]
    max_level_share: float
    min_level_count: int
    distribution_l1: float
    primary_route_top: str | None
    primary_route_module: str | None
    kc_routes: list[str]
    eligible: bool
    failure_reasons: list[str]


@dataclass(frozen=True)
class IRTSupportResult:
    summary: dict[str, object]
    eligible_questions: list[dict[str, object]]
    item_diagnostics: list[IRTItemDiagnostic]


@dataclass(frozen=True)
class IRTCalibrationExport:
    summary: dict[str, object]
    student_ability_rows: list[dict[str, object]]
    item_pool_rows: list[dict[str, object]]
    response_rows: list[dict[str, object]]
    module_summary_rows: list[dict[str, object]]


def _load_question_metadata_map(path: str | Path) -> dict[str, dict[str, object]]:
    source = Path(path)
    with source.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, dict):
        raise ValueError(f"question metadata json must be dict, got {type(payload).__name__}")
    return {str(question_id): raw for question_id, raw in payload.items() if isinstance(raw, dict)}


def _primary_route_info(kc_routes: list[str]) -> tuple[str | None, str | None]:
    if not kc_routes:
        return None, None
    route_counter = Counter()
    for route in kc_routes:
        parts = [part.strip() for part in str(route).split("----") if part.strip()]
        if not parts:
            continue
        route_counter[(parts[0], parts[1] if len(parts) >= 2 else None)] += 1
    if not route_counter:
        return None, None
    top, module = route_counter.most_common(1)[0][0]
    return top, module


def _iter_first_attempt_rows(
    response_csv_path: str | Path,
) -> tuple[list[tuple[str, list[tuple[str, bool]]]], int]:
    source = Path(response_csv_path)
    if not source.exists():
        raise FileNotFoundError(f"response csv not found: {source}")

    rows: list[tuple[str, list[tuple[str, bool]]]] = []
    seen_users: set[str] = set()
    repeated_user_count = 0
    with source.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        required = {"uid", "questions", "responses"}
        if not required.issubset(reader.fieldnames or set()):
            raise ValueError(
                f"response csv missing required columns: expected {required}, got {reader.fieldnames}"
            )
        for row in reader:
            student_id = str(row.get("uid") or "").strip()
            if not student_id:
                raise ValueError("found row with empty uid")
            if student_id in seen_users:
                repeated_user_count += 1
            seen_users.add(student_id)

            question_ids = [question_id.strip() for question_id in (row.get("questions") or "").split(",")]
            responses = [response.strip() for response in (row.get("responses") or "").split(",")]
            event_count = min(len(question_ids), len(responses))
            first_attempts: list[tuple[str, bool]] = []
            seen_questions: set[str] = set()
            for question_id, response in zip(question_ids[:event_count], responses[:event_count]):
                if not question_id or response not in {"0", "1"}:
                    continue
                if question_id in seen_questions:
                    continue
                seen_questions.add(question_id)
                first_attempts.append((question_id, response == "1"))
            rows.append((student_id, first_attempts))
    return rows, repeated_user_count


def _band_students(
    student_rows: list[tuple[str, list[tuple[str, bool]]]],
    min_student_unique_items: int,
) -> StudentAbilityBanding:
    student_scores: dict[str, float] = {}
    for student_id, first_attempts in student_rows:
        total = len(first_attempts)
        if total < min_student_unique_items:
            continue
        correct = sum(1 for _, is_correct in first_attempts if is_correct)
        student_scores[student_id] = correct / total

    if len(student_scores) < 4:
        raise ValueError(
            "not enough students with sufficient unique first-attempt coverage to form four ability levels"
        )

    sorted_scores = sorted(student_scores.values())
    q25 = sorted_scores[int((len(sorted_scores) - 1) * 0.25)]
    q50 = sorted_scores[int((len(sorted_scores) - 1) * 0.50)]
    q75 = sorted_scores[int((len(sorted_scores) - 1) * 0.75)]

    def level_for(score: float) -> str:
        if score >= q75:
            return "high"
        if score >= q50:
            return "medium"
        if score >= q25:
            return "low"
        return "poor"

    student_level = {student_id: level_for(score) for student_id, score in student_scores.items()}
    global_counts = Counter(student_level.values())
    return StudentAbilityBanding(
        thresholds={"q25": q25, "q50": q50, "q75": q75},
        student_score=student_scores,
        student_level=student_level,
        global_level_counts={level: global_counts[level] for level in LEVEL_NAMES},
    )


def build_irt_support_dataset(
    question_path: str | Path,
    response_csv_path: str | Path,
    settings: IRTSupportSettings,
) -> IRTSupportResult:
    questions = load_questions(
        question_path,
        skip_image_questions=not settings.include_image_questions,
    )
    question_lookup = {question.question_id: question for question in questions}
    question_metadata = _load_question_metadata_map(question_path)

    student_rows, repeated_user_count = _iter_first_attempt_rows(response_csv_path)
    banding = _band_students(
        student_rows=student_rows,
        min_student_unique_items=settings.min_student_unique_items,
    )

    item_total = Counter()
    item_correct = Counter()
    item_level_total: dict[str, Counter[str]] = defaultdict(Counter)
    item_level_correct: dict[str, Counter[str]] = defaultdict(Counter)

    for student_id, first_attempts in student_rows:
        level = banding.student_level.get(student_id)
        if level is None:
            continue
        for question_id, is_correct in first_attempts:
            if question_id not in question_lookup:
                continue
            item_total[question_id] += 1
            if is_correct:
                item_correct[question_id] += 1
            item_level_total[question_id][level] += 1
            if is_correct:
                item_level_correct[question_id][level] += 1

    total_band_population = sum(banding.global_level_counts.values())
    if total_band_population <= 0:
        raise ValueError("global ability-band population is empty")
    global_level_share = {
        level: banding.global_level_counts[level] / total_band_population for level in LEVEL_NAMES
    }

    item_diagnostics: list[IRTItemDiagnostic] = []
    eligible_questions: list[dict[str, object]] = []
    reason_counter = Counter()
    route_counter = Counter()

    for question_id, total in item_total.items():
        question = question_lookup[question_id]
        correct = item_correct[question_id]
        accuracy = correct / total
        level_counts = {level: item_level_total[question_id][level] for level in LEVEL_NAMES}
        level_accuracy = {}
        for level in LEVEL_NAMES:
            level_total = level_counts[level]
            level_accuracy[level] = (
                item_level_correct[question_id][level] / level_total if level_total > 0 else None
            )

        shares = {level: level_counts[level] / total for level in LEVEL_NAMES}
        max_level_share = max(shares.values())
        min_level_count = min(level_counts.values())
        distribution_l1 = sum(abs(shares[level] - global_level_share[level]) for level in LEVEL_NAMES)

        raw_metadata = question_metadata.get(question_id, {})
        kc_routes = [str(route) for route in raw_metadata.get("kc_routes", []) if str(route).strip()]
        route_top, route_module = _primary_route_info(kc_routes)

        failure_reasons: list[str] = []
        if total < settings.min_item_response_count:
            failure_reasons.append("min_item_response_count")
        if min_level_count < settings.min_level_response_count:
            failure_reasons.append("min_level_response_count")
        if max_level_share > settings.max_level_share:
            failure_reasons.append("max_level_share")
        if distribution_l1 > settings.max_distribution_l1:
            failure_reasons.append("max_distribution_l1")
        eligible = not failure_reasons

        diagnostic = IRTItemDiagnostic(
            question_id=question_id,
            total=total,
            correct=correct,
            accuracy=accuracy,
            level_counts=level_counts,
            level_accuracy=level_accuracy,
            max_level_share=max_level_share,
            min_level_count=min_level_count,
            distribution_l1=distribution_l1,
            primary_route_top=route_top,
            primary_route_module=route_module,
            kc_routes=kc_routes,
            eligible=eligible,
            failure_reasons=failure_reasons,
        )
        item_diagnostics.append(diagnostic)

        if eligible:
            eligible_questions.append(
                {
                    "question_id": question.question_id,
                    "question_type": question.question_type,
                    "question_text": question.question_text,
                    "options": question.options,
                    "gold_answers": question.answer,
                    "has_options": bool(question.options),
                    "irt_support_total": total,
                    "irt_support_accuracy": accuracy,
                    "irt_support_level_counts": level_counts,
                    "irt_support_max_level_share": max_level_share,
                    "irt_support_distribution_l1": distribution_l1,
                    "primary_route_top": route_top,
                    "primary_route_module": route_module,
                }
            )
            route_counter[(route_top, route_module)] += 1
        else:
            for reason in failure_reasons:
                reason_counter[reason] += 1

    item_diagnostics.sort(key=lambda diagnostic: (not diagnostic.eligible, diagnostic.question_id))
    eligible_questions.sort(key=lambda row: str(row["question_id"]))

    summary = {
        "question_path": str(Path(question_path)),
        "response_csv_path": str(Path(response_csv_path)),
        "settings": {
            "min_item_response_count": settings.min_item_response_count,
            "min_student_unique_items": settings.min_student_unique_items,
            "min_level_response_count": settings.min_level_response_count,
            "max_level_share": settings.max_level_share,
            "max_distribution_l1": settings.max_distribution_l1,
            "include_image_questions": settings.include_image_questions,
        },
        "input_question_count": len(questions),
        "student_row_count": len(student_rows),
        "repeated_user_row_count": repeated_user_count,
        "students_with_ability_level": len(banding.student_level),
        "ability_thresholds": banding.thresholds,
        "global_level_counts": banding.global_level_counts,
        "candidate_item_count": len(item_diagnostics),
        "eligible_item_count": len(eligible_questions),
        "ineligible_item_count": len(item_diagnostics) - len(eligible_questions),
        "failure_reason_counts": dict(reason_counter),
        "eligible_route_top_counts": {
            f"{route_top} / {route_module}": count
            for (route_top, route_module), count in route_counter.most_common()
        },
    }
    return IRTSupportResult(
        summary=summary,
        eligible_questions=eligible_questions,
        item_diagnostics=item_diagnostics,
    )


def export_irt_calibration_dataset(
    question_path: str | Path,
    response_csv_path: str | Path,
    eligible_question_path: str | Path,
    min_student_unique_items: int,
    include_image_questions: bool = False,
) -> IRTCalibrationExport:
    questions = load_questions(
        question_path,
        skip_image_questions=not include_image_questions,
    )
    question_lookup = {question.question_id: question for question in questions}
    question_metadata = _load_question_metadata_map(question_path)

    with Path(eligible_question_path).open("r", encoding="utf-8") as file:
        eligible_questions = json.load(file)
    if not isinstance(eligible_questions, list):
        raise ValueError("eligible question file must be a JSON list")
    eligible_question_ids = {str(row["question_id"]) for row in eligible_questions}

    student_rows, repeated_user_count = _iter_first_attempt_rows(response_csv_path)
    banding = _band_students(
        student_rows=student_rows,
        min_student_unique_items=min_student_unique_items,
    )

    response_rows: list[dict[str, object]] = []
    student_event_counter = Counter()
    item_event_counter = Counter()
    module_event_counter = Counter()
    module_student_sets: dict[str, set[str]] = defaultdict(set)
    module_item_sets: dict[str, set[str]] = defaultdict(set)

    for student_id, first_attempts in student_rows:
        level = banding.student_level.get(student_id)
        score = banding.student_score.get(student_id)
        if level is None or score is None:
            continue
        for order_in_student, (question_id, is_correct) in enumerate(first_attempts, start=1):
            if question_id not in eligible_question_ids:
                continue
            question = question_lookup.get(question_id)
            if question is None:
                continue
            metadata = question_metadata.get(question_id, {})
            kc_routes = [str(route) for route in metadata.get("kc_routes", []) if str(route).strip()]
            route_top, route_module = _primary_route_info(kc_routes)
            module_name = (
                f"{route_top} / {route_module}"
                if route_top is not None and route_module is not None
                else "unknown / unknown"
            )
            response_rows.append(
                {
                    "student_id": student_id,
                    "question_id": question_id,
                    "is_correct": int(is_correct),
                    "ability_score_proxy": score,
                    "ability_level": level,
                    "question_type": question.question_type,
                    "primary_route_top": route_top,
                    "primary_route_module": route_module,
                    "primary_route_name": module_name,
                    "first_attempt_order_in_student": order_in_student,
                }
            )
            student_event_counter[student_id] += 1
            item_event_counter[question_id] += 1
            module_event_counter[module_name] += 1
            module_student_sets[module_name].add(student_id)
            module_item_sets[module_name].add(question_id)

    student_ability_rows = [
        {
            "student_id": student_id,
            "ability_score_proxy": banding.student_score[student_id],
            "ability_level": banding.student_level[student_id],
            "eligible_item_response_count": student_event_counter[student_id],
        }
        for student_id in sorted(student_event_counter)
    ]

    eligible_lookup = {str(row["question_id"]): row for row in eligible_questions}
    item_pool_rows: list[dict[str, object]] = []
    for question_id in sorted(eligible_question_ids):
        row = eligible_lookup[question_id]
        item_pool_rows.append(
            {
                "question_id": question_id,
                "question_type": row["question_type"],
                "question_text": row["question_text"],
                "has_options": row["has_options"],
                "irt_support_total": row["irt_support_total"],
                "irt_support_accuracy": row["irt_support_accuracy"],
                "irt_support_level_counts": row["irt_support_level_counts"],
                "irt_support_max_level_share": row["irt_support_max_level_share"],
                "irt_support_distribution_l1": row["irt_support_distribution_l1"],
                "primary_route_top": row["primary_route_top"],
                "primary_route_module": row["primary_route_module"],
            }
        )

    module_summary_rows: list[dict[str, object]] = []
    for module_name in sorted(module_event_counter):
        module_summary_rows.append(
            {
                "module_name": module_name,
                "n_items": len(module_item_sets[module_name]),
                "n_students": len(module_student_sets[module_name]),
                "n_responses": module_event_counter[module_name],
            }
        )

    summary = {
        "question_path": str(Path(question_path)),
        "response_csv_path": str(Path(response_csv_path)),
        "eligible_question_path": str(Path(eligible_question_path)),
        "min_student_unique_items": min_student_unique_items,
        "include_image_questions": include_image_questions,
        "repeated_user_row_count": repeated_user_count,
        "ability_thresholds": banding.thresholds,
        "global_level_counts": banding.global_level_counts,
        "n_students_in_export": len(student_ability_rows),
        "n_items_in_export": len(item_pool_rows),
        "n_responses_in_export": len(response_rows),
        "n_modules_in_export": len(module_summary_rows),
    }
    return IRTCalibrationExport(
        summary=summary,
        student_ability_rows=student_ability_rows,
        item_pool_rows=item_pool_rows,
        response_rows=response_rows,
        module_summary_rows=module_summary_rows,
    )
