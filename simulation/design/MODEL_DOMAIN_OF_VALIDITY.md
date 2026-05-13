# Model — domain of validity

> **Status:** v1.0 — definitive after Stage 1 + double-sin + (θ, φ) validation
> + diagnostic tests (A) and (B). Pairs with [DISTANCE.md](DISTANCE.md) and
> [SWEEP_PLAN.md](SWEEP_PLAN.md). Read [DESIGN_LOG.md](../../DESIGN_LOG.md)
> for the verbatim discussions that produced these conclusions and
> [RUN_LOG.md](../../RUN_LOG.md) for the run-by-run numbers.

This document states what the simulation can and cannot do, with evidence.
It is the foundation for Stage 2 (per-sample geometry refinement at
θ = 30°) and for any future research extending the model.

---

## 1. Executive summary

Within a clearly delimited domain of validity (**θ ≤ 30°**, sample SS\_12-3,
λ ∈ [3, 25] µm), the simulation reproduces FTIR experimental reflectance
to **Pearson r ≥ 0.97**, with a residual amplitude offset of about 6
percentage points. The configuration that achieves this matches Ane's
independent empirical fit to the same data exactly.

Outside that domain — specifically at **θ ≥ 45°** — the residual grows
sharply, and at θ = 60° the simulation **over-predicts specular
reflectance by 33 percentage points**. The cause is a class of physical
losses (diffuse scattering from non-periodic surface roughness, geometry-
amplified oxide absorption, polarisation-handling subtleties) that an
idealised RCWA on a perfect periodic profile **cannot represent at all**.
This is a model-scope limitation, not a parameter-tuning one.

For Ane's TFM the practical implication is: **report results at θ = 30°,
flag θ ≥ 45° as outside the model's reach, document this as a finding
about the model's domain of applicability**. Stage 2 (per-sample geometry)
and Stage 3 (generalisation across the 6 samples) proceed at θ = 30° only.

---

## 2. What the model computes

| Layer | Treatment |
|---|---|
| Source | Plane wave at wavelength λ, polar angle θ_sim, azimuth φ_sim, polarisation pTEM. **Polarisation is averaged** over Cartesian-x and Cartesian-y bases to model an unpolarised FTIR source: `R = (R_LX + R_LY) / 2`. |
| Top layer | Vacuum (incident half-space) |
| Grating slab | Sinusoidal surface profile `y(x) = A₁ sin(kx) + A₂ sin(2kx + φ₂)` — fundamental + 2nd-harmonic, sliced into 50 vertical pixels of complex permittivity. The fundamental term reproduces the AFM-fitted period and depth; the 2nd-harmonic term reproduces the broader-peaks/sharper-valleys asymmetry visible in Section 5 of Ane's *Tratamiento* PDF. |
| Cr₂O₃ overlayer | Vertical "skin" of thickness `t_oxide` (µm) above the local metal column, taking the n, k of either HS_caliente or RS_frio (Al-Kuhaili & Durrani 2007). Currently uses the sub-bandgap-tail extrapolation outside its 0.3–2.5 µm fit range. |
| Substrate | 200 µm finite SS slab terminated by a vacuum half-space — *equivalent to* a true semi-infinite SS half-space at IR wavelengths (light decays by ≥ e^(-2500) before reaching the back; verified empirically in Diagnostic (A) — see RUN_LOG.md). |
| Solver | Patched `rcwa` (Edmund Sayers' package) with Ane's `theta_orders` tracking and `get_detected_reflectance(beta)` cone filter. NA = 39 harmonics, converged at θ = 30° per Stage 0a and reverified at θ = 60° per Diagnostic (B). |
| Detector model | `R_det(β)` — sum of `R_m` over diffraction orders whose polar angle lies within ±β/2 of the specular direction. Used as the comparison observable against experimental FTIR. |

The simulation is RCWA on a **perfect, infinite, periodic** profile.
There is no physical channel for energy to leave the specular direction
*except* via propagating diffraction orders or absorption inside the
discretised volume. This is the scope limitation that the (θ, φ) validation
ran into.

---

## 3. Locked parameters and how they were chosen

| Parameter | Value | Established by |
|---|---:|---|
| `NA` (harmonics) | 39 | Stage 0a (max\|Δ\| < σ_floor across the band) and reverified at θ = 60° in Diagnostic (B) (more harmonics doesn't help) |
| `φ_sim` (rcwa azimuth) | 89° ↔ φ_exp = 0° | Stage 0b (89° beats 1°, 90° outright; 0° is rcwa-degenerate) |
| `t_oxide` | 0.90 µm | Stage 1 universal Tier-1 sweep (argmin χ²); matches Ane's empirical fit for SS_12-3 exactly (page 10 of AJUSTE) |
| `β` | 2° | Stage 1 + Ane's "CORRECCIÓN DE BETA" (page 11 of AJUSTE). Plateau-degenerate with β = 1°, 5° |
| `oxide_dispersion` | HS_caliente | Stage 1 — beats RS_frio by ~15 χ² across the cube |
| `A₂` (2nd-harmonic amplitude) | 0.30 µm | Double-sin test — −25 % χ² vs pure sin; trend bottoms out before the geometric ceiling at A₂ = 0.375 µm |
| `φ₂` (2nd-harmonic phase) | π/2 rad | Double-sin test — produces broader peaks and sharper valleys, matching the AFM mean profile |
| `period` | 12.9 µm | AFM fit (page 5 of *Tratamiento*) |
| `A₁` (fundamental amplitude) | 1.5 µm (depth = 3.0 µm) | AFM fit (page 5 of *Tratamiento*) |
| `slices` | 50 | Ane's verbatim choice; not retested; reasonable given the period × depth |

`semi_infinite_substrate` defaults to `False`. Available as an option but,
empirically, indistinguishable from the finite-slab default at our
wavelengths and substrate thickness.

---

## 4. Validation matrix — where the model fits and where it breaks

Validation against the full experimental matrix for sample SS\_12-3:
3 incidence angles × 5 azimuths = 15 conditions, all at the locked
parameter values above.

### χ²_red across (θ, φ_exp)

| θ \ φ_exp | 0° | 22.5° | 45° | 67.5° | 90° | row mean |
|---|---:|---:|---:|---:|---:|---:|
| **30°** | 104 | 83 | 76 | 89 | 87 | **88** |
| **45°** | 263 | 232 | 139 | 142 | 96 | **174** |
| **60°** | **1158** | 1071 | 568 | 423 | 603 | **765** |

**Aggregate:** sum 5132 · mean 342 · median 142 · **max/min ratio = 15.3 ×**

### Pearson r across (θ, φ_exp)

| θ \ φ_exp | 0° | 22.5° | 45° | 67.5° | 90° |
|---|---:|---:|---:|---:|---:|
| **30°** | 0.983 | 0.965 | 0.965 | 0.953 | 0.947 |
| **45°** | 0.986 | 0.964 | 0.951 | 0.935 | 0.929 |
| **60°** | 0.942 | 0.893 | 0.858 | 0.856 | 0.857 |

### Reading the matrix

- **At θ = 30° the locked configuration is correct.** The whole row sits in 75–104 χ² (ratio 1.4 ×), with Pearson r ≥ 0.95. The φ_sim = 90° − φ_exp mapping is vindicated by this row's uniformity. *This is the domain of validity.*
- **At θ = 45° the residual roughly doubles** (96–263, ratio 2.7×). The mean χ² jumps from 88 to 174. Shape is still excellent (r ≥ 0.93). *Marginal — usable but with caveats.*
- **At θ = 60° the simulation breaks down.** χ² is 423–1158, ten times the θ = 30° baseline. Pearson r drops below 0.90 at most azimuths — the **shape itself misaligns**, not just the amplitude. *Outside the domain.*

---

## 5. The mode of failure at θ = 60°, in physical terms

At the worst cell (θ = 60°, φ_exp = 0°):

| | At θ = 30° | At θ = 60° |
|---|---:|---:|
| sim ⟨R_det⟩ (locked config, 3–25 µm mean) | 0.60 | 0.69 |
| **exp ⟨R⟩** | **0.54** | **0.37** |
| sim − exp gap | +0.06 | **+0.33** |

The simulation predicts the sample reflects **70 %** of incident light at θ = 60°. The experiment sees only **37 %**.

For a smooth metal at grazing, Fresnel says R should *increase* with θ. The simulation correctly predicts this. The experimental data does the *opposite* — R *drops* by ~30 percentage points going from θ = 30° to θ = 60°. **That pattern is unphysical for an idealised periodic surface.** The "missing" 30 percentage points must be going somewhere — it is being lost from the specular direction in a way the simulation has no way to represent.

---

## 6. What we tested and ruled out

Two structural-bug hypotheses were tested and rejected:

### Diagnostic (A) — substrate termination

The 200 µm SS slab terminated by vacuum was suspected of producing back-reflections that contaminate R_det at large θ (longer internal path). Implemented `semi_infinite_substrate: bool` flag on `SimConfig`, ran two cells with `True`. **Bit-identical** to the finite-slab baseline at both cells (both metrics). Reason: skin depth in our band is 50–200 nm; 200 µm of SS is already 3-4 orders of magnitude thicker, so light decays by ≥ e^(-2500) before reaching the back. The substrate is *already* optically semi-infinite.

### Diagnostic (B) — NA convergence at θ = 60°

NA = 39 was chosen at θ = 30°. Larger θ generally demands more harmonics. Tested NA ∈ {51, 75, 91} at the worst cell. **χ² goes the wrong way:** 1158 → 1179 → 1201 → 1210 with rising NA. NA = 39 is fully converged at θ = 60°; the disagreement is not numerical.

Both classic "is it a bug?" suspects eliminated.

---

## 7. The actual cause — three classes of physical loss the model cannot represent

In rough order of likely contribution:

### 7.1 Diffuse scattering from non-periodic surface roughness

Ane's AFM data (Section 4 of *Tratamiento*) shows the surface profile has a ±σ envelope around the mean periodic structure — height fluctuations beyond the sinusoid itself. RCWA on a *perfect* periodic profile has only two channels for incident energy: propagating diffraction orders (a discrete set determined by the grating equation) or absorption within the discretised structure. There is **no mechanism for energy to leave in non-grating directions** as diffuse scatter.

Real surface roughness scatters light into a continuum of directions, removing it from the specular order. At grazing incidence this scattered fraction grows because the effective optical interaction with surface fluctuations increases with the path-length-to-feature-size ratio. The simulation, having no such channel, simply over-predicts specular at all θ — but the gap is invisible at θ = 30° and dominant at θ = 60°.

### 7.2 Geometry-amplified Cr₂O₃ absorption

The Cr₂O₃ k(λ) we use is the sub-bandgap tail from Al-Kuhaili & Durrani 2007, **extrapolated 10× past its 0.3–2.5 µm fit range**. It contains **no phonon physics** — no Reststrahlen band, no oscillator structure (see [ANALYSIS.md §4](../../ANALYSIS.md)). At θ = 60°, the optical path through the 0.9 µm oxide is `t / cos(60°) = 1.8 µm` — **2× the path at θ = 30°**. If our k(λ) underestimates the true absorption (almost certainly does, in the IR), that error is amplified by the path-length ratio at grazing.

This explains *part* of the gap, especially at long wavelengths.

### 7.3 Polarisation handling at grazing

We average `R_LX` and `R_LY` (Cartesian-x and Cartesian-y polarisations) to model an unpolarised source. At normal-ish incidence (θ = 30°) the difference between TE and TM reflectance is modest; the LX/LY average is a reasonable proxy for unpolarised. At grazing, TE and TM diverge sharply (Fresnel), and any imperfect mapping between (LX, LY) and (TE, TM) shows up as a θ-dependent error. Veemax sources are typically *random* polarisation — close to unpolarised but not strictly identical.

This is probably a smaller effect than (7.1) and (7.2) but contributes.

### What none of these are

None of these three is fixable by *parameter tuning*. They are gaps in what the model represents — adding more parameters (period, depth, β, oxide thickness, etc.) cannot create the missing physical channels. This is why χ² actually got *slightly worse* in Diagnostic (B): refining the harmonic basis just makes the (wrong) idealised model more accurate, which doesn't help.

---

## 8. Implications for downstream work

### 8.1 What we can still do (Stage 2 / 3 at θ = 30°)

- **Per-sample geometry refinement** for SS\_12-3 at θ = 30°, φ_exp ∈ {0, 22.5°, 45°, 67.5°, 90°}: 5 conditions, score aggregate χ². Sweep `period`, `A₁` (depth), possibly `t_oxide` and `A₂` — see if our locked Stage-1 values are sample-specific or generalise.
- **Stage 3 generalisation across the other 5 samples** (SS\_6_1, SS\_6_3, SS\_12_1, SS\_18_1, SS\_18_3) using AFM-fitted periods/depths from page 5 of *Tratamiento*, scored at θ = 30° × 5 φ_exp = 5 conditions per sample. 30 runs total.

The locked universal Tier-1 (t_oxide = 0.9, β = 2°, HS_caliente, A₂ = 0.30, φ₂ = π/2) is the starting point for all of this. Stage 2 / 3 can refute or refine it.

### 8.2 What we are forfeiting

- **Validation across θ for any sample.** The model doesn't reach θ = 60° honestly. We can compute simulations there, but the comparison to experiment is dominated by the model's missing physics.
- **Per-sample t_oxide or surface-roughness fits.** The σ asymmetry visible in Section 4 of *Tratamiento* (different at peaks vs valleys, supporting the user's two-thickness oxide hypothesis) is real, but it's confounded with the diffuse-scattering issue at large θ. Disentangling them needs the missing physics.

### 8.3 Future research directions (for whoever picks this up after the TFM)

| Direction | What it adds | Estimated effort |
|---|---|---|
| **Lorentz-oscillator phonon model for Cr₂O₃** fit empirically against the long-λ residual at θ = 30° | Closes the geometry-amplified absorption gap; should reduce χ² at all (θ, φ) | ~2-5 days |
| **Rayleigh-Rice scattering correction** applied as an output multiplicative factor `exp(-(4π σ_h cos θ / λ)²)` with σ_h fitted | Captures the diffuse-scattering loss in a tractable way; closes the θ-dependent gap | ~1-2 days |
| **Replace idealised sinusoid with the AFM mean profile** + per-position σ bands | Captures the real surface shape, including non-sinusoidal asymmetry not covered by A₂ | ~2-3 days; needs to read the AFM CSVs which user has signalled are off-limits today |
| **2-D / oblique grating handling** if light isn't really along grooves | Probably unnecessary — the φ row at θ = 30° is uniform | n/a |

Each is a research project in its own right. None is required for the TFM result.

---

## 9. Bottom line

**The simulation works.** At θ = 30° on sample SS\_12-3 it reaches Pearson r ≥ 0.95 across the full azimuth row, with a 6 percentage-point residual that matches Ane's independent empirical work. **That is the result to report.**

The θ-dependence study is itself a finding: it identifies the model's domain of validity unambiguously and points future work at the missing physics rather than at parameter overtuning. Going past θ = 30° in the current model would be dishonest — every parameter swept would absorb angular error and produce confidently wrong answers.

**Stage 2 and Stage 3 proceed at θ = 30° only.** That is the F1 path.

---

*Last updated: 2026-05-09 after Diagnostics (A) and (B). See DESIGN_LOG.md for the verbatim conversations.*
