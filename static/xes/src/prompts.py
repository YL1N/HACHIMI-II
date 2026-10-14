"""Auditable prompt templates for the math student answering harness.

These templates are centrally stored so prompt behavior is inspectable,
versionable, and not scattered across files.

IMPORTANT DESIGN RULE
1. If a theory provides original named categories, those categories must be used exactly.
2. If a theory does NOT provide canonical discrete categories, do NOT invent low/medium/high
   and pretend they are theory-native. In such cases, ask for theory-grounded description
   and evidence instead.
3. Method-level states are allowed only for project-specific inference layers
   such as task-local learner state.
"""

STUDENT_MODEL_PROMPT = """
Build a theory-grounded StudentModel for math answering.
Output JSON only. Do not use markdown.
Do NOT answer any question.

Important rule:
- If the theory below has original categories, use them exactly.
- If the theory below does NOT have canonical discrete categories, do NOT invent low/medium/high labels.
- Instead, provide a theory-grounded description and brief evidence from the student persona.

Additional input note:
- The input may include an optional `math_anchor_profile`.
- If present, it is support-set math evidence derived from a matched real student's
  non-evaluation math responses.
- For math-answering behavior, treat this support-based evidence as more direct than
  coarse strong_subjects / weak_subjects labels alone.
- Do not copy metrics mechanically; interpret what they imply about the student's likely
  math confidence, regulation, and workable solving boundary.
- The input may also include an optional `math_task_capability_anchor`.
- If present, it is a support-set-derived structured capability anchor computed directly from
  real non-evaluation response data.
- When `math_task_capability_anchor` is present, treat it as the primary source for
  `math_task_capability_profile`. Do not invent a stronger or weaker capability boundary than it supports.

You must produce the following fields:

1. self_efficacy_analysis
Theory: Bandura's self-efficacy.
Meaning:
Self-efficacy concerns the learner's belief about whether they can successfully carry out the task.
Task:
Describe the student's likely mathematics-related efficacy belief for school-level math answering.
Output:
- efficacy_belief_description
- efficacy_belief_evidence

2. srl_analysis
Theory: Zimmerman's self-regulated learning.
Meaning:
Self-regulated learning concerns how learners plan, monitor, control, and reflect on their learning.
Use the original SRL phase names exactly when relevant:
- Forethought
- Performance
- Self-Reflection
Task:
Describe the student's likely self-regulatory pattern in math answering.
Output:
- primary_srl_vulnerability
- srl_process_evidence

3. control_value_analysis
Theory: Pekrun's control-value theory.
Meaning:
Achievement emotions are shaped by the learner's sense of control and task value.
Task:
Describe separately the student's likely control appraisal and value appraisal toward math tasks.
Output:
- control_appraisal_description
- value_appraisal_description
- control_value_evidence

4. engagement_level_tendency
Theory: ICAP.
IMPORTANT: use the original ICAP categories exactly.
Choose one:
- Passive
- Active
- Constructive
- Interactive

Short theoretical meanings:
- Passive: mainly receives with little overt engagement
- Active: overtly does something simple, such as selecting, copying, or brief responding
- Constructive: generates something beyond the given information
- Interactive: engages in reciprocal co-construction with another person

Output:
- engagement_level_tendency
- engagement_evidence

5. response_directness
This is an implementation-level auxiliary field, not a theory-native category.
Meaning:
Describe whether the student's math-answering style tends to be more hesitant/cautious or more direct.
Output:
- response_directness_description
- response_directness_evidence

6. math_task_capability_profile
This is an implementation-level harness object, not a theory-native category.
Its purpose is to summarize task-relevant math capability in a structured way so later
student-item interaction decisions are not forced to rely on long free-text persona prose.

Choose one for each capability:
- high
- medium
- low

Choose one for confidence_calibration:
- over_confident
- calibrated
- under_confident

Task:
- Use the persona plus optional `math_anchor_profile` evidence to summarize the student's likely
  task-relevant math capability profile for grade-level math items.
- Treat support-based anchor evidence as stronger than generic subject labels when they conflict.
- Keep this profile at the level of stable task tendencies, not one specific item.
- If `math_task_capability_anchor` is present, keep the final profile aligned with it and only
  use the rest of the persona to explain the same boundary, not to override it.

Output:
- arithmetic_fluency
- word_problem_transfer
- multi_step_stability
- geometry_intuition
- pattern_rule_detection
- option_elimination
- fill_blank_precision
- hard_item_persistence
- guessing_tendency
- confidence_calibration
- format_discipline
- common_error_families
- capability_evidence

Additional constraints:
- Keep interpretation bounded to math-answering behavior only.
- Do not describe a full personality.
- Do not write stories.
- Return compact JSON only.
- Do not wrap the answer under keys like student_model, analysis, result, or data.
- Never use null for any required object or list field.

Return exactly this top-level JSON shape:
{
  "self_efficacy_analysis": {
    "efficacy_belief_description": "...",
    "efficacy_belief_evidence": ["..."]
  },
  "srl_analysis": {
    "primary_srl_vulnerability": "...",
    "srl_process_evidence": ["..."]
  },
  "control_value_analysis": {
    "control_appraisal_description": "...",
    "value_appraisal_description": "...",
    "control_value_evidence": ["..."]
  },
  "engagement_level_tendency": "Passive|Active|Constructive|Interactive",
  "engagement_evidence": ["..."],
  "response_directness_description": "...",
  "response_directness_evidence": ["..."],
  "math_task_capability_profile": {
    "arithmetic_fluency": "high|medium|low",
    "word_problem_transfer": "high|medium|low",
    "multi_step_stability": "high|medium|low",
    "geometry_intuition": "high|medium|low",
    "pattern_rule_detection": "high|medium|low",
    "option_elimination": "high|medium|low",
    "fill_blank_precision": "high|medium|low",
    "hard_item_persistence": "high|medium|low",
    "guessing_tendency": "high|medium|low",
    "confidence_calibration": "over_confident|calibrated|under_confident",
    "format_discipline": "high|medium|low",
    "common_error_families": ["..."],
    "capability_evidence": ["..."]
  },
  "raw_summary": "..."
}
"""

STUDENT_INTERNAL_SIGNALS_PROMPT = """
Map StudentModel descriptive outputs into implementation-level internal signals.
Output JSON only. Do not use markdown.

IMPORTANT:
- These are engineering signals, NOT theory-native categories.
- Do not rewrite StudentModel fields.
- Do not use dataset statistics, labels, or target metrics.

Signal definitions:

1) efficacy_signal (low|medium|high)
- Meaning: task-specific confidence expectation for school math answering.
- high: expects likely success with confidence.
- low: expects likely struggle/failure with low confidence.

2) srl_fragility_signal (low|medium|high)
- Meaning: fragility of self-regulation under difficulty.
- high: likely unstable monitoring/control/persistence when difficulty rises.
- low: more stable regulation and persistence under challenge.

3) control_signal (low|medium|high)
- Meaning: perceived controllability of success in math tasks.
- high: feels outcomes are mostly manageable via effort/strategy.
- low: feels outcomes are hard to control.

4) value_signal (low|medium|high)
- Meaning: perceived value/importance/usefulness of math tasks.
- high: high subjective value.
- low: low subjective value.

5) directness_signal (low|medium|high)
- Meaning: tendency to respond directly vs cautiously/hesitantly.
- high: direct/decisive response style.
- low: hesitant/cautious/indirect response style.

Output exactly:
{
  "efficacy_signal": "low|medium|high",
  "srl_fragility_signal": "low|medium|high",
  "control_signal": "low|medium|high",
  "value_signal": "low|medium|high",
  "directness_signal": "low|medium|high"
}
"""

PROBLEM_PROFILE_PROMPT = """
Analyze what this math item requires.
Do NOT solve it.
Do NOT output the answer.
Output JSON only. Do not use markdown.

Important optional input:
- The input may include `difficulty_anchor_context`.
- If present, it contains easy/medium/hard support items matched by module and question type.
- Use these anchors only to calibrate your structural judgment of the current item.
- Do NOT solve the anchor items.
- Do NOT infer the current answer from the anchor items.
- Do NOT add any extra output field beyond the required schema.

You must fill the following fields.

1. operation_complexity
Use Webb DOK categories exactly:
- Level 1 Recall and Reproduction:
  mainly recalling facts, terms, definitions, or carrying out direct, routine procedures
- Level 2 Skills and Concepts:
  using skills or concepts in familiar ways, selecting procedures, organizing information,
  but without major strategic reasoning
- Level 3 Strategic Thinking:
  requiring strategic reasoning, relational thinking, multi-step coordination, or justification
- Level 4 Extended Thinking:
  requiring extended reasoning, complex modeling, or sustained non-routine thinking

Output:
- operation_complexity
- operation_complexity_justification

2. abstraction_level
Use Stein & Smith categories exactly:
- Memorization:
  mainly recall or reproduction with little or no mathematical processing
- Procedures Without Connections:
  procedural work with little emphasis on conceptual meaning
- Procedures With Connections:
  procedural work that requires connections to underlying mathematical ideas or relationships
- Doing Mathematics:
  non-algorithmic thinking, exploring, analyzing relationships, and generating mathematical understanding

Output:
- abstraction_level
- abstraction_level_justification

3. prerequisite_knowledge
List the minimum prerequisite knowledge or skills needed.

4. knowledge_integration_demand
Choose one:
- single_knowledge
- multiple_knowledge_combination

Definitions:
- single_knowledge: mainly depends on one main knowledge element or skill
- multiple_knowledge_combination: requires coordinating multiple knowledge elements

5. representation_shift_required
Choose one:
- none
- low
- high

Definitions:
- none: no meaningful representation change is needed
- low: a small amount of representation shift is needed
- high: solving depends strongly on changing representations

6. response_format_demand
Choose one:
- selection_only
- short_fill
- constructed_numeric
- constructed_explanation

Definitions:
- selection_only: answer mainly by choosing among options
- short_fill: answer by short fill-in
- constructed_numeric: answer by constructing a numeric response
- constructed_explanation: answer requires meaningful explanatory construction

7. guessability
Auxiliary field only. Use cautiously.
Choose one:
- unknown
- low
- medium

Definitions:
- unknown: insufficient basis to judge
- low: unlikely to be guessed correctly without real understanding
- medium: there may be some chance of guessing via surface cues or partial elimination

8. notes
A short list of concise notes, if needed.

Return JSON only.
"""

TASK_LOCAL_STATE_PROMPT = """
Perform third-person ItemResponseState inference only.
Do NOT answer the question.
Output JSON only. Do not use markdown.

You are given:
- a StudentModel
- a ProblemRequirementProfile
- the current math item

Important note about StudentModel:
- StudentModel may include `math_anchor_profile_summary` and `math_anchor_profile_evidence`.
- If present, these are support-based math behavior evidence from matched real non-evaluation
  responses and should be treated as higher-priority math evidence than coarse subject labels.
- StudentModel may include `math_task_capability_profile`.
- If present, treat it as a structured task-relevant math capability summary for the current
  student and use it as a stronger prior than long free-text persona prose.

Important note about harness input:
- The input may include `student_item_interaction_decision`.
- If present, it is a structured student-item fit prior derived from the student's task-relevant
  capability profile and the current item's requirement profile.
- You must respect it unless some field is internally contradictory.

Infer the student's item-specific response state.

Fields:

1. prerequisite_familiarity
Choose one:
- familiar
- partially_familiar
- mostly_unfamiliar

Definitions:
- familiar: the student is likely familiar with most prerequisite knowledge needed
- partially_familiar: the student likely knows some but not all required prerequisites
- mostly_unfamiliar: the required prerequisites are largely beyond the student's likely familiarity

2. response_state
Choose one:
- mastered
- partial
- guessable
- unreachable

Definitions:
- mastered: likely within the student's current workable boundary; can solve relatively stably
- partial: the student has some relevant grasp but is not stable; may partly solve or inconsistently succeed
- guessable: the student does not truly master the item, but may still guess correctly from surface cues or partial elimination
- unreachable: the item is substantially beyond the student's current workable boundary

3. reachable_level
One concise sentence describing how far the student could realistically get.

4. error_path
List the most likely error path or failure pattern.

5. commitment_tendency
Choose one:
- low
- medium
- high

Definitions:
- low: likely to hesitate or avoid strong commitment
- medium: may commit, but with some caution
- high: likely to state an answer directly

6. explanation_depth_cap
Choose one:
- answer_only
- short_reason
- limited_reason
- full_reason

Definitions:
- answer_only: at most give an answer, with no meaningful explanation
- short_reason: at most a very short reason
- limited_reason: some limited explanation is plausible
- full_reason: a fuller explanation is plausible

7. response_style_guidance
List short style constraints for later generation.

Important:
- Do not solve the item.
- Do not output the correct answer.
- Do not make the student stronger than the inferred state.
- Use the student's model and the problem requirements together.
- If `student_item_interaction_decision` is present, use it as the primary current-item prior
  and keep the final ItemResponseState consistent with it.
"""

def _build_answer_generator_prompt(
    perspective_rule: str,
    use_behavior_harness: bool = True,
) -> str:
    constraint_rule = (
        "7. Respect all constraints in ConstraintBundle exactly."
        if use_behavior_harness
        else "7. No compiled behavior harness is supplied; use ItemResponseState only as the state boundary."
    )
    return f"""
Generate exactly one step of the student's internal solving process.
Do not use markdown.
Output JSON only.

Important rules:
1. Do NOT use knowledge or reasoning beyond the inferred ItemResponseState.
2. Do NOT target any dataset-level metric, average score, or evaluation target.
3. Do NOT make the student appear more mature or more capable than allowed.
3.5. If student_model contains `math_anchor_profile_summary` or `math_anchor_profile_evidence`,
     respect them as direct math-behavior evidence when choosing the student's confidence and
     style; do not ignore them in favor of generic subject labels.
3.6. If student_model contains `math_task_capability_profile`, use it as the structured
     task-relevant capability prior instead of relying mainly on free-text persona prose.
3.7. If input contains `student_item_interaction_decision`, treat it as the harness-level
     current-item prior for likely reachability, confidence cap, and likely error family.
     Do not casually override it.
4. If response_state = guessable, the student may still get the answer correct, but should NOT produce mature full reasoning.
5. If response_state = unreachable, the student should NOT appear to fully master the item.
6. If explanation_depth_cap = answer_only, do not provide meaningful explanation.
{constraint_rule}
8. This call is for one step only, not the whole solution.
   - internal_thought must contain only the next incremental thought.
   - Do not dump a full multi-step derivation into one step.
   - internal_thought must be brief: at most 2 short sentences.
   - decision_reason must be brief: at most 1 short sentence.
   - Do not repeat the full earlier history.
9. If the student notices they are circling or cannot make real progress, they should stop
   and give the best current answer instead of continuing forever.
   - If the next step would mostly repeat confusion already seen in thinking_history, choose final_answer now.
   - Use remaining_step_budget carefully; do not waste steps on repetition.
   - If remaining_step_budget = 1, this is the last allowed step, so next_action MUST be final_answer.
   - When remaining_step_budget = 1, do not output continue.
10. predicted_answer formatting:
   - If option-based question, output only option letter (A/B/C/D).
   - If fill-in/constructed with multiple blanks, output ordered values joined by ';' (e.g., "10;2").
   - Do not put full natural-language sentences into predicted_answer.
   - If next_action = final_answer, predicted_answer is mandatory even when uncertain.
   - If uncertain, still provide the best current guess in the required answer format.
11. internal_thought perspective:
   - {perspective_rule}
   - Do not mix perspectives.
12. student_response must be the student's brief final utterance only.
    - Do not reveal chain-of-thought, scratch work, repeated recalculation, or self-dialogue.
    - Keep it concise and within the allowed sentence cap.
    - If next_action = final_answer, student_response is mandatory and must agree with predicted_answer.
13. next_action must be one of:
    - continue
    - final_answer
14. Field consistency:
    - If next_action = continue, predicted_answer must be "" and student_response must be "".
    - If next_action = final_answer, predicted_answer and student_response must both be non-empty.
15. Output discipline:
    - Always output all 5 JSON keys.
    - Never omit predicted_answer or student_response on a final_answer step.
    - If remaining_step_budget = 1, final_answer with non-empty answer fields is mandatory.

Return only:
{{
  "internal_thought": "...",
  "next_action": "continue|final_answer",
  "decision_reason": "...",
  "predicted_answer": "...",
  "student_response": "..."
}}
"""


ANSWER_GENERATOR_PROMPT_FIRST_PERSON = _build_answer_generator_prompt(
    "Use first-person student voice.",
    use_behavior_harness=True,
)
ANSWER_GENERATOR_PROMPT_THIRD_PERSON = _build_answer_generator_prompt(
    "Use third-person student voice.",
    use_behavior_harness=True,
)


def _build_direct_answer_prompt(perspective_rule: str) -> str:
    return f"""
Generate the student's final answer directly.
Do not use markdown.
Output JSON only.

You are given:
- StudentModel
- implementation_derived_signals
- ProblemRequirementProfile
- the current math item

Important rules:
1. Do NOT use any dataset statistics, labels, target accuracy, or evaluation targets.
2. Do NOT invent an ItemResponseState or hidden constraint set.
3. Keep the student bounded by the provided StudentModel and internal signals.
3.5. If student_model contains `math_anchor_profile_summary` or `math_anchor_profile_evidence`,
     respect them as direct math-behavior evidence when choosing the student's confidence and
     style; do not ignore them in favor of generic subject labels.
3.6. If student_model contains `math_task_capability_profile`, use it as the structured
     task-relevant capability prior instead of relying mainly on free-text persona prose.
4. Do not write step-by-step reasoning, scratch work, or chain-of-thought.
5. student_response must be the student's brief final utterance only.
6. predicted_answer formatting:
   - If option-based question, output only option letter (A/B/C/D).
   - If fill-in/constructed with multiple blanks, output ordered values joined by ';' (e.g., "10;2").
   - Do not put full natural-language sentences into predicted_answer.
7. student_response perspective:
   - {perspective_rule}
   - Do not mix perspectives.
8. predicted_answer and student_response must both be non-empty.

Return only:
{{
  "predicted_answer": "...",
  "student_response": "..."
}}
"""


DIRECT_ANSWER_PROMPT_FIRST_PERSON = _build_direct_answer_prompt(
    "Use first-person student voice."
)
DIRECT_ANSWER_PROMPT_THIRD_PERSON = _build_direct_answer_prompt(
    "Use third-person student voice."
)


def get_answer_generator_prompt(
    response_persona: str,
    use_behavior_harness: bool = True,
) -> str:
    if not use_behavior_harness:
        if response_persona == "first":
            return _build_answer_generator_prompt(
                "Use first-person student voice.",
                use_behavior_harness=False,
            )
        if response_persona == "third":
            return _build_answer_generator_prompt(
                "Use third-person student voice.",
                use_behavior_harness=False,
            )
        raise ValueError(
            f"invalid response_persona: {response_persona!r}, expected 'first' or 'third'"
        )
    if response_persona == "first":
        return ANSWER_GENERATOR_PROMPT_FIRST_PERSON
    if response_persona == "third":
        return ANSWER_GENERATOR_PROMPT_THIRD_PERSON
    raise ValueError(
        f"invalid response_persona: {response_persona!r}, expected 'first' or 'third'"
    )


def get_direct_answer_prompt(response_persona: str) -> str:
    if response_persona == "first":
        return DIRECT_ANSWER_PROMPT_FIRST_PERSON
    if response_persona == "third":
        return DIRECT_ANSWER_PROMPT_THIRD_PERSON
    raise ValueError(
        f"invalid response_persona: {response_persona!r}, expected 'first' or 'third'"
    )

VIOLATION_REVIEW_PROMPT = """
Judge boundary consistency, NOT answer correctness.
Use only:
- ItemResponseState
- ConstraintBundle
- generated output

Output JSON only:
{
  "has_violation": true/false,
  "reasons": [...],
  "severity": "low|medium|high"
}

Check the following dimensions:

1. capability_leakage
Definition:
The output shows capability beyond what the ItemResponseState supports.

2. over_mature_reasoning
Definition:
The output uses reasoning depth, clarity, or confidence that is too mature for the inferred student state.

3. explanation_depth_cap_violation
Definition:
The output exceeds the allowed explanation depth defined by explanation_depth_cap and ConstraintBundle.

4. contradiction_with_response_state
Definition:
The generated answer or explanation contradicts the inferred response_state
(for example, an unreachable state producing a fully competent explanation).

Do NOT judge based on whether the answer is correct.
Judge only whether the output is consistent with the inferred student boundary.
"""

ANSWER_CORRECTNESS_JUDGE_PROMPT = """
Judge whether a predicted answer is correct for the given math item.
Output JSON only. Do not use markdown.

You are given:
- question_text
- options (may be empty)
- predicted_answer

Task:
1. Solve/interpret the item yourself.
2. Decide whether predicted_answer is correct.
3. Do not use any external dataset statistics.

Output schema:
{
  "is_correct": true/false,
  "confidence": "low|medium|high"
}

Rules:
- If options are present, compare predicted option with the correct option.
- For fill-in/multi-blank answers, accept equivalent concise formats when they express the same required values.
- Return only JSON.
"""
