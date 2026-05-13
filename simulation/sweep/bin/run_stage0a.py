#!/usr/bin/env python3
"""run_stage0a.py — Stage 0a NA convergence (sample SS_12_3).

Locks the harmonics count NA before any physical-parameter sweep
(see ../../design/DISTANCE.md §6 and ../../design/SWEEP_PLAN.md "Stage 0a").

Usage
-----
    python bin/run_stage0a.py                          # serial, default NA grid
    python bin/run_stage0a.py --parallel 4             # 4 workers
    python bin/run_stage0a.py --na-grid 31,35,51       # custom grid
    python bin/run_stage0a.py --resume                 # skip configs whose AVG csv exists
    python bin/run_stage0a.py --dry-run                # print plan, don't execute

Output
------
    runs/stage0a_NA_convergence/
        results.csv                       one row per NA, sweep-cube schema
        decision.txt                      chosen NA + convergence table
        run.log                           timestamped progress log
        traces/<stem>/{LX,LY,AVG}.csv     simulation traces per NA

Decision rule
-------------
    Pick the smallest NA in the grid where
        max_λ | R_det(NA, λ) − R_det(NA_max, λ) | < σ_floor (= 0.01).
    If no NA below NA_max satisfies this, fall back to NA_max and warn.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

# Resolve simulation root from this file's location, not from cwd
HERE      = Path(__file__).resolve().parent           # simulation/sweep/bin
SWEEP_DIR = HERE.parent                                # simulation/sweep
SIM_DIR   = SWEEP_DIR.parent                           # simulation
LIB_DIR   = SIM_DIR / "lib"
sys.path.insert(0, str(LIB_DIR))

import sweep_runner as sr   # noqa: E402

# ---------------------------------------------------------------------------
# Stage 0a centre-of-cube parameters (per SWEEP_PLAN.md)
# ---------------------------------------------------------------------------
CENTRE = dict(
    period_um        = 12.9,
    A_um             = 1.5,
    t_oxide_um       = 0.30,
    oxide_dispersion = "HS_caliente",
    theta_deg        = 30.0,
    phi_sim_deg      = 89.0,
    slices           = 50,
    beta_deg         = 2.0,
    wavelengths_um   = np.arange(3.0, 25.0, 0.25),
)
DEFAULT_NA_GRID = [15, 19, 23, 27, 31, 35, 39, 51]
SAMPLE          = "12-3"
THETA_EXP_DEG   = 30
PHI_EXP_DEG     = 0
SIGMA_FLOOR     = 0.01


# ---------------------------------------------------------------------------
# One-config worker (top-level so multiprocessing can pickle it)
# ---------------------------------------------------------------------------
def _worker(NA: int, output_dir_str: str) -> dict:
    """Run one configuration. Re-imports module locally for ProcessPool safety."""
    import sys as _sys
    _sys.path.insert(0, str(LIB_DIR))
    import sweep_runner as _sr
    cfg = _sr.SimConfig(harmonics=NA, **CENTRE)
    return _sr.run_one_config(
        cfg            = cfg,
        sample         = SAMPLE,
        theta_exp_deg  = THETA_EXP_DEG,
        phi_exp_deg    = PHI_EXP_DEG,
        output_dir     = Path(output_dir_str),
    )


# ---------------------------------------------------------------------------
# Stage driver
# ---------------------------------------------------------------------------
def run_stage(na_grid: list[int],
              out_dir: Path,
              parallel: int = 1,
              resume: bool = False,
              dry_run: bool = False) -> pd.DataFrame:
    out_dir.mkdir(parents=True, exist_ok=True)
    traces_dir = out_dir / "traces"
    traces_dir.mkdir(exist_ok=True)

    log = logging.getLogger("stage0a")
    fh  = logging.FileHandler(out_dir / "run.log", mode="a")
    fh.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s"))
    log.addHandler(fh)
    log.addHandler(logging.StreamHandler(sys.stdout))
    log.setLevel(logging.INFO)

    log.info("=" * 70)
    log.info(f"Stage 0a — NA convergence")
    log.info(f"  NA grid           = {na_grid}")
    log.info(f"  parallel          = {parallel}")
    log.info(f"  resume            = {resume}")
    log.info(f"  dry_run           = {dry_run}")
    log.info(f"  output            = {out_dir}")
    log.info(f"  centre params     = "
             f"period={CENTRE['period_um']}µm, A={CENTRE['A_um']}µm, "
             f"t_oxide={CENTRE['t_oxide_um']}µm, "
             f"oxide={CENTRE['oxide_dispersion']}, "
             f"theta={CENTRE['theta_deg']}°, phi_sim={CENTRE['phi_sim_deg']}°, "
             f"beta={CENTRE['beta_deg']}°")

    # Plan: one cfg per NA, decide which we still need to compute
    todo = []
    for NA in na_grid:
        cfg  = sr.SimConfig(harmonics=NA, **CENTRE)
        stem = cfg.filename_stem()
        avg  = traces_dir / stem / f"AVG_{stem}.csv"
        if resume and avg.exists():
            log.info(f"  NA={NA:3d}: AVG csv exists → skip")
        else:
            todo.append(NA)

    if dry_run:
        log.info(f"DRY RUN — would compute NA = {todo}")
        return pd.DataFrame()

    rows: list[dict] = []
    t_overall = time.time()

    if parallel <= 1:
        for NA in todo:
            log.info(f"  NA={NA:3d}: starting …")
            t0 = time.time()
            row = _worker(NA, str(traces_dir / sr.SimConfig(harmonics=NA, **CENTRE).filename_stem()))
            rows.append(row)
            log.info(
                f"  NA={NA:3d}: χ²_red(R_det)={row['Rdet_chi2_red']:7.2f}  "
                f"RMSE={row['Rdet_RMSE']:.4f}  pearson={row['Rdet_pearson_r']:.4f}  "
                f"runtime={time.time()-t0:.1f}s"
            )
    else:
        log.info(f"Spawning {parallel} workers …")
        with ProcessPoolExecutor(max_workers=parallel) as pool:
            jobs = {
                pool.submit(
                    _worker, NA,
                    str(traces_dir / sr.SimConfig(harmonics=NA, **CENTRE).filename_stem())
                ): NA
                for NA in todo
            }
            for fut in as_completed(jobs):
                NA = jobs[fut]
                try:
                    row = fut.result()
                    rows.append(row)
                    log.info(
                        f"  NA={NA:3d}: χ²_red(R_det)={row['Rdet_chi2_red']:7.2f}  "
                        f"RMSE={row['Rdet_RMSE']:.4f}  pearson={row['Rdet_pearson_r']:.4f}"
                    )
                except Exception as e:
                    log.error(f"  NA={NA:3d}: FAILED — {e}")

    # Merge with any existing rows from resume mode
    results_csv = out_dir / "results.csv"
    if resume and results_csv.exists():
        prior = pd.read_csv(results_csv)
        df    = pd.concat([prior, pd.DataFrame(rows)]).drop_duplicates("harmonics", keep="last")
    else:
        df    = pd.DataFrame(rows)
    df = df.sort_values("harmonics").reset_index(drop=True)
    df.to_csv(results_csv, index=False)

    log.info(f"Wall time: {time.time()-t_overall:.1f}s ({(time.time()-t_overall)/60:.1f} min)")
    log.info(f"Results CSV: {results_csv}")
    return df


# ---------------------------------------------------------------------------
# Convergence decision
# ---------------------------------------------------------------------------
def decide_NA(out_dir: Path, na_grid: list[int]) -> tuple[int, dict[int, float]]:
    """Smallest NA where max_λ |R_det(NA) - R_det(NA_max)| < SIGMA_FLOOR."""
    NA_ref = max(na_grid)
    traces = out_dir / "traces"

    def _read(NA):
        cfg = sr.SimConfig(harmonics=NA, **CENTRE)
        stem = cfg.filename_stem()
        return pd.read_csv(traces / stem / f"AVG_{stem}.csv")

    df_ref = _read(NA_ref)
    deltas = {NA: float(np.max(np.abs(_read(NA)["R_det"] - df_ref["R_det"]))) for NA in na_grid}

    chosen = next((NA for NA in sorted(na_grid) if deltas[NA] < SIGMA_FLOOR), NA_ref)

    decision_path = out_dir / "decision.txt"
    with decision_path.open("w") as f:
        f.write(f"# Stage 0a decision\n")
        f.write(f"NA_chosen = {chosen}\n")
        f.write(f"sigma_floor = {SIGMA_FLOOR}\n")
        f.write(f"NA_ref = {NA_ref}\n")
        f.write(f"max_abs_delta_vs_NA{NA_ref}:\n")
        for NA in sorted(deltas):
            mark = "  ← chosen" if NA == chosen else ""
            f.write(f"  NA={NA:3d}  max|Δ|={deltas[NA]:.4f}{mark}\n")
    print(f"\nDecision written: {decision_path}\n")
    print(f"  → use NA = {chosen} for Stage 0b, Stage 1, Stage 2, Stage 3.\n")
    return chosen, deltas


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage 0a NA convergence")
    parser.add_argument("--na-grid", default=",".join(map(str, DEFAULT_NA_GRID)),
                        help=f"comma-separated NA values (default: {','.join(map(str, DEFAULT_NA_GRID))})")
    parser.add_argument("--out", default=str(SWEEP_DIR / "runs" / "stage0a_NA_convergence"),
                        help="output directory")
    parser.add_argument("--parallel", type=int, default=1,
                        help="number of worker processes (default: 1)")
    parser.add_argument("--resume", action="store_true",
                        help="skip NAs whose AVG csv already exists")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the plan and exit")
    parser.add_argument("--no-decide", action="store_true",
                        help="skip the decision step (just run sims)")
    args = parser.parse_args(argv)

    na_grid = [int(s.strip()) for s in args.na_grid.split(",") if s.strip()]
    out_dir = Path(args.out)

    df = run_stage(
        na_grid  = na_grid,
        out_dir  = out_dir,
        parallel = args.parallel,
        resume   = args.resume,
        dry_run  = args.dry_run,
    )

    if args.dry_run or args.no_decide or df.empty:
        return 0

    chosen, deltas = decide_NA(out_dir, na_grid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
