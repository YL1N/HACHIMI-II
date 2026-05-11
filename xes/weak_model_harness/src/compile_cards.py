from __future__ import annotations

from dataclasses import asdict, is_dataclass

from .cards import (
    PromptLadderCard,
    ResponseProtocol,
    RiskCard,
    ScaffoldBudget,
    StudentState,
    TaskState,
)
from .support_profile import TaskSupportProfile

LEVEL_SCORE = {"low": 0.0, "medium": 1.0, "high": 2.0}
PRESSURE_SCORE = {"low": 0.0, "medium": 1.0, "high": 2.0}
SUPPORT_LEVEL_SCORE = {"L0": 0, "L1": 1, "L2": 2, "L3": 3}

ATTRIBUTE_TO_CAPABILITIES = {
    "fact_retrieval": ["arithmetic_fluency"],
    "arithmetic_computation": ["arithmetic_fluency"],
    "compare_quantities": ["arithmetic_fluency", "word_problem_transfer"],
    "place_value_structure": ["arithmetic_fluency", "format_discipline"],
    "fraction_ratio_reasoning": ["arithmetic_fluency", "pattern_rule_detection"],
    "measurement_unit_reasoning": ["word_problem_transfer", "multi_step_stability"],
    "geometry_visualization": ["geometry_intuition"],
    "pattern_rule_reasoning": ["pattern_rule_detection"],
    "data_table_interpretation": ["word_problem_transfer", "multi_step_stability"],
    "word_problem_schema_mapping": ["word_problem_transfer"],
    "multi_step_planning": ["multi_step_stability", "hard_item_persistence"],
    "equation_relation_tracking": ["multi_step_stability", "pattern_rule_detection"],
    "option_discrimination": ["option_elimination"],
    "precision_formatting": ["fill_blank_precision", "format_discipline"],
}

DEMAND_PRESSURE_BY_OPERATION = {
    "Level 1 Recall and Reproduction": "low",
    "Level 2 Skills and Concepts": "medium",
    "Level 3 Strategic Thinking": "high",
    "Level 4 Extended Thinking": "high",
}

DEMAND_PRESSURE_BY_ABSTRACTION = {
    "Memorization": "low",
    "Procedures Without Connections": "medium",
    "Procedures With Connections": "medium",
    "Doing Mathematics": "high",
}

SCAFFOLD_GUIDE = {
    "identify_knowns_and_unknowns": {
        "level": "L1",
        "hint": "先分清题目已知什么、要求什么，不要一上来乱算。",
    },
    "keep_one_relation_at_a_time": {
        "level": "L2",
        "hint": "一次只盯住一个数量关系，先把第一层关系理顺。",
    },
    "convert_to_same_representation": {
        "level": "L2",
        "hint": "先把信息换成同一种表示方式，再继续往下做。",
    },
    "check_unit_or_interval": {
        "level": "L3",
        "hint": "最后检查单位、间隔、首尾条件有没有漏掉。",
    },
    "verify_last_step_before_answer": {
        "level": "L3",
        "hint": "写答案前，只检查最后一步有没有把前面的关系用对。",
    },
    "eliminate_obvious_options": {
        "level": "L1",
        "hint": "如果是选择题，先排除明显不合理的选项。",
    },
    "focus_on_final_numeric_answer": {
        "level": "L1",
        "hint": "最后只保留题目真正要的那个数，不要把中间结果当答案。",
    },
}


def _mean_capability_level_from_values(capability_values: dict[str, str], capability_names: list[str]) -> str:
    scores = [LEVEL_SCORE[str(capability_values[name])] for name in capability_names]
    mean_score = sum(scores) / len(scores)
    if mean_score >= 1.5:
        return "high"
    if mean_score >= 0.75:
        return "medium"
    return "low"


def _demand_pressure(task_state: TaskState) -> str:
    pressure = max(
        PRESSURE_SCORE[DEMAND_PRESSURE_BY_OPERATION[task_state.operation_complexity]],
        PRESSURE_SCORE[DEMAND_PRESSURE_BY_ABSTRACTION[task_state.abstraction_level]],
    )
    if task_state.knowledge_integration_demand == "multiple_knowledge_combination":
        pressure += 0.5
    if task_state.representation_shift_required == "high":
        pressure += 0.5
    if task_state.response_format_demand in {"short_fill", "constructed_numeric", "constructed_explanation"}:
        pressure += 0.5
    if pressure >= 2.0:
        return "high"
    if pressure >= 1.0:
        return "medium"
    return "low"


def _support_level_from_readiness(
    *,
    mean_readiness: float,
    low_count: int,
    demand_pressure: str,
    question_type: str,
) -> str:
    if mean_readiness >= 1.6 and low_count == 0 and demand_pressure == "low":
        return "L0"
    if mean_readiness >= 1.2 and low_count <= 1 and demand_pressure != "high":
        return "L1"
    if mean_readiness >= 0.75 or question_type.strip() == "单选":
        return "L2"
    return "L3"


def _collect_hints(allowed_scaffolds: list[str], max_support_level: str) -> tuple[list[str], list[str], list[str]]:
    level1: list[str] = []
    level2: list[str] = []
    level3: list[str] = []
    max_score = SUPPORT_LEVEL_SCORE[max_support_level]
    for scaffold in allowed_scaffolds:
        guide = SCAFFOLD_GUIDE.get(scaffold)
        if guide is None:
            continue
        guide_level = str(guide["level"])
        if SUPPORT_LEVEL_SCORE[guide_level] > max_score:
            continue
        hint = str(guide["hint"])
        if guide_level == "L1":
            level1.append(hint)
        elif guide_level == "L2":
            level2.append(hint)
        else:
            level3.append(hint)
    return level1[:3], level2[:3], level3[:3]


def compile_student_state(student_model: object) -> StudentState:
    capability = getattr(student_model, "math_task_capability_profile", None)
    if capability is None:
        raise ValueError("student_model.math_task_capability_profile is required")
    error_families = list(getattr(capability, "common_error_families", []))
    primary_error_family = error_families[0] if error_families else "unknown"
    capability_values = {
        "arithmetic_fluency": str(capability.arithmetic_fluency),
        "word_problem_transfer": str(capability.word_problem_transfer),
        "multi_step_stability": str(capability.multi_step_stability),
        "geometry_intuition": str(capability.geometry_intuition),
        "pattern_rule_detection": str(capability.pattern_rule_detection),
        "option_elimination": str(capability.option_elimination),
        "fill_blank_precision": str(capability.fill_blank_precision),
        "hard_item_persistence": str(capability.hard_item_persistence),
        "guessing_tendency": str(capability.guessing_tendency),
        "confidence_calibration": str(capability.confidence_calibration),
        "format_discipline": str(capability.format_discipline),
    }
    attribute_mastery = {
        attribute: _mean_capability_level_from_values(capability_values, capability_names)
        for attribute, capability_names in ATTRIBUTE_TO_CAPABILITIES.items()
    }
    regulation_signals = {
        "guessing_tendency": capability_values["guessing_tendency"],
        "confidence_calibration": capability_values["confidence_calibration"],
        "hard_item_persistence": capability_values["hard_item_persistence"],
        "format_discipline": capability_values["format_discipline"],
    }
    return StudentState(
        student_id=str(student_model.student_id),
        grade=str(student_model.grade),
        academic_level=str(student_model.academic_level),
        arithmetic_fluency=capability_values["arithmetic_fluency"],
        word_problem_transfer=capability_values["word_problem_transfer"],
        multi_step_stability=capability_values["multi_step_stability"],
        geometry_intuition=capability_values["geometry_intuition"],
        pattern_rule_detection=capability_values["pattern_rule_detection"],
        option_elimination=capability_values["option_elimination"],
        fill_blank_precision=capability_values["fill_blank_precision"],
        hard_item_persistence=capability_values["hard_item_persistence"],
        guessing_tendency=capability_values["guessing_tendency"],
        confidence_calibration=capability_values["confidence_calibration"],
        format_discipline=capability_values["format_discipline"],
        primary_error_family=primary_error_family,
        raw_summary=str(student_model.raw_summary),
        attribute_mastery=attribute_mastery,
        regulation_signals=regulation_signals,
    )


def compile_task_state(
    question_id: str,
    question_type: str,
    profile: object,
    task_support_profile: TaskSupportProfile,
) -> TaskState:
    difficulty_anchor_context = getattr(profile, "difficulty_anchor_context", None)
    if is_dataclass(difficulty_anchor_context):
        difficulty_anchor_context = asdict(difficulty_anchor_context)
    return TaskState(
        question_id=question_id,
        question_type=question_type,
        prerequisite_knowledge=list(profile.prerequisite_knowledge),
        operation_complexity=str(profile.operation_complexity),
        abstraction_level=str(profile.abstraction_level),
        knowledge_integration_demand=str(profile.knowledge_integration_demand),
        representation_shift_required=str(profile.representation_shift_required),
        response_format_demand=str(profile.response_format_demand),
        guessability=str(profile.guessability),
        perceived_difficulty=(
            str(profile.real_difficulty_band)
            if getattr(profile, "real_difficulty_band", None) is not None
            else (
                str(profile.perceived_difficulty_for_target_grade)
                if getattr(profile, "perceived_difficulty_for_target_grade", None) is not None
                else None
            )
        ),
        difficulty_anchor_context=difficulty_anchor_context,
        notes=list(profile.notes),
        q_matrix_attributes=list(task_support_profile.q_matrix_attributes),
        q_matrix_rationale=list(task_support_profile.q_matrix_rationale),
        cognitive_operations=list(task_support_profile.cognitive_operations),
        format_risk_points=list(task_support_profile.format_risk_points),
    )


def compile_scaffold_budget(
    student_state: StudentState,
    task_state: TaskState,
    task_support_profile: TaskSupportProfile,
) -> ScaffoldBudget:
    attribute_readiness = {
        attribute: student_state.attribute_mastery.get(attribute, "low")
        for attribute in task_state.q_matrix_attributes
    }
    readiness_scores = [LEVEL_SCORE[level] for level in attribute_readiness.values()]
    mean_readiness = sum(readiness_scores) / len(readiness_scores) if readiness_scores else 0.0
    low_count = sum(1 for level in attribute_readiness.values() if level == "low")
    demand_pressure = _demand_pressure(task_state)
    max_support_level = _support_level_from_readiness(
        mean_readiness=mean_readiness,
        low_count=low_count,
        demand_pressure=demand_pressure,
        question_type=task_state.question_type,
    )
    support_focus = list(task_support_profile.coaching_focus[:3]) or [
        "先降低无关负担，再自己完成关键计算。"
    ]
    allowed_scaffolds = list(task_support_profile.allowed_scaffolds)
    forbidden_help = [
        "不要直接给最终答案。",
        "不要直接给完整解题步骤。",
        "不要替学生完成关键计算或关键关系判断。",
        "不要根据预期对错反向控制输出。",
    ]
    evidence_rationale = [
        f"target_attributes={','.join(task_state.q_matrix_attributes)}",
        f"attribute_readiness={attribute_readiness}",
        f"demand_pressure={demand_pressure}",
        f"max_support_level={max_support_level}",
    ]
    return ScaffoldBudget(
        target_attributes=list(task_state.q_matrix_attributes),
        attribute_readiness=attribute_readiness,
        demand_pressure=demand_pressure,
        max_support_level=max_support_level,
        support_focus=support_focus,
        allowed_scaffolds=allowed_scaffolds,
        forbidden_help=forbidden_help,
        evidence_rationale=evidence_rationale,
    )


def compile_prompt_ladder(
    task_state: TaskState,
    scaffold_budget: ScaffoldBudget,
    task_support_profile: TaskSupportProfile,
) -> PromptLadderCard:
    level1_hints, level2_hints, level3_hints = _collect_hints(
        scaffold_budget.allowed_scaffolds,
        scaffold_budget.max_support_level,
    )
    if not level1_hints and scaffold_budget.max_support_level in {"L1", "L2", "L3"}:
        level1_hints = ["先确认题目到底问什么，再决定要算哪个量。"]
    if not level2_hints and scaffold_budget.max_support_level in {"L2", "L3"}:
        level2_hints = ["如果信息有点乱，就先把关系按顺序分成前后两步。"]
    if not level3_hints and scaffold_budget.max_support_level == "L3":
        level3_hints = ["写答案前，再检查一次单位、首尾条件和题目要求的最终量。"]
    return PromptLadderCard(
        level0_instruction="先按你自己的当前水平独立尝试；只有在 harness 已经释放的提示范围内，才可以借助提示。",
        level1_hints=level1_hints,
        level2_hints=level2_hints,
        level3_hints=level3_hints,
        release_rule=(
            f"本题最多只允许使用到 {scaffold_budget.max_support_level} 级提示。"
            "提示只能帮助你组织信息、决定先后顺序、检查格式；不能把题直接做完。"
        ),
    )


def compile_risk_card(
    student_state: StudentState,
    task_state: TaskState,
    task_support_profile: TaskSupportProfile,
    scaffold_budget: ScaffoldBudget,
) -> RiskCard:
    likely_pitfalls = list(task_support_profile.common_misconceptions[:3])
    if "word_problem_schema_mapping" in task_state.q_matrix_attributes and student_state.word_problem_transfer == "low":
        likely_pitfalls.append("容易把题意关系映射错，比如该加减时误用乘除。")
    if "multi_step_planning" in task_state.q_matrix_attributes and student_state.multi_step_stability == "low":
        likely_pitfalls.append("容易漏掉中间一步，或者把两步关系混在一起。")
    if "precision_formatting" in task_state.q_matrix_attributes and student_state.fill_blank_precision == "low":
        likely_pitfalls.append("容易把中间结果当最终答案，或者答案格式不够精确。")
    self_check_targets = list(task_state.format_risk_points[:3])
    if task_state.response_format_demand == "selection_only":
        self_check_targets.append("最后确认只输出一个选项字母。")
    else:
        self_check_targets.append("最后确认只输出题目要求的最终答案。")
    guardrails = [
        "这些风险点只是提醒你注意，不是要求你故意做错。",
        "如果不会，也要给出受限且贴题的学生式尝试，不要输出成熟专家解答。",
        "不要编造题目里没有的信息。",
        f"不要使用超过 {scaffold_budget.max_support_level} 级的帮助。",
    ]
    return RiskCard(
        likely_pitfalls=likely_pitfalls[:4],
        self_check_targets=self_check_targets[:4],
        guardrails=guardrails,
    )


def compile_response_protocol(
    task_state: TaskState,
    scaffold_budget: ScaffoldBudget,
) -> ResponseProtocol:
    if task_state.response_format_demand == "selection_only":
        answer_mode = "option_letter_only"
        max_tokens = 4
    else:
        answer_mode = "final_answer_only"
        max_tokens = 16
    response_style = "just_answer"
    boundary_reminders = [
        f"max_support_level={scaffold_budget.max_support_level}",
        f"answer_mode={answer_mode}",
        "先自己做，再在已释放的提示范围内借力。",
    ]
    return ResponseProtocol(
        answer_mode=answer_mode,
        max_tokens=max_tokens,
        response_style=response_style,
        max_support_level=scaffold_budget.max_support_level,
        boundary_reminders=boundary_reminders,
    )
