"""sweep_runner.py — orchestration for the configuration-space sweep.

The Tier-1 (universal) and Tier-2 (per-sample) parameter exploration defined in
DISTANCE.md v0.2 §4 and §6 calls into the functions here:

    - solve_one(cfg)              : run one RCWA simulation, both polarisations
    - average_polarisations(...)  : (LX + LY) / 2
    - load_experimental_repeats(...)
    - score(sim_df, sample, …)    : χ²_red, RMSE, MAE, … for both R and R_det
    - run_one_config(cfg, …)      : solve + score + persist + return one row

This is a thin layer over Ane's notebook code (test8.qmd §5). The simulation
logic is unchanged; we just wrap it as a function so we can loop it from the
stage qmds without copy-paste.

This module imports the patched rcwa (Ane's solver.py / harmonics.py installed
in the venv site-packages) — `Solver.get_detected_reflectance(beta)` is a
patched method that does not exist upstream.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
import time

import numpy as np
import pandas as pd
from scipy.interpolate import UnivariateSpline, interp1d

from rcwa import Source, Layer, LayerStack, Crystal, Solver
from rcwa.shorthand import complexArray


# ---------------------------------------------------------------------------
# Paths — resolve relative to this file so the module works from any cwd
# ---------------------------------------------------------------------------
HERE         = Path(__file__).resolve().parent         # simulation/lib/
SIM_DIR      = HERE.parent                             # simulation/
PROJECT_ROOT = SIM_DIR.parent                          # 20260508_ane_corujo_simulations/
DATA_DIR     = PROJECT_ROOT / "data"                   # all input data, project-level
EXP_DIR      = DATA_DIR / "experimental"               # 321 FTIR CSVs (read-only snapshot)
MAT_DIR      = DATA_DIR / "materials"                  # SS permittivity + Cr2O3 dispersions

# Material data — single source of truth, used by every simulation
SS_PERMITTIVITY_CSV = MAT_DIR / "SS_permittivity.csv"  # symlink to ../20260508_messages/SS_letter (1).csv

# Cr2O3 dispersion choices (HS = 300 °C substrate, RS = unheated substrate).
# Frozen copies — regenerated only by Ane's datos_cromo() in ane_originals/test8.qmd.
OXIDE_DISPERSIONS: dict[str, Path] = {
    "HS_caliente": MAT_DIR / "Cr2O3_HS_caliente.csv",
    "RS_frio":     MAT_DIR / "Cr2O3_RS_frio.csv",
}

# Defaults from DISTANCE.md §2
SIGMA_FLOOR_DEFAULT = 0.01

# φ filename map (experimental side: half degrees rendered with hyphen)
PHI_EXP_TO_FILESTR = {0: "0", 22.5: "22-5", 45: "45", 67.5: "67-5", 90: "90"}


# ---------------------------------------------------------------------------
# Material loaders
# ---------------------------------------------------------------------------
def ss_splines(csv_path: Path = SS_PERMITTIVITY_CSV):
    """SS complex permittivity ε'(λ), ε''(λ). Header columns labelled 'n','k' but
    the underlying values are real and imaginary permittivity — see ANALYSIS.md §5."""
    df = pd.read_csv(csv_path)
    df["lambda"] = 1e4 / df["wavenumber"].values
    df = df.sort_values("lambda").reset_index(drop=True)
    return (
        UnivariateSpline(df["lambda"].values, df["n"].values),
        UnivariateSpline(df["lambda"].values, df["k"].values),
    )


def oxide_splines(name: str = "HS_caliente"):
    """Cr₂O₃ refractive index and extinction coefficient. n,k are genuinely n,k here."""
    if name not in OXIDE_DISPERSIONS:
        raise KeyError(f"oxide_dispersion={name!r} not in {list(OXIDE_DISPERSIONS)}")
    df = pd.read_csv(OXIDE_DISPERSIONS[name]).sort_values("lambda_um").reset_index(drop=True)
    return (
        UnivariateSpline(df["lambda_um"].values, df["n"].values),
        UnivariateSpline(df["lambda_um"].values, df["k"].values),
    )


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------
def sinusoidal_profile(period_um: float, A_um: float,
                       A2_um: float = 0.0, phi2_rad: float = 0.0,
                       n_pts: int = 500, phase: float = 0.0) -> pd.DataFrame:
    """Surface profile: fundamental + optional 2nd harmonic.

        y(x) = A1 sin(k x + φ) + A2 sin(2 k x + φ + φ2)

    With A2 = 0 (default) this reduces to the pure-sinusoid model used through
    Stage 0a/0b/1. With A2 > 0 and φ2 = π/2 the profile gets *broader peaks
    and sharper valleys* — the asymmetry visible in Section 5 of Ane's
    `Tratamiento de imágenes` PDF. See DESIGN_LOG.md (post-Stage-1 synthesis)
    for motivation.
    """
    x = np.linspace(0.0, period_um, n_pts)
    k = 2.0 * np.pi / period_um
    y = A_um * np.sin(k * x + phase)
    if A2_um != 0.0:
        y = y + A2_um * np.sin(2.0 * k * x + phase + phi2_rad)
    return pd.DataFrame({"x": x, "y": y})


def discretize_with_oxide(df: pd.DataFrame,
                          material_perm: complex,
                          oxide_perm: complex,
                          env_perm: complex = 1.0,
                          slices: int = 50,
                          oxide_thickness_um: float = 0.05) -> np.ndarray:
    """Direct port of Ane's `discretize_rugosity_with_oxide`. Returns a (slices, len(df))
    complex permittivity matrix where each row is the ε(x) of one z-slice.

    Oxide is applied as a vertical band of thickness `oxide_thickness_um` above the
    local metal column. See ANALYSIS.md §6.4 for the cos(slope) caveat — not patched."""
    min_y, max_y = float(df["y"].min()), float(df["y"].max())
    total_height = max_y - min_y
    df_norm = (df["y"] - min_y) / total_height

    M = np.full((slices, len(df)), env_perm, dtype=complex)
    for i in range(1, slices + 1):
        z_level = i / slices
        metal_idx = df.index[df_norm > z_level].tolist()
        M[-i][metal_idx] = material_perm
        oxide_threshold = z_level + (oxide_thickness_um / total_height)
        oxide_idx = df.index[(df_norm > z_level) & (df_norm <= oxide_threshold)].tolist()
        M[-i][oxide_idx] = oxide_perm
    return M


# ---------------------------------------------------------------------------
# RCWA solve
# ---------------------------------------------------------------------------
POLARISATIONS: dict[str, np.ndarray] = {
    "LX": complexArray([1, 0j]),
    "LY": complexArray([0, 1j]),
}


@dataclass
class SimConfig:
    """One simulation point. Wavelengths default to Ane's 3–25 µm grid at 0.25 µm."""
    period_um:        float
    A_um:             float                    # half-amplitude (depth = 2 A)
    t_oxide_um:       float
    oxide_dispersion: str                      # key in OXIDE_DISPERSIONS
    theta_deg:        float
    phi_sim_deg:      float                    # rcwa azimuth (89° ↔ φ_exp = 0°)
    harmonics:        int                      # NA, must be odd
    slices:           int = 50
    beta_deg:         float = 2.0
    A2_um:            float = 0.0           # second-harmonic amplitude (0 = pure sin)
    phi2_rad:         float = 0.0           # second-harmonic relative phase
    semi_infinite_substrate: bool = False   # if True: SS as transmission half-space, no finite slab
    wavelengths_um:   np.ndarray = field(default_factory=lambda: np.arange(3.0, 25.0, 0.25))

    def filename_stem(self) -> str:
        # `:g` preserves integers without trailing zeros ("89") *and* non-integers
        # at full precision ("89.999"). Earlier `:.0f` rounded — 89.999 collided
        # with 90.0 in disk filenames; lesson logged in DESIGN_LOG.md (2026-05-09).
        base = (
            f"P{self.period_um:.3f}_A{self.A_um:.3f}_tox{self.t_oxide_um:.3f}_"
            f"{self.oxide_dispersion}_th{self.theta_deg:g}_phi{self.phi_sim_deg:g}_"
            f"NA{self.harmonics}_b{self.beta_deg:.1f}"
        )
        # Append second-harmonic suffix only when non-default — preserves existing stems
        # for every Stage 0a / 0b / 1 trace already on disk.
        if self.A2_um != 0.0 or self.phi2_rad != 0.0:
            base += f"_A2{self.A2_um:g}_phi2{self.phi2_rad:.3f}"
        if self.semi_infinite_substrate:
            base += "_SI"
        return base


def solve_one(cfg: SimConfig,
              sample_pattern: pd.DataFrame | None = None,
              ss_splines_=None,
              oxide_splines_=None,
              verbose: bool = False) -> dict[str, pd.DataFrame]:
    """Run RCWA at every λ for both polarisations. Returns {pol_name: dataframe}.
    Each dataframe has columns x, R, T, A, R_det."""
    if sample_pattern is None:
        sample_pattern = sinusoidal_profile(
            cfg.period_um, cfg.A_um,
            A2_um=cfg.A2_um, phi2_rad=cfg.phi2_rad,
        )
    if ss_splines_ is None:
        ss_splines_ = ss_splines()
    if oxide_splines_ is None:
        oxide_splines_ = oxide_splines(cfg.oxide_dispersion)

    n_ss, k_ss = ss_splines_
    n_ox, k_ox = oxide_splines_

    width = int(np.max(sample_pattern["x"]) - np.min(sample_pattern["x"]))
    layer_thickness = (sample_pattern["y"].max() - sample_pattern["y"].min()) / cfg.slices
    incident_layer = Layer(er=1.0, ur=1.0)
    deg = np.pi / 180.0
    theta = cfg.theta_deg * deg
    phi   = cfg.phi_sim_deg * deg

    perm_ss_real = n_ss(cfg.wavelengths_um)
    perm_ss_imag = k_ss(cfg.wavelengths_um)

    out: dict[str, pd.DataFrame] = {}
    for pol_name, pTEM in POLARISATIONS.items():
        per_lambda = []
        for lam, pr, pi in zip(cfg.wavelengths_um, perm_ss_real, perm_ss_imag):
            permittivity_ss = complex(pr, -pi)                # ε = ε' − iε''
            o_perm          = complex(float(n_ox(lam)), -float(k_ox(lam)))

            P = discretize_with_oxide(
                sample_pattern,
                material_perm=permittivity_ss,
                oxide_perm=o_perm,
                slices=cfg.slices,
                oxide_thickness_um=cfg.t_oxide_um,
            )
            inner = []
            for row in P:
                inner.append(Layer(
                    crystal=Crystal(np.array([width, 0]), er=row, ur=1.000022 + 0 * row),
                    thickness=layer_thickness,
                ))
            # Substrate: either a finite SS slab terminated in vacuum (backward-compat,
            # what every prior stage used) or a true semi-infinite SS half-space as the
            # transmission_layer. See ANALYSIS.md §6.7 — the finite-slab variant can
            # produce θ-dependent multi-reflection artefacts.
            if cfg.semi_infinite_substrate:
                transmission_layer = Layer(er=permittivity_ss, ur=1.000022)
            else:
                inner.append(Layer(er=permittivity_ss, ur=1.000022, thickness=200))
                transmission_layer = Layer(er=1.0, ur=1.0)

            source = Source(wavelength=float(lam), theta=theta, phi=phi,
                            pTEM=pTEM, layer=incident_layer)
            stack  = LayerStack(*inner, incident_layer=incident_layer,
                                transmission_layer=transmission_layer)
            solver = Solver(layer_stack=stack, source=source, n_harmonics=cfg.harmonics)
            r = solver.solve()
            R    = float(np.real(r["RTot"]))
            T    = float(np.real(r["TTot"]))
            Rdet = float(solver.get_detected_reflectance(beta=cfg.beta_deg))
            per_lambda.append((float(lam), R, T, 1.0 - (R + T), Rdet))
            if verbose:
                print(f"  [{pol_name}] λ={lam:5.2f}  R={R:.4f}  T={T:.4f}  Rdet={Rdet:.4f}")

        out[pol_name] = pd.DataFrame(per_lambda, columns=["x", "R", "T", "A", "R_det"])
    return out


def average_polarisations(results: dict[str, pd.DataFrame]) -> pd.DataFrame:
    lx, ly = results["LX"], results["LY"]
    return pd.DataFrame({
        "x":     lx["x"].values,
        "R":     0.5 * (lx["R"]     + ly["R"]),
        "T":     0.5 * (lx["T"]     + ly["T"]),
        "A":     0.5 * (lx["A"]     + ly["A"]),
        "R_det": 0.5 * (lx["R_det"] + ly["R_det"]),
    })


# ---------------------------------------------------------------------------
# Experimental loading + scoring
# ---------------------------------------------------------------------------
def load_experimental_repeats(sample: str, theta_deg: float, phi_exp_deg: float,
                              exp_dir: Path = EXP_DIR):
    phi_str = PHI_EXP_TO_FILESTR.get(phi_exp_deg)
    if phi_str is None:
        raise ValueError(f"phi_exp must be in {list(PHI_EXP_TO_FILESTR)}, got {phi_exp_deg}")
    pattern = f"{sample}_{int(theta_deg)}_{phi_str}_*.CSV"
    files = sorted(Path(exp_dir).glob(pattern))
    if not files:
        raise FileNotFoundError(f"No experimental files match {pattern} in {exp_dir}")
    repeats = []
    for f in files:
        raw = pd.read_csv(f, header=None, names=["wavenumber_cm1", "R_pct"])
        raw = raw[raw["R_pct"] > 0].copy()
        raw["lambda_um"] = 1e4 / raw["wavenumber_cm1"]
        raw["R"] = raw["R_pct"] / 100.0
        raw = raw.sort_values("lambda_um").reset_index(drop=True)
        repeats.append((raw["lambda_um"].values, raw["R"].values))
    return files, repeats


def score(sim_df: pd.DataFrame,
          sample: str,
          theta_deg: float,
          phi_exp_deg: float,
          exp_dir: Path = EXP_DIR,
          sigma_floor: float = SIGMA_FLOOR_DEFAULT,
          k_free: int = 0) -> dict:
    """Reduced χ² (with σ floor) and conventional metrics for both R and R_det.

    See DISTANCE.md §2 for the metric definition."""
    files, repeats = load_experimental_repeats(sample, theta_deg, phi_exp_deg, exp_dir)
    lam = sim_df["x"].values
    R_stack = np.array([
        interp1d(l, r, bounds_error=False, fill_value=np.nan, assume_sorted=True)(lam)
        for l, r in repeats
    ])
    R_mean = np.nanmean(R_stack, axis=0)
    R_std  = np.nanstd(R_stack, axis=0, ddof=1)
    R_sem  = R_std / np.sqrt(R_stack.shape[0])
    valid  = ~np.isnan(R_mean)

    def metrics(s: np.ndarray) -> dict:
        s_v = s[valid]
        m_v = R_mean[valid]
        sem = np.maximum(R_sem[valid], sigma_floor)
        res = s_v - m_v
        N = len(res)
        chi2 = float(np.sum((res / sem) ** 2))
        return {
            "N":          N,
            "chi2_red":   chi2 / max(N - k_free, 1),
            "RMSE":       float(np.sqrt(np.mean(res ** 2))),
            "MAE":        float(np.mean(np.abs(res))),
            "max_abs":    float(np.max(np.abs(res))),
            "pearson_r":  float(np.corrcoef(s_v, m_v)[0, 1]),
            "mean_sigma": float(np.mean(sem)),
        }

    out = {
        "exp_files":  ";".join(f.name for f in files),
        "n_overlap":  int(valid.sum()),
    }
    for prefix, col in (("R", "R"), ("Rdet", "R_det")):
        for k, v in metrics(sim_df[col].values).items():
            out[f"{prefix}_{k}"] = v
    return out


# ---------------------------------------------------------------------------
# High-level entry point: solve + score + record
# ---------------------------------------------------------------------------
def run_one_config(cfg: SimConfig,
                   sample: str,
                   theta_exp_deg: float,
                   phi_exp_deg: float,
                   output_dir: Path,
                   sample_pattern: pd.DataFrame | None = None,
                   ss_splines_=None,
                   oxide_splines_=None,
                   verbose: bool = False) -> dict:
    """One end-to-end evaluation. Returns a dict ready to append as a sweep row.

    Persists three CSVs (LX, LY, AVG) under output_dir, named with cfg.filename_stem()."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    pol_results = solve_one(cfg,
                            sample_pattern=sample_pattern,
                            ss_splines_=ss_splines_,
                            oxide_splines_=oxide_splines_,
                            verbose=verbose)
    avg_df    = average_polarisations(pol_results)
    runtime_s = time.time() - t0

    stem = cfg.filename_stem()
    avg_path = output_dir / f"AVG_{stem}.csv"
    avg_df.to_csv(avg_path, index=False)
    pol_results["LX"].to_csv(output_dir / f"LX_{stem}.csv", index=False)
    pol_results["LY"].to_csv(output_dir / f"LY_{stem}.csv", index=False)

    metrics_dict = score(avg_df, sample, theta_exp_deg, phi_exp_deg)

    row = {**asdict(cfg)}
    # `wavelengths_um` is too long for a CSV cell — summarise
    wl = row.pop("wavelengths_um")
    row["lambda_min_um"] = float(np.min(wl))
    row["lambda_max_um"] = float(np.max(wl))
    row["n_lambda"]      = int(len(wl))
    row["sample"]        = sample
    row["theta_exp_deg"] = theta_exp_deg
    row["phi_exp_deg"]   = phi_exp_deg
    row.update(metrics_dict)
    row["runtime_s"]     = runtime_s
    row["sim_csv"]       = str(avg_path.relative_to(SIM_DIR))
    return row
