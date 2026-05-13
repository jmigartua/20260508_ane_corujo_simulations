# Distance, configuration space, batch sweep

> **Status:** v0.2 — tiered configuration-space framework + staged sweep
> strategy, paired with the working implementation in
> [compare.qmd §5–§7](compare.qmd). Scope: define a single scalar that
> measures "how good is this RCWA simulation against the experiment?",
> strong enough to serve as the optimisation target for an automated
> parameter-space sweep, **and** spell out which parameters belong on
> the sweep axes vs. which should be fixed vs. which should be excluded.
>
> v0.1 → v0.2 changes: §4 fully rewritten (tiered inclusion criteria
> replacing the flat parameter table); new §4.1 (aggregation across (θ, φ)
> experimental conditions); new §4.2 (hierarchical universal-vs-per-sample
> structure); §6 replaced with the staged sweep strategy. The original
> design discussion that produced these changes is preserved verbatim
> in the project-root [DESIGN_LOG.md](../DESIGN_LOG.md).

---

## 1. The job of a distance

We want one number per simulation run. Smaller = closer to experiment. That number must:

1. **Aggregate across the spectrum** — one reflectance curve in, one scalar out.
2. **Respect experimental uncertainty** — bins where 3 repeats agree tightly should weigh more than bins where they scatter.
3. **Be insensitive to bins that don't exist** — if the experimental λ range and the simulation λ range overlap only partially, the metric should compute on the overlap, period.
4. **Mean something** — a value of "1" should have a physical interpretation, not be an arbitrary scale.
5. **Be cheap** — we will evaluate it tens of thousands of times during a sweep.

## 2. Choice — reduced chi-squared with a noise floor

$$
\boxed{\;
\chi^{2}_{\text{red}}
\;=\; \frac{1}{N - k}\,
\sum_{i=1}^{N}
\left(
\frac{R_{\text{sim}}(\lambda_i) \;-\; \langle R_{\text{exp}}(\lambda_i)\rangle}
     {\max\!\bigl(\sigma_{\bar R}(\lambda_i),\, \sigma_{\text{floor}}\bigr)}
\right)^{\!2}
\;}
$$

where, with three experimental repeats $r_1, r_2, r_3$ at wavelength $\lambda_i$:

- $\langle R_{\text{exp}}\rangle(\lambda_i) = \tfrac{1}{3} \sum_j r_j(\lambda_i)$ — sample mean
- $\sigma(\lambda_i) = \sqrt{\tfrac{1}{N_r-1} \sum_j (r_j - \langle R\rangle)^2}$ — sample std (Bessel)
- $\sigma_{\bar R}(\lambda_i) = \sigma(\lambda_i)/\sqrt{N_r}$ — **standard error of the mean** (this is what we divide by, not the per-measurement std)
- $\sigma_{\text{floor}} = 0.01$ — 1 % absolute floor (see below)
- $N$ — number of overlap points (intersection of simulation grid with experiment grid)
- $k$ — number of free parameters being optimised in the sweep (0 when scoring a fixed configuration)

### Why each piece

| Piece | Why |
|---|---|
| Squared residual | Penalises large mismatches more — desirable for sweeps because flat λ ranges shouldn't drown out narrow disagreements at the diffraction edges |
| Divide by $\sigma_{\bar R}$ | Gives the metric a physical interpretation: "how many standard errors of the mean is the simulation off, on average". $\chi^2_{\text{red}} \approx 1$ ↔ simulation consistent with experimental scatter |
| Floor at 1 % | With $N_r = 3$ repeats, the sample std is itself a noisy estimate. At bins where the three repeats happen to coincide, $\sigma$ collapses to a tiny number and a 0.001 deviation balloons into a huge $\chi^2$ contribution. The floor encodes our prior that no FTIR bin is intrinsically more precise than ~1 % absolute reflectance |
| Bessel correction | Sample std with $N_r - 1$ rather than $N_r$, because we are estimating the population std from a small sample |
| $N - k$ in the denominator | Standard reduced-χ² normalisation: when fitting $k$ parameters, the residual has $N - k$ effective degrees of freedom |

### What we do NOT do

- **No L1 / RMSE as the primary metric.** They ignore $\sigma$ — a bin where 3 repeats spread over ±5 % weighs the same as a bin where they agree to 0.2 %, even though the latter constrains the simulation 25× more tightly. We compute RMSE/MAE for human eyeballing, not for the sweep target.
- **No band weighting (yet).** A future refinement: multiply the integrand by $w(\lambda)$ to focus the sweep on the diffraction-feature band of interest. Easy to add when the band is decided.
- **No spectral-feature alignment.** When the simulation gets a diffraction-edge close-but-not-quite, χ²_red will be large. That is the *correct* behaviour for finding the right period, depth, and convention; it does mean we shouldn't expect χ²_red < 1 unless the simulation is genuinely indistinguishable from experiment.

## 3. The two observables — `R_total` and `R_det(β)`

The simulation produces both. The right one to compare with the FTIR depends on the detector geometry:

- **Hemispherical detector** (integrating sphere): every diffracted order that propagates is collected. Compare with `R_total = ΣR_m` (over propagating m).
- **Narrow-cone detector** (typical specular FTIR with collimating optics): only orders within ±β/2 of the specular direction are collected. Compare with `R_det(β)` for the right β.

The first comparison run (sample SS_12_3, θ = 30°, φ_exp = 0°, simulation t_oxide = 0.9 µm, β = 2°) already gave a very strong signal:

| Metric | R_total | R_det β = 2° |
|---|---:|---:|
| χ²_red | 749 | **137** |
| RMSE | 0.274 | **0.117** |
| MAE | 0.228 | **0.108** |
| max \|residual\| | 0.553 | **0.244** |
| Pearson r | 0.83 | **0.97** |

R_det wins by a factor of ~5× in χ²_red, ~2× in RMSE, and Pearson r jumps from 0.83 to 0.97. The FTIR detector is **clearly** aperture-limited, not hemispherical. The remaining ~6 percentage point uniform offset between ⟨R_det β=2°⟩ ≈ 0.60 and ⟨R_exp⟩ ≈ 0.54 is the residual we want the sweep to close — most likely by widening β past 2°.

> **Action item for the user:** what is the FTIR detector half-angle? That single number determines which simulation observable is the right comparison target, and therefore which χ²_red number is the truth-teller. The Tier-1 sweep over `beta_apertura` (§4) is the proxy fix until then.

## 4. Configuration space — tiered inclusion

A configuration-space dimension only earns its slot if it is (i) genuinely uncertain, (ii) measurably affects the simulation output, **and** (iii) physically meaningful — i.e. learning its best value teaches us something. By that test, the parameters governing the simulation split into four tiers.

### Tier 1 — must sweep (genuinely uncertain, large effect)

| Parameter | Why it must be in | Suggested range |
|---|---|---|
| `t_oxide` (µm) | Cr₂O₃ overlayer thickness was never measured; current run uses 0.9 µm placeholder | 0, 0.05, 0.10, 0.20, 0.30, 0.50, 0.90 |
| `beta_apertura` (°) | First comparison already showed R_det β = 2° gives Pearson 0.97 vs R_total 0.83 — this single axis carries most of the systematic offset we saw. Should be the *first* axis you sweep | 1, 2, 5, 10, 20, 30 |
| `oxide_dispersion` (categorical) | Choice between {HS / RS / phonon-aware-replacement} — see [ANALYSIS.md §4](../ANALYSIS.md). Until we know the right Cr₂O₃ k(λ), every other parameter is fitting around an unknown | 3 categorical values |

### Tier 2 — sweep with tight priors (uncertain but bounded by other knowledge)

| Parameter | Why prior, not free | Suggested range |
|---|---|---|
| `main_period` (µm) | AFM gives 12.85 ± 0.05 µm (period_fft, period_autocorr, period_p2p all within 1 %). No reason to give it more | 12.7 – 13.0 in 5 steps |
| `depth = 2·A1` (µm) | AFM gives 2.40 µm but the *sinusoidal-amplitude fit* gives 2.52 µm — sample is not perfectly sinusoidal, so the effective sinusoidal depth is genuinely uncertain. Wider prior | 2.2 – 3.4 in 5 steps |

### Tier 3 — set, don't sweep

| Parameter | Why fixed | What to do |
|---|---|---|
| `harmonics` (NA) | Convergence parameter, not a fit parameter | One-axis study at the centre point, fix at the smallest NA where R_det is stable |
| `slices` | Same | Same — likely 50 is fine |
| `theta`, `phi` (experimental setpoints) | Not knobs — they are the *conditions* under which we evaluate the simulation | Iterate over all (θ, φ) experimentally available, aggregate χ² (see §4.1) |
| `phi_sim − phi_exp` convention offset | Discrete — it's a coordinate convention, not a continuous variable | Sanity-check at {0°, 1°, 89°, 90°} once, fix |
| `ur` (≈ 1.000022) | Truly fixed for non-magnetic materials | Leave |

### Tier 4 — exclude (controversial, will absorb error and lie to you)

| Parameter | Why exclude |
|---|---|
| `R_scale` (overall calibration factor) | Adding this lets the metric soak up any uniform offset — including offsets that come from a *wrong* β or *wrong* oxide model. Including R_scale at this stage will hide which Tier-1 axis is the real culprit. Re-introduce it only after Tier 1 has converged |

### 4.1 Aggregating across (θ, φ) experimental conditions

The χ²_red defined in §2 is a per-(θ, φ) scalar. A configuration that fits one (θ, φ) but breaks another is overfitting to a slice. The right objective for the sweep is

$$
\chi^{2}_{\text{total}}(\theta_{\text{params}})
\;=\; \sum_{(\theta,\,\phi)} \chi^{2}_{\text{red}}\!\bigl(\theta,\phi;\, \theta_{\text{params}}\bigr)
$$

summed (or weighted, if some geometries are noisier than others) over all (θ, φ) available. For sample SS_12_3 there are 3 θ × 5 φ = **15** conditions. So a single configuration's score = **15 simulation runs** even before we vary anything.

If this becomes prohibitive, two relaxations:

1. Score on a **canonical subset** first (e.g. {θ = 30°, φ ∈ {0°, 45°, 90°}}: 3 conditions, the extremes of the φ axis at one θ) — still constrains the geometry but cuts cost 5×.
2. Use **summed RMSE** instead of summed χ²_red as the cheap proxy during the search, then evaluate the chosen winner at full χ²_red.

### 4.2 Universal vs. per-sample parameters (hierarchical structure)

Some Tier-1 / Tier-2 parameters are **physical or instrumental constants** that should take a single value across all 6 samples; others are **per-sample structural** properties.

| Class | Parameter | Universal across samples? |
|---|---|---|
| Instrument | `beta_apertura` | YES |
| Material | `oxide_dispersion` | YES |
| Material | `t_oxide` | DEBATABLE — same fabrication batch suggests yes; verify by fitting per-sample then checking if values cluster |
| Convention | `phi_sim − phi_exp` offset | YES (it's a coordinate convention) |
| Geometry | `main_period` | NO — sample-specific (AFM shows them clearly different) |
| Geometry | `depth` | NO — sample-specific |

A clean sweep is therefore **hierarchical**:

- **Outer loop:** universal Tier-1 params
- **Inner loop:** per-sample Tier-2 geometry, refit per sample

Naively the cost multiplies — but cleverly, per-sample inner loops re-use the same wavelength grid and only the AFM-derived geometry differs, so the bottleneck is

> *number of universal-param combinations* × *number of samples* × *number of (θ, φ)*

With 6 samples × 15 geometries × 105 universal-Tier-1 points = **9 450 runs** at ~4 min each ≈ **40 days**. Not viable as written. The factored strategy in §6 makes it tractable.

## 5. Pipeline architecture

```
                    ┌─────────────────────────────────────────────┐
                    │  sweep_driver.py / sweep.qmd                │
                    │  ──────────────────────                     │
                    │  for each universal-param combo (Tier 1):   │
                    │    for each sample:                         │
                    │      for each per-sample geometry (Tier 2): │
                    │        for each (θ, φ):                     │
                    │          1. solve_one_config(…) → AVG csv   │
                    │          2. score(AVG csv, exp_triple)      │
                    │             → χ²_red                        │
                    │        aggregate χ²_total over (θ, φ)        │
                    │      record best Tier-2 for this sample     │
                    │    aggregate across samples                 │
                    │    append row to sweep_results.csv          │
                    └─────────────────────────────────────────────┘
                              │                 │
                              ▼                 ▼
              ┌───────────────────────┐   ┌────────────────────────┐
              │ solve_one_config()    │   │ score()                │
              │ — wrapper around the  │   │ — the function from    │
              │   §5 cell of test8    │   │   compare.qmd §5       │
              │ — writes AVG csv      │   │ — pure numpy/pandas    │
              │ — returns the path    │   │ — no rcwa import       │
              └───────────────────────┘   └────────────────────────┘
                              │                 ▲
                              ▼                 │
              ┌───────────────────────┐   ┌────────────────────────┐
              │ rcwa solver (patched) │   │ data/experimental/     │
              │ — Solver.solve()      │   │ (read-only snapshot)   │
              │ — get_detected_…(β)   │   │                        │
              └───────────────────────┘   └────────────────────────┘
```

Each row of `sweep_results.csv` looks like:

```
stage, sample, theta_deg, phi_exp_deg,
period_um, depth_um, t_oxide_um, harmonics, beta_deg, phi_sim_deg, oxide_dispersion,
N, chi2_red_R, chi2_red_Rdet, chi2_total_Rdet,
RMSE_R, RMSE_Rdet, MAE_R, MAE_Rdet, pearson_r,
runtime_s, sim_csv_path, exp_csv_paths
```

That CSV **is** the configuration-space cube. Visualisation: `groupby(t_oxide)` and heatmap `chi2_total_Rdet` over (period, depth); contour the minimum; rinse-repeat for any 2-D slice. Parallel-coordinates plots for ≥ 4 axes.

## 6. Staged sweep — the factored strategy

The full Cartesian sweep is intractable (§4.2). Instead, factor by tier and stage:

| Stage | Goal | What varies | What's fixed | Conditions | Runs | Wall-clock |
|---|---|---|---|---|---|---|
| **0a** convergence | NA at which R_det stabilises | `harmonics ∈ {15, 19, 23, 27, 31, 35, 39, 51}` | centre of cube | one (θ, φ) | 8 | ~30 min |
| **0b** φ convention | Reconcile φ_sim with φ_exp | `phi_sim ∈ {0°, 1°, 89°, 90°}` | centre of cube | one (θ, φ) | 4 | ~15 min |
| **1** universal Tier-1 | Right `t_oxide`, `β`, `oxide_dispersion` | Tier 1 only | 1 sample (SS_12_3), 1 (θ, φ), nominal Tier-2 | 1 condition | 7 × 6 × 3 = **126** | ≈ 9 hours overnight |
| **2** per-sample Tier-2 | SS_12_3 best geometry | Tier 2 only | Tier 1 = Stage-1 best | all 15 (θ, φ) for SS_12_3 | 25 × 15 = **375** | ≈ 25 hours |
| **3** generalisation | Validate Tier-1 universally | Tier 2 only, per sample | Tier 1 = Stage-1 best | all 15 (θ, φ) × 5 other samples | 25 × 15 × 5 = **1 875** | ≈ 5 days (or run the 5 samples in parallel) |

**Decision points between stages:**

- After **Stage 0a/0b**: NA and convention offset committed, never touched again
- After **Stage 1**: if best χ²_total ≫ 1, *do not proceed to Stage 2*. The bottleneck is structural (wrong oxide model, β not in the swept range, profile-shape mismatch). Fix the structural problem first. This is the safety rail that prevents Stage 2 from "succeeding" by absorbing model error into geometry
- After **Stage 2**: SS_12_3 best geometry locked in. Compare with AFM-fitted geometry — if they disagree by more than the AFM uncertainty, that's a finding worth its own paragraph
- After **Stage 3**: if Tier-1 best from SS_12_3 doesn't generalise to the other samples, the universal-vs-per-sample classification in §4.2 was wrong (most likely culprit: `t_oxide` is sample-specific after all)

## 7. Search strategies, in increasing sophistication

When we are ready to build the sweep driver, we have a ladder:

1. **Grid sweep** — Cartesian product of axis values. Simple, no surprises, worst-case is just expensive. Right starting point and the one assumed in §6.
2. **Latin-hypercube sampling** — same number of evaluations, much better space coverage. Use when dimensions ≥ 4.
3. **Bayesian optimisation** (e.g. `scikit-optimize`'s `gp_minimize`) — uses χ²_total as a black box, fits a Gaussian-process surrogate, picks the next configuration that has the highest expected improvement. Excellent for ≤ 8 axes, but only after we are certain the metric is well-behaved.
4. **Local refinement** — once the grid sweep has identified a basin, run `scipy.optimize.minimize` with `Nelder-Mead` (simplex, derivative-free) starting at the grid minimum. Cheap finishing pass.

Recommended path: Stage 1 grid → if Stage 1 best is in a clear basin, Stage 2 grid + Nelder-Mead refinement → only consider Bayesian optimisation if we widen the axes after Stage 3.

## 8. Safety rails

- **Convergence trap.** Stage 0a is non-negotiable. Otherwise we will be fitting parameters to compensate for a numerical artefact.
- **Sigma floor sanity.** Today's run shows `⟨σ_eff⟩ = 0.0100` exactly = the floor — the three repeats agree to better than 1 % almost everywhere. Means the metric is currently driven by the floor, not by experimental scatter, which is fine but worth knowing. If a future sample has noisier data, σ_floor stops being binding and the metric self-adjusts.
- **NaN handling.** Any λ where the experiment is missing → drop from the sum, decrement N. The function in compare.qmd already does this via the `valid` mask.
- **Reproducibility.** Each row of `sweep_results.csv` includes the path of the simulation CSV that produced it, so any single point can be re-derived.
- **Trust no χ²_red < 1.** With $\sigma_{\text{floor}} = 0.01$ and a uniform offset of $> 0.01$, the metric is bounded below by some positive constant. If you see χ²_red < 1 during the sweep, the floor was bypassed, the experimental σ has spuriously inflated, or the experiment-side data was misread. Investigate before celebrating.

## 9. Open question (not for this turn)

The simulation φ = 89° / experiment φ = 0° convention. Resolution paths:

1. Read the rcwa source to confirm where azimuth is measured from (likely from one of the lattice vectors). Compare with the FTIR convention (likely from grating-perpendicular).
2. Sanity-check by running the simulation at a known φ — e.g. for a 1-D grating, φ_sim such that incident k lies *along* the grating direction should give a planar-thin-film answer (no diffraction); φ_sim such that k lies *perpendicular* to the grating should give maximum diffraction. Whichever of {0°, 90°, 89°, 1°} maps to "perpendicular" is the geometry Ane is using as 89°.

Stage 0b (§6) is exactly this sanity check. Once nailed down, fold the offset into a single constant in the sweep driver and stop carrying φ as an axis.

---
*v0.2 — paired with [compare.qmd](compare.qmd). Design discussion that produced this version preserved verbatim in [DESIGN_LOG.md](../DESIGN_LOG.md). Update all three files together when reasoning evolves.*
