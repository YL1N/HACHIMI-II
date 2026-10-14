"""Build a HACHIMI-1M persona bank for Khan/CoMTA dynamic simulation.

Extracts persona profiles from the HACHIMI-1M corpus (jiang2026hachimi)
for use with the Khan/CoMTA tutoring-dialogue simulation pipeline.

The HACHIMI-1M corpus is available from the first-generation HACHIMI release.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
EEDI_DIR = SCRIPT_DIR.parent / "eedi"
sys.path.insert(0, str(EEDI_DIR))

from src.persona_prior import HachimiPersona, write_persona_bank  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a HACHIMI-1M persona bank for Khan/CoMTA."
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
    )
    return parser


def _load_and_convert(path: str, max_personas: int) -> list[HachimiPersona]:
    corpus_path = Path(path)
    if not corpus_path.exists():
        raise FileNotFoundError(
            f"HACHIMI-1M corpus not found: {corpus_path}\n"
            "Download it from the HACHIMI (first-generation) release."
        )
    personas: list[HachimiPersona] = []
    with corpus_path.open("r", encoding="utf-8") as f:
        for line in f:
            if max_personas > 0 and len(personas) >= max_personas:
                break
            raw = json.loads(line.strip())
            subjects = raw.get("subjects", [])
            parsed = []
            for s in subjects:
                if isinstance(s, (list, tuple)) and len(s) == 2:
                    parsed.append((str(s[0]).strip(), int(s[1])))
                elif isinstance(s, str):
                    parsed.append((s.strip(), 0))
            personas.append(HachimiPersona(
                persona_id=str(raw.get("persona_id", raw.get("id", ""))).strip(),
                grade_or_age=str(raw.get("grade_or_age", raw.get("grade", ""))).strip(),
                academic_level=str(raw.get("academic_level", raw.get("level", ""))).strip(),
                subjects=parsed,
                learning_style_tags=raw.get("learning_style_tags", []),
                self_efficacy_description=str(raw.get("self_efficacy_description", "")).strip(),
                motivation_description=str(raw.get("motivation_description", "")).strip(),
                confidence_description=str(raw.get("confidence_description", "")).strip(),
                interactional_style=str(raw.get("interactional_style", "")).strip(),
                persona_description=str(raw.get("persona_description", "")).strip(),
            ))
    return personas


def main() -> None:
    args = _build_parser().parse_args()
    personas = _load_and_convert(args.hachimi_1m_path, args.max_personas)
    if not personas:
        raise ValueError("No personas loaded.")
    out = Path(args.output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    write_persona_bank(out, personas)
    print(f"Wrote {len(personas)} personas to {out}")


if __name__ == "__main__":
    main()
