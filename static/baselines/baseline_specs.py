from __future__ import annotations

from dataclasses import dataclass


BASELINE_DIRECT_ROLEPLAY = "direct_roleplay"
BASELINE_STRONG_PROMPTING_ESS = "strong_prompting_ess"
BASELINE_PROFILE_CONDITIONED = "profile_conditioned"

BASELINE_NAMES = (
    BASELINE_DIRECT_ROLEPLAY,
    BASELINE_STRONG_PROMPTING_ESS,
    BASELINE_PROFILE_CONDITIONED,
)

DATASET_NAMES = ("xes", "eedi_static", "enem_cn")

GENERATION_FORBIDDEN_FIELDS = (
    "real_answer",
    "correct_answer",
    "real_is_correct",
    "gold_answer",
    "gold_answers",
    "is_correct",
    "correctness",
    "empirical_accuracy",
    "all_train_response_count",
    "item_response_state",
    "student_item_interaction_decision",
    "constraint_bundle",
    "problem_requirement_profile",
    "interaction_decision",
    "response_state",
)


@dataclass(frozen=True)
class BaselineSpec:
    name: str
    family: str
    source_reference: str
    method_status: str
    generation_visible_fields: tuple[str, ...]
    generation_forbidden_fields: tuple[str, ...]
    theory_note: str


BASELINE_SPECS = {
    BASELINE_DIRECT_ROLEPLAY: BaselineSpec(
        name=BASELINE_DIRECT_ROLEPLAY,
        family="direct role-play",
        source_reference=(
            "Simulated Students in Tutoring Dialogues: Substance or Illusion? "
            "(https://arxiv.org/abs/2601.04025); "
            "LLM-student-simulations "
            "(https://github.com/lucabenedetto/LLM-student-simulations)"
        ),
        method_status="inspired baseline, not a full paper reproduction",
        generation_visible_fields=(
            "dataset_name",
            "student_id",
            "question_id",
            "question_text",
            "image_path",
            "answer_space",
        ),
        generation_forbidden_fields=GENERATION_FORBIDDEN_FIELDS,
        theory_note=(
            "One-step role-play prompt. It is intentionally weak and only asks the "
            "model to answer as the student, so it tests whether detailed state "
            "machinery is actually needed."
        ),
    ),
    BASELINE_STRONG_PROMPTING_ESS: BaselineSpec(
        name=BASELINE_STRONG_PROMPTING_ESS,
        family="ESS-inspired strong prompting",
        source_reference=(
            "Towards Valid Student Simulation with Large Language Models "
            "(https://arxiv.org/abs/2601.05473)"
        ),
        method_status="inspired baseline, not a full ESS system reproduction",
        generation_visible_fields=(
            "dataset_name",
            "student_id",
            "question_id",
            "history_summary",
            "question_text",
            "image_path",
            "answer_space",
        ),
        generation_forbidden_fields=GENERATION_FORBIDDEN_FIELDS,
        theory_note=(
            "Augments direct role-play with stronger natural-language constraints "
            "on accessible knowledge, reasoning depth, uncertainty, and error "
            "preservation, applied purely at the prompt level. It receives the "
            "visible history summary, receives no profile text, and builds no "
            "named state, decision, or compiled constraint objects."
        ),
    ),
    BASELINE_PROFILE_CONDITIONED: BaselineSpec(
        name=BASELINE_PROFILE_CONDITIONED,
        family="profile-conditioned",
        source_reference=(
            "Generative Students: Using LLM-Simulated Student Profiles to Support Question Item Evaluation "
            "(https://arxiv.org/abs/2405.11591); "
            "Personality-aware Student Simulation for Conversational Intelligent Tutoring Systems "
            "(https://arxiv.org/abs/2404.06762); "
            "Who Am I? History-Aware Profiles for Student Simulation in Tutoring Dialogues "
            "(https://arxiv.org/abs/2605.30051)"
        ),
        method_status="inspired baseline for profile/persona/history-conditioned simulators",
        generation_visible_fields=(
            "dataset_name",
            "student_id",
            "question_id",
            "history_summary",
            "profile_text",
            "question_text",
            "image_path",
            "answer_space",
        ),
        generation_forbidden_fields=GENERATION_FORBIDDEN_FIELDS,
        theory_note=(
            "Conditions generation on history/profile text. Profile dimensions "
            "follow common education constructs: self-efficacy, self-regulated "
            "learning, and control-value appraisal."
        ),
    ),
}


def get_baseline_spec(name: str) -> BaselineSpec:
    if name not in BASELINE_SPECS:
        raise ValueError(f"unknown baseline: {name}")
    return BASELINE_SPECS[name]
