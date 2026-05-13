#!/usr/bin/env python3
"""run_validate_thetaphi.py — does the locked Stage-1 winner + double-sin profile
generalise across the full experimental (θ, φ) matrix for sample 12-3?

Configuration is locked at:
    NA = 39                (Stage 0a)
    φ_sim ↔ φ_exp = 0°     mapped via 89° (Stage 0b)
    t_oxide = 0.90 µm      (Stage 1)
    β       = 2°           (Stage 1)
    oxide   = HS_caliente  (Stage 1)
    A₂      = 0.30 µm      (double-sin test)
    φ₂      = π/2          (double-sin test)
    period  = 12.9 µm,  A₁ = 1.5 µm,  slices = 50

Sweep:
    θ_exp  ∈ {30°, 45°, 60°}                    (3)
    φ_exp  ∈ {0°, 22.5°, 45°, 67.5°, 90°}       (5)
                                              ----
    total   15 runs

φ_sim is derived from φ_exp by `phi_sim_for_phi_exp(...)` — symmetric mapping
`90° − φ_exp` with a 1° offset at the singularities (`φ_exp = 0° → φ_sim = 89°`,
`φ_exp = 90° → φ_sim = 1°`). See DESIGN_LOG.md (Stage 0b) for the rationale.

Decision rule: report χ²_red per (θ, φ) and the aggregate sum/mean. If any
(θ, φ) row diverges substantially from the rest, that's evidence of a
structural angular issue we haven't captured.
"""
from __future__ import annotations

import argparse, itertools, logging, sys, time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

HERE      = Path(__file__).resolve().parent
SWEEP_DIR = HERE.parent
SIM_DIR   = SWEEP_DIR.parent
LIB_DIR   = SIM_DIR / "lib"
sys.path.insert(0, str(LIB_DIR))

import sweep_runner as sr   # noqa: E402

# All universal parameters locked from prior stages
LOCKED = dict(
    period_um        = 12.9,
    A_um             = 1.5,
    t_oxide_um       = 0.9,
    oxide_dispersion = "HS_caliente",
    harmonics        = 39,
    slices           = 50,
    beta_deg         = 2.0,
    A2_um            = 0.30,
    phi2_rad         = float(np.pi / 2),
    wavelengths_um   = np.arange(3.0, 25.0, 0.25),
)
SAMPLE        = "12-3"
DEFAULT_THETAS    = [30.0, 45.0, 60.0]
DEFAULT_PHIS_EXP  = [0.0, 22.5, 45.0, 67.5, 90.0]


def phi_sim_for_phi_exp(phi_exp_deg: float) -> float:
    """Map experimental azimuth to simulation azimuth.

    Geometric rule: φ_sim = 90° − φ_exp.
    Singularity dodges (per Stage 0b): if base would be 0° or 90°, offset by 1°.
    """
    base = 90.0 - float(phi_exp_deg)
    if abs(base) < 1e-9:
        return 1.0      # avoid rcwa 0° singular-matrix degeneracy
    if abs(base - 90.0) < 1e-9:
        return 89.0     # avoid the silent near-90° branch
    return base


def _worker(theta_deg: float, phi_exp_deg: float, output_dir_str: str) -> dict:
    import sys as _sys
    _sys.path.insert(0, str(LIB_DIR))
    import sweep_runner as _sr
    phi_sim = phi_sim_for_phi_exp(phi_exp_deg)
    cfg = _sr.SimConfig(theta_deg=theta_deg, phi_sim_deg=phi_sim, **LOCKED)
    return _sr.run_one_config(
        cfg            = cfg,
        sample         = SAMPLE,
        theta_exp_deg  = theta_deg,
        phi_exp_deg    = phi_exp_deg,
        output_dir     = Path(output_dir_str),
    )


def _config_for(theta_deg: float, phi_exp_deg: float):
    return sr.SimConfig(theta_deg=theta_deg,
                        phi_sim_deg=phi_sim_for_phi_exp(phi_exp_deg),
                        **LOCKED)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Validate locked config across 15 (θ, φ)")
    p.add_argument("--thetas",   default=",".join(f"{x:g}" for x in DEFAULT_THETAS))
    p.add_argument("--phis-exp", default=",".join(f"{x:g}" for x in DEFAULT_PHIS_EXP))
    p.add_argument("--out",      default=str(SWEEP_DIR / "runs" / "validate_thetaphi"))
    p.add_argument("--parallel", type=int, default=1)
    p.add_argument("--resume",   action="store_true")
    p.add_argument("--dry-run",  action="store_true")
    args = p.parse_args(argv)

    thetas    = [float(s.strip()) for s in args.thetas.split(",")    if s.strip()]
    phis_exp  = [float(s.strip()) for s in args.phis_exp.split(",")  if s.strip()]
    out_dir   = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    traces_dir = out_dir / "traces"
    traces_dir.mkdir(exist_ok=True)

    log = logging.getLogger("validate_thetaphi")
    fh  = logging.FileHandler(out_dir / "run.log", mode="a")
    fh.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s"))
    log.addHandler(fh); log.addHandler(logging.StreamHandler(sys.stdout))
    log.setLevel(logging.INFO)

    grid = list(itertools.product(thetas, phis_exp))
    log.info("=" * 70)
    log.info("Validate (θ, φ) — locked Stage-1 winner + double-sin profile")
    log.info(f"  θ grid       = {thetas}")
    log.info(f"  φ_exp grid   = {phis_exp}")
    log.info(f"  total configs = {len(grid)}")
    log.info(f"  parallel     = {args.parallel}")
    log.info(f"  output       = {out_dir}")
    log.info(f"  locked params: t_oxide={LOCKED['t_oxide_um']}µm, β={LOCKED['beta_deg']}°, "
             f"oxide={LOCKED['oxide_dispersion']}, NA={LOCKED['harmonics']}, "
             f"A2={LOCKED['A2_um']}µm, φ2={LOCKED['phi2_rad']:.4f} rad")
    log.info(f"  φ_sim mapping: φ_exp=0°→89°, 22.5°→67.5°, 45°→45°, 67.5°→22.5°, 90°→1°")

    todo = []
    for theta, phi_exp in grid:
        cfg  = _config_for(theta, phi_exp)
        stem = cfg.filename_stem()
        avg  = traces_dir / stem / f"AVG_{stem}.csv"
        if args.resume and avg.exists():
            log.info(f"  (θ={theta:g}, φ_exp={phi_exp:g}): AVG csv exists → skip")
        else:
            todo.append((theta, phi_exp))

    if args.dry_run:
        log.info(f"DRY RUN — would compute {len(todo)} configs")
        return 0

    rows: list[dict] = []
    t_overall = time.time()

    if args.parallel <= 1:
        for theta, phi_exp in todo:
            log.info(f"  (θ={theta:g}, φ_exp={phi_exp:g}): starting …")
            t0 = time.time()
            row = _worker(theta, phi_exp,
                          str(traces_dir / _config_for(theta, phi_exp).filename_stem()))
            rows.append(row)
            log.info(f"  (θ={theta:g}, φ_exp={phi_exp:g}): "
                     f"χ²_red(R_det)={row['Rdet_chi2_red']:7.2f}  "
                     f"RMSE={row['Rdet_RMSE']:.4f}  pearson={row['Rdet_pearson_r']:.4f}  "
                     f"runtime={time.time()-t0:.1f}s")
    else:
        log.info(f"Spawning {args.parallel} workers …")
        with ProcessPoolExecutor(max_workers=args.parallel) as pool:
            jobs = {pool.submit(
                _worker, theta, phi_exp,
                str(traces_dir / _config_for(theta, phi_exp).filename_stem())
            ): (theta, phi_exp) for theta, phi_exp in todo}
            done = 0
            for fut in as_completed(jobs):
                theta, phi_exp = jobs[fut]
                done += 1
                try:
                    row = fut.result(); rows.append(row)
                    log.info(f"  [{done:2d}/{len(todo)}] (θ={theta:g}, φ_exp={phi_exp:g}): "
                             f"χ²_red(R_det)={row['Rdet_chi2_red']:7.2f}  "
                             f"RMSE={row['Rdet_RMSE']:.4f}  pearson={row['Rdet_pearson_r']:.4f}")
                except Exception as e:
                    log.error(f"  (θ={theta:g}, φ_exp={phi_exp:g}): FAILED — {e}")

    # Merge with prior results.csv if --resume
    results_csv = out_dir / "results.csv"
    if args.resume and results_csv.exists():
        prior = pd.read_csv(results_csv)
        df    = pd.concat([prior, pd.DataFrame(rows)]).drop_duplicates(
            ["theta_exp_deg", "phi_exp_deg"], keep="last"
        )
    else:
        df    = pd.DataFrame(rows)
    df = df.sort_values(["theta_exp_deg", "phi_exp_deg"]).reset_index(drop=True)
    df.to_csv(results_csv, index=False)

    log.info(f"Wall time: {time.time()-t_overall:.1f}s ({(time.time()-t_overall)/60:.1f} min)")

    # Decision summary
    if not df.empty:
        decision = out_dir / "decision.txt"
        with decision.open("w") as f:
            f.write(f"# Validate (θ, φ) — sum / mean / range over {len(df)} configs\n")
            f.write(f"chi2_red sum    = {df['Rdet_chi2_red'].sum():.2f}\n")
            f.write(f"chi2_red mean   = {df['Rdet_chi2_red'].mean():.2f}\n")
            f.write(f"chi2_red median = {df['Rdet_chi2_red'].median():.2f}\n")
            f.write(f"chi2_red min    = {df['Rdet_chi2_red'].min():.2f}\n")
            f.write(f"chi2_red max    = {df['Rdet_chi2_red'].max():.2f}\n")
            f.write(f"chi2_red ratio max/min = {df['Rdet_chi2_red'].max()/df['Rdet_chi2_red'].min():.2f}\n")
            f.write("\nPer-cell chi2_red(R_det):\n")
            piv = df.pivot(index="theta_exp_deg", columns="phi_exp_deg", values="Rdet_chi2_red")
            f.write(piv.round(1).to_string())
            f.write("\n")
        log.info(f"Decision file: {decision}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
