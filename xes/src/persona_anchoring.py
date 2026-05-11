from __future__ import annotations

import csv
import json
import random
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

from .data_loading import (
    K_GRADE,
    MathAnchorProfile,
    MathTaskCapabilityAnchor,
    PersonaRecord,
    load_personas,
)
from .irt_support import _band_students

MATH_SUBJECT = "数学"
TARGET_GRADE = "三年级"
LEVELS = ("high", "medium", "low", "poor")
PRIOR_CENTERS = {
    "strong": 0.82,
    "neutral": 0.50,
    "weak": 0.18,
}
PRIOR_BOUNDS = {
    "strong": (0.67, 1.01),
    "neutral": (0.33, 0.67),
    "weak": (-0.01, 0.33),
}
DIFFICULTY_BANDS = ("easy", "medium", "hard")
CAPABILITY_FIELDS = (
    "arithmetic_fluency",
    "word_problem_transfer",
    "multi_step_stability",
    "geometry_intuition",
    "pattern_rule_detection",
    "option_elimination",
    "fill_blank_precision",
    "hard_item_persistence",
)
CAPABILITY_METRIC_MAP = {
    "arithmetic_fluency": "arithmetic",
    "word_problem_transfer": "application",
    "multi_step_stability": "multi_step",
    "geometry_intuition": "geometry",
    "pattern_rule_detection": "pattern",
    "option_elimination": "selection",
    "fill_blank_precision": "fill",
    "hard_item_persistence": "hard",
}
ARITHMETIC_MODULE_NAMES = {
    "计算模块",
    "运算求解",
    "数与运算",
    "数的运算",
    "式与方程",
}
APPLICATION_MODULE_NAMES = {
    "应用题模块",
    "应用题",
    "综合与实践",
    "实践应用",
    "行程模块",
}
GEOMETRY_MODULE_NAMES = {
    "几何模块",
    "空间与图形",
    "图形认知",
    "图形的认识",
    "测量",
}
PATTERN_MODULE_NAMES = {
    "计数模块",
    "组合模块",
    "数论模块",
    "数学广角",
    "逻辑分析",
    "分类讨论思想",
    "枚举思想",
    "逆向思想",
}
MULTI_STEP_TOP_NAMES = {"拓展思维"}
MULTI_STEP_MODULE_NAMES = {
    "应用题模块",
    "应用题",
    "综合与实践",
    "实践应用",
    "行程模块",
    "组合模块",
    "计数模块",
    "数论模块",
    "几何模块",
}


@dataclass(frozen=True)
class AnchorBuildSettings:
    min_student_unique_items: int = 50
    hard_max_accuracy: float = 0.50
    medium_max_accuracy: float = 0.75
    seed: int = 42
    capability_neighbor_count: int = 5
    min_capability_item_count: int = 5


@dataclass(frozen=True)
class SupportStudentProfile:
    student_id: str
    support_level: str
    support_item_count: int
    support_accuracy: float
    support_accuracy_percentile_within_level: float
    within_level_strength: str
    easy_accuracy: float | None
    medium_accuracy: float | None
    hard_accuracy: float | None


@dataclass(frozen=True)
class SupportQuestionProfile:
    question_id: str
    primary_route_top: str
    primary_route_module: str
    has_options: bool
    arithmetic: bool
    application: bool
    geometry: bool
    pattern: bool
    multi_step: bool


@dataclass(frozen=True)
class SupportStudentCapabilityStats:
    student_id: str
    support_level: str
    metric_counts: dict[str, int]
    metric_correct: dict[str, int]


def _resolve_math_prior(persona: PersonaRecord) -> str:
    strong_has_math = MATH_SUBJECT in persona.strong_subjects
    weak_has_math = MATH_SUBJECT in persona.weak_subjects
    if strong_has_math and weak_has_math:
        raise ValueError(
            f"persona {persona.student_id} has 数学 in both strong_subjects and weak_subjects"
        )
    if strong_has_math:
        return "strong"
    if weak_has_math:
        return "weak"
    return "neutral"


def _load_raw_persona_rows(path: str | Path) -> dict[str, dict[str, object]]:
    source = Path(path)
    rows: dict[str, dict[str, object]] = {}
    with source.open("r", encoding="utf-8") as file:
        for line_no, line in enumerate(file, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(
                    f"persona source line {line_no} must be object/dict, got {type(row).__name__}"
                )
            student_id = str(row.get("id", "")).strip()
            if not student_id:
                raise ValueError(f"persona source line {line_no} missing id")
            if student_id in rows:
                raise ValueError(f"duplicate persona id in source file: {student_id}")
            rows[student_id] = row
    if not rows:
        raise ValueError(f"no persona rows loaded from {source}")
    return rows


def load_excluded_question_ids(frozen_question_paths: list[str | Path]) -> set[str]:
    excluded: set[str] = set()
    for raw_path in frozen_question_paths:
        path = Path(raw_path)
        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
        if not isinstance(payload, list):
            raise ValueError(f"frozen question file must be list: {path}")
        for row_index, row in enumerate(payload, start=1):
            if not isinstance(row, dict):
                raise ValueError(
                    f"frozen question row must be object/dict: {path}[{row_index}]"
                )
            question_id = str(row.get("question_id", "")).strip()
            if not question_id:
                raise ValueError(f"frozen question row missing question_id: {path}[{row_index}]")
            excluded.add(question_id)
    return excluded


def _iter_first_attempts_by_student(
    response_csv_path: str | Path,
    excluded_question_ids: set[str],
) -> list[tuple[str, list[tuple[str, bool]]]]:
    source = Path(response_csv_path)
    if not source.exists():
        raise FileNotFoundError(f"response csv not found: {source}")

    attempts_by_student: dict[str, list[tuple[str, bool]]] = defaultdict(list)
    seen_question_by_student: dict[str, set[str]] = defaultdict(set)

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
            question_ids = [question_id.strip() for question_id in (row.get("questions") or "").split(",")]
            responses = [response.strip() for response in (row.get("responses") or "").split(",")]
            for question_id, response in zip(question_ids, responses):
                if not question_id or response not in {"0", "1"}:
                    continue
                if question_id in excluded_question_ids:
                    continue
                if question_id in seen_question_by_student[student_id]:
                    continue
                seen_question_by_student[student_id].add(question_id)
                attempts_by_student[student_id].append((question_id, response == "1"))

    rows = sorted(attempts_by_student.items(), key=lambda item: item[0])
    if not rows:
        raise ValueError("no usable support first-attempt rows found after exclusion")
    return rows


def _load_support_question_profiles(response_csv_path: str | Path) -> dict[str, SupportQuestionProfile]:
    source = Path(response_csv_path)
    question_path = (source.parent.parent / "metadata" / "questions.json").resolve()
    if not question_path.exists():
        raise FileNotFoundError(f"support question metadata not found: {question_path}")

    with question_path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, dict):
        raise ValueError(f"support question metadata must be dict: {question_path}")

    profiles: dict[str, SupportQuestionProfile] = {}
    for question_id, raw in payload.items():
        if not isinstance(raw, dict):
            continue
        kc_routes = [str(route).strip() for route in raw.get("kc_routes", []) if str(route).strip()]
        route_counter = Counter()
        for route in kc_routes:
            parts = [part.strip() for part in route.split("----") if part.strip()]
            if not parts:
                continue
            top = parts[0]
            module = parts[1] if len(parts) >= 2 else ""
            route_counter[(top, module)] += 1
        if route_counter:
            (route_top, route_module), _ = route_counter.most_common(1)[0]
        else:
            route_top, route_module = "", ""

        has_options = bool(raw.get("options"))
        arithmetic = route_module in ARITHMETIC_MODULE_NAMES
        application = route_module in APPLICATION_MODULE_NAMES
        geometry = route_module in GEOMETRY_MODULE_NAMES
        pattern = route_module in PATTERN_MODULE_NAMES
        multi_step = (
            route_top in MULTI_STEP_TOP_NAMES
            or route_module in MULTI_STEP_MODULE_NAMES
        )
        profiles[str(question_id)] = SupportQuestionProfile(
            question_id=str(question_id),
            primary_route_top=route_top,
            primary_route_module=route_module,
            has_options=has_options,
            arithmetic=arithmetic,
            application=application,
            geometry=geometry,
            pattern=pattern,
            multi_step=multi_step,
        )
    if not profiles:
        raise ValueError(f"no support question profiles loaded from {question_path}")
    return profiles


def _difficulty_band_for_accuracy(
    accuracy: float,
    hard_max_accuracy: float,
    medium_max_accuracy: float,
) -> str:
    if accuracy < hard_max_accuracy:
        return "hard"
    if accuracy <= medium_max_accuracy:
        return "medium"
    return "easy"


def build_support_student_profiles(
    response_csv_path: str | Path,
    excluded_question_ids: set[str],
    settings: AnchorBuildSettings,
) -> tuple[list[SupportStudentProfile], dict[str, object]]:
    student_rows = _iter_first_attempts_by_student(
        response_csv_path=response_csv_path,
        excluded_question_ids=excluded_question_ids,
    )
    banding = _band_students(
        student_rows=student_rows,
        min_student_unique_items=settings.min_student_unique_items,
    )

    item_total = Counter()
    item_correct = Counter()
    filtered_student_rows: list[tuple[str, list[tuple[str, bool]]]] = []
    for student_id, first_attempts in student_rows:
        if student_id not in banding.student_level:
            continue
        filtered_student_rows.append((student_id, first_attempts))
        for question_id, is_correct in first_attempts:
            item_total[question_id] += 1
            if is_correct:
                item_correct[question_id] += 1

    item_band: dict[str, str] = {}
    for question_id, total in item_total.items():
        accuracy = item_correct[question_id] / total
        item_band[question_id] = _difficulty_band_for_accuracy(
            accuracy=accuracy,
            hard_max_accuracy=settings.hard_max_accuracy,
            medium_max_accuracy=settings.medium_max_accuracy,
        )

    by_level: dict[str, list[tuple[str, float]]] = defaultdict(list)
    student_metrics_raw: dict[str, dict[str, object]] = {}
    for student_id, first_attempts in filtered_student_rows:
        support_item_count = len(first_attempts)
        correct = sum(1 for _, is_correct in first_attempts if is_correct)
        support_accuracy = correct / support_item_count

        band_total = Counter()
        band_correct = Counter()
        for question_id, is_correct in first_attempts:
            difficulty_band = item_band.get(question_id)
            if difficulty_band is None:
                continue
            band_total[difficulty_band] += 1
            if is_correct:
                band_correct[difficulty_band] += 1

        def _band_accuracy(name: str) -> float | None:
            total = band_total[name]
            if total <= 0:
                return None
            return band_correct[name] / total

        support_level = banding.student_level[student_id]
        student_metrics_raw[student_id] = {
            "support_level": support_level,
            "support_item_count": support_item_count,
            "support_accuracy": support_accuracy,
            "easy_accuracy": _band_accuracy("easy"),
            "medium_accuracy": _band_accuracy("medium"),
            "hard_accuracy": _band_accuracy("hard"),
        }
        by_level[support_level].append((student_id, support_accuracy))

    profiles: list[SupportStudentProfile] = []
    for level in LEVELS:
        pairs = sorted(by_level[level], key=lambda item: (item[1], item[0]))
        if not pairs:
            continue
        n = len(pairs)
        for index, (student_id, _) in enumerate(pairs):
            percentile = 0.5 if n == 1 else index / (n - 1)
            if percentile >= PRIOR_BOUNDS["strong"][0]:
                strength = "above_level_average"
            elif percentile < PRIOR_BOUNDS["weak"][1]:
                strength = "below_level_average"
            else:
                strength = "near_level_average"
            raw = student_metrics_raw[student_id]
            profiles.append(
                SupportStudentProfile(
                    student_id=student_id,
                    support_level=level,
                    support_item_count=int(raw["support_item_count"]),
                    support_accuracy=float(raw["support_accuracy"]),
                    support_accuracy_percentile_within_level=percentile,
                    within_level_strength=strength,
                    easy_accuracy=raw["easy_accuracy"],
                    medium_accuracy=raw["medium_accuracy"],
                    hard_accuracy=raw["hard_accuracy"],
                )
            )

    summary = {
        "support_student_n": len(profiles),
        "excluded_question_count": len(excluded_question_ids),
        "ability_thresholds": banding.thresholds,
        "global_level_counts": banding.global_level_counts,
        "hard_max_accuracy": settings.hard_max_accuracy,
        "medium_max_accuracy": settings.medium_max_accuracy,
        "min_student_unique_items": settings.min_student_unique_items,
        "difficulty_band_item_counts": dict(Counter(item_band.values())),
    }
    return profiles, summary


def _ordered_candidates_for_prior(
    candidates: list[SupportStudentProfile],
    prior: str,
    level: str,
) -> list[SupportStudentProfile]:
    lower, upper = PRIOR_BOUNDS[prior]
    target_center = PRIOR_CENTERS[prior]
    preferred = [
        candidate
        for candidate in candidates
        if lower <= candidate.support_accuracy_percentile_within_level < upper
    ]
    fallback = [candidate for candidate in candidates if candidate not in preferred]

    def _sort_key(candidate: SupportStudentProfile) -> tuple[float, float, str]:
        return (
            abs(candidate.support_accuracy_percentile_within_level - target_center),
            -candidate.support_item_count,
            candidate.student_id,
        )

    preferred = sorted(preferred, key=_sort_key)
    fallback = sorted(fallback, key=_sort_key)
    return preferred + fallback


def _build_anchor_summary(
    prior: str,
    profile: SupportStudentProfile,
) -> tuple[str, list[str]]:
    prior_hint = {
        "strong": "The synthetic persona explicitly marks mathematics as a strong subject.",
        "neutral": "The synthetic persona does not explicitly mark mathematics as either strong or weak.",
        "weak": "The synthetic persona explicitly marks mathematics as a weak subject.",
    }[prior]
    strength_hint = {
        "above_level_average": "above the average of the same academic_level band",
        "near_level_average": "near the average of the same academic_level band",
        "below_level_average": "below the average of the same academic_level band",
    }[profile.within_level_strength]

    def _fmt(value: float | None) -> str:
        return "NA" if value is None else f"{value:.3f}"

    summary = (
        "Matched support-set math evidence from a real grade-3 student: "
        f"within the real {profile.support_level} academic band, this anchor performs {strength_hint} "
        f"on non-evaluation math items. {prior_hint}"
    )
    evidence = [
        f"support_item_count={profile.support_item_count}",
        f"support_accuracy={profile.support_accuracy:.3f}",
        (
            "support_accuracy_percentile_within_level="
            f"{profile.support_accuracy_percentile_within_level:.3f}"
        ),
        f"easy_accuracy={_fmt(profile.easy_accuracy)}",
        f"medium_accuracy={_fmt(profile.medium_accuracy)}",
        f"hard_accuracy={_fmt(profile.hard_accuracy)}",
    ]
    return summary, evidence


def _student_id_sort_key(student_id: str) -> tuple[int, int | str]:
    text = str(student_id).strip()
    try:
        return 0, int(text)
    except ValueError:
        return 1, text


def _safe_accuracy(correct: int, total: int) -> float | None:
    if total <= 0:
        return None
    return correct / total


def _accuracy_to_level(
    accuracy: float | None,
    support_level: str,
    prior: str,
    global_accuracy: float,
) -> str:
    if accuracy is None:
        level_bias = {
            "high": "high",
            "medium": "medium",
            "low": "medium",
            "poor": "low",
        }[support_level]
        if prior == "strong" and level_bias != "high":
            return "medium"
        if prior == "weak" and level_bias != "low":
            return "medium"
        return level_bias

    strong_shift = 0.08 if prior == "strong" else 0.0
    weak_shift = -0.08 if prior == "weak" else 0.0
    adjusted = accuracy + strong_shift + weak_shift
    if adjusted >= global_accuracy + 0.10:
        return "high"
    if adjusted <= global_accuracy - 0.10:
        return "low"
    return "medium"


def _guessing_tendency_level(
    selection_accuracy: float | None,
    fill_accuracy: float | None,
    prior: str,
) -> str:
    if selection_accuracy is None or fill_accuracy is None:
        return "medium"
    gap = selection_accuracy - fill_accuracy
    if gap >= 0.15:
        return "high"
    if gap <= 0.03 and prior != "weak":
        return "low"
    return "medium"


def _build_support_capability_stats(
    student_rows: list[tuple[str, list[tuple[str, bool]]]],
    banding_student_level: dict[str, str],
    question_profiles: dict[str, SupportQuestionProfile],
    item_band: dict[str, str],
) -> dict[str, SupportStudentCapabilityStats]:
    stats: dict[str, SupportStudentCapabilityStats] = {}
    for student_id, first_attempts in student_rows:
        support_level = banding_student_level.get(student_id)
        if support_level is None:
            continue
        metric_counts = Counter()
        metric_correct = Counter()
        for question_id, is_correct in first_attempts:
            profile = question_profiles.get(question_id)
            if profile is None:
                continue
            active_metrics: list[str] = []
            if profile.arithmetic:
                active_metrics.append("arithmetic")
            if profile.application:
                active_metrics.append("application")
            if profile.geometry:
                active_metrics.append("geometry")
            if profile.pattern:
                active_metrics.append("pattern")
            if profile.has_options:
                active_metrics.append("selection")
            else:
                active_metrics.append("fill")
            if item_band.get(question_id) == "hard":
                active_metrics.append("hard")
            if profile.multi_step:
                active_metrics.append("multi_step")
            for metric_name in active_metrics:
                metric_counts[metric_name] += 1
                if is_correct:
                    metric_correct[metric_name] += 1
        stats[student_id] = SupportStudentCapabilityStats(
            student_id=student_id,
            support_level=support_level,
            metric_counts=dict(metric_counts),
            metric_correct=dict(metric_correct),
        )
    return stats


def _build_math_task_capability_anchor(
    selected_profiles: list[SupportStudentProfile],
    support_capability_stats: dict[str, SupportStudentCapabilityStats],
    support_level: str,
    prior: str,
    min_capability_item_count: int,
) -> MathTaskCapabilityAnchor:
    if not selected_profiles:
        raise ValueError("selected_profiles cannot be empty when building capability anchor")

    aggregated_counts = Counter()
    aggregated_correct = Counter()
    support_anchor_ids: list[str] = []
    for profile in selected_profiles:
        support_anchor_ids.append(profile.student_id)
        capability_stats = support_capability_stats.get(profile.student_id)
        if capability_stats is None:
            raise ValueError(
                f"missing support capability stats for anchor student {profile.student_id}"
            )
        aggregated_counts.update(capability_stats.metric_counts)
        aggregated_correct.update(capability_stats.metric_correct)

    metric_accuracy = {
        metric_name: _safe_accuracy(
            aggregated_correct.get(metric_name, 0),
            aggregated_counts.get(metric_name, 0),
        )
        for metric_name in set(CAPABILITY_METRIC_MAP.values())
    }
    global_accuracy = sum(profile.support_accuracy for profile in selected_profiles) / len(
        selected_profiles
    )

    capability_values: dict[str, str] = {}
    for field_name in CAPABILITY_FIELDS:
        metric_name = CAPABILITY_METRIC_MAP[field_name]
        if aggregated_counts.get(metric_name, 0) < min_capability_item_count:
            capability_values[field_name] = _accuracy_to_level(
                accuracy=None,
                support_level=support_level,
                prior=prior,
                global_accuracy=global_accuracy,
            )
            continue
        capability_values[field_name] = _accuracy_to_level(
            accuracy=metric_accuracy.get(metric_name),
            support_level=support_level,
            prior=prior,
            global_accuracy=global_accuracy,
        )

    guessing_tendency = _guessing_tendency_level(
        selection_accuracy=metric_accuracy.get("selection"),
        fill_accuracy=metric_accuracy.get("fill"),
        prior=prior,
    )

    evidence: list[str] = [
        f"support_anchor_ids={','.join(sorted(support_anchor_ids, key=_student_id_sort_key))}",
        f"support_aggregation_size={len(support_anchor_ids)}",
        f"support_level={support_level}",
        f"global_accuracy={global_accuracy:.3f}",
    ]
    for metric_name in [
        "arithmetic",
        "application",
        "multi_step",
        "geometry",
        "pattern",
        "selection",
        "fill",
        "hard",
    ]:
        accuracy = metric_accuracy.get(metric_name)
        accuracy_text = "NA" if accuracy is None else f"{accuracy:.3f}"
        evidence.append(
            f"{metric_name}_accuracy={accuracy_text}|n={aggregated_counts.get(metric_name, 0)}"
        )

    return MathTaskCapabilityAnchor(
        arithmetic_fluency=capability_values["arithmetic_fluency"],
        word_problem_transfer=capability_values["word_problem_transfer"],
        multi_step_stability=capability_values["multi_step_stability"],
        geometry_intuition=capability_values["geometry_intuition"],
        pattern_rule_detection=capability_values["pattern_rule_detection"],
        option_elimination=capability_values["option_elimination"],
        fill_blank_precision=capability_values["fill_blank_precision"],
        hard_item_persistence=capability_values["hard_item_persistence"],
        guessing_tendency=guessing_tendency,
        capability_evidence=evidence,
        support_anchor_ids=sorted(support_anchor_ids, key=_student_id_sort_key),
        support_level=support_level,
        support_aggregation_size=len(support_anchor_ids),
    )


def build_response_anchored_persona_rows(
    persona_path: str | Path,
    response_csv_path: str | Path,
    excluded_question_ids: set[str],
    settings: AnchorBuildSettings,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    personas = load_personas(persona_path, limit=None)
    raw_rows_by_id = _load_raw_persona_rows(persona_path)
    support_question_profiles = _load_support_question_profiles(response_csv_path)

    for persona in personas:
        if persona.grade != TARGET_GRADE:
            raise ValueError(
                "response-anchored personas currently only support the XES grade-3 task; "
                f"found persona {persona.student_id} with grade={persona.grade!r}"
            )

    support_profiles, support_summary = build_support_student_profiles(
        response_csv_path=response_csv_path,
        excluded_question_ids=excluded_question_ids,
        settings=settings,
    )
    support_student_rows = _iter_first_attempts_by_student(
        response_csv_path=response_csv_path,
        excluded_question_ids=excluded_question_ids,
    )
    support_banding = _band_students(
        student_rows=support_student_rows,
        min_student_unique_items=settings.min_student_unique_items,
    )
    item_total = Counter()
    item_correct = Counter()
    for student_id, first_attempts in support_student_rows:
        if student_id not in support_banding.student_level:
            continue
        for question_id, is_correct in first_attempts:
            item_total[question_id] += 1
            if is_correct:
                item_correct[question_id] += 1
    item_band: dict[str, str] = {}
    for question_id, total in item_total.items():
        item_band[question_id] = _difficulty_band_for_accuracy(
            accuracy=item_correct[question_id] / total,
            hard_max_accuracy=settings.hard_max_accuracy,
            medium_max_accuracy=settings.medium_max_accuracy,
        )
    support_capability_stats = _build_support_capability_stats(
        student_rows=support_student_rows,
        banding_student_level=support_banding.student_level,
        question_profiles=support_question_profiles,
        item_band=item_band,
    )
    support_by_level: dict[str, list[SupportStudentProfile]] = defaultdict(list)
    for profile in support_profiles:
        support_by_level[profile.support_level].append(profile)

    used_anchor_ids: set[str] = set()
    persona_groups: dict[tuple[str, str], list[PersonaRecord]] = defaultdict(list)
    for persona in personas:
        prior = _resolve_math_prior(persona)
        persona_groups[(persona.academic_level, prior)].append(persona)

    output_rows: list[dict[str, object]] = []
    matched_strength_counts = Counter()
    anchor_accuracy_by_prior: dict[str, list[float]] = defaultdict(list)
    anchor_percentile_by_prior: dict[str, list[float]] = defaultdict(list)

    for level in LEVELS:
        for prior in ("strong", "neutral", "weak"):
            group = sorted(
                persona_groups.get((level, prior), []),
                key=lambda persona: persona.student_id,
            )
            if not group:
                continue
            available = [
                candidate
                for candidate in support_by_level[level]
                if candidate.student_id not in used_anchor_ids
            ]
            if len(available) < len(group):
                raise ValueError(
                    f"not enough unused support anchors for level={level}, prior={prior}: "
                    f"need={len(group)}, available={len(available)}"
                )
            ordered_candidates = _ordered_candidates_for_prior(
                candidates=available,
                prior=prior,
                level=level,
            )
            selected_candidates = ordered_candidates[: len(group)]
            for persona, candidate in zip(group, selected_candidates):
                used_anchor_ids.add(candidate.student_id)
                summary, evidence = _build_anchor_summary(prior=prior, profile=candidate)
                neighbor_candidates = _ordered_candidates_for_prior(
                    candidates=support_by_level[level],
                    prior=prior,
                    level=level,
                )[: settings.capability_neighbor_count]
                capability_anchor = _build_math_task_capability_anchor(
                    selected_profiles=neighbor_candidates,
                    support_capability_stats=support_capability_stats,
                    support_level=level,
                    prior=prior,
                    min_capability_item_count=settings.min_capability_item_count,
                )
                row = dict(raw_rows_by_id[persona.student_id])
                row["math_anchor_profile"] = asdict(
                    MathAnchorProfile(
                        anchor_student_id=candidate.student_id,
                        support_item_count=candidate.support_item_count,
                        support_accuracy=candidate.support_accuracy,
                        support_accuracy_percentile_within_level=(
                            candidate.support_accuracy_percentile_within_level
                        ),
                        support_level=candidate.support_level,
                        within_level_strength=candidate.within_level_strength,
                        easy_accuracy=candidate.easy_accuracy,
                        medium_accuracy=candidate.medium_accuracy,
                        hard_accuracy=candidate.hard_accuracy,
                        summary=summary,
                        evidence=evidence,
                        excluded_question_count=len(excluded_question_ids),
                    )
                )
                row["math_task_capability_anchor"] = asdict(capability_anchor)
                output_rows.append(row)
                matched_strength_counts[candidate.within_level_strength] += 1
                anchor_accuracy_by_prior[prior].append(candidate.support_accuracy)
                anchor_percentile_by_prior[prior].append(
                    candidate.support_accuracy_percentile_within_level
                )

    output_rows.sort(key=lambda row: str(row["id"]))
    summary = {
        "persona_source_path": str(Path(persona_path)),
        "response_csv_path": str(Path(response_csv_path)),
        "excluded_question_count": len(excluded_question_ids),
        "settings": asdict(settings),
        "support_summary": support_summary,
        "n_output_personas": len(output_rows),
        "matched_strength_counts": dict(matched_strength_counts),
        "capability_neighbor_count": settings.capability_neighbor_count,
        "min_capability_item_count": settings.min_capability_item_count,
        "anchor_accuracy_mean_by_prior": {
            prior: (sum(values) / len(values) if values else None)
            for prior, values in anchor_accuracy_by_prior.items()
        },
        "anchor_percentile_mean_by_prior": {
            prior: (sum(values) / len(values) if values else None)
            for prior, values in anchor_percentile_by_prior.items()
        },
    }
    return output_rows, summary
