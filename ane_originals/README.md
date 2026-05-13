# Ane's original work — read-only reference

These are Ane Corujo Arteche's actual files, kept verbatim as historical
reference. **Do not edit.** Active work uses
[`../simulation/lib/sweep_runner.py`](../simulation/lib/sweep_runner.py)
and the related notebooks in [`../simulation/`](../simulation/).

## Files

| File | What |
|---|---|
| [`test8.qmd`](test8.qmd) | Verbatim conversion of Ane's `Test8_full (1).ipynb`, the "Programa principal" she sent on 2026-05-08. The simulation cell has been very lightly edited (extended wavelength range to 3–25 µm; loop over both polarisations LX / LY automatically) — those changes are flagged with `# [BOLU]`. Everything else is hers. |
| [`representacion.qmd`](representacion.qmd) | Conversion of her `Representacion.ipynb`. Loads experimental + simulation CSVs from disk and overlays them. Most cells reference data folders that don't exist locally — kept as a record of how she did the analysis before we rebuilt it. |

## Original `.ipynb` source

The original notebooks (with output cells, etc.) live at
[`../20260508_messages/`](../20260508_messages/) — that folder is
untouched and is the canonical archive of her email of 2026-05-08.

## Re-rendering

These files are **outside** the `simulation/` Quarto project, so
`quarto render simulation/` does not touch them. If you want to render
them anyway, do it manually from the project root:

```bash
quarto render ane_originals/test8.qmd
```

`test8.qmd` has its `pd.read_csv('./SS_letter.csv')` style paths preserved
verbatim — they assume cwd is `simulation/` (where a compatibility symlink
exists), so render with:

```bash
cd simulation && quarto render ../ane_originals/test8.qmd
```

— or just don't run it. The numerical equivalent of `test8.qmd` is
[`../simulation/exploratory/simulate.qmd`](../simulation/exploratory/simulate.qmd),
which lives inside the active Quarto project.
