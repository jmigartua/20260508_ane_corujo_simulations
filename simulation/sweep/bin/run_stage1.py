#!/usr/bin/env python3
"""run_stage1.py — Stage 1 universal Tier-1 sweep (sample SS_12_3).

Sweeps the three universal-across-samples parameters from
`design/SWEEP_PLAN.md` Tier 1:

    t_oxide_um       ∈ {0, 0.05, 0.10, 0.20, 0.30, 0.50, 0.90}    (7)
    beta_deg         ∈ {1, 2, 5, 10, 20, 30}                       (6)
    oxide_dispersion ∈ {HS_caliente, RS_frio}                      (2)
                                                                  ----
                                                                   84

at NA = 39 (locked by Stage 0a) and phi_sim = 89° (locked by Stage 0b),
against the (sample=12-3, theta=30°, phi_exp=0°) experimental triple.

Usage
-----
    python sweep/bin/run_stage1.py                          # serial, default grid
    python sweep/bin/run_stage1.py --parallel 4             # 4 workers (~2.5 h wall)
    python sweep/bin/run_stage1.py --resume                 # skip done configs
    python sweep/bin/run_stage1.py --dry-run                # print plan, exit

Output
------
    runs/stage1_universals/
        results.csv              one row per (t_oxide, beta, oxide_dispersion)
        decision.txt             best triple + summary
        run.log                  timestamped progress
        traces/<stem>/{LX,LY,AVG}.csv

Decision rule
-------------
    argmin Rdet_chi2_red across all 84 combinations.

Safety rail (DISTANCE.md §6)
----------------------------
    If best Rdet_chi2_red ≫ 1, do NOT proceed to Stage 2. The bottleneck is
    structural (most likely the Cr2O3 phonon model). Discuss before sweeping
    period/depth.
"""
from __future__ import annotations

import argparse
import itertools
import logging
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

HERE      = Path(__file__).resolve().parent           # simulation/sweep/bin
SWEEP_DIR = HERE.parent                                # simulation/sweep
SIM_DIR   = SWEEP_DIR.parent                           # simulation
LIB_DIR   = SIM_DIR / "lib"
sys.path.insert(0, str(LIB_DIR))

import sweep_runner as sr   # noqa: E402

# ---------------------------------------------------------------------------
# Stage 1 — locked from Stage 0a (NA) and Stage 0b (phi_sim)
# ---------------------------------------------------------------------------
CENTRE = dict(
    period_um        = 12.9,
    A_um             = 1.5,
    theta_deg        = 30.0,
    phi_sim_deg      = 89.0,                  # LOCKED by Stage 0b
    harmonics        = 39,                    # LOCKED by Stage 0a
    slices           = 50,
    wavelengths_um   = np.arange(3.0, 25.0, 0.25),
)
DEFAULT_T_OXIDE_GRID    = [0.0, 0.05, 0.10, 0.20, 0.30, 0.50, 0.90]
DEFAULT_BETA_GRID       = [1.0, 2.0, 5.0, 10.0, 20.0, 30.0]
DEFAULT_OXIDE_GRID      = ["HS_caliente", "RS_frio"]
SAMPLE                  = "12-3"
THETA_EXP_DEG           = 30
PHI_EXP_DEG             = 0


def _worker(t_oxide: float, beta: float, oxide: str, output_dir_str: str) -> dict:
    import sys as _sys
    _sys.path.insert(0, str(LIB_DIR))
    import sweep_runner as _sr
    cfg = _sr.SimConfig(
        t_oxide_um       = t_oxide,
        beta_deg         = beta,
        oxide_dispersion = oxide,
        **CENTRE,
    )
    return _sr.run_one_config(
        cfg            = cfg,
        sample         = SAMPLE,
        theta_exp_deg  = THETA_EXP_DEG,
        phi_exp_deg    = PHI_EXP_DEG,
        output_dir     = Path(output_dir_str),
    )


def _config_for(t_oxide, beta, oxide):
    return sr.SimConfig(t_oxide_um=t_oxide, beta_deg=beta, oxide_dispersion=oxide, **CENTRE)


def run_stage(t_oxide_grid: list[float],
              beta_grid: list[float],
              oxide_grid: list[str],
              out_dir: Path,
              parallel: int = 1,
              resume: bool = False,
              dry_run: bool = False) -> pd.DataFrame:
    out_dir.mkdir(parents=True, exist_ok=True)
    traces_dir = out_dir / "traces"
    traces_dir.mkdir(exist_ok=True)

    log = logging.getLogger("stage1")
    fh  = logging.FileHandler(out_dir / "run.log", mode="a")
    fh.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s"))
    log.addHandler(fh)
    log.addHandler(logging.StreamHandler(sys.stdout))
    log.setLevel(logging.INFO)

    grid = list(itertools.product(t_oxide_grid, beta_grid, oxide_grid))
    log.info("=" * 70)
    log.info("Stage 1 — universal Tier-1 sweep")
    log.info(f"  grid              = {len(t_oxide_grid)} × {len(beta_grid)} × {len(oxide_grid)} = {len(grid)} configs")
    log.info(f"  t_oxide_grid      = {t_oxide_grid}")
    log.info(f"  beta_grid         = {beta_grid}")
    log.info(f"  oxide_grid        = {oxide_grid}")
    log.info(f"  parallel          = {parallel}")
    log.info(f"  resume            = {resume}")
    log.info(f"  dry_run           = {dry_run}")
    log.info(f"  output            = {out_dir}")
    log.info(f"  centre params     = "
             f"period={CENTRE['period_um']}µm, A={CENTRE['A_um']}µm, "
             f"NA={CENTRE['harmonics']} (Stage 0a), phi_sim={CENTRE['phi_sim_deg']}° (Stage 0b), "
             f"theta={CENTRE['theta_deg']}°")
    log.info(f"  exp target        = {SAMPLE}, θ={THETA_EXP_DEG}°, φ_exp={PHI_EXP_DEG}°")

    todo = []
    for tox, beta, oxide in grid:
        cfg  = _config_for(tox, beta, oxide)
        stem = cfg.filename_stem()
        avg  = traces_dir / stem / f"AVG_{stem}.csv"
        if resume and avg.exists():
            log.info(f"  [{tox:.2f}, {beta:5.1f}, {oxide}]: AVG csv exists → skip")
        else:
            todo.append((tox, beta, oxide))

    if dry_run:
        log.info(f"DRY RUN — would compute {len(todo)} configs")
        return pd.DataFrame()

    rows: list[dict] = []
    t_overall = time.time()

    if parallel <= 1:
        for tox, beta, oxide in todo:
            log.info(f"  [{tox:.2f}, {beta:5.1f}, {oxide}]: starting …")
            t0 = time.time()
            row = _worker(tox, beta, oxide,
                          str(traces_dir / _config_for(tox, beta, oxide).filename_stem()))
            rows.append(row)
            log.info(
                f"  [{tox:.2f}, {beta:5.1f}, {oxide}]: χ²_red(R_det)={row['Rdet_chi2_red']:8.2f}  "
                f"RMSE={row['Rdet_RMSE']:.4f}  pearson={row['Rdet_pearson_r']:.4f}  "
                f"runtime={time.time()-t0:.1f}s"
            )
    else:
        log.info(f"Spawning {parallel} workers …")
        with ProcessPoolExecutor(max_workers=parallel) as pool:
            jobs = {
                pool.submit(
                    _worker, tox, beta, oxide,
                    str(traces_dir / _config_for(tox, beta, oxide).filename_stem())
                ): (tox, beta, oxide)
                for tox, beta, oxide in todo
            }
            done = 0
            for fut in as_completed(jobs):
                tox, beta, oxide = jobs[fut]
                done += 1
                try:
                    row = fut.result()
                    rows.append(row)
                    log.info(
                        f"  [{done:2d}/{len(todo)}] [{tox:.2f}, {beta:5.1f}, {oxide}]: "
                        f"χ²_red(R_det)={row['Rdet_chi2_red']:8.2f}  "
                        f"RMSE={row['Rdet_RMSE']:.4f}  pearson={row['Rdet_pearson_r']:.4f}"
                    )
                except Exception as e:
                    log.error(f"  [{tox:.2f}, {beta:5.1f}, {oxide}]: FAILED — {e}")

    results_csv = out_dir / "results.csv"
    if resume and results_csv.exists():
        prior = pd.read_csv(results_csv)
        df    = pd.concat([prior, pd.DataFrame(rows)]).drop_duplicates(
            ["t_oxide_um", "beta_deg", "oxide_dispersion"], keep="last"
        )
    else:
        df    = pd.DataFrame(rows)
    df = df.sort_values(["oxide_dispersion", "t_oxide_um", "beta_deg"]).reset_index(drop=True)
    df.to_csv(results_csv, index=False)

    log.info(f"Wall time: {time.time()-t_overall:.1f}s ({(time.time()-t_overall)/60:.1f} min)")
    log.info(f"Results CSV: {results_csv}")
    return df


def decide_best(out_dir: Path) -> tuple[dict, pd.Series]:
    df = pd.read_csv(out_dir / "results.csv")
    best_idx = df["Rdet_chi2_red"].idxmin()
    best = df.loc[best_idx]
    triple = {
        "t_oxide_um":       float(best["t_oxide_um"]),
        "beta_deg":         float(best["beta_deg"]),
        "oxide_dispersion": str(best["oxide_dispersion"]),
        "Rdet_chi2_red":    float(best["Rdet_chi2_red"]),
        "Rdet_RMSE":        float(best["Rdet_RMSE"]),
        "Rdet_pearson_r":   float(best["Rdet_pearson_r"]),
    }
    decision_path = out_dir / "decision.txt"
    with decision_path.open("w") as f:
        f.write(f"# Stage 1 decision — universal Tier-1 best\n")
        f.write(f"t_oxide_um       = {triple['t_oxide_um']}\n")
        f.write(f"beta_deg         = {triple['beta_deg']}\n")
        f.write(f"oxide_dispersion = {triple['oxide_dispersion']}\n")
        f.write(f"Rdet_chi2_red    = {triple['Rdet_chi2_red']:.4f}\n")
        f.write(f"Rdet_RMSE        = {triple['Rdet_RMSE']:.4f}\n")
        f.write(f"Rdet_pearson_r   = {triple['Rdet_pearson_r']:.4f}\n")
        f.write(f"\n# Top 5 by chi2_red\n")
        top = df.nsmallest(5, "Rdet_chi2_red")[
            ["t_oxide_um", "beta_deg", "oxide_dispersion",
             "Rdet_chi2_red", "Rdet_RMSE", "Rdet_pearson_r"]
        ]
        f.write(top.to_string(index=False))
        f.write("\n")
        if triple["Rdet_chi2_red"] > 5:
            f.write(f"\n# WARNING: best chi2_red = {triple['Rdet_chi2_red']:.1f} >> 1\n")
            f.write(f"# Per DISTANCE.md §6, do NOT proceed to Stage 2.\n")
            f.write(f"# Bottleneck is structural (probably oxide-dispersion phonon model).\n")
    print(f"\nDecision written: {decision_path}\n")
    print(f"  → best triple: t_oxide={triple['t_oxide_um']} µm, "
          f"β={triple['beta_deg']}°, oxide={triple['oxide_dispersion']}\n"
          f"  → χ²_red = {triple['Rdet_chi2_red']:.2f}\n")
    return triple, best


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Stage 1 universal Tier-1 sweep")
    p.add_argument("--t-oxide-grid",    default=",".join(f"{x:g}" for x in DEFAULT_T_OXIDE_GRID))
    p.add_argument("--beta-grid",       default=",".join(f"{x:g}" for x in DEFAULT_BETA_GRID))
    p.add_argument("--oxide-grid",      default=",".join(DEFAULT_OXIDE_GRID))
    p.add_argument("--out",             default=str(SWEEP_DIR / "runs" / "stage1_universals"))
    p.add_argument("--parallel",        type=int, default=1)
    p.add_argument("--resume",          action="store_true")
    p.add_argument("--dry-run",         action="store_true")
    p.add_argument("--no-decide",       action="store_true")
    args = p.parse_args(argv)

    t_oxide_grid = [float(s.strip()) for s in args.t_oxide_grid.split(",") if s.strip()]
    beta_grid    = [float(s.strip()) for s in args.beta_grid.split(",")    if s.strip()]
    oxide_grid   = [s.strip()        for s in args.oxide_grid.split(",")   if s.strip()]
    out_dir = Path(args.out)

    df = run_stage(
        t_oxide_grid = t_oxide_grid,
        beta_grid    = beta_grid,
        oxide_grid   = oxide_grid,
        out_dir      = out_dir,
        parallel     = args.parallel,
        resume       = args.resume,
        dry_run      = args.dry_run,
    )

    if args.dry_run or args.no_decide or df.empty:
        return 0

    decide_best(out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
