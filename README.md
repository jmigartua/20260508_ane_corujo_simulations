# Ane Corujo TFM — RCWA simulations of textured stainless steel

Reproducing and extending Ane Corujo Arteche's Master's-thesis simulations:
RCWA reflectance of stainless-steel surfaces with sinusoidal microtexturing
and a thin chromium-oxide overlayer, matched against angle-resolved FTIR
measurements. The configuration-space sweep aims to find the simulation
parameters that best reproduce experiment.

## Folder map

| Path | What lives here |
|---|---|
| [`simulation/`](simulation/) | The active work — Quarto project + Python modules + scripts |
| ↳ [`simulation/lib/`](simulation/lib/) | Shared Python modules (`sweep_runner.py`, `plot_helpers.py`) |
| ↳ [`simulation/sweep/`](simulation/sweep/) | Script-driven parameter sweep — bin/, reports/, runs/ |
| ↳ [`simulation/exploratory/`](simulation/exploratory/) | Single-config interactive tools (simulate.qmd, compare.qmd, test8_plot.qmd) |
| ↳ [`simulation/design/`](simulation/design/) | Sweep design docs (`DISTANCE.md`, `SWEEP_PLAN.md`) |
| [`data/experimental/`](data/experimental/) | 321 FTIR CSVs (read-only snapshot) |
| [`data/materials/`](data/materials/) | Material refractive index / permittivity files |
| [`ane_originals/`](ane_originals/) | Ane's verbatim notebooks (read-only reference) |
| [`20260508_messages/`](20260508_messages/) | Original email archive (do not edit) |
| [`ANALYSIS.md`](ANALYSIS.md) | Project-wide analysis of Ane's setup, with caveats |
| [`DESIGN_LOG.md`](DESIGN_LOG.md) | Verbatim design discussions, decisions, why-we-chose-what |
| [`RUN_LOG.md`](RUN_LOG.md) | Simulation run history (commands, runtimes, key results) |
| [`requirements.txt`](requirements.txt) | Python deps (rcwa, numpy, scipy, matplotlib, pandas, jupyter) |
| `.venv/` | Python 3.12 virtualenv (created by `python3.12 -m venv .venv`) |

## Quick start

```bash
# activate the venv
source .venv/bin/activate

# render an exploratory analysis (loads CSVs, no RCWA)
cd simulation && quarto render exploratory/compare.qmd

# run a sweep stage in batch (RCWA in parallel)
python simulation/sweep/bin/run_stage0a.py --parallel 4

# render the matching report
quarto render simulation/sweep/reports/stage0a_report.qmd
```

## Two paradigms, one project

- **Scripts run, reports consume.** Heavy execution = Python scripts in
  `simulation/sweep/bin/` invoked from CLI (parallelisable, restartable).
  Reports in `simulation/sweep/reports/` are .qmd files that load the
  scripts' `results.csv` and render plots.
- **Exploratory single-config work** lives in `simulation/exploratory/` —
  .qmd files that drive one RCWA configuration interactively. Use these
  when iterating on a single parameter set; use the sweep when iterating
  over many.
- **Materials and experimental data** are at project level (`data/`) —
  shared inputs that any simulation pipeline (rcwa today, GRCWA / S4 /
  whatever tomorrow) would consume identically.

## More

- The sweep architecture, distance metric, and tier classification of
  parameters are in [`simulation/design/DISTANCE.md`](simulation/design/DISTANCE.md)
  and [`simulation/design/SWEEP_PLAN.md`](simulation/design/SWEEP_PLAN.md).
- The simulation's **domain of validity** — what the model can and cannot
  do, with evidence — is documented in
  [`simulation/design/MODEL_DOMAIN_OF_VALIDITY.md`](simulation/design/MODEL_DOMAIN_OF_VALIDITY.md).
  Read this before extending the model.
- The verbatim design discussions that produced those documents are in
  [`DESIGN_LOG.md`](DESIGN_LOG.md).
- Every run's command + wall time + key results land in
  [`RUN_LOG.md`](RUN_LOG.md).
