# Experimental FTIR reflectance data

Read-only snapshot of Ane's measured reflectance — 321 CSV files used as
ground truth for the RCWA distance metric in
[`../../simulation/design/DISTANCE.md`](../../simulation/design/DISTANCE.md).

## Source

Copied 2026-05-08 from
`/Users/User/Desktop/2026/20260300/20260311_01_ane_corujo_pruebas_TFM/20260401_reflectividad/_ane_corujo/00_data/`
(Ane's FTIR data area). Original `00_data/` left untouched. Files marked
`a-w` (read-only) so the project doesn't accidentally mutate the snapshot.

## Naming convention

```
<sample>_<theta>_<phi>_<repeat>.CSV
```

| Token | Values | Meaning |
|---|---|---|
| sample | `6-1`, `6-3`, `12-1`, `12-3`, `18-1`, `18-3` | nominal `period-depth` (µm) |
| theta | `30`, `45`, `60` | incidence polar angle (°) |
| phi | `0`, `22-5`, `45`, `67-5`, `90` | azimuth (° — half-degrees rendered with hyphen) |
| repeat | `1`, `2`, `3` | repeat index |

Plus reference files: `Sustrato_pulido_*`, `Sustrato_sin_pulir_*`,
`background_*`, `aire_*`, `wolframio_*`, `prueba*` (the latter are
debugging traces).

## File format

Two columns, no header:

```
wavenumber [cm⁻¹], reflectance [%]
```

The first row of every file is a sentinel (R = 0 at the first wavenumber)
— our loader drops it. Convert wavelength via `λ[µm] = 10000 / ν̃[cm⁻¹]`.

## Coverage

| Sample | Geometries | Repeats | Files |
|---|---:|---:|---:|
| 6-1, 6-3, 12-1, 12-3, 18-1, 18-3 | 3 θ × 5 φ = 15 | 3 | 6 × 15 × 3 = **270** grating measurements |
| references | — | — | **51** auxiliary |
| **total** | | | **321** |

## How code reads it

`simulation/lib/sweep_runner.py` resolves this via:

```python
EXP_DIR = PROJECT_ROOT / "data" / "experimental"
files, repeats = sweep_runner.load_experimental_repeats(sample, theta, phi_exp)
```

— file-relative resolution, so it works regardless of where you invoke from.
