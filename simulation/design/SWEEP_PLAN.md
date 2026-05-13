# Sweep plan — sample SS_12_3

> **Scope.** Concrete parameter grids and execution order for the
> configuration-space exploration of sample **SS_12_3** (nominal label
> 12 µm period × 3 µm depth, currently simulated by [test8.qmd](../test8.qmd)).
>
> **Foundation.** This plan is the SS_12_3-specific instantiation of the staged
> strategy in [DISTANCE.md §6](../DISTANCE.md). The inclusion criteria (Tier 1 /
> Tier 2 / Tier 3 / Tier 4) are spelled out in
> [DISTANCE.md §4](../DISTANCE.md). The reasoning is preserved verbatim in
> [DESIGN_LOG.md](../../DESIGN_LOG.md).
>
> **Code.** Every stage qmd imports [sweep_runner.py](sweep_runner.py) — one
> module, three functions (`run_one_config`, `score`, `solve_one`).

## Anchor — the centre of the cube

All stages share these settings unless noted otherwise:

| | Value | Source |
|---|---|---|
| Sample | `12-3` (nominal 12 µm × 3 µm) | Ane's test8.qmd |
| Sinusoid period | 12.9 µm | test8.qmd `periods = [12.90]` |
| Sinusoid amplitude | A = 1.5 µm  →  depth = 3.0 µm | test8.qmd `A1 = 3.00/2` |
| `theta_deg` (incidence) | 30° | test8.qmd `angles = np.arange(30, 40, 10)` |
| `phi_sim_deg` (azimuth) | 89° (≡ φ_exp = 0° per Ane) | test8.qmd, to be ratified by Stage 0b |
| `slices` (z-discretisation) | 50 | test8.qmd |
| `wavelengths_um` | `np.arange(3, 25, 0.25)` (88 points) | extended per recent edit |
| `beta_apertura` | 2° (placeholder; actual FTIR NA unknown) | first comparison run |
| `oxide_dispersion` | `HS_caliente` (Al-Kuhaili HS film) | Ane's `datos_cromo` parameters |
| `t_oxide_um` | 0.30 µm (mid-range first-pass) | per Tier-1 ladder, see Stage 1 |
| Per-run cost | ≈ 4–5 minutes (88 λ × 2 pol × 35 NA × 51 layers) | measured |

The χ² target is summed (or canonical-subset summed) across (θ, φ) experimental
conditions per [DISTANCE.md §4.1](../DISTANCE.md). The single-run scalar lives
in `sweep_runner.score(...)["Rdet_chi2_red"]`.

## Stage 0a — NA convergence

> **Goal.** Find the smallest harmonics count NA at which `R_det(λ)` is stable to
> better than the experimental σ floor (1 %) across the full λ range. Lock that
> NA for every subsequent stage. **Without this, every other axis of the sweep
> would absorb a numerical artefact.**

| Param | Values |
|---|---|
| `harmonics` | **15, 19, 23, 27, 31, 35, 39, 51** (8 odd values) |
| Everything else | anchor (centre of cube) |
| (θ, φ) | one point — (30°, 0°) |

**Runs:** 8.  **Wall time:** ≈ 30 min on this machine.
**Decision:** smallest NA where `max_λ |R_det(NA, λ) − R_det(51, λ)| < 0.01`.
Likely NA = 31 or 35 (Ane's note in the original notebook said *"a partir de 27;
pero mejor usar 31"*).

Outputs: `simulation/sweep/results/stage0/AVG_*.csv` (8 files), and one row per
NA in `stage0_results.csv`.

**Driver.** [stage0_convergence.qmd](stage0_convergence.qmd).

## Stage 0b — φ-convention sanity check

> **Goal.** Confirm Ane's empirical claim that `phi_sim = 89° ≡ phi_exp = 0°`.
> If false, every χ² so far has been computed against the wrong experimental
> file.

| Param | Values |
|---|---|
| `phi_sim_deg` | **0°, 1°, 89°, 90°** |
| `harmonics` | the value chosen by Stage 0a |
| Everything else | anchor |
| (θ, φ_exp) | (30°, 0°) for all 4 runs |

**Runs:** 4.  **Wall time:** ≈ 15 min.
**Decision:** the φ_sim that minimises `Rdet_chi2_red` against the φ_exp = 0°
experimental triple. Lock that as the "φ_sim ≡ φ_exp = 0°" mapping.
Validation: spot-check by running the same φ_sim against `12-3_30_90_*.CSV`
(which is φ_exp = 90°) — it should be a *bad* match.

Driver: `stage0b_phi_convention.qmd` (to add — short, ≈ 4 cells).

## Stage 1 — universal Tier-1 (`t_oxide` × `β` × `oxide_dispersion`)

> **Goal.** Find the universal triple that best fits the spectrum. These are
> instrument / material constants; one value per triple is meant to fit *all*
> samples and *all* (θ, φ).

| Param | Values |
|---|---|
| `t_oxide_um` | **0, 0.05, 0.10, 0.20, 0.30, 0.50, 0.90** (7 values) |
| `beta_deg` | **1, 2, 5, 10, 20, 30** (6 values) |
| `oxide_dispersion` | **HS_caliente, RS_frio** (2 values; phonon-aware model not yet implemented — see [ANALYSIS.md §4](../../ANALYSIS.md)) |
| `harmonics` | locked from Stage 0a |
| `phi_sim_deg` | locked from Stage 0b |
| Everything else | anchor |
| (θ, φ_exp) | one well-behaved point — (30°, 0°) |

**Runs:** 7 × 6 × 2 = **84**.  **Wall time:** ≈ 6 hours.
> Why one (θ, φ) here, not all 15? Because the universal axes are heavily
> constrained by the long-λ (single-order) end of the spectrum, where (θ, φ)
> matters less. Extending to all 15 multiplies cost 15× for marginal gain.
> Validation against other (θ, φ) happens in Stage 2.

**Decision:** the `(t_oxide, β, oxide_dispersion)` triple with the lowest
`Rdet_chi2_red`. **Safety rail (DISTANCE.md §6):** if the best χ²_red is
≫ 1, *do not proceed to Stage 2*. The bottleneck is structural (most likely the
Cr₂O₃ phonon model — replacing the sub-bandgap-tail extrapolation with
literature ε(λ) is the next move).

Driver: `stage1_tier1.qmd` (to write after Stage 0 results land).

## Stage 2 — per-sample Tier-2 (`period` × `depth`)

> **Goal.** Refine SS_12_3's grating geometry under the locked Stage-1
> universals. Aggregate χ² across all 15 (θ, φ) so we are not overfitting
> a slice.

| Param | Values |
|---|---|
| `period_um` | **12.7, 12.8, 12.9, 13.0, 13.1** (5 values, ±1 % around test8 nominal) |
| `A_um` (so depth = 2 A) | **1.10, 1.30, 1.50, 1.70, 1.90** (depths 2.2 – 3.8 µm) |
| Stage-1 universals | locked |
| (θ, φ_exp) | **all 15 = {30°, 45°, 60°} × {0°, 22.5°, 45°, 67.5°, 90°}** |

**Runs per (θ, φ):** 5 × 5 = 25 simulations.
**Total runs:** 25 × 15 = **375**.  **Wall time:** ≈ 25 hours.

> **Cost-saver, if 25 hours is too much:** evaluate on a canonical subset
> first — {θ = 30°, φ ∈ {0°, 45°, 90°}} = 3 conditions, 75 runs, ~5 hours.
> Confirms the geometry without overfitting one slice. Then evaluate the
> chosen winner on all 15 conditions for the publication-quality final number.

**Decision:** the `(period, depth)` pair minimising `sum_{θ,φ} chi²_red`.
Compare with AFM-fitted geometry (period_fft = 12.85 µm, depth = 2.40 µm
from `summary_report.csv`); a discrepancy beyond AFM uncertainty is itself
a finding.

Driver: `stage2_tier2.qmd` (later).

## Stage 3 — generalisation across the other 5 samples

> **Goal.** Validate that the Stage-1 universal triple actually generalises.
> Refit Tier-2 per sample under locked universals.

For each of the 5 other samples (6-1, 6-3, 12-1, 18-1, 18-3):

- 5 × 5 = 25 (period, depth) per sample
- 15 (θ, φ) conditions per sample
- = 375 runs/sample → 1 875 runs total

**Wall time:** ≈ 5 days serial, or run the 5 samples in parallel.

> **Diagnostic value.** If Stage-1 universals do NOT generalise (some samples
> need a different t_oxide or β), then the universal-vs-per-sample
> classification in DISTANCE.md §4.2 was wrong — most likely culprit is
> `t_oxide` actually varying per sample (different oxidation history). That's
> a real finding, not a sweep failure.

Driver: `stage3_generalisation.qmd` (later).

## Output schema

Each stage qmd writes a `stageX_results.csv` with one row per simulation and
the schema from `sweep_runner.run_one_config(...)`:

```
period_um, A_um, t_oxide_um, oxide_dispersion,
theta_deg, phi_sim_deg, harmonics, slices, beta_deg,
lambda_min_um, lambda_max_um, n_lambda,
sample, theta_exp_deg, phi_exp_deg,
exp_files, n_overlap,
R_N, R_chi2_red, R_RMSE, R_MAE, R_max_abs, R_pearson_r, R_mean_sigma,
Rdet_N, Rdet_chi2_red, Rdet_RMSE, Rdet_MAE, Rdet_max_abs, Rdet_pearson_r, Rdet_mean_sigma,
runtime_s, sim_csv
```

This is the configuration-space cube the user described — one row per point,
filtered/grouped/heatmapped per analysis question.

---
*Update this file when stage decisions land (e.g. "Stage 0a: NA = 31 confirmed at max-Δ = 0.004").*
