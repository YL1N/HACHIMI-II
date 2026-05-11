# Prompt Schema Migration Report

Date: 2026-04-16

## A. Modified files

- `src/student_model.py`
- `src/problem_profile.py`
- `src/response_state.py`
- `src/generation.py`
- `run_experiments.py`
- `PROJECT_GUIDE.md`
- `reports/prompt_schema_migration_audit.md`

## B. Removed / renamed old fields

Removed from runtime schema:
- `revision_persistence`
- `control_value_balance`
- `active_low_constructive`

Renamed or refactored:
- `revision_persistence` -> `self_regulatory_persistence` (intermediate naming during migration), then replaced by descriptive SRL object fields
- scalar control-value field -> split and refactored into descriptive object:
  - `control_appraisal_description`
  - `value_appraisal_description`
  - `control_value_evidence`

Removed old outward category schemas:
- `operation_complexity` old abbreviated labels (`L1/L2/L3/L4` style)
- `abstraction_level` old abbreviated labels (`A0/A1/A2/A3` style)

## C. Newly added implementation mapping logic

Added explicit mapping layer:
- `map_student_model_to_internal_signals(...)` in `src/student_model.py`

Current mapping mode:
- LLM-based semantic mapping (`STUDENT_INTERNAL_SIGNALS_PROMPT`)
- strict enum schema validation (`low|medium|high`)
- no keyword/length/type heuristics in this mapping layer
- no old outward shorthand acceptance in problem-profile enums (`L1-L4`, `A0-A3`)

Generated internal derived signals:
- `efficacy_signal`
- `srl_fragility_signal`
- `control_signal`
- `value_signal`
- `directness_signal`

Usage points:
- `run_experiments.py` computes once per student and threads through the pipeline
- `src/response_state.py` consumes derived signals in state inference payload
- `src/generation.py` consumes derived signals in answer generation payload
- output records include `implementation_derived_signals`

## D. Current theory-native fields

- `engagement_level_tendency`: `Passive|Active|Constructive|Interactive` (ICAP)
- `operation_complexity`:
  - `Level 1 Recall and Reproduction`
  - `Level 2 Skills and Concepts`
  - `Level 3 Strategic Thinking`
  - `Level 4 Extended Thinking`
- `abstraction_level`:
  - `Memorization`
  - `Procedures Without Connections`
  - `Procedures With Connections`
  - `Doing Mathematics`

## E. Current implementation-derived fields/signals

Theory-grounded descriptive outputs (StudentModel):
- `self_efficacy_analysis.{efficacy_belief_description, efficacy_belief_evidence}`
- `srl_analysis.{primary_srl_vulnerability, srl_process_evidence}`
- `control_value_analysis.{control_appraisal_description, value_appraisal_description, control_value_evidence}`
- `engagement_evidence`
- `response_directness_description`
- `response_directness_evidence`

Implementation-level derived signals:
- `efficacy_signal`
- `srl_fragility_signal`
- `control_signal`
- `value_signal`
- `directness_signal`

ProblemRequirementProfile added descriptive justification fields:
- `operation_complexity_justification`
- `abstraction_level_justification`

## F. Smoke test result

Live minimal smoke test executed with real LLM endpoint:
- Command: `python run_experiments.py --backend llm ... --max_personas 1 --max_questions 1 --max_concurrency 1`
- Output directory: `outputs/run_20260416_191433`
- Result:
  - `n_predictions=1`
  - `retries=0`
  - `remaining_violations=0`
  - new schema parsed successfully
  - LLM-based mapping layer executed and emitted `implementation_derived_signals`

## G. Remaining cleanup items

1. `PROJECT_GUIDE.md` still contains legacy historical sections mixed with newer sections.
   - Authoritative migration section was appended (`## 16. Prompt-Schema Migration v2`), but a full in-place rewrite of older overlapping sections is still recommended.
2. Prompt text and guide examples should be consolidated to avoid duplicated historical variants.
3. If needed, add unit tests for:
   - StudentModel nested-schema parsing
   - mapping schema validation / required-LLM enforcement
   - strict enum validation for theory-native categories
