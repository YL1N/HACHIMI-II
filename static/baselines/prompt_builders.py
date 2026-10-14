from __future__ import annotations

from pathlib import Path
from typing import Any

from .baseline_specs import (
    BASELINE_DIRECT_ROLEPLAY,
    BASELINE_PROFILE_CONDITIONED,
    BASELINE_STRONG_PROMPTING_ESS,
    get_baseline_spec,
)
from .dataset_adapters import Example, build_prompt_payload


JSON_OUTPUT_INSTRUCTION = """
Return only valid JSON:
{
  "predicted_answer": "one answer from answer_space, or a short free-text answer when answer_space is free_text",
  "student_response": "the student's visible response"
}
Do not include hidden reasoning.
""".strip()


def build_prompt_messages(baseline_name: str, example: Example) -> list[dict[str, Any]]:
    spec = get_baseline_spec(baseline_name)
    payload = build_prompt_payload(example)
    visible = _visible_payload_for_baseline(payload, spec.generation_visible_fields)
    if baseline_name == BASELINE_DIRECT_ROLEPLAY:
        system = _direct_roleplay_system()
        user = _render_payload("Generation-visible item", visible)
    elif baseline_name == BASELINE_STRONG_PROMPTING_ESS:
        system = _strong_prompting_system()
        user = _render_payload("Generation-visible student/item context", visible)
    elif baseline_name == BASELINE_PROFILE_CONDITIONED:
        system = _profile_conditioned_system()
        user = _render_payload("Generation-visible profile/item context", visible)
    else:
        raise ValueError(f"unknown baseline: {baseline_name}")
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def prompt_template_markdown(baseline_name: str) -> str:
    get_baseline_spec(baseline_name)
    if baseline_name == BASELINE_DIRECT_ROLEPLAY:
        system = _direct_roleplay_system()
    elif baseline_name == BASELINE_STRONG_PROMPTING_ESS:
        system = _strong_prompting_system()
    elif baseline_name == BASELINE_PROFILE_CONDITIONED:
        system = _profile_conditioned_system()
    else:
        raise ValueError(f"unknown baseline: {baseline_name}")
    return f"# {baseline_name}\n\n## System\n\n{system}\n\n## User payload\n\nGeneration-visible fields only.\n"


def write_prompt_templates(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for baseline_name in (BASELINE_DIRECT_ROLEPLAY, BASELINE_STRONG_PROMPTING_ESS, BASELINE_PROFILE_CONDITIONED):
        (output_dir / f"{baseline_name}.md").write_text(prompt_template_markdown(baseline_name), encoding="utf-8")


def _visible_payload_for_baseline(payload: dict[str, Any], visible_fields: tuple[str, ...]) -> dict[str, Any]:
    return {field: payload[field] for field in visible_fields if field in payload}


def _direct_roleplay_system() -> str:
    return (
        "You simulate one static item response from a student. "
        "Answer as the student would answer this one item. "
        "Use only the visible question, answer space, image if provided, and visible metadata. "
        + JSON_OUTPUT_INSTRUCTION
    )


def _strong_prompting_system() -> str:
    return (
        "You simulate one static item response from a student under explicit competence boundaries. "
        "Use the visible history summary only as prior evidence of broad ability. "
        "The student may know, partially know, guess, make mistakes, or give a short exam-style answer. "
        "Do not solve like an expert by default. Do not use any hidden gold answer, real current answer, "
        "item statistics, or future information. "
        + JSON_OUTPUT_INSTRUCTION
    )


def _profile_conditioned_system() -> str:
    return (
        "You simulate one static item response from a student using the visible profile and history summary. "
        "Treat self-efficacy, self-regulated learning, and control/value notes as broad behavior clues, "
        "not as labels that determine correctness. "
        "Generate only the current answer and visible student response. "
        "Do not use hidden gold answer, real current answer, item statistics, or future information. "
        + JSON_OUTPUT_INSTRUCTION
    )


def _render_payload(title: str, payload: dict[str, Any]) -> str:
    lines = [title + ":"]
    for key, value in payload.items():
        if key == "image_path":
            if value:
                lines.append(f"- {key}: provided as separate vision input")
            else:
                lines.append(f"- {key}: none")
        else:
            lines.append(f"- {key}: {value}")
    return "\n".join(lines)
