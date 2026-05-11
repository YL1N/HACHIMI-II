# Prompt Schema Migration Audit

Date: 2026-04-16
Scope: `src/*.py`, `run_experiments.py`, `PROJECT_GUIDE.md`

## Summary
Current implementation is aligned with the migration target for core schema and responsibility split.
The major previous gap (heuristic mapping in `map_student_model_to_internal_signals`) has been removed and replaced by LLM-based mapping with strict schema validation.

## 1) StudentModel schema status

Implemented as theory-grounded descriptive outputs:
- `self_efficacy_analysis.{efficacy_belief_description, efficacy_belief_evidence}`
- `srl_analysis.{primary_srl_vulnerability, srl_process_evidence}`
- `control_value_analysis.{control_appraisal_description, value_appraisal_description, control_value_evidence}`
- `engagement_level_tendency` (ICAP native)
- `engagement_evidence`
- `response_directness_description`
- `response_directness_evidence`
- `raw_summary`

File: `src/student_model.py`

## 2) ProblemRequirementProfile schema status

Implemented fields:
- `operation_complexity` + `operation_complexity_justification`
- `abstraction_level` + `abstraction_level_justification`
- `prerequisite_knowledge`
- `knowledge_integration_demand`
- `representation_shift_required`
- `response_format_demand`
- `guessability`
- `notes`

Outward enums use theory-native labels for DOK and Stein/Smith categories.
File: `src/problem_profile.py`

## 3) ItemResponseState schema status

Implemented and LLM-inferred:
- `prerequisite_familiarity`
- `response_state`
- `reachable_level`
- `error_path`
- `commitment_tendency`
- `explanation_depth_cap`
- `response_style_guidance`

File: `src/response_state.py`

## 4) Implementation mapping layer status

Implemented explicit mapping function:
- `map_student_model_to_internal_signals(...)`

Current behavior:
- LLM-based semantic mapping (`STUDENT_INTERNAL_SIGNALS_PROMPT`)
- strict enum validation to `low|medium|high`
- no keyword/length cue heuristics

Generated signals:
- `efficacy_signal`
- `srl_fragility_signal`
- `control_signal`
- `value_signal`
- `directness_signal`

Files:
- `src/student_model.py`
- `src/prompts.py`

## 5) Pipeline integration status

Derived signals are now computed once per student in `run_experiments.py` and passed through:
- `resolve_item_response_state(...)`
- `generate_student_answer(...)`
- `retry_with_tighter_constraints(...)`

No repeated per-step remapping.

## 6) Heuristic status

Removed from core semantic path:
- keyword-cue mapping in StudentModel->signal conversion

Retained (allowed rule layer):
- schema/enum/list validation
- `compile_constraints(...)`
- hard violation rule checks (`check_hard_violation_rules(...)`)
- retry flow control (`retry_with_tighter_constraints(...)`)
- evaluation/aggregation/reporting

## 7) Smoke validation

Live run succeeded with real endpoint:
- Output: `outputs/run_20260416_190556`
- `n_predictions=1`
- schema parsed end-to-end
- derived signals emitted in output records
