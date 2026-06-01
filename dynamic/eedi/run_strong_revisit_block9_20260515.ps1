$ErrorActionPreference = "Stop"

$root = "D:\Study\sii\MathStudent"
$python = "python"
$runner = Join-Path $root "eedi\run_eedi_experiments.py"
$evalRunner = Join-Path $root "eedi\run_detached_eval.py"
$summaryRunner = Join-Path $root "eedi\summarize_strong_revisit_1000.py"
$config = Join-Path $root "eedi\configs\run_strong_population_calibrated_test1000_20260511.json"
$smokeOutputRoot = Join-Path $root "eedi\outputs\eedi_strong_revisit_block9_smoke_20260515"
$screenOutputRoot = Join-Path $root "eedi\outputs\eedi_strong_revisit_block9_1000_20260515"

New-Item -ItemType Directory -Force -Path $smokeOutputRoot | Out-Null
New-Item -ItemType Directory -Force -Path $screenOutputRoot | Out-Null

$variants = @(
    @{
        name = "original_baseline_pc_default"
        args = @()
    },
    @{
        name = "candidate_structure_default"
        args = @("--error_blueprint_mode", "structure_only")
    },
    @{
        name = "constraint_no_specific_error_realization"
        args = @("--error_blueprint_mode", "structure_only", "--constraint_profile", "no_specific_error_realization")
    },
    @{
        name = "constraint_no_local_wrong_claim_anchor"
        args = @("--error_blueprint_mode", "structure_only", "--constraint_profile", "no_local_wrong_claim_anchor")
    },
    @{
        name = "constraint_no_commitment_style"
        args = @("--error_blueprint_mode", "structure_only", "--constraint_profile", "no_commitment_style")
    },
    @{
        name = "constraint_no_style_constraints"
        args = @("--error_blueprint_mode", "structure_only", "--constraint_profile", "no_style_constraints")
    },
    @{
        name = "constraint_minimal_length_only"
        args = @("--error_blueprint_mode", "structure_only", "--constraint_profile", "minimal_length_only")
    }
)

foreach ($variant in $variants) {
    $name = $variant.name
    $outDir = Join-Path $smokeOutputRoot $name
    New-Item -ItemType Directory -Force -Path $outDir | Out-Null

    Write-Host "==== Smoke: $name ===="
    $runArgs = @(
        $runner,
        "--config", $config,
        "--output_dir", $outDir,
        "--max_tasks", "40",
        "--skip_official_eval"
    ) + $variant.args
    & $python @runArgs

    $inputCsv = Join-Path $outDir "official_eval_input.csv"
    if (-not (Test-Path $inputCsv)) {
        throw "official_eval_input.csv not found for smoke $name"
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
        "--max_concurrency", "32"
    )
    & $python @evalArgs
}

foreach ($variant in $variants) {
    $name = $variant.name
    $outDir = Join-Path $screenOutputRoot $name
    New-Item -ItemType Directory -Force -Path $outDir | Out-Null

    Write-Host "==== Screening: $name ===="
    $runArgs = @(
        $runner,
        "--config", $config,
        "--output_dir", $outDir,
        "--skip_official_eval"
    ) + $variant.args
    & $python @runArgs

    $inputCsv = Join-Path $outDir "official_eval_input.csv"
    if (-not (Test-Path $inputCsv)) {
        throw "official_eval_input.csv not found for screening $name"
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
        "--max_concurrency", "32"
    )
    & $python @evalArgs
}

Write-Host "==== Summarizing ===="
& $python $summaryRunner --input_root $screenOutputRoot
