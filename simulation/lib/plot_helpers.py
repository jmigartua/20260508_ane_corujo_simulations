"""plot_helpers.py — reusable comparison-plot routine for single-config drivers.

Kept separate from sweep_runner.py so the numerical core stays free of
matplotlib (faster import, easier to test). Used by simulate.qmd and any
stage qmd that wants to show a single-config result without re-implementing
the figure layout.
"""

from __future__ import annotations
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.interpolate import interp1d


# Apply the LaTeX rcParams once per import. Idempotent.
_LATEX_APPLIED = False
def _ensure_latex_rcparams() -> None:
    global _LATEX_APPLIED
    if _LATEX_APPLIED:
        return
    plt.rcParams.update({
        "text.usetex":     True,
        "font.family":     "serif",
        "font.size":       9,
        "axes.titlesize":  10,
        "axes.labelsize":  10,
        "legend.fontsize": 8,
        "text.latex.preamble": r"\usepackage{amsmath}\usepackage{amssymb}",
    })
    _LATEX_APPLIED = True


# Standard y-axis padding for sim-vs-exp plots (extends slightly below 0 and above 1
# so curves at the boundaries don't visually clip)
Y_PAD = 0.03


def plot_comparison_with_residual(
    sim_avg_path: Path,
    exp_paths: Iterable[Path],
    *,
    observable: str = "R_det",                  # which sim column to use ("R" or "R_det")
    sim_lx_path: Path | None = None,            # optional, for faded LX/LY underlay
    sim_ly_path: Path | None = None,
    sample_label: str = "",
    theta_exp_deg: float = 0,
    phi_exp_deg: float = 0,
    beta_deg: float | None = None,
    figsize: tuple[float, float] = (8.0, 7.0),
    title: str | None = None,
    extra_sim_curves: list[tuple[Path, str]] | None = None,   # [(avg_path, label), …]
) -> tuple[plt.Figure, np.ndarray]:
    """**Standard sim-vs-exp comparison plot** — top panel comparison, bottom panel residual.

    Top panel: sim (mean), experimental ⟨R⟩ ± σ band, optional faded LX/LY.
               y-axis pinned to [-Y_PAD, 1+Y_PAD] so the dynamic range is the
               full physical range, with a small aesthetic margin at top and
               bottom (slightly negative, non-physical, just for breathing room).
    Bottom panel: residual (sim − ⟨R_exp⟩), with a ±σ_exp envelope and a zero line.

    Returns (fig, axes) where axes is shape (2,)."""
    _ensure_latex_rcparams()

    sim_avg = pd.read_csv(sim_avg_path)
    if observable not in sim_avg.columns:
        raise KeyError(f"observable {observable!r} not in {sim_avg_path.name}")
    lam = sim_avg["x"].values

    repeats = _load_experimental_repeats(exp_paths)
    R_stack = np.array([
        interp1d(l, r, bounds_error=False, fill_value=np.nan, assume_sorted=True)(lam)
        for l, r in repeats
    ])
    R_exp_mean = np.nanmean(R_stack, axis=0)
    R_exp_std  = np.nanstd(R_stack, axis=0, ddof=1)

    fig, ax = plt.subplots(2, 1, figsize=figsize, sharex=True, constrained_layout=True,
                           gridspec_kw={"height_ratios": [3, 1.5]})

    # ── TOP — comparison ─────────────────────────────────────────────────
    if sim_lx_path is not None and sim_ly_path is not None:
        df_lx = pd.read_csv(sim_lx_path); df_ly = pd.read_csv(sim_ly_path)
        ax[0].plot(df_lx["x"], df_lx[observable], color="C0", alpha=0.30, lw=1.0,
                   label=rf"$\,(L_x)$" if observable == "R" else rf"$\,(L_x)$")
        ax[0].plot(df_ly["x"], df_ly[observable], color="C3", alpha=0.30, lw=1.0,
                   label=rf"$\,(L_y)$")
    ax[0].fill_between(lam, R_exp_mean - R_exp_std, R_exp_mean + R_exp_std,
                       color="C2", alpha=0.20)
    ax[0].plot(lam, R_exp_mean, color="C2", lw=2.0,
               label=r"$\langle R \rangle_{\mathrm{exp}}\!\pm\!\sigma$")
    ax[0].plot(lam, sim_avg[observable], color="black", lw=2.2,
               label=r"$\langle R \rangle_{\mathrm{sim}}$" if observable == "R"
                     else r"$\langle R_{\mathrm{det}} \rangle_{\mathrm{sim}}$")
    if extra_sim_curves:
        cmap = plt.cm.plasma
        for i, (p, lab) in enumerate(extra_sim_curves):
            df_e = pd.read_csv(p)
            ax[0].plot(df_e["x"], df_e[observable],
                       color=cmap(0.15 + 0.7 * i / max(len(extra_sim_curves) - 1, 1)),
                       lw=1.6, ls="--", label=lab)

    ax[0].set_ylim(-Y_PAD, 1.0 + Y_PAD)                # ← new standard
    ax[0].set_ylabel(rf"$R_{{\mathrm{{tot}}}}$" if observable == "R"
                     else rf"$R_{{\mathrm{{det}}}}\,(\beta={beta_deg:g}^{{\circ}})$"
                          if beta_deg is not None else r"$R_{\mathrm{det}}$")
    if title is None:
        sample_tex = sample_label.replace("_", r"\_") if sample_label else ""
        title = (rf"SS\_{sample_tex}, $\theta={theta_exp_deg:.0f}^{{\circ}}$, "
                 rf"$\varphi_{{\mathrm{{exp}}}}={phi_exp_deg:g}^{{\circ}}$"
                 if sample_label else "Comparison")
    ax[0].set_title(title)
    ax[0].grid(True, alpha=0.4)
    ax[0].legend(loc="lower right", framealpha=0.88, ncol=1)

    # ── BOTTOM — residual ────────────────────────────────────────────────
    residual = sim_avg[observable].values - R_exp_mean
    ax[1].fill_between(lam, -R_exp_std, +R_exp_std,
                       color="C2", alpha=0.20, label=r"$\pm\sigma_{\mathrm{exp}}$")
    ax[1].axhline(0, color="C2", lw=1.0, alpha=0.6)
    ax[1].plot(lam, residual, color="black", lw=1.5,
               label=r"$R_{\mathrm{sim}} - \langle R \rangle_{\mathrm{exp}}$")
    if extra_sim_curves:
        cmap = plt.cm.plasma
        for i, (p, lab) in enumerate(extra_sim_curves):
            df_e = pd.read_csv(p)
            res_e = df_e[observable].values - R_exp_mean
            ax[1].plot(df_e["x"], res_e,
                       color=cmap(0.15 + 0.7 * i / max(len(extra_sim_curves) - 1, 1)),
                       lw=1.2, ls="--")

    # symmetric y-range with small padding
    ymax = float(np.nanmax(np.abs(residual)))
    ax[1].set_ylim(-1.1 * ymax, 1.1 * ymax)
    ax[1].set_xlabel(r"$\lambda\;[\mu\mathrm{m}]$")
    ax[1].set_ylabel(r"$\Delta R$")
    ax[1].grid(True, alpha=0.4)
    ax[1].legend(loc="lower right", framealpha=0.88, fontsize=8)

    return fig, ax


def _load_experimental_repeats(exp_paths: Iterable[Path]) -> list[tuple[np.ndarray, np.ndarray]]:
    out = []
    for f in exp_paths:
        raw = pd.read_csv(f, header=None, names=["wn", "R_pct"])
        raw = raw[raw["R_pct"] > 0].copy()
        raw["lambda_um"] = 1e4 / raw["wn"]
        raw["R"] = raw["R_pct"] / 100.0
        raw = raw.sort_values("lambda_um").reset_index(drop=True)
        out.append((raw["lambda_um"].values, raw["R"].values))
    return out


def plot_sim_vs_exp(
    sim_lx_path: Path,
    sim_ly_path: Path,
    sim_avg_path: Path,
    exp_paths: Iterable[Path],
    *,
    sample_label: str = "",
    theta_exp_deg: float = 0,
    phi_exp_deg: float = 0,
    beta_deg: float = 2.0,
    figsize: tuple[float, float] = (7.5, 6.5),
) -> tuple[plt.Figure, np.ndarray]:
    """Render the canonical 2-row comparison figure (R_tot above, R_det below).

    Polarisations are drawn faded (alpha 0.30); the simulation mean is bold
    black; the experimental ⟨R⟩ ± σ band is green. LaTeX (Computer Modern)
    rendering throughout. Returns (fig, axes)."""
    _ensure_latex_rcparams()

    df_lx  = pd.read_csv(sim_lx_path)
    df_ly  = pd.read_csv(sim_ly_path)
    df_avg = pd.read_csv(sim_avg_path)

    repeats = _load_experimental_repeats(exp_paths)
    R_stack = np.array([
        interp1d(l, r, bounds_error=False, fill_value=np.nan, assume_sorted=True)(df_avg["x"].values)
        for l, r in repeats
    ])
    R_exp_mean = np.nanmean(R_stack, axis=0)
    R_exp_std  = np.nanstd(R_stack, axis=0, ddof=1)

    fig, ax = plt.subplots(2, 1, figsize=figsize, sharex=True, constrained_layout=True)

    # Escape underscores in the sample label so usetex doesn't subscript them
    sample_tex = sample_label.replace("_", r"\_") if sample_label else ""
    title_top = (
        rf"Total reflectance --- SS\_{sample_tex}, "
        rf"$\theta={theta_exp_deg:.0f}^{{\circ}}$, $\varphi_{{\mathrm{{exp}}}}={phi_exp_deg:g}^{{\circ}}$"
        if sample_label else r"Total reflectance"
    )
    title_bot = rf"Detected reflectance --- within $\pm\beta/2$ of specular, $\beta={beta_deg:g}^{{\circ}}$"

    # TOP — total reflectance
    ax[0].plot(df_lx["x"], df_lx["R"], color="C0", alpha=0.30, lw=1.0, label=r"$R\,(L_x)$")
    ax[0].plot(df_ly["x"], df_ly["R"], color="C3", alpha=0.30, lw=1.0, label=r"$R\,(L_y)$")
    ax[0].fill_between(df_avg["x"], R_exp_mean - R_exp_std, R_exp_mean + R_exp_std,
                       color="C2", alpha=0.20)
    ax[0].plot(df_avg["x"], R_exp_mean, color="C2", lw=2.0,
               label=r"$\langle R \rangle_{\mathrm{exp}}\!\pm\!\sigma$")
    ax[0].plot(df_avg["x"], df_avg["R"], color="black", lw=2.2,
               label=r"$\langle R \rangle_{\mathrm{sim}}$")
    ax[0].set_ylabel(r"$R_{\mathrm{tot}}$")
    ax[0].set_title(title_top)
    ax[0].grid(True, alpha=0.4)
    ax[0].legend(loc="lower right", framealpha=0.88, ncol=1)

    # BOTTOM — detected reflectance
    ax[1].plot(df_lx["x"], df_lx["R_det"], color="C0", alpha=0.30, lw=1.0, label=r"$R_{\mathrm{det}}\,(L_x)$")
    ax[1].plot(df_ly["x"], df_ly["R_det"], color="C3", alpha=0.30, lw=1.0, label=r"$R_{\mathrm{det}}\,(L_y)$")
    ax[1].fill_between(df_avg["x"], R_exp_mean - R_exp_std, R_exp_mean + R_exp_std,
                       color="C2", alpha=0.20)
    ax[1].plot(df_avg["x"], R_exp_mean, color="C2", lw=2.0,
               label=r"$\langle R \rangle_{\mathrm{exp}}\!\pm\!\sigma$")
    ax[1].plot(df_avg["x"], df_avg["R_det"], color="black", lw=2.2,
               label=r"$\langle R_{\mathrm{det}} \rangle_{\mathrm{sim}}$")
    ax[1].set_xlabel(r"$\lambda\;[\mu\mathrm{m}]$")
    ax[1].set_ylabel(rf"$R_{{\mathrm{{det}}}}\,(\beta={beta_deg:g}^{{\circ}})$")
    ax[1].set_title(title_bot)
    ax[1].grid(True, alpha=0.4)
    ax[1].legend(loc="lower right", framealpha=0.88, ncol=1)

    return fig, ax
