$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$bankConfig = "dynamic/eedi/configs/population_calibration_train200_uniform_20260511.json"
$strongConfig = "dynamic/eedi/configs/run_strong_population_calibrated_test1000_20260511.json"
$weakConfig = "dynamic/eedi/configs/run_weak_v31_population_calibrated_test1000_20260511.json"

$bankPath = "dynamic/eedi/outputs/population_calibration_train200_uniform_structural_only_20260511.jsonl"
$strongOutputDir = "dynamic/eedi/outputs/official_test_1000_strong_population_calibrated_train200k8_structural_only_20260511"
$weakOutputDir = "dynamic/eedi/outputs/official_test_1000_weak_qwen2_5_7b_v31_population_calibrated_train200k8_structural_only_20260511"

$logDir = "dynamic/eedi/outputs/population_calibrated_batch_logs_20260511"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$bankLog = Join-Path $logDir "bank.log"
$strongLog = Join-Path $logDir "strong.log"
$weakLog = Join-Path $logDir "weak.log"

if (-not $env:DASHSCOPE_API_KEY) {
    throw "DASHSCOPE_API_KEY is required for the weak v31 run."
}

if (-not (Test-Path $bankPath)) {
    python dynamic/eedi/build_population_calibration_bank.py --config $bankConfig *>&1 | Tee-Object -FilePath $bankLog
    if ($LASTEXITCODE -ne 0) {
        throw "population calibration bank build failed"
    }
}

python dynamic/eedi/run_eedi_experiments.py --config $strongConfig --output_dir $strongOutputDir *>&1 | Tee-Object -FilePath $strongLog
if ($LASTEXITCODE -ne 0) {
    throw "strong harness run failed"
}

python dynamic/eedi/run_eedi_weak_harness.py --config $weakConfig --output_dir $weakOutputDir *>&1 | Tee-Object -FilePath $weakLog
if ($LASTEXITCODE -ne 0) {
    throw "weak harness run failed"
}

Write-Output "DONE"
