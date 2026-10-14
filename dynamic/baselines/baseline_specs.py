from __future__ import annotations

from dataclasses import dataclass


FORBIDDEN_FIELDS: tuple[str, ...] = (
    "gt_turn",
    "gold_turn",
    "target_turn",
    "current_student_reply",
    "future_turns",
    "official_correctness",
    "official_acts",
    "official_kcs",
    "official_annotations",
    "eval_labels",
)

EVALUATION_ONLY_FIELDS: tuple[str, ...] = ("gt_turn",)


@dataclass(frozen=True)
class BaselineSpec:
    name: str
    family: str
    prompt_type: str
    source_reference: str
    description: str
    uses_profile: bool
    uses_memory: bool
    system_message: str
    instruction: str


BASELINE_SPECS: dict[str, BaselineSpec] = {
    "direct_roleplay": BaselineSpec(
        name="direct_roleplay",
        family="direct_roleplay",
        prompt_type="direct_student_roleplay_json",
        source_reference=(
            "Simulated Students in Tutoring Dialogues: Substance or Illusion? "
            "(https://arxiv.org/abs/2601.04025); "
            "LLM-student-simulations "
            "(https://github.com/lucabenedetto/LLM-student-simulations)"
        ),
        description="Direct role-play baseline with only visible question and history.",
        uses_profile=False,
        uses_memory=False,
        system_message=(
            "You simulate only the next student utterance in a math tutoring dialogue. "
            "Use only the visible information in the user message."
        ),
        instruction=(
            "Write the student's next short reply. Do not write tutor text, labels, "
            "multiple dialogue turns, or predictions about later turns."
        ),
    ),
    "strong_prompting_ess": BaselineSpec(
        name="strong_prompting_ess",
        family="strong_prompting_ess",
        prompt_type="explicit_student_simulation_scaffold_json",
        source_reference=(
            "Towards Valid Student Simulation with Large Language Models "
            "(https://arxiv.org/abs/2601.05473)"
        ),
        description="Strong prompting baseline using an explicit student-simulation scaffold.",
        uses_profile=False,
        uses_memory=False,
        system_message=(
            "You are a controlled baseline for student-turn simulation. "
            "Stay inside the current turn and visible dialogue history."
        ),
        instruction=(
            "Before answering, silently consider the latest tutor request, the student's "
            "visible prior behavior, and the math context. Then output only the next "
            "student reply as one concise utterance."
        ),
    ),
    "profile_conditioned": BaselineSpec(
        name="profile_conditioned",
        family="profile_conditioned",
        prompt_type="coarse_profile_conditioned_json",
        source_reference=(
            "Personality-aware Student Simulation for Conversational Intelligent Tutoring Systems "
            "(https://arxiv.org/abs/2404.06762); "
            "Who Am I? History-Aware Profiles for Student Simulation in Tutoring Dialogues "
            "(https://arxiv.org/abs/2605.30051)"
        ),
        description=(
            "Baseline conditioned on a coarse profile inferred only from prior student turns."
        ),
        uses_profile=True,
        uses_memory=False,
        system_message=(
            "You simulate a student response using a coarse profile derived from past visible turns. "
            "Do not infer from hidden labels or future messages."
        ),
        instruction=(
            "Use the coarse student profile only as a weak style and confidence cue. "
            "Generate one natural next student utterance."
        ),
    ),
    "agent_style_memory": BaselineSpec(
        name="agent_style_memory",
        family="agent_style_memory",
        prompt_type="short_memory_conditioned_json",
        source_reference=(
            "EduAgent: Generative Student Agents in Learning "
            "(https://arxiv.org/abs/2404.07963; https://github.com/EduAgent/EduAgent); "
            "Agent4Edu: Generating Learner Response Data by Generative Agents for Intelligent Education Systems "
            "(https://arxiv.org/abs/2501.10332; https://github.com/bigdata-ustc/Agent4Edu)"
        ),
        description=(
            "Agent-style baseline with a short visible memory of recent student/tutor behavior."
        ),
        uses_profile=True,
        uses_memory=True,
        system_message=(
            "You simulate the next student utterance using only visible history and a short memory. "
            "The memory is not a hidden state label."
        ),
        instruction=(
            "Use the short memory to keep local style continuity. Output one student reply only."
        ),
    ),
}


def get_baseline_spec(name: str) -> BaselineSpec:
    try:
        return BASELINE_SPECS[name]
    except KeyError as exc:
        valid = ", ".join(sorted(BASELINE_SPECS))
        raise ValueError(f"unknown baseline={name!r}; valid values: {valid}") from exc
