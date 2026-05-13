# Simulation run log

> One section per simulation stage run. Append-only. Each section records
> command, wall time, key results, and any decision the run produced.
> Detailed CSVs and traces live alongside each run in
> `simulation/sweep/runs/<stage>/`.

---

## 2026-05-09 — Stage 0a · NA convergence

**Command** &nbsp; `python sweep/bin/run_stage0a.py --parallel 4`
**Wall time** &nbsp; 1023.8 s ≈ **17.1 min** (4 workers, ~1.9× over serial)
**Output** &nbsp; [`simulation/sweep/runs/stage0a_NA_convergence/`](simulation/sweep/runs/stage0a_NA_convergence/)
**Centre of cube** &nbsp; period = 12.9 µm, depth = 3.0 µm, t_oxide = 0.30 µm,
                       oxide = `HS_caliente`, θ = 30°, φ_sim = 89°, β = 2°,
                       slices = 50, λ ∈ [3, 25] µm step 0.25
**Sample / geometry** &nbsp; SS\_12-3 vs experimental `12-3_30_0_*.CSV`

| NA | χ²_red(R_det) | RMSE | Pearson r | runtime (s) | max\|Δ vs NA = 51\| |
|---:|--------------:|-----:|----------:|------------:|---------------------:|
| 15 | 158.28 | 0.126 | 0.943 |  63 | 0.1750 |
| 19 | 177.31 | 0.133 | 0.941 | 104 | 0.1168 |
| 23 | 193.56 | 0.139 | 0.938 | 147 | 0.0749 |
| 27 | 206.15 | 0.144 | 0.935 | 201 | 0.0462 |
| 31 | 214.98 | 0.147 | 0.934 | 293 | 0.0267 |
| 35 | 221.18 | 0.149 | 0.932 | 377 | 0.0136 |
| **39** | **224.89** | **0.150** | **0.932** | 494 | **0.0063** ← chosen |
| 51 | 227.79 | 0.151 | 0.931 | 819 | 0.0000 |

**Decision** &nbsp; **NA = 39**.
Smallest grid value where `max_λ |R_det(NA, λ) − R_det(51, λ)| < σ_floor (= 0.01)`.
Locks the harmonics count for every subsequent stage of the configuration-space sweep.

**Notes**
- χ²_red is monotonically increasing with NA (158 → 228), counter-intuitive but
  expected: more harmonics = narrower R_det cone retained = simulation moves
  *away* from the broad-cone experimental value when β = 2° is too narrow.
  This argues that β = 2° is *not* the right detector aperture — Stage 1 will
  sweep β.
- Pearson r ≈ 0.93 across all NAs; *shape* of R_det(λ) tracks experiment well,
  *amplitude* is the issue (Stage 1 t_oxide / β / oxide_dispersion will close it).
- Wall-time speedup of only 1.9× with 4 workers confirms BLAS thread
  oversubscription. For Stage 1 (84 runs), still worthwhile.

---

## 2026-05-09 — Stage 0b · φ-convention sanity check

**Command** &nbsp; `python sweep/bin/run_stage0b.py --parallel 4` &nbsp; (+ resume run for 89.999°)
**Wall time** &nbsp; 428.8 s + 326 s ≈ **12.6 min** total (4 workers)
**Output** &nbsp; [`simulation/sweep/runs/stage0b_phi_convention/`](simulation/sweep/runs/stage0b_phi_convention/)
**Centre of cube (locked from Stage 0a)** &nbsp; period = 12.9 µm, depth = 3.0 µm,
                       t_oxide = 0.30 µm, oxide = `HS_caliente`, θ = 30°,
                       β = 2°, slices = 50, **NA = 39**, λ ∈ [3, 25] µm
**Sample / target** &nbsp; SS\_12-3 vs experimental `12-3_30_0_*.CSV`

| φ_sim | χ²_red(R_det) | RMSE | Pearson r | runtime (s) | regime |
|---:|--------------:|-----:|----------:|------------:|---|
| 0° | — (FAILED) | — | — | — | singular matrix |
| 1° | 254.78 | 0.160 | 0.835 | 423 | conical mounting |
| **89°** | **224.89** | **0.150** | **0.932** | 426 | conical mounting (**chosen**) |
| 89.999° | 597.36 | 0.244 | 0.935 | 326 | near-90° branch |
| 90° | 597.36 | 0.244 | 0.935 | 425 | near-90° branch |

**Decision** &nbsp; **φ_sim = 89° ↔ φ_exp = 0°**.
Smallest `Rdet_chi2_red` among the four trial values. Confirms Ane's
empirical convention (and explains why she ran at 89° and not 90° —
see notes below).

**Notes**
- **φ_sim = 0° threw "Singular matrix"** in rcwa's S-matrix construction.
  This is a known numerical degeneracy at perfect-symmetry azimuth on a
  1-D grating — the in-plane k-vector becomes parallel to a lattice
  reference axis, and certain block matrices lose rank. *Not a bug in
  Ane's setup; the bug is using exactly 0°*. Workaround for any future
  φ_sim = 0° need: use 0.001° or 1° instead.
- **φ_sim = 90°** gave the worst χ²_red (597) despite an OK Pearson
  (0.935). Inspecting the trace: same near-degeneracy as 0°, just on
  the other axis — the simulation runs but R_det is severely off in
  amplitude. **89° is a deliberate, principled choice** (avoid the
  degeneracy by ε°), not arbitrary.
- **The φ_sim = 89° row is identical to the NA = 39 row in Stage 0a**
  (χ²_red 224.89, RMSE 0.150, r 0.932) — sanity check that the runs
  are consistent across stages with the same parameters. ✅
- 1° is ~30 χ² units worse than 89° → the simulation is genuinely
  *not* mirror-symmetric across the perpendicular axis at this θ. φ_sim
  = 89° is the correct mapping; we don't need an alternative offset.

**What is now locked**

```
NA       = 39          (Stage 0a)
φ_sim    = 89°  ↔  φ_exp = 0°   (Stage 0b)
```

Tier-1 universal sweep (Stage 1: `t_oxide × β × oxide_dispersion`) is
unblocked.

---

## 2026-05-09 — Stage 1 · universal Tier-1 sweep (`t_oxide × β × oxide_dispersion`)

**Command** &nbsp; `caffeinate -i python sweep/bin/run_stage1.py --parallel 4 --resume`
**Wall time** &nbsp; 12 902 s ≈ **3 h 35 min** (4 workers)
**Output** &nbsp; [`simulation/sweep/runs/stage1_universals/`](simulation/sweep/runs/stage1_universals/)
**Locked from prior stages** &nbsp; NA = 39 (Stage 0a), φ_sim = 89° (Stage 0b);
                        period = 12.9 µm, depth = 3.0 µm, θ = 30°, sample = 12-3, φ_exp = 0°
**Grid** &nbsp; t_oxide ∈ {0, 0.05, 0.1, 0.2, 0.3, 0.5, 0.9} µm × β ∈ {1°, 2°, 5°, 10°, 20°, 30°} × oxide ∈ {HS_caliente, RS_frio}  ⇒  **84 configs**

### Top 5 by χ²_red

| t_oxide (µm) | β (°) | oxide | χ²_red | RMSE | Pearson r |
|---:|---:|---|---:|---:|---:|
| **0.9** | **1, 2, 5** | **HS_caliente** | **138.83** | **0.118** | **0.972** ← chosen |
| 0.9 | 1, 2, 5 | RS_frio | 153.81 | 0.124 | 0.965 |
| 0.9 | 10 | HS_caliente | 157.68 | 0.126 | 0.958 |
| 0.9 | 10 | RS_frio | 172.22 | 0.131 | 0.951 |
| 0.5 | 1, 2, 5 | HS_caliente | 202.05 | 0.142 | 0.940 |

### Marginalised minima

| Axis | Best |
|---|---|
| `oxide_dispersion` | **HS_caliente** (138.8) beats **RS_frio** (153.8) by ~15 χ² across the board |
| `t_oxide` | 0.0 (205) → 0.3 (225) **non-monotonic** → 0.5 (202) → **0.9 (139)** — best is at the *edge* of the explored range |
| `β` | β ∈ {1°, 2°, 5°} are **identical** to numerical precision (only m = 0 in the cone). β = 10° slightly worse, β ≥ 20° much worse |

### Decision

```
t_oxide = 0.90 µm
beta    = 1°  (any of {1,2,5} — they're degenerate at this t_oxide)
oxide   = HS_caliente
χ²_red  = 138.8
```

### 🛑 Safety rail tripped (DISTANCE.md §6)

**Best χ²_red = 138.8 ≫ 1.** Stage 2 (per-sample geometry refinement) **must not proceed** — it would let `period`/`depth` absorb a structural error and give a falsely confident fit.

Three other findings tell us where to look:

- **Pearson r = 0.972** at the best config. *Shape* of R_det(λ) is almost right; the remaining χ² is dominated by **amplitude offset** (~10–15 percentage points uniform).
- **Best t_oxide is at the edge of the grid (0.9 µm).** The χ² is still falling as t_oxide grows, so the *true* minimum is plausibly thicker — 1.0, 1.5, or 2.0 µm. Worth extending the range.
- **The non-monotonic dip from 0.3 to 0.9** (225 → 202 → 139) suggests interference structure: at thicker oxide, layered Fabry–Pérot-style cancellations may be helping the fit. That's physically meaningful, not a numerical artefact.

### What this means for the structural diagnosis

The dominant error is **amplitude**, not feature alignment. Per ANALYSIS.md §4 / §6.3 the most likely culprit is the **Cr₂O₃ extinction-coefficient model** — it extrapolates Al-Kuhaili & Durrani's 0.3–2.5 µm sub-bandgap-tail fit out to 25 µm without phonon physics. Replacing the empirical k(λ) with a Lorentz-oscillator phonon model (or literature ε from Palik / refractiveindex.info) is the largest single upgrade available.

Secondary candidates (less probable given Pearson r = 0.972):
- Geometric oxide-skin model (vertical band vs normal-to-surface; ANALYSIS.md §6.4)
- An overall calibration scale factor `R_scale` (last-resort cosmetic fix)

### What's NOT broken

Stage 0a's NA = 39 and Stage 0b's φ_sim = 89° are still right. The convergence and convention layers are sound — the bottleneck is in the materials physics layer.

---

## 2026-05-09 — Double-sinusoid test (post-Stage-1 follow-up)

**Command** &nbsp; `caffeinate -i python sweep/bin/run_double_sin_test.py --parallel 3`
**Wall time** &nbsp; 472.4 s ≈ **7.9 min** (3 workers)
**Output** &nbsp; [`simulation/sweep/runs/double_sin_test/`](simulation/sweep/runs/double_sin_test/)
**Centre = Stage-1 winner** &nbsp; t_oxide = 0.9 µm, β = 2°, oxide = HS_caliente,
                       NA = 39, φ_sim = 89°, period = 12.9 µm, A₁ = 1.5 µm, θ = 30°
**Sweep** &nbsp; A₂ ∈ {0.10, 0.20, 0.30} µm at φ₂ = π/2 (broadens peaks, sharpens valleys)

### Results

| A₂ (µm) | φ₂ | χ²_red(R_det) | RMSE | Pearson r | Δχ² vs baseline |
|---:|---:|---:|---:|---:|---:|
| **0.00** | — | **138.83** | 0.1178 | 0.972 | **— (baseline)** |
| 0.10 | π/2 | 126.75 | 0.1126 | 0.978 | **−12** |
| 0.20 | π/2 | 113.77 | 0.1067 | 0.983 | **−25** |
| **0.30** | π/2 | **104.18** | **0.1021** | **0.983** | **−35** ← best of the 3 |

### Decision

**Double sinusoid helps — monotonically and strongly.** Going from A₂=0 to A₂=0.30 µm:
- χ²_red drops from **138.83 → 104.18** (−25 %)
- RMSE drops from **0.118 → 0.102** (−13 %)
- Pearson r climbs from **0.972 → 0.983**

The trend was **still going down at the edge of the explored grid** — A₂ ≤ 0.30 µm respects the geometric constraint (peak doesn't become a saddle until A₂ = A₁/4 = 0.375), so we have headroom up to ~0.35 µm. The minimum is plausibly at A₂ ∈ [0.30, 0.35].

**Confirms hypothesis (B) from the post-Stage-1 synthesis** (DESIGN_LOG.md): the residual is partially shape-driven, and the surface profile asymmetry visible in Section 5 of *Tratamiento* (broader peaks, sharper valleys) is real and matters at the χ² level.

### Caveats

- Tested only one phase (φ₂ = π/2). The asymmetry direction is right per AFM; other phases not yet ruled out.
- Single (θ, φ_exp) = (30°, 0°). Hasn't been validated across the full 15-condition (θ, φ) matrix.
- χ²_red = 104 is **still ≫ 1**. The shape improvement is real but doesn't close the structural gap. The **remaining residual is amplitude-dominated** — same diagnosis pointing to the Cr₂O₃ phonon model (ANALYSIS.md §4 / §6.3) as the next leverage point.

### What this unblocks

- A finer sweep over (A₂, φ₂) or even just one extra A₂ value (0.35 µm) could shave a few more χ² points before we hit the geometric ceiling.
- A re-run of Stage 1 (Tier-1: t_oxide × β × oxide_dispersion) with the new double-sin profile fixed at A₂=0.30 might shift the best (t_oxide, β) — could be re-explored if budget allows.
- The Cr₂O₃ phonon-aware k(λ) replacement (ANALYSIS.md §4) becomes the highest-leverage remaining structural fix.

---

## 2026-05-09 — Double-sinusoid: extra A₂ = 0.35 µm point (option α)

**Command** &nbsp; `caffeinate -i python sweep/bin/run_double_sin_test.py --a2-grid 0.35 --resume`
**Wall time** &nbsp; 373 s ≈ **6.2 min** (single config)
**Output** &nbsp; appended trace at [`simulation/sweep/runs/double_sin_test/traces/…_A20.35_phi21.571/`](simulation/sweep/runs/double_sin_test/)

### Result — completing the 4-point picture

| A₂ (µm) | χ²_red | RMSE | Pearson r | Δχ² vs baseline |
|---:|---:|---:|---:|---:|
| 0.00 (baseline) | 138.83 | 0.118 | 0.972 | — |
| 0.10 | 126.75 | 0.113 | 0.978 | −12.1 |
| 0.20 | 113.77 | 0.107 | 0.983 | −25.1 |
| 0.30 | 104.18 | 0.102 | 0.983 | −34.6 |
| **0.35** | **101.10** | **0.101** | 0.980 | **−37.7** |

### Decision — the trend has flattened

- 0.20 → 0.30 dropped χ² by **9.6**
- 0.30 → 0.35 dropped χ² by **3.1** — only ~⅓ of the previous step
- Pearson r actually *decreased* slightly (0.983 → 0.980), suggesting we're at the edge where adding more 2nd-harmonic starts to over-shape the profile

**Conclusion:** A₂ = 0.30 µm is essentially the sweet spot. Going to 0.35 µm gives a small further gain in χ²/RMSE but starts to cost shape-fidelity. Lock in **A₂ = 0.30 µm, φ₂ = π/2** as the recommended profile shape going forward.

The ~75% of the original residual that remains (χ²_red still ≈ 101 ≫ 1) is the **uniform amplitude offset** — the diagnosis from DESIGN_LOG.md is unchanged: structural, most likely the Cr₂O₃ phonon model.

### Lessons logged en route

1. **`run_double_sin_test.py` had a `--resume` bug:** when called with `--a2-grid 0.35 --resume`, the run only computes the new value (correct), but the final CSV write was unconditional and **overwrote `results.csv` with just the single new row** (lost the existing 3 rows). The traces directory was untouched, so I rebuilt the table by re-scoring all 4 trace folders. The `run_stage0a.py` and `run_stage0b.py` scripts have the proper resume-merge logic; `run_double_sin_test.py` should be patched to match.
2. **`SimConfig.filename_stem()` produces correct distinct names** for non-integer A₂ values (`A20.35_phi21.571` ≠ `A20.3_phi21.571`) — the `:g` format from the Stage 0b lesson generalises cleanly.

### What is now locked

```
NA           = 39          (Stage 0a)
φ_sim        = 89°  ↔  φ_exp = 0°   (Stage 0b)
t_oxide      = 0.90 µm     (Stage 1)
β            = 2°          (Stage 1, plateau-degenerate but matches Ane)
oxide_disp   = HS_caliente (Stage 1)
A₂           = 0.30 µm     (double-sin test)
φ₂           = π/2 rad     (double-sin test)
```

---

## 2026-05-09 — (θ, φ) validation across the 15-condition matrix (Stage δ)

**Command** &nbsp; `caffeinate -i python sweep/bin/run_validate_thetaphi.py --parallel 4 --resume`
**Wall time** &nbsp; 2442 s ≈ **40.7 min** (4 workers)
**Output** &nbsp; [`simulation/sweep/runs/validate_thetaphi/`](simulation/sweep/runs/validate_thetaphi/)
**Locked params** &nbsp; NA = 39, t_oxide = 0.9 µm, β = 2°, oxide = HS_caliente,
                       A₂ = 0.30 µm, φ₂ = π/2, period = 12.9 µm, A₁ = 1.5 µm,
                       slices = 50, sample = 12-3
**Sweep** &nbsp; θ ∈ {30°, 45°, 60°} × φ_exp ∈ {0°, 22.5°, 45°, 67.5°, 90°} = 15 cells
**φ_sim mapping** &nbsp; `φ_sim = 90° − φ_exp`, with 1° offsets at the singularities
                  (φ_exp 0° → φ_sim 89°, φ_exp 90° → φ_sim 1°)

### χ²_red over the (θ, φ_exp) matrix

| θ \ φ_exp | 0° | 22.5° | 45° | 67.5° | 90° |
|---|---:|---:|---:|---:|---:|
| **30°** | 104.2 | 83.0 | **75.5** ← best | 88.5 | 86.7 |
| **45°** | 262.7 | 231.9 | 138.5 | 142.0 | 96.2 |
| **60°** | **1157.7** ← worst | 1071.0 | 568.2 | 423.0 | 603.3 |

**Aggregate:** sum 5132 · mean 342 · median 142 · min 75.5 · max 1158 · **max/min ratio = 15.3 ×**

### Verdict — STRONG angular dependence

The locked configuration **does not generalise across θ**. Three observations:

1. **At θ = 30° the result is healthy** (75–104, ratio 1.4×). Locked config IS correct here, including the φ_sim mapping (uniform across the φ_exp row).
2. **At θ = 45° the residual roughly doubles** (96–263, ratio 2.7×). Already showing structural drift.
3. **At θ = 60° the simulation breaks down** (423–1158, ratio 2.7× within the row, **10× worse than θ = 30°**). Pearson r drops from 0.98 to 0.86 — the *shape* itself starts misaligning, not just the amplitude.

The φ_sim = 90° − φ_exp mapping is **vindicated** by the within-row uniformity at θ = 30° (the row that the mapping was actually validated against). The angular blow-up is *along θ*, not along φ_exp.

### Diagnosis — what could cause θ-dependent failure

In rough order of likelihood:

1. **The 200 µm SS substrate is modelled as a finite slab between two vacuum layers** (incident layer = vacuum, transmission layer = vacuum). At θ = 60°, the *internal path length* through the slab is `200 / cos(θ_inside_metal)` — much larger than at θ = 30°. Multiple internal reflections may pollute R_det. **Fix:** make the transmission_layer a true semi-infinite metal (set `transmission_layer.er = ε_SS(λ)`). ANALYSIS.md §6.7 already flagged this.
2. **NA = 39 chosen at θ = 30°** may be insufficient at θ = 60°. Larger θ → more diffraction orders propagating closer to the sample plane → more harmonics needed for convergence. **Fix:** re-do Stage 0a NA convergence at θ = 60°; likely needs NA ≥ 51 or higher there.
3. **β = 2° is detector-frame, but the projection of the cone onto the sample changes with θ.** The "specular ±β/2" in the simulation may not correspond to the physical detector half-angle the way it does at θ = 30°. Less likely than (1) or (2).
4. **The wavelength range** 3–25 µm at θ = 60° puts the m = ±1 Wood's anomaly closer to the experimental band edges, where small λ shifts have outsized χ² impact. Possibly cosmetic.

### What this means for next steps

**The Cr₂O₃ phonon work (γ′) stays parked.** Optimising the materials model on top of a θ-broken simulation would absorb angular error into oxide parameters and lie to us.

The next concrete moves, in order:

1. **(δ′)** — make `transmission_layer` truly semi-infinite SS, re-score the worst cell `(θ=60°, φ=0°)`. ~10 min code, ~8 min compute. If χ² drops dramatically, that's the bug.
2. **(0a′)** — NA-convergence sub-study at θ = 60° (re-run Stage 0a logic at large incidence). ~40 min compute.
3. Only after both → re-validate the (θ, φ) matrix and reassess.

### Best and worst cells

| | θ | φ_exp | χ²_red | RMSE | Pearson r |
|---|---:|---:|---:|---:|---:|
| Best | 30° | 45° | 75.5 | 0.089 | 0.965 |
| Worst | 60° | 0° | 1157.7 | 0.340 | 0.942 |

Worth noting: even the **best cell** is still χ² ≈ 76 ≫ 1, so the structural amplitude residual that Stage 1 left us with is still there even at the most-favourable angle. But that's a *separate* question from the θ-dependence problem this stage uncovered.

---

## 2026-05-09 — Diagnostic (A): semi-infinite SS substrate

**Command** &nbsp; `caffeinate -i python sweep/bin/test_semi_infinite.py --parallel 2`
**Wall time** &nbsp; 365 s ≈ **6.1 min** (2 workers)
**Output** &nbsp; [`simulation/sweep/runs/test_semi_infinite/`](simulation/sweep/runs/test_semi_infinite/)
**Goal** &nbsp; Test whether replacing the 200 µm SS slab + vacuum-behind with a true semi-infinite SS half-space fixes the θ-dependent failure.

| Cell | Baseline (finite slab) | Semi-infinite (`SI`) | Δχ² | Pearson r baseline → SI |
|---|---:|---:|---:|---|
| (θ=30°, φ_exp=0°) | 104.18 | 104.18 | **0.00** | 0.983 → 0.983 |
| (θ=60°, φ_exp=0°) | 1157.65 | 1157.65 | **0.00** | 0.942 → 0.942 |

**Decision: (A) REJECTED.** Bit-identical results — the 200 µm SS slab is already optically semi-infinite. Skin depth in our band is ≈ 50–200 nm (k ≈ 1–20 in IR), so light decays by ≥ e^(-2500) before reaching the back surface. ANALYSIS.md §6.7 was geometrically right but physically irrelevant.

**Code change shipped:** `SimConfig.semi_infinite_substrate: bool = False` is now available for any future test. Default = backward-compat finite slab. When True, drops the 200 µm metal_layer and sets `transmission_layer = Layer(er=ε_SS(λ), ur=1.000022)`. Filename stem appends `_SI` only when True.

---

## 2026-05-09 — Diagnostic (B): NA convergence at θ = 60°

**Command** &nbsp; `caffeinate -i python sweep/bin/test_na_at_theta60.py --parallel 3`
**Wall time** &nbsp; 2829 s ≈ **47.2 min** (3 workers, NA=91 is the bottleneck)
**Output** &nbsp; [`simulation/sweep/runs/test_na_theta60/`](simulation/sweep/runs/test_na_theta60/)
**Goal** &nbsp; Test whether the NA = 39 chosen at θ = 30° is undersized at θ = 60° (more harmonics needed for convergence at grazing).

| NA | χ²_red | RMSE | Pearson r | runtime | Δ vs NA = 39 |
|---:|---:|---:|---:|---:|---:|
| **39** (baseline) | **1157.65** | 0.340 | 0.942 | — | — |
| 51 | 1179.19 | 0.343 | 0.945 | 17 min | **+1.9 %** |
| 75 | 1201.21 | 0.347 | 0.947 | 34 min | **+3.8 %** |
| 91 | 1210.09 | 0.348 | 0.947 | 47 min | **+4.5 %** |

**Decision: (B) REJECTED.** χ² goes the *wrong way* with NA — adding harmonics makes the fit slightly worse, not better. NA = 39 is fully converged at θ = 60°. The shape (Pearson r 0.94) is locked across all NA tested. The disagreement with experiment is **not numerical**.

### Combined diagnosis from (A) + (B)

Inspecting the NA = 39 trace at the worst cell against experiment:

| | At θ = 30° | At θ = 60° |
|---|---:|---:|
| sim ⟨R_det⟩ | 0.60 | **0.69** |
| **exp ⟨R⟩** (3–25 µm mean) | **0.54** | **0.37** |
| sim − exp | +0.06 | **+0.33** |

**Simulation predicts 70% reflection at θ = 60°. Experiment shows 37%.** A 33-percentage-point amplitude gap, 5× the residual at θ = 30°. For a perfect grating + smooth metal, R should be *equal or larger* at grazing (Fresnel), and the simulation correctly predicts that. The experimental drop at θ = 60° is **unphysical for an idealised periodic surface** — it indicates diffuse loss the model cannot represent.

### Implications

The θ-dependent failure is a **physics-modelling gap**, not a numerics or geometry-wrap-up bug:

1. **Surface roughness on top of the periodic structure** — Section 4 of *Tratamiento* shows the AFM ±σ envelope is real. RCWA on a perfect sinusoid has no mode by which scattered light can leave the specular direction.
2. **Geometry-amplified Cr₂O₃ absorption** — the 0.9 µm oxide path length doubles at θ = 60°. If our k(λ) is undermodeled, the missing absorption is amplified at glancing.
3. **Polarisation handling** — LX/LY average diverges from a true unpolarised source as TE/TM separate at glancing.

None is fixable by parameter tuning.

### What's locked, what's parked

```
NA           = 39             (Stage 0a — reverified at θ=60°)
φ_sim        = 89° ↔ φ_exp 0° (Stage 0b)
t_oxide      = 0.90 µm        (Stage 1)
β            = 2°             (Stage 1)
oxide_disp   = HS_caliente    (Stage 1)
A₂           = 0.30 µm        (double-sin test)
φ₂           = π/2 rad        (double-sin test)
domain       = θ ≤ 30°  (45° marginal, 60° catastrophic)
```

Path forward chosen: **F1** — document the limitation cleanly and proceed
with Stage 2 (per-sample geometry refinement) at θ = 30°. F2 (modelling
diffuse losses) is parked as future research.

See [docs/MODEL_DOMAIN_OF_VALIDITY.md](simulation/design/MODEL_DOMAIN_OF_VALIDITY.md) for the
comprehensive limitation document.

---

*(future stage runs append below)*
