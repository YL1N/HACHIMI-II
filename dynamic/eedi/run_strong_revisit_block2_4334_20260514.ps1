$ErrorActionPreference = "Stop"

$root = "D:\Study\sii\MathStudent"
$python = "python"
$runner = Join-Path $root "eedi\run_eedi_experiments.py"
$evalRunner = Join-Path $root "eedi\run_detached_eval.py"
$summaryRunner = Join-Path $root "eedi\summarize_strong_revisit_1000.py"
$config = Join-Path $root "eedi\configs\run_strong_population_calibrated_full4334_20260511.json"
$baseOutputRoot = Join-Path $root "eedi\outputs\eedi_strong_revisit_block2_4334_20260514"

New-Item -ItemType Directory -Force -Path $baseOutputRoot | Out-Null

$variants = @(
    @{
        name = "baseline_pc_default"
        args = @()
    },
    @{
        name = "student_behavioral_only"
        args = @("--student_context_profile_mode", "behavioral_only")
    },
    @{
        name = "tutor_core_only"
        args = @("--tutor_turn_profile_mode", "core")
    },
    @{
        name = "interaction_transition_core_only"
        args = @("--interaction_state_mode", "core", "--transition_prediction_mode", "core")
    },
    @{
        name = "error_structure_only"
        args = @("--error_blueprint_mode", "structure_only")
    },
    @{
        name = "lean_state_stack"
        args = @(
            "--student_context_profile_mode", "behavioral_only",
            "--tutor_turn_profile_mode", "core",
            "--interaction_state_mode", "core",
            "--transition_prediction_mode", "core",
            "--error_blueprint_mode", "structure_only"
        )
    }
)

foreach ($variant in $variants) {
    $name = $variant.name
    $outDir = Join-Path $baseOutputRoot $name
    New-Item -ItemType Directory -Force -Path $outDir | Out-Null

    Write-Host "==== Running $name ===="
    $runArgs = @(
        $runner,
        "--config", $config,
        "--output_dir", $outDir,
        "--skip_official_eval"
    ) + $variant.args
    & $python @runArgs

    $inputCsv = Join-Path $outDir "official_eval_input.csv"
    if (-not (Test-Path $inputCsv)) {
        throw "official_eval_input.csv not found for $name"
    }

    $evalOutDir = Join-Path $outDir "detached_eval_5metrics"
    New-Item -ItemType Directory -Force -Path $evalOutDir | Out-Null

    $evalArgs = @(
        $evalRunner,
        "--input_file", $inputCsv,
        "--config", $config,
        "--output_dir", $evalOutDir,
        "--llm_base_url", "https://ai-notebook-inspire.sii.edu.cn/ws-9dcc0e1f-80a4-4af2-bc2f-0e352e7b17e6/project-b795c114-135a-40db-b3d0-19b60f25237b/user-c6264b38-46a1-4bb6-a3a7-1db39453f6f8/vscode/a8d28302-91b1-48a6-aa64-fd7cc9ec78a7/42ee0f16-fe96-4181-9765-4e16e74567f7/proxy/9501/v1",
        "--llm_model", "qwen",
        "--llm_api_key", "123",
        "--max_concurrency", "50"
    )
    & $python @evalArgs
}

Write-Host "==== Summarizing ===="
& $python $summaryRunner --input_root $baseOutputRoot
