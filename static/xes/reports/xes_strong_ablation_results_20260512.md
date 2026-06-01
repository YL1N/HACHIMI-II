# XES strong harness ablation results

## Core metrics

| variant | acc | consistency | item_P | item_S | student_P | student_S | failure_rate |
|---|---|---|---|---|---|---|---|
| baseline_hachimi_state_step | 0.6939 | 0.6703 | 0.3469 | 0.3990 | 0.6757 | 0.6936 | 0.0000 |
| history_only_state_step | 0.7054 | 0.6752 | 0.2912 | 0.3746 | 0.6606 | 0.6661 | 0.0002 |
| hachimi_direct | 0.6089 | 0.5988 | 0.2028 | 0.2286 | 0.3716 | 0.4115 | 0.0000 |
| hachimi_state_single | 0.6851 | 0.6653 | 0.3041 | 0.3522 | 0.6898 | 0.6999 | 0.0000 |
| hachimi_no_difficulty_anchor | 0.7069 | 0.6767 | 0.3113 | 0.3913 | 0.6757 | 0.6973 | 0.0000 |
| hachimi_third_person_response | 0.5634 | 0.5852 | 0.3162 | 0.3684 | 0.6764 | 0.6934 | 0.0000 |
| history_only_direct | 0.6094 | 0.6017 | 0.2310 | 0.2728 | 0.2463 | 0.1974 | 0.0000 |
| history_only_state_single | 0.6925 | 0.6717 | 0.2726 | 0.3128 | 0.7087 | 0.7152 | 0.0000 |
| history_only_no_difficulty_anchor | 0.6976 | 0.6740 | 0.3079 | 0.3620 | 0.6742 | 0.7017 | 0.0000 |
| hachimi_direct_no_difficulty_anchor | 0.6167 | 0.6062 | 0.2209 | 0.2528 | 0.5049 | 0.4950 | 0.0000 |
| hachimi_state_single_no_difficulty_anchor | 0.6799 | 0.6524 | 0.2716 | 0.2942 | 0.6756 | 0.6952 | 0.0000 |
| history_only_direct_no_difficulty_anchor | 0.6127 | 0.6023 | 0.2135 | 0.2539 | 0.4783 | 0.4701 | 0.0000 |
| hachimi_no_real_difficulty_band | 0.7094 | 0.6753 | 0.2662 | 0.3491 | 0.6545 | 0.6955 | 0.0000 |
| hachimi_no_difficulty_signal | 0.7382 | 0.6913 | 0.2635 | 0.3416 | 0.6701 | 0.6843 | 0.0000 |
| hachimi_no_difficulty_signal_no_internal_signals | 0.7309 | 0.6847 | 0.2560 | 0.3261 | 0.7017 | 0.7276 | 0.0000 |
| hachimi_no_difficulty_signal_minimal_signals | 0.7286 | 0.6870 | 0.2617 | 0.3372 | 0.6722 | 0.6987 | 0.0000 |
| hachimi_no_difficulty_signal_student_capability_only | 0.6932 | 0.6599 | 0.2365 | 0.2972 | 0.6216 | 0.6374 | 0.0123 |
| hachimi_no_difficulty_signal_student_no_psych_fields | 0.7148 | 0.6877 | 0.2915 | 0.3555 | 0.6121 | 0.6627 | 0.0189 |
| hachimi_no_difficulty_signal_student_no_style_fields | 0.7142 | 0.6729 | 0.2810 | 0.3140 | 0.6521 | 0.6644 | 0.0050 |
| hachimi_no_difficulty_signal_problem_core_only | 0.7736 | 0.7097 | 0.2298 | 0.3383 | 0.6769 | 0.7295 | 0.0019 |
| hachimi_no_difficulty_signal_no_problem_justifications | 0.7231 | 0.6877 | 0.2746 | 0.3388 | 0.6742 | 0.7002 | 0.0090 |
| hachimi_no_difficulty_signal_no_problem_notes | 0.7203 | 0.6727 | 0.2285 | 0.3621 | 0.6491 | 0.6496 | 0.0069 |
| hachimi_no_difficulty_signal_no_interaction_decision | 0.8227 | 0.7245 | 0.1441 | 0.2389 | 0.1572 | 0.5872 | 0.0276 |
| hachimi_no_difficulty_signal_item_state_label_only | 0.7731 | 0.7106 | 0.2442 | 0.2656 | 0.6690 | 0.6788 | 0.0000 |
| hachimi_no_difficulty_signal_loose_constraints | 0.7655 | 0.7134 | 0.2899 | 0.3497 | 0.7080 | 0.7404 | 0.0000 |

## Delta vs baseline

| variant | delta_consistency | delta_item_P | delta_student_P |
|---|---|---|---|
| baseline_hachimi_state_step | 0.0000 | 0.0000 | 0.0000 |
| history_only_state_step | 0.0049 | -0.0557 | -0.0151 |
| hachimi_direct | -0.0715 | -0.1442 | -0.3041 |
| hachimi_state_single | -0.0050 | -0.0428 | 0.0141 |
| hachimi_no_difficulty_anchor | 0.0064 | -0.0356 | 0.0000 |
| hachimi_third_person_response | -0.0851 | -0.0308 | 0.0007 |
| history_only_direct | -0.0686 | -0.1159 | -0.4294 |
| history_only_state_single | 0.0014 | -0.0743 | 0.0330 |
| history_only_no_difficulty_anchor | 0.0036 | -0.0391 | -0.0015 |
| hachimi_direct_no_difficulty_anchor | -0.0641 | -0.1260 | -0.1707 |
| hachimi_state_single_no_difficulty_anchor | -0.0179 | -0.0753 | -0.0001 |
| history_only_direct_no_difficulty_anchor | -0.0681 | -0.1335 | -0.1973 |
| hachimi_no_real_difficulty_band | 0.0050 | -0.0808 | -0.0211 |
| hachimi_no_difficulty_signal | 0.0210 | -0.0834 | -0.0056 |
| hachimi_no_difficulty_signal_no_internal_signals | 0.0144 | -0.0909 | 0.0260 |
| hachimi_no_difficulty_signal_minimal_signals | 0.0167 | -0.0852 | -0.0035 |
| hachimi_no_difficulty_signal_student_capability_only | -0.0104 | -0.1104 | -0.0541 |
| hachimi_no_difficulty_signal_student_no_psych_fields | 0.0174 | -0.0555 | -0.0636 |
| hachimi_no_difficulty_signal_student_no_style_fields | 0.0026 | -0.0659 | -0.0236 |
| hachimi_no_difficulty_signal_problem_core_only | 0.0394 | -0.1171 | 0.0012 |
| hachimi_no_difficulty_signal_no_problem_justifications | 0.0174 | -0.0723 | -0.0015 |
| hachimi_no_difficulty_signal_no_problem_notes | 0.0024 | -0.1184 | -0.0266 |
| hachimi_no_difficulty_signal_no_interaction_decision | 0.0542 | -0.2029 | -0.5185 |
| hachimi_no_difficulty_signal_item_state_label_only | 0.0403 | -0.1027 | -0.0066 |
| hachimi_no_difficulty_signal_loose_constraints | 0.0431 | -0.0570 | 0.0323 |

## Run dirs

- `baseline_hachimi_state_step`: `xes\outputs\xes_strong_ablation_60x96_20260512\baseline_hachimi_state_step\run_20260512_135129`
- `history_only_state_step`: `xes\outputs\xes_strong_ablation_60x96_20260512\history_only_state_step\run_20260512_141637`
- `hachimi_direct`: `xes\outputs\xes_strong_ablation_60x96_20260512\hachimi_direct\run_20260512_144141`
- `hachimi_state_single`: `xes\outputs\xes_strong_ablation_60x96_20260512\hachimi_state_single\run_20260512_145141`
- `hachimi_no_difficulty_anchor`: `xes\outputs\xes_strong_ablation_60x96_20260512\hachimi_no_difficulty_anchor\run_20260512_151410`
- `hachimi_third_person_response`: `xes\outputs\xes_strong_ablation_60x96_20260512\hachimi_third_person_response\run_20260512_154659`
- `history_only_direct`: `xes\outputs\xes_strong_ablation_60x96_20260512\history_only_direct\run_20260512_161154`
- `history_only_state_single`: `xes\outputs\xes_strong_ablation_60x96_20260512\history_only_state_single\run_20260512_162154`
- `history_only_no_difficulty_anchor`: `xes\outputs\xes_strong_ablation_60x96_20260512\history_only_no_difficulty_anchor\run_20260512_164411`
- `hachimi_direct_no_difficulty_anchor`: `xes\outputs\xes_strong_ablation_60x96_20260512\hachimi_direct_no_difficulty_anchor\run_20260512_170902`
- `hachimi_state_single_no_difficulty_anchor`: `xes\outputs\xes_strong_ablation_60x96_20260512\hachimi_state_single_no_difficulty_anchor\run_20260512_171855`
- `history_only_direct_no_difficulty_anchor`: `xes\outputs\xes_strong_ablation_60x96_20260512\history_only_direct_no_difficulty_anchor\run_20260512_174126`
- `hachimi_no_real_difficulty_band`: `xes\outputs\xes_strong_ablation_60x96_20260512\hachimi_no_real_difficulty_band\run_20260512_183644`
- `hachimi_no_difficulty_signal`: `xes\outputs\xes_strong_ablation_60x96_20260512\hachimi_no_difficulty_signal\run_20260512_203802`
- `hachimi_no_difficulty_signal_no_internal_signals`: `xes\outputs\xes_strong_ablation_60x96_20260512\hachimi_no_difficulty_signal_no_internal_signals\run_20260512_210309`
- `hachimi_no_difficulty_signal_minimal_signals`: `xes\outputs\xes_strong_ablation_60x96_20260512\hachimi_no_difficulty_signal_minimal_signals\run_20260512_212803`
- `hachimi_no_difficulty_signal_student_capability_only`: `xes\outputs\xes_strong_ablation_60x96_20260512\hachimi_no_difficulty_signal_student_capability_only\run_20260513_093439`
- `hachimi_no_difficulty_signal_student_no_psych_fields`: `xes\outputs\xes_strong_ablation_60x96_20260512\hachimi_no_difficulty_signal_student_no_psych_fields\run_20260513_095956`
- `hachimi_no_difficulty_signal_student_no_style_fields`: `xes\outputs\xes_strong_ablation_60x96_20260512\hachimi_no_difficulty_signal_student_no_style_fields\run_20260513_103415`
- `hachimi_no_difficulty_signal_problem_core_only`: `xes\outputs\xes_strong_ablation_60x96_20260512\hachimi_no_difficulty_signal_problem_core_only\run_20260513_110041`
- `hachimi_no_difficulty_signal_no_problem_justifications`: `xes\outputs\xes_strong_ablation_60x96_20260512\hachimi_no_difficulty_signal_no_problem_justifications\run_20260513_113634`
- `hachimi_no_difficulty_signal_no_problem_notes`: `xes\outputs\xes_strong_ablation_60x96_20260512\hachimi_no_difficulty_signal_no_problem_notes\run_20260513_121231`
- `hachimi_no_difficulty_signal_no_interaction_decision`: `xes\outputs\xes_strong_ablation_60x96_20260512\hachimi_no_difficulty_signal_no_interaction_decision\run_20260513_125009`
- `hachimi_no_difficulty_signal_item_state_label_only`: `xes\outputs\xes_strong_ablation_60x96_20260512\hachimi_no_difficulty_signal_item_state_label_only\run_20260513_135936`
- `hachimi_no_difficulty_signal_loose_constraints`: `xes\outputs\xes_strong_ablation_60x96_20260512\hachimi_no_difficulty_signal_loose_constraints\run_20260513_151749`
