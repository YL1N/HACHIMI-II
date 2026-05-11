# EEDI 弱模型 harness 对比（strong vs 3B vs 7B）

## 1. 核心指标对比
| run | n_rows | correctness | same_error | error_realization | cosine | rougeL | pred_na | n_records | n_failures | failure_rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| strong | 956 | 0.6679 | 0.3333 | 0.3514 | 0.1731 | 0.1706 | 44 | 1000 | 96 | 0.0960 |
| weak-3b | 926 | 0.5551 | 0.3571 | 0.3784 | 0.1664 | 0.1490 | 120 | 965 | 35 | 0.0363 |
| weak-7b | 922 | 0.5714 | 0.4643 | 0.2523 | 0.1555 | 0.1579 | 111 | 960 | 40 | 0.0417 |

基线默认取第一行：`strong`。

## 2. 相对基线增减
| run | Δcorrectness | Δsame_error | Δerror_realization | Δpred_na | Δfailure_rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| weak-3b | -0.1128 | +0.0238 | +0.0270 | +76 | -0.0597 |
| weak-7b | -0.0965 | +0.1310 | -0.0991 | +67 | -0.0543 |

## 3. 运行层分布
| run | response_space | target_engagement | response_commitment | response_maturity | violations |
| --- | --- | --- | --- | --- | --- |
| strong | 无 | 无 | avoidant:231<br>committed:495<br>tentative:274 | brief_local_explanation:486<br>fragment_only:401<br>full_student_level_reasoning:49<br>limited_structured_reasoning:64 | error_path_discontinuity:31<br>over_fast_transition:4<br>over_mature_response:212 |
| weak-3b | brief_acknowledgment:307<br>clarification_request:101<br>local_explanation:61<br>partial_attempt:392<br>revision_attempt:104 | Active:504<br>Constructive:282<br>Interactive:40<br>Passive:139 | 无 | 无 | 无 |
| weak-7b | brief_acknowledgment:304<br>clarification_request:98<br>local_explanation:56<br>partial_attempt:406<br>revision_attempt:96 | Active:501<br>Constructive:263<br>Interactive:51<br>Passive:145 | 无 | 无 | 无 |

## 4. 失败概览
### strong
- run目录：`D:\Study\sii\MathStudent\eedi\outputs\official_test_1000_updated_20260429`
- detached eval：`D:\Study\sii\MathStudent\eedi\outputs\official_test_1000_updated_20260429\detached_eval_1000\detached_eval_summary.json`
- 运行层指标：`D:\Study\sii\MathStudent\eedi\outputs\official_test_1000_updated_20260429\metrics.json`
- 失败来源：`D:\Study\sii\MathStudent\eedi\outputs\official_test_1000_updated_20260429\task_failures_summary_firstpass_100c.json`
- top failure types：无
- top failure messages：无

### weak-3b
- run目录：`D:\Study\sii\MathStudent\eedi\outputs\official_test_1000_weak_qwen2_5_3b_20260508`
- detached eval：`D:\Study\sii\MathStudent\eedi\outputs\official_test_1000_weak_qwen2_5_3b_20260508\detached_eval_1000\detached_eval_summary.json`
- 运行层指标：`D:\Study\sii\MathStudent\eedi\outputs\official_test_1000_weak_qwen2_5_3b_20260508\metrics.json`
- 失败来源：`D:\Study\sii\MathStudent\eedi\outputs\official_test_1000_weak_qwen2_5_3b_20260508\task_failures.jsonl`
- top failure types：ValueError x34; RuntimeError x1
- top failure messages：generated weak student turn failed validation after retry: ['pred_turn exceeds max_sentences=1 with sentence_count=2'] x11; target_of_intervention must be one of ('misconception', 'missing_step', 'confidence', 'commitment', 'explanation_depth', 'dialogue_flow'), got "['dialogue_fl... x9; turn_rationale must be a non-empty list x8; target_of_intervention must be one of ('misconception', 'missing_step', 'confidence', 'commitment', 'explanation_depth', 'dialogue_flow'), got "['confidence'... x3; no JSON object found after one explicit JSON repair retry. first_content='{\n "instructional_intent": "guide student to recognize the operation Leo applied t... x1

### weak-7b
- run目录：`D:\Study\sii\MathStudent\eedi\outputs\official_test_1000_weak_qwen2_5_7b_20260508`
- detached eval：`D:\Study\sii\MathStudent\eedi\outputs\official_test_1000_weak_qwen2_5_7b_20260508\detached_eval_1000\detached_eval_summary.json`
- 运行层指标：`D:\Study\sii\MathStudent\eedi\outputs\official_test_1000_weak_qwen2_5_7b_20260508\metrics.json`
- 失败来源：`D:\Study\sii\MathStudent\eedi\outputs\official_test_1000_weak_qwen2_5_7b_20260508\task_failures.jsonl`
- top failure types：ValueError x40
- top failure messages：generated weak student turn failed validation after retry: ['pred_turn exceeds max_sentences=1 with sentence_count=2'] x19; target_of_intervention must be one of ('misconception', 'missing_step', 'confidence', 'commitment', 'explanation_depth', 'dialogue_flow'), got "['dialogue_fl... x7; uptake_rationale must be a non-empty list x3; generated weak student turn failed validation after retry: ['pred_turn exceeds max_sentences=2 with sentence_count=3'] x3; generated weak student turn failed validation after retry: ['pred_turn exceeds max_sentences=2 with sentence_count=4'] x2
