from __future__ import annotations

import csv
import json
import random
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .enem_matrix import science_competency_for_skill, science_skill_code, science_skill_summary


LEVEL_NAMES = ("poor", "low", "medium", "high")
ANSWER_SPACE = ("A", "B", "C", "D", "E")
REGULAR_AREA_CODES: dict[str, tuple[str, ...]] = {
    "CN": ("1419", "1420", "1421", "1422"),
    "MT": ("1407", "1408", "1409", "1410"),
    "CH": ("1383", "1384", "1385", "1386"),
    "LC": ("1395", "1396", "1397", "1398"),
}
AREA_POSITION_START = {"LC": 1, "CH": 46, "CN": 91, "MT": 136}


@dataclass(frozen=True)
class EnemItem:
    question_id: str
    area: str
    item_position: int
    correct_answer: str
    skill_code: str
    skill_summary: str
    competency_id: int
    competency_short_name: str
    competency_focus: str
    is_abandoned: bool
    is_adapted: bool
    base_booklet_code: str
    base_booklet_color: str
    image_path: str | None
    image_context_note: str
    question_text: str | None
    question_text_language: str | None
    use_image_with_question_text: bool
    irt_a: float | None
    irt_b: float | None
    irt_c: float | None
    difficulty_band_for_split: str


@dataclass(frozen=True)
class AreaItemBank:
    area: str
    regular_codes: list[str]
    base_booklet_code: str
    common_items: dict[str, EnemItem]
    rows_by_code: dict[str, list[dict[str, str]]]
    row_by_code_and_item: dict[str, dict[str, dict[str, str]]]


@dataclass(frozen=True)
class EnemAttempt:
    question_id: str
    area: str
    item_position: int
    answer_value: str
    correct_answer: str
    is_correct: bool
    skill_code: str
    competency_short_name: str
    booklet_code: str


@dataclass(frozen=True)
class EnemStaticQuestion:
    question_id: str
    area: str
    item_position: int
    answer_space: list[str]
    image_path: str | None
    image_context_note: str
    question_text: str | None
    question_text_language: str | None
    use_image_with_question_text: bool
    skill_code: str
    skill_summary: str
    competency_id: int
    competency_short_name: str
    competency_focus: str


@dataclass(frozen=True)
class EnemStaticStudent:
    student_id: str
    target_area: str
    ability_level: str
    ability_score_proxy: float
    history_accuracy: float
    history: list[EnemAttempt]
    test: list[EnemAttempt]


@dataclass(frozen=True)
class EnemStaticDataset:
    config: dict[str, Any]
    dataset_root: Path
    target_area: str
    history_item_ids: list[str]
    test_item_ids: list[str]
    questions: dict[str, EnemStaticQuestion]
    students: list[EnemStaticStudent]


def load_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8-sig") as file:
        return json.load(file)


def _read_items_csv(dataset_root: Path) -> list[dict[str, str]]:
    item_path = dataset_root / "DADOS" / "ITENS_PROVA_2024.csv"
    if not item_path.exists():
        raise FileNotFoundError(f"ENEM item file not found: {item_path}")
    with item_path.open("r", encoding="latin1", newline="") as file:
        return list(csv.DictReader(file, delimiter=";"))


def _parse_float(value: str) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    return float(text.replace(",", "."))


def _booklet_color(code: str, area: str) -> str:
    mapping = {
        "CN": {"1419": "AZUL", "1420": "AMARELO", "1421": "VERDE", "1422": "CINZA"},
        "MT": {"1407": "AZUL", "1408": "AMARELO", "1409": "VERDE", "1410": "CINZA"},
        "CH": {"1383": "AZUL", "1384": "AMARELO", "1385": "BRANCO", "1386": "VERDE"},
        "LC": {"1395": "AZUL", "1396": "AMARELO", "1397": "VERDE", "1398": "BRANCO"},
    }
    return mapping.get(area, {}).get(code, "UNKNOWN")


def _difficulty_bands(rows: list[dict[str, str]]) -> dict[str, str]:
    scored = [
        (str(row["CO_ITEM"]), _parse_float(row.get("NU_PARAM_B", "")))
        for row in rows
        if row.get("IN_ITEM_ABAN") == "0"
    ]
    scored = [(item_id, score) for item_id, score in scored if score is not None]
    if not scored:
        return {}
    scored.sort(key=lambda item: item[1])
    bands: dict[str, str] = {}
    for idx, (item_id, _score) in enumerate(scored):
        if idx < len(scored) / 3:
            bands[item_id] = "low_b_for_split"
        elif idx < 2 * len(scored) / 3:
            bands[item_id] = "mid_b_for_split"
        else:
            bands[item_id] = "high_b_for_split"
    return bands


def load_area_item_bank(
    dataset_root: str | Path,
    area: str = "CN",
    regular_codes: list[str] | None = None,
    base_booklet_code: str | None = None,
    image_manifest: dict[str, str] | None = None,
    text_manifest: dict[str, dict[str, str]] | None = None,
    use_image_with_question_text: bool = False,
) -> AreaItemBank:
    root = Path(dataset_root)
    target_area = area.upper()
    codes = regular_codes or list(REGULAR_AREA_CODES.get(target_area, ()))
    if not codes:
        raise ValueError(f"unsupported ENEM area or missing regular_codes: {area}")
    base_code = base_booklet_code or codes[0]
    if base_code not in codes:
        raise ValueError(f"base_booklet_code={base_code} not in regular_codes={codes}")

    rows = _read_items_csv(root)
    rows_by_code: dict[str, list[dict[str, str]]] = {}
    for code in codes:
        code_rows = [
            row
            for row in rows
            if row.get("SG_AREA") == target_area and row.get("CO_PROVA") == code
        ]
        if not code_rows:
            raise ValueError(f"no item rows for area={target_area} code={code}")
        code_rows.sort(key=lambda row: int(row["CO_POSICAO"]))
        rows_by_code[code] = code_rows

    non_abandoned_sets = [
        {str(row["CO_ITEM"]) for row in rows_by_code[code] if row.get("IN_ITEM_ABAN") == "0"}
        for code in codes
    ]
    common_ids = set.intersection(*non_abandoned_sets)
    if not common_ids:
        raise ValueError(f"no common non-abandoned items for area={target_area}")

    base_rows = [row for row in rows_by_code[base_code] if str(row["CO_ITEM"]) in common_ids]
    base_rows.sort(key=lambda row: int(row["CO_POSICAO"]))
    difficulty_bands = _difficulty_bands(base_rows)
    row_by_code_and_item = {
        code: {str(row["CO_ITEM"]): row for row in code_rows}
        for code, code_rows in rows_by_code.items()
    }

    common_items: dict[str, EnemItem] = {}
    for row in base_rows:
        skill_id = str(row["CO_HABILIDADE"]).strip()
        competency = science_competency_for_skill(skill_id) if target_area == "CN" else None
        item_id = str(row["CO_ITEM"])
        text_row = (text_manifest or {}).get(item_id) or {}
        common_items[item_id] = EnemItem(
            question_id=item_id,
            area=target_area,
            item_position=int(row["CO_POSICAO"]),
            correct_answer=str(row["TX_GABARITO"]).strip(),
            skill_code=science_skill_code(skill_id) if target_area == "CN" else f"H{skill_id}",
            skill_summary=science_skill_summary(skill_id) if target_area == "CN" else f"ENEM habilidade {skill_id}",
            competency_id=competency.competency_id if competency else 0,
            competency_short_name=competency.short_name if competency else target_area.lower(),
            competency_focus=competency.capability_focus if competency else f"ENEM {target_area} skill",
            is_abandoned=row.get("IN_ITEM_ABAN") == "1",
            is_adapted=row.get("IN_ITEM_ADAPTADO") == "1",
            base_booklet_code=base_code,
            base_booklet_color=_booklet_color(base_code, target_area),
            image_path=(image_manifest or {}).get(item_id),
            image_context_note=(
                f"Image comes from base booklet code {base_code}; "
                f"target question is QUESTÃO {row['CO_POSICAO']}."
            ),
            question_text=text_row.get("question_text"),
            question_text_language=text_row.get("question_text_language"),
            use_image_with_question_text=use_image_with_question_text,
            irt_a=_parse_float(row.get("NU_PARAM_A", "")),
            irt_b=_parse_float(row.get("NU_PARAM_B", "")),
            irt_c=_parse_float(row.get("NU_PARAM_C", "")),
            difficulty_band_for_split=difficulty_bands.get(item_id, "unknown_b_for_split"),
        )
    return AreaItemBank(
        area=target_area,
        regular_codes=list(codes),
        base_booklet_code=base_code,
        common_items=common_items,
        rows_by_code=rows_by_code,
        row_by_code_and_item=row_by_code_and_item,
    )


def split_history_test_items(
    items: list[EnemItem],
    history_size: int,
    seed: int = 42,
) -> tuple[list[str], list[str]]:
    if history_size <= 0:
        raise ValueError("history_size must be positive")
    if history_size >= len(items):
        raise ValueError(f"history_size={history_size} must be smaller than item_count={len(items)}")
    rng = random.Random(seed)
    groups: dict[tuple[int, str], list[EnemItem]] = defaultdict(list)
    for item in items:
        groups[(item.competency_id, item.difficulty_band_for_split)].append(item)
    for group_items in groups.values():
        rng.shuffle(group_items)

    history: list[EnemItem] = []
    group_keys = sorted(groups)
    cursor = 0
    while len(history) < history_size and any(groups[key] for key in group_keys):
        key = group_keys[cursor % len(group_keys)]
        if groups[key]:
            history.append(groups[key].pop(0))
        cursor += 1
    if len(history) < history_size:
        remaining = [item for key in group_keys for item in groups[key]]
        rng.shuffle(remaining)
        history.extend(remaining[: history_size - len(history)])

    history_ids = [item.question_id for item in history]
    history_set = set(history_ids)
    test_ids = [item.question_id for item in sorted(items, key=lambda row: row.item_position) if item.question_id not in history_set]
    return history_ids, test_ids


def ability_level_from_history_accuracy(history_accuracy: float) -> str:
    if history_accuracy < 0.25:
        return "poor"
    if history_accuracy < 0.45:
        return "low"
    if history_accuracy < 0.65:
        return "medium"
    return "high"


def _answer_at_position(answer_vector: str, item_position: int, area: str) -> str:
    offset = AREA_POSITION_START[area]
    idx = item_position - offset
    if idx < 0 or idx >= len(answer_vector):
        raise ValueError(
            f"answer vector too short for area={area} position={item_position}: len={len(answer_vector)}"
        )
    return answer_vector[idx].strip().upper()


def _attempts_from_result_row(
    row: dict[str, str],
    item_bank: AreaItemBank,
    selected_item_ids: set[str],
) -> dict[str, EnemAttempt]:
    area = item_bank.area
    code = str(row.get(f"CO_PROVA_{area}") or "")
    if code not in item_bank.rows_by_code:
        return {}
    answer_vector = str(row.get(f"TX_RESPOSTAS_{area}") or "")
    attempts: dict[str, EnemAttempt] = {}
    for item_id in selected_item_ids:
        item_row = item_bank.row_by_code_and_item[code].get(item_id)
        if item_row is None or item_row.get("IN_ITEM_ABAN") == "1":
            continue
        item = item_bank.common_items[item_id]
        answer_value = _answer_at_position(answer_vector, int(item_row["CO_POSICAO"]), area)
        correct_answer = str(item_row["TX_GABARITO"]).strip().upper()
        attempts[item_id] = EnemAttempt(
            question_id=item_id,
            area=area,
            item_position=int(item_row["CO_POSICAO"]),
            answer_value=answer_value,
            correct_answer=correct_answer,
            is_correct=answer_value == correct_answer,
            skill_code=item.skill_code,
            competency_short_name=item.competency_short_name,
            booklet_code=code,
        )
    return attempts


def _selected_level_targets(config: dict[str, Any], max_students: int | None) -> dict[str, int]:
    if max_students is not None:
        if max_students <= 0:
            raise ValueError("max_students must be positive when provided")
        total = int(max_students)
        base = total // len(LEVEL_NAMES)
        rem = total % len(LEVEL_NAMES)
        return {level: base + (1 if idx < rem else 0) for idx, level in enumerate(LEVEL_NAMES)}
    raw = config.get("students_per_level")
    if isinstance(raw, dict):
        return {level: int(raw.get(level, 0)) for level in LEVEL_NAMES}
    total = int(max_students or config.get("max_students") or 40)
    base = total // len(LEVEL_NAMES)
    rem = total % len(LEVEL_NAMES)
    return {level: base + (1 if idx < rem else 0) for idx, level in enumerate(LEVEL_NAMES)}


def summarize_history(student: EnemStaticStudent) -> dict[str, Any]:
    by_competency: dict[str, list[EnemAttempt]] = defaultdict(list)
    for attempt in student.history:
        by_competency[attempt.competency_short_name].append(attempt)
    competency_accuracy = {
        name: sum(1 for attempt in attempts if attempt.is_correct) / len(attempts)
        for name, attempts in by_competency.items()
    }
    answer_counts = Counter(attempt.answer_value for attempt in student.history)
    return {
        "student_id": student.student_id,
        "target_area": student.target_area,
        "ability_level": student.ability_level,
        "ability_score_proxy": student.ability_score_proxy,
        "history_accuracy": student.history_accuracy,
        "history_count": len(student.history),
        "test_count": len(student.test),
        "competency_accuracy": competency_accuracy,
        "answer_counts": dict(answer_counts),
        "blank_or_invalid_count": sum(1 for attempt in student.history if attempt.answer_value not in ANSWER_SPACE),
    }


def _question_from_item(item: EnemItem) -> EnemStaticQuestion:
    return EnemStaticQuestion(
        question_id=item.question_id,
        area=item.area,
        item_position=item.item_position,
        answer_space=list(ANSWER_SPACE),
        image_path=item.image_path,
        image_context_note=item.image_context_note,
        question_text=item.question_text,
        question_text_language=item.question_text_language,
        use_image_with_question_text=item.use_image_with_question_text,
        skill_code=item.skill_code,
        skill_summary=item.skill_summary,
        competency_id=item.competency_id,
        competency_short_name=item.competency_short_name,
        competency_focus=item.competency_focus,
    )


def build_dataset(
    config_path: str | Path,
    history_size: int | None = None,
    max_students: int | None = None,
    max_questions: int | None = None,
) -> EnemStaticDataset:
    config = load_json(config_path)
    dataset_root = Path(str(config.get("source_dataset_root") or Path(config_path).resolve().parent / "enem2024"))
    if not dataset_root.exists():
        raise FileNotFoundError(f"ENEM dataset root not found: {dataset_root}")
    target_area = str(config.get("target_area") or "CN").upper()
    effective_history_size = int(history_size or config.get("history_size") or 20)
    seed = int(config.get("sampling_seed") or 42)

    image_manifest: dict[str, str] = {}
    image_manifest_path = str(config.get("question_image_manifest_path") or "").strip()
    if image_manifest_path:
        manifest_path = Path(image_manifest_path)
        if not manifest_path.is_absolute():
            manifest_path = Path(config_path).resolve().parent / manifest_path
        if not manifest_path.exists():
            raise FileNotFoundError(f"question image manifest not found: {manifest_path}")
        with manifest_path.open("r", encoding="utf-8") as file:
            for line in file:
                if not line.strip():
                    continue
                row = json.loads(line)
                image_manifest[str(row["question_id"])] = str(row["image_path"])

    text_manifest: dict[str, dict[str, str]] = {}
    text_manifest_path = str(config.get("question_text_manifest_path") or "").strip()
    if text_manifest_path:
        manifest_path = Path(text_manifest_path)
        if not manifest_path.is_absolute():
            manifest_path = Path(config_path).resolve().parent / manifest_path
        if not manifest_path.exists():
            raise FileNotFoundError(f"question text manifest not found: {manifest_path}")
        with manifest_path.open("r", encoding="utf-8") as file:
            for line in file:
                if not line.strip():
                    continue
                row = json.loads(line)
                text_manifest[str(row["question_id"])] = {
                    "question_text": str(row["question_text"]),
                    "question_text_language": str(row.get("question_text_language") or "en"),
                }

    item_bank = load_area_item_bank(
        dataset_root=dataset_root,
        area=target_area,
        regular_codes=[str(code) for code in config.get("regular_codes", REGULAR_AREA_CODES[target_area])],
        base_booklet_code=str(config.get("base_booklet_code") or REGULAR_AREA_CODES[target_area][0]),
        image_manifest=image_manifest,
        text_manifest=text_manifest,
        use_image_with_question_text=bool(config.get("use_image_with_question_text", False)),
    )
    item_list = list(item_bank.common_items.values())
    history_ids, test_ids = split_history_test_items(item_list, effective_history_size, seed=seed)
    if max_questions is not None:
        if max_questions <= 0:
            raise ValueError("max_questions must be positive when provided")
        test_ids = test_ids[:max_questions]
    selected_item_ids = set(history_ids) | set(test_ids)
    questions = {item_id: _question_from_item(item_bank.common_items[item_id]) for item_id in test_ids}

    result_path = dataset_root / "DADOS" / "RESULTADOS_2024.csv"
    if not result_path.exists():
        raise FileNotFoundError(f"ENEM results file not found: {result_path}")
    level_targets = _selected_level_targets(config, max_students)
    selected_by_level: dict[str, list[EnemStaticStudent]] = {level: [] for level in LEVEL_NAMES}
    max_scan_rows = config.get("max_scan_rows")
    max_scan_rows = int(max_scan_rows) if max_scan_rows is not None else None

    with result_path.open("r", encoding="latin1", newline="") as file:
        reader = csv.DictReader(file, delimiter=";")
        for row_idx, row in enumerate(reader, start=1):
            if max_scan_rows is not None and row_idx > max_scan_rows:
                break
            if all(len(selected_by_level[level]) >= level_targets[level] for level in LEVEL_NAMES):
                break
            if row.get(f"TP_PRESENCA_{target_area}") != "1":
                continue
            if row.get(f"CO_PROVA_{target_area}") not in item_bank.regular_codes:
                continue
            attempts = _attempts_from_result_row(row, item_bank, selected_item_ids)
            if not selected_item_ids.issubset(attempts):
                continue
            history = [attempts[item_id] for item_id in history_ids]
            test = [attempts[item_id] for item_id in test_ids]
            history_accuracy = sum(1 for attempt in history if attempt.is_correct) / len(history)
            level = ability_level_from_history_accuracy(history_accuracy)
            if len(selected_by_level[level]) >= level_targets[level]:
                continue
            selected_by_level[level].append(
                EnemStaticStudent(
                    student_id=str(row["NU_SEQUENCIAL"]),
                    target_area=target_area,
                    ability_level=level,
                    ability_score_proxy=history_accuracy,
                    history_accuracy=history_accuracy,
                    history=history,
                    test=test,
                )
            )

    missing = {
        level: level_targets[level] - len(selected_by_level[level])
        for level in LEVEL_NAMES
        if len(selected_by_level[level]) < level_targets[level]
    }
    if missing:
        raise ValueError(f"not enough ENEM students selected for requested level targets: {missing}")

    students = [student for level in LEVEL_NAMES for student in selected_by_level[level]]
    return EnemStaticDataset(
        config=config,
        dataset_root=dataset_root,
        target_area=target_area,
        history_item_ids=history_ids,
        test_item_ids=test_ids,
        questions=questions,
        students=students,
    )


def as_jsonable_dataset(dataset: EnemStaticDataset) -> dict[str, Any]:
    return {
        "config": dataset.config,
        "dataset_root": str(dataset.dataset_root),
        "target_area": dataset.target_area,
        "history_item_ids": dataset.history_item_ids,
        "test_item_ids": dataset.test_item_ids,
        "questions": {key: asdict(value) for key, value in dataset.questions.items()},
        "students": [asdict(student) for student in dataset.students],
    }
