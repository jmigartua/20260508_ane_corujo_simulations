#!/usr/bin/env python3
"""run_double_sin_test.py — does adding a 2nd harmonic to the surface profile
help, at the Stage-1 winner geometry?

Centre = Stage-1 winner: t_oxide = 0.90 µm, β = 2°, oxide = HS_caliente,
period = 12.9 µm, A = 1.5 µm (depth = 3.0 µm), θ = 30°, φ_sim = 89°,
NA = 39, slices = 50.

Sweep: 3 configs over second-harmonic amplitude A2 at fixed phase φ2 = π/2
(the asymmetry direction matching Ane's AFM observation of broader peaks
and sharper valleys — Section 5 of *Tratamiento*). Baseline (A2 = 0) lives
in the Stage 1 traces and is referenced from the report.

Usage
-----
    python sweep/bin/run_double_sin_test.py --parallel 3
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
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

CENTRE = dict(
    period_um        = 12.9,
    A_um             = 1.5,
    t_oxide_um       = 0.9,
    oxide_dispersion = "HS_caliente",
    theta_deg        = 30.0,
    phi_sim_deg      = 89.0,
    harmonics        = 39,
    slices           = 50,
    beta_deg         = 2.0,
    wavelengths_um   = np.arange(3.0, 25.0, 0.25),
)
DEFAULT_A2_GRID  = [0.10, 0.20, 0.30]      # µm
DEFAULT_PHI2_RAD = np.pi / 2               # broadens peaks, sharpens valleys
SAMPLE           = "12-3"
THETA_EXP_DEG    = 30
PHI_EXP_DEG      = 0


def _worker(A2: float, phi2: float, output_dir_str: str) -> dict:
    import sys as _sys
    _sys.path.insert(0, str(LIB_DIR))
    import sweep_runner as _sr
    cfg = _sr.SimConfig(A2_um=A2, phi2_rad=phi2, **CENTRE)
    return _sr.run_one_config(
        cfg            = cfg,
        sample         = SAMPLE,
        theta_exp_deg  = THETA_EXP_DEG,
        phi_exp_deg    = PHI_EXP_DEG,
        output_dir     = Path(output_dir_str),
    )


def _config_for(A2: float, phi2: float):
    return sr.SimConfig(A2_um=A2, phi2_rad=phi2, **CENTRE)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Stage-1-winner + 2nd-harmonic test")
    p.add_argument("--a2-grid",  default=",".join(f"{x:g}" for x in DEFAULT_A2_GRID))
    p.add_argument("--phi2-rad", type=float, default=DEFAULT_PHI2_RAD)
    p.add_argument("--out",      default=str(SWEEP_DIR / "runs" / "double_sin_test"))
    p.add_argument("--parallel", type=int, default=1)
    p.add_argument("--resume",   action="store_true")
    p.add_argument("--dry-run",  action="store_true")
    args = p.parse_args(argv)

    a2_grid = [float(s.strip()) for s in args.a2_grid.split(",") if s.strip()]
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    traces_dir = out_dir / "traces"
    traces_dir.mkdir(exist_ok=True)

    log = logging.getLogger("doublesin")
    fh  = logging.FileHandler(out_dir / "run.log", mode="a")
    fh.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s"))
    log.addHandler(fh); log.addHandler(logging.StreamHandler(sys.stdout))
    log.setLevel(logging.INFO)

    log.info("=" * 70)
    log.info("Double-sin test — at Stage-1 winner")
    log.info(f"  A2 grid (µm)      = {a2_grid}")
    log.info(f"  phi2 (rad)        = {args.phi2_rad:.4f}  ({np.degrees(args.phi2_rad):.1f}°)")
    log.info(f"  parallel          = {args.parallel}")
    log.info(f"  output            = {out_dir}")

    todo = []
    for A2 in a2_grid:
        cfg = _config_for(A2, args.phi2_rad)
        stem = cfg.filename_stem()
        avg = traces_dir / stem / f"AVG_{stem}.csv"
        if args.resume and avg.exists():
            log.info(f"  A2={A2:.2f}: AVG csv exists → skip")
        else:
            todo.append(A2)

    if args.dry_run:
        log.info(f"DRY RUN — would compute A2 = {todo}")
        return 0

    rows = []
    t0 = time.time()
    if args.parallel <= 1:
        for A2 in todo:
            log.info(f"  A2={A2:.2f}: starting …")
            row = _worker(A2, args.phi2_rad,
                          str(traces_dir / _config_for(A2, args.phi2_rad).filename_stem()))
            rows.append(row)
            log.info(f"  A2={A2:.2f}: χ²_red(R_det)={row['Rdet_chi2_red']:7.2f}  "
                     f"RMSE={row['Rdet_RMSE']:.4f}  pearson={row['Rdet_pearson_r']:.4f}")
    else:
        log.info(f"Spawning {args.parallel} workers …")
        with ProcessPoolExecutor(max_workers=args.parallel) as pool:
            jobs = {pool.submit(_worker, A2, args.phi2_rad,
                                str(traces_dir / _config_for(A2, args.phi2_rad).filename_stem())): A2
                    for A2 in todo}
            for fut in as_completed(jobs):
                A2 = jobs[fut]
                try:
                    row = fut.result(); rows.append(row)
                    log.info(f"  A2={A2:.2f}: χ²_red(R_det)={row['Rdet_chi2_red']:7.2f}  "
                             f"RMSE={row['Rdet_RMSE']:.4f}  pearson={row['Rdet_pearson_r']:.4f}")
                except Exception as e:
                    log.error(f"  A2={A2:.2f}: FAILED — {e}")

    df = pd.DataFrame(rows).sort_values("A2_um").reset_index(drop=True)
    df.to_csv(out_dir / "results.csv", index=False)
    log.info(f"Wall time: {time.time()-t0:.1f}s ({(time.time()-t0)/60:.1f} min)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
