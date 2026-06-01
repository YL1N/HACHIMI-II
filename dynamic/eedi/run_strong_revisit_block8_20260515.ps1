$ErrorActionPreference = "Stop"

$root = "D:\Study\sii\MathStudent"
$python = "python"
$runner = Join-Path $root "eedi\run_eedi_experiments.py"
$evalRunner = Join-Path $root "eedi\run_detached_eval.py"
$summaryRunner = Join-Path $root "eedi\summarize_strong_revisit_1000.py"
$smokeConfig = Join-Path $root "eedi\configs\run_strong_population_calibrated_test1000_20260511.json"
$screenConfig = Join-Path $root "eedi\configs\run_strong_population_calibrated_test1000_20260511.json"
$smokeOutputRoot = Join-Path $root "eedi\outputs\eedi_strong_revisit_block8_smoke_20260515"
$screenOutputRoot = Join-Path $root "eedi\outputs\eedi_strong_revisit_block8_1000_20260515"

New-Item -ItemType Directory -Force -Path $smokeOutputRoot | Out-Null
New-Item -ItemType Directory -Force -Path $screenOutputRoot | Out-Null

$smokeVariants = @(
    @{
        name = "error_structure_only"
        args = @("--error_blueprint_mode", "structure_only")
    },
    @{
        name = "error_structure_plus_wrong_claim_seed"
        args = @("--error_blueprint_mode", "structure_plus_wrong_claim_seed")
    },
    @{
        name = "error_structure_plus_buggy_rule"
        args = @("--error_blueprint_mode", "structure_plus_buggy_rule")
    },
    @{
        name = "structure_no_mechanism"
        args = @("--error_blueprint_mode", "structure_no_mechanism")
    }
)

foreach ($variant in $smokeVariants) {
    $name = $variant.name
    $outDir = Join-Path $smokeOutputRoot $name
    New-Item -ItemType Directory -Force -Path $outDir | Out-Null

    Write-Host "==== Smoke: $name ===="
    $runArgs = @(
        $runner,
        "--config", $smokeConfig,
        "--output_dir", $outDir,
        "--max_tasks", "40",
        "--skip_official_eval"
    ) + $variant.args
    & $python @runArgs

    $inputCsv = Join-Path $outDir "official_eval_input.csv"
    if (Test-Path $inputCsv) {
        $evalOutDir = Join-Path $outDir "detached_eval_5metrics"
        New-Item -ItemType Directory -Force -Path $evalOutDir | Out-Null
        $evalArgs = @(
            $evalRunner,
            "--input_file", $inputCsv,
            "--config", $smokeConfig,
            "--output_dir", $evalOutDir,
            "--llm_base_url", "https://ai-notebook-inspire.sii.edu.cn/ws-9dcc0e1f-80a4-4af2-bc2f-0e352e7b17e6/project-b795c114-135a-40db-b3d0-19b60f25237b/user-c6264b38-46a1-4bb6-a3a7-1db39453f6f8/vscode/a8d28302-91b1-48a6-aa64-fd7cc9ec78a7/42ee0f16-fe96-4181-9765-4e16e74567f7/proxy/9501/v1",
            "--llm_model", "qwen",
            "--llm_api_key", "123",
            "--max_concurrency", "32"
        )
        & $python @evalArgs
    }
}

$screenVariants = @(
    @{
        name = "baseline_pc_default"
        args = @()
    },
    @{
        name = "error_structure_only"
        args = @("--error_blueprint_mode", "structure_only")
    },
    @{
        name = "error_structure_plus_wrong_claim_seed"
        args = @("--error_blueprint_mode", "structure_plus_wrong_claim_seed")
    },
    @{
        name = "error_structure_plus_buggy_rule"
        args = @("--error_blueprint_mode", "structure_plus_buggy_rule")
    },
    @{
        name = "structure_no_mechanism"
        args = @("--error_blueprint_mode", "structure_no_mechanism")
    }
)

foreach ($variant in $screenVariants) {
    $name = $variant.name
    $outDir = Join-Path $screenOutputRoot $name
    New-Item -ItemType Directory -Force -Path $outDir | Out-Null

    Write-Host "==== Screening: $name ===="
    $runArgs = @(
        $runner,
        "--config", $screenConfig,
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
        "--config", $screenConfig,
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
