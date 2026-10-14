"""Build a HACHIMI-1M persona bank for Eedi dynamic simulation.

Extracts persona profiles from the HACHIMI-1M corpus (jiang2026hachimi) and
formats them as the persona bank consumed by the dynamic pipeline's persona
matching module (src/persona_prior.py).

The HACHIMI-1M corpus is available from the first-generation HACHIMI release.
This script reads the persona corpus, filters for mathematics education
personas, and writes a persona bank in JSONL format.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.persona_prior import HachimiPersona, write_persona_bank
from src.runtime_paths import PROJECT_ROOT, resolve_eedi_path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a HACHIMI-1M persona bank for Eedi dynamic simulation."
    )
    parser.add_argument(
        "--hachimi_1m_path",
        type=str,
        required=True,
        help="Path to the HACHIMI-1M persona corpus (JSONL).",
    )
    parser.add_argument(
        "--output_path",
        type=str,
        required=True,
        help="Output path for the persona bank (JSONL).",
    )
    parser.add_argument(
        "--max_personas",
        type=int,
        default=200,
        help="Maximum number of personas to include.",
    )
    parser.add_argument(
        "--sampling_mode",
        type=str,
        choices=["head", "uniform"],
        default="uniform",
    )
    parser.add_argument(
        "--subject_filter",
        type=str,
        default="mathematics",
        help="Filter personas by subject (case-insensitive substring match).",
    )
    return parser


def _load_hachimi_1m(path: str, subject_filter: str) -> list[dict]:
    corpus_path = Path(path)
    if not corpus_path.exists():
        raise FileNotFoundError(
            f"HACHIMI-1M corpus not found: {corpus_path}\n"
            "Download it from the HACHIMI (first-generation) release."
        )
    personas = []
    with corpus_path.open("r", encoding="utf-8") as f:
        for line in f:
            raw = json.loads(line.strip())
            if subject_filter:
                subjects = raw.get("subjects", [])
                subject_names = [
                    (s[0] if isinstance(s, (list, tuple)) else str(s)).lower()
                    for s in subjects
                ]
                if not any(subject_filter.lower() in name for name in subject_names):
                    continue
            personas.append(raw)
    return personas


def _convert_persona(raw: dict) -> HachimiPersona:
    subjects = raw.get("subjects", [])
    parsed_subjects = []
    for s in subjects:
        if isinstance(s, (list, tuple)) and len(s) == 2:
            parsed_subjects.append((str(s[0]).strip(), int(s[1])))
        elif isinstance(s, str):
            parsed_subjects.append((s.strip(), 0))
    return HachimiPersona(
        persona_id=str(raw.get("persona_id", raw.get("id", ""))).strip(),
        grade_or_age=str(raw.get("grade_or_age", raw.get("grade", ""))).strip(),
        academic_level=str(raw.get("academic_level", raw.get("level", ""))).strip(),
        subjects=parsed_subjects,
        learning_style_tags=raw.get("learning_style_tags", raw.get("learning_styles", [])),
        self_efficacy_description=str(raw.get("self_efficacy_description", raw.get("self_efficacy", ""))).strip(),
        motivation_description=str(raw.get("motivation_description", raw.get("motivation", ""))).strip(),
        confidence_description=str(raw.get("confidence_description", raw.get("confidence", ""))).strip(),
        interactional_style=str(raw.get("interactional_style", raw.get("interaction_style", ""))).strip(),
        persona_description=str(raw.get("persona_description", raw.get("description", ""))).strip(),
    )


def _select_uniform(items: list, max_items: int) -> list:
    if max_items <= 0 or len(items) <= max_items:
        return list(items)
    if max_items == 1:
        return [items[0]]
    last = len(items) - 1
    indices = sorted(set(
        round(i * last / (max_items - 1)) for i in range(max_items)
    ))
    while len(indices) < max_items:
        for idx in range(len(items)):
            if idx not in set(indices):
                indices.append(idx)
                if len(indices) >= max_items:
                    break
    indices.sort()
    return [items[i] for i in indices]


def main() -> None:
    args = _build_parser().parse_args()
    raw_personas = _load_hachimi_1m(args.hachimi_1m_path, args.subject_filter)
    if not raw_personas:
        raise ValueError("No personas found matching the filter criteria.")
    if args.sampling_mode == "uniform":
        selected = _select_uniform(raw_personas, args.max_personas)
    else:
        selected = raw_personas[: args.max_personas]
    personas = [_convert_persona(raw) for raw in selected]
    output_path = resolve_eedi_path(args.output_path)
    write_persona_bank(output_path, personas)
    print(f"Wrote {len(personas)} personas to {output_path}")


if __name__ == "__main__":
    main()
