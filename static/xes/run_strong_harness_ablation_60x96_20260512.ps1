param(
    [int]$MaxConcurrency = 50,
    [bool]$SkipCompleted = $true,
    [string[]]$Variants = @(
        "hachimi_no_difficulty_signal",
        "hachimi_no_difficulty_signal_no_internal_signals",
        "hachimi_no_difficulty_signal_minimal_signals",
        "hachimi_no_difficulty_signal_student_capability_only",
        "hachimi_no_difficulty_signal_student_no_psych_fields",
        "hachimi_no_difficulty_signal_student_no_style_fields",
        "hachimi_no_difficulty_signal_problem_core_only",
        "hachimi_no_difficulty_signal_no_problem_justifications",
        "hachimi_no_difficulty_signal_no_problem_notes",
        "hachimi_no_difficulty_signal_no_interaction_decision",
        "hachimi_no_difficulty_signal_item_state_label_only",
        "hachimi_no_difficulty_signal_loose_constraints"
    )
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$xesRoot = Join-Path $repoRoot "xes"
$outputRoot = Join-Path $xesRoot "outputs\xes_strong_ablation_60x96_20260512"
$logRoot = Join-Path $outputRoot "_logs"
New-Item -ItemType Directory -Force -Path $outputRoot | Out-Null
New-Item -ItemType Directory -Force -Path $logRoot | Out-Null

$baseUrl = "https://ai-notebook-inspire.sii.edu.cn/ws-9dcc0e1f-80a4-4af2-bc2f-0e352e7b17e6/project-b795c114-135a-40db-b3d0-19b60f25237b/user-c6264b38-46a1-4bb6-a3a7-1db39453f6f8/vscode/a8d28302-91b1-48a6-aa64-fd7cc9ec78a7/42ee0f16-fe96-4181-9765-4e16e74567f7/proxy/9501/v1"
$targetGrade = [System.Text.Encoding]::UTF8.GetString([byte[]](0xE4,0xB8,0x89,0xE5,0xB9,0xB4,0xE7,0xBA,0xA7))

$commonArgs = @(
    "run_student_conditioned_benchmark.py",
    "--eligible_question_path", "outputs/irt_support/run_20260427_183859/eligible_questions.json",
    "--response_csv_path", "../XES3G5M/question_level/train_valid_sequences_quelevel.csv",
    "--persona_path", "../merged_students_10k.jsonl",
    "--question_path", "../XES3G5M/metadata/questions.json",
    "--target_grade", $targetGrade,
    "--max_students", "60",
    "--history_size", "30",
    "--test_size", "96",
    "--sampling_seed", "42",
    "--fixed_cohort_path", "configs/common_test_60x96_20260507.json",
    "--official_correctness_mode", "rules_only",
    "--response_persona", "first",
    "--max_thinking_steps", "12",
    "--max_concurrency", "$MaxConcurrency",
    "--llm_base_url", $baseUrl,
    "--llm_model", "qwen",
    "--llm_no_auth",
    "--llm_timeout_s", "120",
    "--llm_temperature", "0.2",
    "--llm_max_tokens", "2000",
    "--llm_response_format_json"
)

function Invoke-XesAblationRun {
    param(
        [string]$Name,
        [string]$PersonaSourceMode,
        [string]$MethodVariant,
        [string]$ResponsePersona = "first",
        [bool]$EnableDifficultyAnchorContext = $false,
        [bool]$EnableRealDifficultyBand = $false,
        [string]$InternalSignalsMode = "full",
        [string]$StudentModelFieldsMode = "full",
        [string]$ProblemProfileFieldsMode = "full",
        [string]$InteractionDecisionMode = "full",
        [string]$ItemStateFieldsMode = "full",
        [string]$ConstraintMode = "full",
        [string]$ViolationRetryMode = "off"
    )

    if ($Variants -notcontains $Name) {
        return
    }

    $variantRoot = Join-Path $outputRoot $Name
    New-Item -ItemType Directory -Force -Path $variantRoot | Out-Null
    if ($SkipCompleted) {
        $finishedRun = Get-ChildItem -Path $variantRoot -Directory -Filter "run_*" -ErrorAction SilentlyContinue |
            Where-Object { Test-Path (Join-Path $_.FullName "metrics.json") } |
            Sort-Object Name -Descending |
            Select-Object -First 1
        if ($null -ne $finishedRun) {
            Write-Host "=== SKIP ${Name}: existing metrics at $($finishedRun.FullName) ==="
            return
        }
    }

    $stdoutLog = Join-Path $logRoot "$Name.stdout.log"
    $stderrLog = Join-Path $logRoot "$Name.stderr.log"

    $args = @($commonArgs)
    $args += @(
        "--persona_source_mode", $PersonaSourceMode,
        "--method_variant", $MethodVariant,
        "--response_persona", $ResponsePersona,
        "--internal_signals_mode", $InternalSignalsMode,
        "--student_model_fields_mode", $StudentModelFieldsMode,
        "--problem_profile_fields_mode", $ProblemProfileFieldsMode,
        "--interaction_decision_mode", $InteractionDecisionMode,
        "--item_state_fields_mode", $ItemStateFieldsMode,
        "--constraint_mode", $ConstraintMode,
        "--violation_retry_mode", $ViolationRetryMode,
        "--output_root", $variantRoot
    )
    if ($EnableDifficultyAnchorContext) {
        $args += "--enable_difficulty_anchor_context"
    } else {
        $args += "--no-enable_difficulty_anchor_context"
    }
    if ($EnableRealDifficultyBand) {
        $args += "--enable_real_difficulty_band"
    } else {
        $args += "--no-enable_real_difficulty_band"
    }

    Write-Host "=== RUN $Name ==="
    $process = Start-Process -FilePath "python" -ArgumentList $args -WorkingDirectory $xesRoot -NoNewWindow -Wait -PassThru -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog
    if ($process.ExitCode -ne 0) {
        throw "Ablation run failed: $Name exit=$($process.ExitCode). See $stderrLog"
    }
}

Invoke-XesAblationRun -Name "hachimi_no_difficulty_signal" -PersonaSourceMode "xes_history_plus_hachimi" -MethodVariant "state_step"
Invoke-XesAblationRun -Name "hachimi_no_difficulty_signal_no_internal_signals" -PersonaSourceMode "xes_history_plus_hachimi" -MethodVariant "state_step" -InternalSignalsMode "none"
Invoke-XesAblationRun -Name "hachimi_no_difficulty_signal_minimal_signals" -PersonaSourceMode "xes_history_plus_hachimi" -MethodVariant "state_step" -InternalSignalsMode "minimal"
Invoke-XesAblationRun -Name "hachimi_no_difficulty_signal_student_capability_only" -PersonaSourceMode "xes_history_plus_hachimi" -MethodVariant "state_step" -StudentModelFieldsMode "capability_only"
Invoke-XesAblationRun -Name "hachimi_no_difficulty_signal_student_no_psych_fields" -PersonaSourceMode "xes_history_plus_hachimi" -MethodVariant "state_step" -StudentModelFieldsMode "no_psych_fields"
Invoke-XesAblationRun -Name "hachimi_no_difficulty_signal_student_no_style_fields" -PersonaSourceMode "xes_history_plus_hachimi" -MethodVariant "state_step" -StudentModelFieldsMode "no_style_fields"
Invoke-XesAblationRun -Name "hachimi_no_difficulty_signal_problem_core_only" -PersonaSourceMode "xes_history_plus_hachimi" -MethodVariant "state_step" -ProblemProfileFieldsMode "problem_core_only"
Invoke-XesAblationRun -Name "hachimi_no_difficulty_signal_no_problem_justifications" -PersonaSourceMode "xes_history_plus_hachimi" -MethodVariant "state_step" -ProblemProfileFieldsMode "no_problem_justifications"
Invoke-XesAblationRun -Name "hachimi_no_difficulty_signal_no_problem_notes" -PersonaSourceMode "xes_history_plus_hachimi" -MethodVariant "state_step" -ProblemProfileFieldsMode "no_problem_notes"
Invoke-XesAblationRun -Name "hachimi_no_difficulty_signal_no_interaction_decision" -PersonaSourceMode "xes_history_plus_hachimi" -MethodVariant "state_step" -InteractionDecisionMode "none"
Invoke-XesAblationRun -Name "hachimi_no_difficulty_signal_item_state_label_only" -PersonaSourceMode "xes_history_plus_hachimi" -MethodVariant "state_step" -ItemStateFieldsMode "state_label_only"
Invoke-XesAblationRun -Name "hachimi_no_difficulty_signal_loose_constraints" -PersonaSourceMode "xes_history_plus_hachimi" -MethodVariant "state_step" -ConstraintMode "loose"

Write-Host "All selected XES strong revisit runs finished."
Write-Host "Output root: $outputRoot"
