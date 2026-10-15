# F1LAB — Notebook workflow: local Neovim first, Kaggle optionally

## Recommended workflow: Jupytext + Neovim + local Jupyter kernel

This requires no GPU. FastF1 session caching is local and already configured.

```bash
cd ~/Documents/projects/F1LAB
uv add --dev jupytext pynvim jupyter-client
uv run bash scripts/make_nvim_pairs.sh
nvim notebooks/03_qualifying_form_ablation.py
```

`# %%` begins a code cell, `# %% [markdown]` begins a Markdown cell. This is a **real notebook** stored in a Git-friendly `.py` format. See https://jupytext.readthedocs.io/en/latest/formats-scripts.html .

Notebook 03 has been executed against the real mixed 2022–2025 benchmark.
Its versioned `.py`/`.ipynb` pair is under `notebooks/`; the executed copy and
`mae_validation_test.png` are local ignored artifacts under
`data/processed/qualifying_ablation/`. Rebuild the paired notebook with
`.venv/bin/jupytext --sync notebooks/03_qualifying_form_ablation.ipynb` after
editing its text source. Run the CLI experiment in `ML_EVALUATION.md` first so
the notebook can load its metric tables. The notebook renders those saved
tables; it does not refit models itself.

If you want the interactive outputs right away **without configuring plugins**:

```bash
uv run jupyter lab
```

Open `notebooks/03_qualifying_form_ablation.ipynb` in the browser. The `.py` source is still editable from Neovim. Before switching between the two editors, save and run:

```bash
uv run jupytext --sync notebooks/03_qualifying_form_ablation.ipynb
```

Avoid editing the `.py` and `.ipynb` simultaneously without synchronization.

## Run cells directly *inside* Neovim (optional)

Molten supports evaluating selected code through a Jupyter kernel. It requires Neovim Python provider, a Python Jupyter kernel and plugin setup.

```bash
uv run python -m ipykernel install --user --name f1lab --display-name 'Python (F1LAB)'
```

With **lazy.nvim**, a minimal plugin declaration in your own Lua plugin config looks like:

```lua
{
  "benlubas/molten-nvim",
  build = ":UpdateRemotePlugins",
  init = function()
    vim.g.molten_output_win_max_height = 20
  end,
}
```

Set `vim.g.python3_host_prog` to your F1LAB `.venv/bin/python` before registering remote plugins (if you use another Python provider, install `pynvim` there instead). Run `:UpdateRemotePlugins`, restart Neovim, then `:MoltenInit f1lab`. Visual-select code between `# %%` lines and run `:MoltenEvaluateVisual`; use `:MoltenShowOutput` to view text output. Plot/image rendering requires additional terminal and image plugins.

For a more comprehensive editing setup with Markdown and LSP support, see https://github.com/benlubas/molten-nvim/blob/main/docs/Notebook-Setup.md ; this combines **Molten + Quarto + Jupytext + image.nvim**. You can adopt it later; it is not required to run Sprint 3.

## Hosted Kaggle (alternative, not the default)

Kaggle Notebooks can run the analysis on CPU; no GPU is needed for Ridge or LightGBM on this dataset. Open a notebook on Kaggle, enable **Internet** in notebook settings for GitHub / FastF1 ingestion, and in the first notebook cell:

```python
!git clone --branch feat/foundation --single-branch https://github.com/JedidiAymen/F1LAB.git /kaggle/working/F1LAB
!pip -q install fastf1 pandas pyarrow lightgbm scikit-learn matplotlib scipy jupyterlab

import os, sys
os.chdir('/kaggle/working/F1LAB')
sys.path.insert(0, '/kaggle/working/F1LAB/src')
```

Then execute the ingestion / ablation from notebook cells using `!python -m ...` or import functions. You must copy updated files into Kaggle (or push to GitHub first), and store exported `.parquet` as a Kaggle dataset or download it: Kaggle working-directory files and FastF1 cache are not a substitute for your local persistent data warehouse.

Kaggle documents package installs with Internet enabled: https://www.kaggle.com/docs/notebooks .

## What to keep in Git

Commit notebook source and code; normally omit `.ipynb_checkpoints/`, `data/cache/`, `data/processed/`, and rendered plots. Prefer deterministic CLI commands for training and keep notebooks for diagnostics and explanations.
