#!/bin/bash
# Full H1/H2 experiments with production settings
# Run this after smoke test passes

cd "$(dirname "$0")"

echo "================================================================================"
echo "Running FULL H1/H2 Experiments"
echo "================================================================================"
echo "Configuration:"
echo "  Max questions: 150"
echo "  Max personas: 80"
echo "  Max concurrency: 16"
echo "  Config: configs/run_local.json"
echo "  Frozen questions: outputs/run_20260420_014128/selected_questions.json"
echo "================================================================================"
echo ""

python run_h1_h2_experiments.py \
  --experiment both \
  --max_questions 150 \
  --max_personas 80 \
  --max_concurrency 16 \
  --config configs/run_local.json \
  --frozen_questions outputs/run_20260420_014128/selected_questions.json

echo ""
echo "================================================================================"
echo "Full experiments completed!"
echo "================================================================================"
