#!/usr/bin/env python3
"""run_stage0b.py — Stage 0b φ-convention sanity check (sample SS_12_3).

Ratifies (or refutes) Ane's claim that simulation-side `phi_sim = 89°`
corresponds to experimental `phi_exp = 0°`. We run the same configuration
at four phi_sim values — {0°, 1°, 89°, 90°} — and pick the one whose R_det
best matches the φ_exp = 0° experimental triple. See ../../design/DISTANCE.md
§9 and ../../design/SWEEP_PLAN.md "Stage 0b".

Uses NA = 39 (locked by Stage 0a).

Usage
-----
    python sweep/bin/run_stage0b.py                          # serial, default phi grid
    python sweep/bin/run_stage0b.py --parallel 4             # 4 workers
    python sweep/bin/run_stage0b.py --phi-grid 0,90          # custom grid
    python sweep/bin/run_stage0b.py --resume                 # skip configs whose AVG csv exists
    python sweep/bin/run_stage0b.py --dry-run                # print plan, don't execute

Output
------
    runs/stage0b_phi_convention/
        results.csv                       one row per phi_sim, sweep-cube schema
        decision.txt                      chosen phi_sim + summary table
        run.log                           timestamped progress log
        traces/<stem>/{LX,LY,AVG}.csv     simulation traces per phi_sim

Decision rule
-------------
    Pick the phi_sim with the smallest Rdet_chi2_red against the
    {sample, theta=30, phi_exp=0} experimental triple. That phi_sim
    is the simulation azimuth equivalent to phi_exp = 0°.
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

HERE      = Path(__file__).resolve().parent           # simulation/sweep/bin
SWEEP_DIR = HERE.parent                                # simulation/sweep
SIM_DIR   = SWEEP_DIR.parent                           # simulation
LIB_DIR   = SIM_DIR / "lib"
sys.path.insert(0, str(LIB_DIR))

import sweep_runner as sr   # noqa: E402

# ---------------------------------------------------------------------------
# Stage 0b — same centre as 0a, with NA=39 locked by 0a's decision
# ---------------------------------------------------------------------------
CENTRE = dict(
    period_um        = 12.9,
    A_um             = 1.5,
    t_oxide_um       = 0.30,
    oxide_dispersion = "HS_caliente",
    theta_deg        = 30.0,
    harmonics        = 39,                   # LOCKED by Stage 0a (max|Δ|=0.0063 < σ_floor)
    slices           = 50,
    beta_deg         = 2.0,
    wavelengths_um   = np.arange(3.0, 25.0, 0.25),
)
DEFAULT_PHI_GRID = [0.0, 1.0, 89.0, 90.0]
SAMPLE          = "12-3"
THETA_EXP_DEG   = 30
PHI_EXP_DEG     = 0


def _worker(phi_sim_deg: float, output_dir_str: str) -> dict:
    """Run one configuration. Re-imports module locally for ProcessPool safety."""
    import sys as _sys
    _sys.path.insert(0, str(LIB_DIR))
    import sweep_runner as _sr
    cfg = _sr.SimConfig(phi_sim_deg=phi_sim_deg, **CENTRE)
    return _sr.run_one_config(
        cfg            = cfg,
        sample         = SAMPLE,
        theta_exp_deg  = THETA_EXP_DEG,
        phi_exp_deg    = PHI_EXP_DEG,
        output_dir     = Path(output_dir_str),
    )


def run_stage(phi_grid: list[float],
              out_dir: Path,
              parallel: int = 1,
              resume: bool = False,
              dry_run: bool = False) -> pd.DataFrame:
    out_dir.mkdir(parents=True, exist_ok=True)
    traces_dir = out_dir / "traces"
    traces_dir.mkdir(exist_ok=True)

    log = logging.getLogger("stage0b")
    fh  = logging.FileHandler(out_dir / "run.log", mode="a")
    fh.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s"))
    log.addHandler(fh)
    log.addHandler(logging.StreamHandler(sys.stdout))
    log.setLevel(logging.INFO)

    log.info("=" * 70)
    log.info("Stage 0b — φ-convention sanity check")
    log.info(f"  phi grid          = {phi_grid}")
    log.info(f"  parallel          = {parallel}")
    log.info(f"  resume            = {resume}")
    log.info(f"  dry_run           = {dry_run}")
    log.info(f"  output            = {out_dir}")
    log.info(f"  centre params     = "
             f"period={CENTRE['period_um']}µm, A={CENTRE['A_um']}µm, "
             f"t_oxide={CENTRE['t_oxide_um']}µm, NA={CENTRE['harmonics']} (locked by 0a), "
             f"theta={CENTRE['theta_deg']}°, oxide={CENTRE['oxide_dispersion']}, beta={CENTRE['beta_deg']}°")
    log.info(f"  exp target        = {SAMPLE}, θ={THETA_EXP_DEG}°, φ_exp={PHI_EXP_DEG}°")

    todo = []
    for phi in phi_grid:
        cfg  = sr.SimConfig(phi_sim_deg=phi, **CENTRE)
        stem = cfg.filename_stem()
        avg  = traces_dir / stem / f"AVG_{stem}.csv"
        if resume and avg.exists():
            log.info(f"  φ_sim={phi:5.1f}°: AVG csv exists → skip")
        else:
            todo.append(phi)

    if dry_run:
        log.info(f"DRY RUN — would compute φ_sim = {todo}")
        return pd.DataFrame()

    rows: list[dict] = []
    t_overall = time.time()

    if parallel <= 1:
        for phi in todo:
            log.info(f"  φ_sim={phi:5.1f}°: starting …")
            t0 = time.time()
            row = _worker(phi, str(traces_dir / sr.SimConfig(phi_sim_deg=phi, **CENTRE).filename_stem()))
            rows.append(row)
            log.info(
                f"  φ_sim={phi:5.1f}°: χ²_red(R_det)={row['Rdet_chi2_red']:7.2f}  "
                f"RMSE={row['Rdet_RMSE']:.4f}  pearson={row['Rdet_pearson_r']:.4f}  "
                f"runtime={time.time()-t0:.1f}s"
            )
    else:
        log.info(f"Spawning {parallel} workers …")
        with ProcessPoolExecutor(max_workers=parallel) as pool:
            jobs = {
                pool.submit(
                    _worker, phi,
                    str(traces_dir / sr.SimConfig(phi_sim_deg=phi, **CENTRE).filename_stem())
                ): phi
                for phi in todo
            }
            for fut in as_completed(jobs):
                phi = jobs[fut]
                try:
                    row = fut.result()
                    rows.append(row)
                    log.info(
                        f"  φ_sim={phi:5.1f}°: χ²_red(R_det)={row['Rdet_chi2_red']:7.2f}  "
                        f"RMSE={row['Rdet_RMSE']:.4f}  pearson={row['Rdet_pearson_r']:.4f}"
                    )
                except Exception as e:
                    log.error(f"  φ_sim={phi:5.1f}°: FAILED — {e}")

    results_csv = out_dir / "results.csv"
    if resume and results_csv.exists():
        prior = pd.read_csv(results_csv)
        df    = pd.concat([prior, pd.DataFrame(rows)]).drop_duplicates("phi_sim_deg", keep="last")
    else:
        df    = pd.DataFrame(rows)
    df = df.sort_values("phi_sim_deg").reset_index(drop=True)
    df.to_csv(results_csv, index=False)

    log.info(f"Wall time: {time.time()-t_overall:.1f}s ({(time.time()-t_overall)/60:.1f} min)")
    log.info(f"Results CSV: {results_csv}")
    return df


def decide_phi(out_dir: Path, phi_grid: list[float]) -> tuple[float, dict[float, float]]:
    """phi_sim with smallest Rdet_chi2_red wins."""
    df = pd.read_csv(out_dir / "results.csv")
    chi2 = {float(row["phi_sim_deg"]): float(row["Rdet_chi2_red"]) for _, row in df.iterrows()}
    chosen = min(chi2, key=chi2.get)

    decision_path = out_dir / "decision.txt"
    with decision_path.open("w") as f:
        f.write(f"# Stage 0b decision\n")
        f.write(f"phi_sim_chosen = {chosen}  (corresponds to phi_exp = {PHI_EXP_DEG}°)\n")
        f.write(f"NA_locked = {CENTRE['harmonics']}\n")
        f.write(f"\n")
        f.write(f"chi2_red(R_det) per phi_sim:\n")
        for phi in sorted(chi2):
            mark = "  ← chosen" if phi == chosen else ""
            f.write(f"  φ_sim={phi:5.1f}°  χ²_red={chi2[phi]:7.2f}{mark}\n")
    print(f"\nDecision written: {decision_path}\n")
    print(f"  → phi_sim = {chosen}° corresponds to phi_exp = {PHI_EXP_DEG}°.\n"
          f"     Use this offset for Stage 1 / 2 / 3.\n")
    return chosen, chi2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage 0b φ-convention sanity check")
    parser.add_argument("--phi-grid", default=",".join(f"{p:g}" for p in DEFAULT_PHI_GRID),
                        help=f"comma-separated phi_sim values in degrees (default: {','.join(f'{p:g}' for p in DEFAULT_PHI_GRID)})")
    parser.add_argument("--out", default=str(SWEEP_DIR / "runs" / "stage0b_phi_convention"),
                        help="output directory")
    parser.add_argument("--parallel", type=int, default=1,
                        help="number of worker processes (default: 1)")
    parser.add_argument("--resume", action="store_true",
                        help="skip phi values whose AVG csv already exists")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the plan and exit")
    parser.add_argument("--no-decide", action="store_true",
                        help="skip the decision step (just run sims)")
    args = parser.parse_args(argv)

    phi_grid = [float(s.strip()) for s in args.phi_grid.split(",") if s.strip()]
    out_dir = Path(args.out)

    df = run_stage(
        phi_grid = phi_grid,
        out_dir  = out_dir,
        parallel = args.parallel,
        resume   = args.resume,
        dry_run  = args.dry_run,
    )

    if args.dry_run or args.no_decide or df.empty:
        return 0

    chosen, chi2 = decide_phi(out_dir, phi_grid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
