#!/usr/bin/env python3
"""test_na_at_theta60.py — does NA convergence break down at θ = 60°?

Re-runs the worst cell from `validate_thetaphi/` (θ=60°, φ_exp=0°) at
NA ∈ {51, 75, 91} and compares to the NA = 39 baseline (χ²_red = 1157.65).

If χ² drops monotonically with NA → hypothesis (B) confirmed: NA = 39 is
undersized at θ = 60° because diffraction orders propagate near grazing
and demand more harmonics. We then lock a higher NA for θ = 60° and
re-run the (θ, φ) validation.

If χ² is roughly flat in NA → (B) rejected too. The θ-dependent
failure is something else (β-projection, geometry, polarisation handling
at large θ, …) and we escalate.

Estimated wall time at parallel 3: ~80 min (NA = 91 at θ = 60° is the
bottleneck — matrices ≈ 5× larger than NA = 39, runtime scales ~NA³).
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

LOCKED = dict(
    period_um        = 12.9,
    A_um             = 1.5,
    t_oxide_um       = 0.9,
    oxide_dispersion = "HS_caliente",
    theta_deg        = 60.0,         # the worst-case θ
    phi_sim_deg      = 89.0,         # ↔ phi_exp = 0°
    slices           = 50,
    beta_deg         = 2.0,
    A2_um            = 0.30,
    phi2_rad         = float(np.pi / 2),
    wavelengths_um   = np.arange(3.0, 25.0, 0.25),
)
DEFAULT_NA_GRID = [51, 75, 91]
SAMPLE        = "12-3"
THETA_EXP_DEG = 60
PHI_EXP_DEG   = 0


def _worker(NA, output_dir_str):
    import sys as _sys; _sys.path.insert(0, str(LIB_DIR))
    import sweep_runner as _sr
    cfg = _sr.SimConfig(harmonics=NA, **LOCKED)
    return _sr.run_one_config(
        cfg=cfg, sample=SAMPLE, theta_exp_deg=THETA_EXP_DEG,
        phi_exp_deg=PHI_EXP_DEG, output_dir=Path(output_dir_str),
    )


def main(argv=None):
    p = argparse.ArgumentParser(description="NA convergence test at θ = 60°")
    p.add_argument("--na-grid", default=",".join(map(str, DEFAULT_NA_GRID)))
    p.add_argument("--out",     default=str(SWEEP_DIR / "runs" / "test_na_theta60"))
    p.add_argument("--parallel", type=int, default=1)
    p.add_argument("--resume",  action="store_true")
    args = p.parse_args(argv)

    na_grid = [int(s.strip()) for s in args.na_grid.split(",") if s.strip()]
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    traces = out / "traces"; traces.mkdir(exist_ok=True)

    log = logging.getLogger("na_th60"); log.setLevel(logging.INFO)
    fh = logging.FileHandler(out / "run.log", mode="a")
    fh.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s"))
    log.addHandler(fh); log.addHandler(logging.StreamHandler(sys.stdout))

    log.info("=" * 70)
    log.info("NA convergence at θ = 60°, φ_exp = 0°")
    log.info(f"  NA grid  = {na_grid}")
    log.info(f"  parallel = {args.parallel}")
    log.info(f"  baseline NA = 39 → χ²_red = 1157.65 (validate_thetaphi)")

    todo = []
    for NA in na_grid:
        cfg = sr.SimConfig(harmonics=NA, **LOCKED)
        stem = cfg.filename_stem()
        avg = traces / stem / f"AVG_{stem}.csv"
        if args.resume and avg.exists():
            log.info(f"  NA = {NA}: exists → skip")
        else:
            todo.append(NA)

    rows = []
    t0 = time.time()
    if args.parallel <= 1:
        for NA in todo:
            log.info(f"  NA = {NA}: starting …")
            cfg = sr.SimConfig(harmonics=NA, **LOCKED)
            row = _worker(NA, str(traces / cfg.filename_stem()))
            rows.append(row)
            log.info(f"  NA = {NA}: χ²_red(R_det)={row['Rdet_chi2_red']:8.2f}  "
                     f"RMSE={row['Rdet_RMSE']:.4f}  pearson={row['Rdet_pearson_r']:.4f}  "
                     f"runtime={row['runtime_s']:.0f}s")
    else:
        with ProcessPoolExecutor(max_workers=args.parallel) as pool:
            jobs = {pool.submit(
                _worker, NA, str(traces / sr.SimConfig(harmonics=NA, **LOCKED).filename_stem())
            ): NA for NA in todo}
            for fut in as_completed(jobs):
                NA = jobs[fut]
                try:
                    row = fut.result(); rows.append(row)
                    log.info(f"  NA = {NA}: χ²_red(R_det)={row['Rdet_chi2_red']:8.2f}  "
                             f"RMSE={row['Rdet_RMSE']:.4f}  pearson={row['Rdet_pearson_r']:.4f}  "
                             f"runtime={row['runtime_s']:.0f}s")
                except Exception as e:
                    log.error(f"  NA = {NA}: FAILED — {e}")

    if args.resume and (out / "results.csv").exists():
        prior = pd.read_csv(out / "results.csv")
        df = pd.concat([prior, pd.DataFrame(rows)]).drop_duplicates("harmonics", keep="last")
    else:
        df = pd.DataFrame(rows)
    df = df.sort_values("harmonics").reset_index(drop=True)
    df.to_csv(out / "results.csv", index=False)
    log.info(f"Wall time: {time.time()-t0:.1f}s ({(time.time()-t0)/60:.1f} min)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
