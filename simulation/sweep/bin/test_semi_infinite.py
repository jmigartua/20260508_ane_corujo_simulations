#!/usr/bin/env python3
"""test_semi_infinite.py — does replacing the 200 µm SS slab + vacuum-behind
with a semi-infinite SS transmission half-space fix the θ-dependent failure
seen in the (θ, φ) validation?

Re-runs two cells from `validate_thetaphi/`:
  - WORST cell  (θ = 60°, φ_exp = 0°)  baseline χ²_red ≈ 1158
  - REFERENCE   (θ = 30°, φ_exp = 0°)  baseline χ²_red ≈ 104

…with the same locked parameters (NA = 39, t_oxide = 0.9 µm, β = 2°,
oxide = HS_caliente, A₂ = 0.30 µm, φ₂ = π/2) **plus**
`semi_infinite_substrate = True`.

Decision:
  - If WORST drops to O(100) → hypothesis (A) confirmed; bug found.
  - If WORST stays high (≫ 100) → (A) rejected; escalate to (B) NA convergence.
  - REFERENCE should ideally stay where it was (~100); if it gets dramatically
    *worse*, the semi-infinite formulation has a different bug.

Usage:  python sweep/bin/test_semi_infinite.py --parallel 2
"""
from __future__ import annotations

import argparse, logging, sys, time
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

# Locked from prior stages
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
SAMPLE = "12-3"

# Two cells to run: (theta, phi_exp); phi_sim derived from phi_exp via 90 - phi_exp
CELLS = [
    (60.0, 0.0),      # worst from validate_thetaphi
    (30.0, 0.0),      # reference (best stable cell — at this θ baseline is right)
]

def phi_sim_for_phi_exp(phi_exp_deg):
    base = 90.0 - float(phi_exp_deg)
    if abs(base) < 1e-9:    return 1.0
    if abs(base - 90) < 1e-9: return 89.0
    return base


def _worker(theta, phi_exp, output_dir_str):
    import sys as _sys; _sys.path.insert(0, str(LIB_DIR))
    import sweep_runner as _sr
    cfg = _sr.SimConfig(
        theta_deg=theta, phi_sim_deg=phi_sim_for_phi_exp(phi_exp),
        semi_infinite_substrate=True,
        **LOCKED,
    )
    return _sr.run_one_config(
        cfg=cfg, sample=SAMPLE, theta_exp_deg=theta, phi_exp_deg=phi_exp,
        output_dir=Path(output_dir_str),
    )


def main(argv=None):
    p = argparse.ArgumentParser(description="Semi-infinite-SS substrate test")
    p.add_argument("--out", default=str(SWEEP_DIR / "runs" / "test_semi_infinite"))
    p.add_argument("--parallel", type=int, default=1)
    p.add_argument("--resume", action="store_true")
    args = p.parse_args(argv)

    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    traces = out / "traces"; traces.mkdir(exist_ok=True)

    log = logging.getLogger("semi_inf"); log.setLevel(logging.INFO)
    fh = logging.FileHandler(out / "run.log", mode="a")
    fh.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s"))
    log.addHandler(fh); log.addHandler(logging.StreamHandler(sys.stdout))

    log.info("=" * 70)
    log.info("test_semi_infinite — locked Stage-1+double-sin + semi_infinite_substrate=True")
    log.info(f"  cells: {CELLS}")
    log.info(f"  parallel = {args.parallel}")

    todo = []
    for theta, phi_exp in CELLS:
        cfg  = sr.SimConfig(theta_deg=theta, phi_sim_deg=phi_sim_for_phi_exp(phi_exp),
                            semi_infinite_substrate=True, **LOCKED)
        stem = cfg.filename_stem()
        avg  = traces / stem / f"AVG_{stem}.csv"
        if args.resume and avg.exists():
            log.info(f"  (θ={theta:g}, φ_exp={phi_exp:g}): exists → skip")
        else:
            todo.append((theta, phi_exp))

    rows = []
    t0 = time.time()
    if args.parallel <= 1 or len(todo) <= 1:
        for theta, phi_exp in todo:
            log.info(f"  (θ={theta:g}, φ_exp={phi_exp:g}): starting …")
            cfg = sr.SimConfig(theta_deg=theta, phi_sim_deg=phi_sim_for_phi_exp(phi_exp),
                               semi_infinite_substrate=True, **LOCKED)
            row = _worker(theta, phi_exp, str(traces / cfg.filename_stem()))
            rows.append(row)
            log.info(f"  (θ={theta:g}, φ_exp={phi_exp:g}): "
                     f"χ²_red(R_det)={row['Rdet_chi2_red']:8.2f}  "
                     f"RMSE={row['Rdet_RMSE']:.4f}  pearson={row['Rdet_pearson_r']:.4f}")
    else:
        with ProcessPoolExecutor(max_workers=args.parallel) as pool:
            jobs = {pool.submit(
                _worker, theta, phi_exp,
                str(traces / sr.SimConfig(theta_deg=theta, phi_sim_deg=phi_sim_for_phi_exp(phi_exp),
                                          semi_infinite_substrate=True, **LOCKED).filename_stem())
            ): (theta, phi_exp) for theta, phi_exp in todo}
            for fut in as_completed(jobs):
                theta, phi_exp = jobs[fut]
                try:
                    row = fut.result(); rows.append(row)
                    log.info(f"  (θ={theta:g}, φ_exp={phi_exp:g}): "
                             f"χ²_red(R_det)={row['Rdet_chi2_red']:8.2f}  "
                             f"RMSE={row['Rdet_RMSE']:.4f}  pearson={row['Rdet_pearson_r']:.4f}")
                except Exception as e:
                    log.error(f"  (θ={theta:g}, φ_exp={phi_exp:g}): FAILED — {e}")

    if args.resume and (out / "results.csv").exists():
        prior = pd.read_csv(out / "results.csv")
        df = pd.concat([prior, pd.DataFrame(rows)]).drop_duplicates(
            ["theta_exp_deg", "phi_exp_deg"], keep="last"
        )
    else:
        df = pd.DataFrame(rows)
    df = df.sort_values(["theta_exp_deg", "phi_exp_deg"]).reset_index(drop=True)
    df.to_csv(out / "results.csv", index=False)
    log.info(f"Wall time: {time.time()-t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
