# ENEM static natural-science student simulation

Standalone static-simulation implementation for ENEM 2024. It does not reuse the
`static/xes` entry point and does not import the XES code, but the method layer
follows the same meta-method:

```
history/calibration -> observed profile -> persona match -> StudentModel -> StudentInternalSignals -> ProblemProfile -> StudentItemInteraction -> ItemResponseState -> ConstraintBundle -> StudentAnswer -> offline evaluation
```

## Scope

- Dataset: ENEM 2024 microdata.
- Current main subject: `CN` (Ciências da Natureza, natural sciences).
- Item type: five-option (A/B/C/D/E) objective items.
- History: a subset of items within the same subject used as calibration
  history.
- Test: the remaining items are the prediction targets.

ENEM is not longitudinal learning-history data, so history here is not a time
series but the visible calibration items within a single exam.

## Natural-science instantiation

The ENEM-CN fields are not renamed math fields; they are re-instantiated for a
natural-science framework:

- ENEM's official natural-science competency matrix: `H1-H30` and 8 competency
  areas.
- NRC / NGSS science frameworks: science practices, core ideas, crosscutting
  concepts.
- PISA science framework: explain phenomena, interpret data and evidence,
  evaluate scientific inquiry.

Accordingly the science student-capability object uses
`ScienceTaskCapabilityProfile` rather than XES's `MathTaskCapabilityProfile`.
Core fields include:

- `scientific_concept_recall`
- `phenomenon_explanation`
- `mechanism_reasoning`
- `data_evidence_interpretation`
- `model_representation_transfer`
- `scientific_inquiry_reasoning`
- `science_technology_society_reasoning`
- `quantitative_science_reasoning`
- `option_elimination`
- `hard_item_persistence`
- `guessing_tendency`
- `confidence_calibration`
- `format_discipline`

## Data boundary

The generation path may not use:

- the real answer to a test item
- the real correctness of a test item
- the official correct answer
- the ENEM total score
- item IRT difficulty or empirical difficulty

The IRT `NU_PARAM_B` parameter may be used only for the offline balanced
history/test split; it does not enter the prompt.

## Default set

- Config: `configs/enem_cn_static_english_text_plus_image_20260529.json`
  (the set of the reported runs): 44 common CN items, of which `20` are the
  calibration history and `24` are test items.
- Students: `--max_students 7200` by default, `1800` per ability band.
- Item content: the English item text from `question_text_manifest.jsonl`
  together with the cropped item image. The two manifest paths in the config
  are resolved relative to `configs/`.

The item crops are produced with `--build_page_images`, and the English item
text with:

```powershell
python static\enem\run_translate_question_images.py `
  --config_path static\enem\configs\enem_cn_static_smoke_20260528.json `
  --build_page_images `
  --run_dir static\enem\outputs\enem_cn_question_text_translation\qwen35_en_44_20260529 `
  --llm_base_url <BASE_URL> --llm_model <MODEL> --llm_api_key <API_KEY>
```

## Smoke test

```powershell
python static\enem\run_enem_static_benchmark.py --config_path static\enem\configs\enem_cn_static_smoke_20260528.json --dry_run --max_students 4 --max_questions 2 --max_concurrency 2
```

## Reported run

```powershell
python static\enem\run_enem_static_benchmark.py `
  --config_path static\enem\configs\enem_cn_static_english_text_plus_image_20260529.json `
  --max_students 7200 --ablation_mode full `
  --llm_base_url <BASE_URL> --llm_model <MODEL> --llm_api_key <API_KEY> `
  --temperature 0.2 --max_tokens 1800 --timeout_s 240 --response_format_json `
  --generation_attempts 8 --task_retry_attempts 6 --failure_rerun_rounds 6 `
  --hachimi_persona_paths <personas.jsonl>
```

`--ablation_mode` selects `full`, `without_hachimi_prior`,
`without_task_local_state`, or `without_behavior_harness`. Without
`--hachimi_persona_paths` no persona is matched. `--student_shard_index` and
`--student_shard_count` split the students across parallel processes. The
reported runs use four shards (`<shard_root>/shard_00_of_04` ...
`shard_03_of_04` as `--run_dir`), merged and evaluated with:

```powershell
python static\enem\merge_enem_shards.py `
  --config_path static\enem\configs\enem_cn_static_english_text_plus_image_20260529.json `
  --max_students 7200 --shard_count 4 `
  --shard_root <shard_root> --merged_run_dir <merged_run_dir>
```

The merged directory holds `predictions.jsonl`, `eval_rows.jsonl`,
`metrics.json`, and `shard_manifest.json`.

## Multimodal run

`--build_page_images` first generates a per-item cropped-image manifest from the
official PDF. The argument name `page_images` is retained to avoid changing the
entry point, but what is sent to the model is each item's own crop, not the full
page.

The crops are an ENEM-level cache, not run-level temporary files. By default they
are saved under:

`static/enem/cache/question_images/CN_1419_dpi150_bbox_column_crop_v1/`

For the same PDF, subject, base paper, DPI, and crop-algorithm version, later
runs reuse these images and `question_image_manifest.jsonl`. If the cache
manifest exists but item count, DPI, crop version, or image files disagree, the
program raises rather than silently rebuilding.

```powershell
python static\enem\run_enem_static_benchmark.py `
  --config_path static\enem\configs\enem_cn_static_smoke_20260528.json `
  --build_page_images `
  --max_students 20 `
  --max_questions 4 `
  --llm_base_url <BASE_URL> `
  --llm_model <MODEL> `
  --llm_api_key <API_KEY> `
  --response_format_json
```

Cropping:

- `QUESTÃO xx` coordinates are read from the PDF text layer via
  `pdftotext -bbox`.
- Standard two-column pages are cropped per left/right column.
- Full-width pages are cropped full-width to avoid truncating long stems.
- The manifest records `crop_mode`, `crop_box`, `page_number`, `column`, and
  `dpi` for auditing.

Crop invariants:

- All common CN items must produce a crop.
- Each crop box must contain its own item number.
- Each crop box must not contain another item's number.
