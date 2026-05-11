# Theory-Prompt Compliance Audit (2026-04-16)

## Scope
Audit target:
- prompt templates (`src/prompts.py`)
- semantic modules (`src/student_model.py`, `src/problem_profile.py`, `src/response_state.py`, `src/generation.py`)
- rule modules (`compile_constraints`, schema validation, violation checks, retry, evaluation)

Audit question:
1. Are LLM-mandatory semantic modules actually using LLM?
2. Are theory-linked fields aligned with source theories?
3. Is there any heuristic replacement in core semantic modules?

## A. LLM usage compliance

LLM-mandatory modules are LLM-driven with explicit `llm_client` requirement:
- `build_student_model(...)`
- `map_student_model_to_internal_signals(...)`
- `build_problem_requirement_profile(...)`
- `resolve_item_response_state(...)`
- `generate_student_answer(...)`
- `review_violation_with_llm(...)` (boundary samples)

No semantic fallback to keyword/if-else heuristics remains in these modules.

## B. Theory-by-theory cross-check

### 1) Bandura self-efficacy
Source check:
- Bandura (1977) frames self-efficacy as judgments/beliefs about one’s capability to execute actions.

Implementation check:
- Prompt uses descriptive efficacy belief analysis (`efficacy_belief_description` + evidence), not fake theory-native bins.
- Internal low/medium/high only appears in implementation mapping layer (`efficacy_signal`), explicitly marked non-theory-native.

Verdict: aligned.

### 2) Zimmerman SRL
Source check:
- Zimmerman’s cyclical SRL model uses phases: Forethought, Performance, Self-Reflection.

Implementation check:
- Prompt explicitly requires SRL interpretation and instructs use of these phase names when relevant.
- Output is descriptive (`primary_srl_vulnerability` + process evidence), not pretending there is one canonical native discrete label set.
- Internal derived signal (`srl_fragility_signal`) is implementation-level only.

Verdict: aligned.

### 3) Pekrun control-value theory
Source check:
- Control-value theory explains achievement emotions via control appraisals and value appraisals.

Implementation check:
- Prompt separates `control_appraisal_description` and `value_appraisal_description`, with shared evidence.
- No merged pseudo-native scalar like old `control_value_balance` remains in runtime schema.
- Internal signals (`control_signal`, `value_signal`) are clearly marked implementation-derived.

Verdict: aligned.

### 4) ICAP (Chi & Wylie)
Source check:
- ICAP categories are Passive, Active, Constructive, Interactive.

Implementation check:
- Prompt uses original ICAP category names exactly.
- Schema validation enforces these values for `engagement_level_tendency`.

Verdict: aligned.

### 5) Webb DOK
Source check:
- DOK levels are Level 1 Recall and Reproduction, Level 2 Skills and Concepts, Level 3 Strategic Thinking, Level 4 Extended Thinking.

Implementation check:
- Prompt uses full DOK names.
- Problem profile schema enforces full labels.
- Old outward shorthand acceptance (`L1/L2/L3/L4`) has been removed from parser alias mapping.

Verdict: aligned.

### 6) Stein & Smith task demand categories
Source check:
- Categories used in the Task Analysis Guide are Memorization, Procedures Without Connections, Procedures With Connections, Doing Mathematics.

Implementation check:
- Prompt uses full category names.
- Problem profile schema enforces full labels.
- Old outward shorthand acceptance (`A0/A1/A2/A3`) has been removed from parser alias mapping.

Verdict: aligned.

## C. Heuristic audit (core semantic vs allowed rule layer)

### Removed from core semantic path
- keyword cue mapping in `map_student_model_to_internal_signals(...)`
- any implicit semantic fallback when `llm_client` is missing

### Retained (allowed by responsibility split)
- schema/enum/list validation
- `compile_constraints(...)`
- hard violation initial screening (`check_hard_violation_rules(...)`)
- boundary routing + one retry flow control
- evaluation/aggregation/reporting

No rule heuristic directly decides correctness labels in generation path.

## D. End-to-end smoke evidence

Latest live smoke run:
- output: `outputs/run_20260416_191433`
- `n_predictions=1`
- `remaining_violations=0`
- full chain runs with new schema and LLM-based mapping

## E. Sources used

- Bandura, A. (1977), Psychological Review (ScienceDirect landing):
  https://www.sciencedirect.com/science/article/pii/0146640278900024
- Zimmerman SRL phases (chapter text with Forethought/Performance/Self-Reflection):
  https://www.researchgate.net/publication/285323162_Self-regulation_Where_metacognition_and_motivation_intersect
- Pekrun control-value theory article page:
  https://www.ovid.com/journals/edpr/fulltext/10.1007/s10648-006-9029-9~the-control-value-theory-of-achievement-emotions-assumptions
- ICAP framework paper (ASU-hosted PDF):
  https://education.asu.edu/sites/default/files/lcl/chiwylie2014icap_2.pdf
- Webb DOK level names (Webb PDF):
  https://mathed.umbc.edu/wp-content/uploads/sites/524/2022/08/Webb_2002_DOK_Levels.pdf
- Task Analysis Guide with Stein/Smith category set:
  https://mcp-coaching.osu.edu/files/2015/11/3-5-3-Smith_Stein_2011_Task_analysis_guide.pdf
