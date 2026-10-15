#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
for file in notebooks/01_qualifying_weekend.ipynb notebooks/02_qualifying_backtest.ipynb notebooks/03_qualifying_form_ablation.ipynb; do
  if [[ -f "$file" ]]; then
    uv run jupytext --set-formats ipynb,py:percent "$file"
    uv run jupytext --to py:percent "$file"
  fi
done
printf '\nNeovim: nvim notebooks/03_qualifying_form_ablation.py\n'
printf 'Sync edits: uv run jupytext --sync notebooks/03_qualifying_form_ablation.ipynb\n'
