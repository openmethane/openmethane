"""Where in the column the monthly run's drift accumulates.

    python3 drift_profile.py

Needs, locally:
  - the 30 daily CGRID files from the #244 baseline arm, an emissions-at-prior
    forward-only run over June 2024, under
    `<sandbox>/aust10km/experiment-244/baseline/CGRID.<YYYYMMDD>.nc`
    (s3://om-dev-results/tests/b46a78d2-.../run-cmaq/output/)
  - the daily CAMS ICON files under
    `<sandbox>/aust10km/monthly/2024/06/aust10km/daily/2024/06/<dd>/cmaq/...`

That arm's bias correction is byte-identical to the production monthly run's
(icon_bias 0.120333, emissions_bias 0.000839, mean operator weight 0.96542), and
it read the same staged inputs, so its state is the production run's state.

CGRID holds the field at the end of each day; ICON holds the CAMS field that
morning. Differencing them by layer shows how far the running model has drifted
from the data that drives it, and where.

Only the first day's ICON was bias-corrected -- `bias_correct_cams.py` corrects
`icon_files[0]` and every BCON -- so days 2 onwards need the correction added
before they can be compared with the model.
"""

import os
import pathlib
import sys

import netCDF4
import numpy as np


def _required_dir(variable, what):
    """Resolve a directory the caller has to point at, or say so clearly."""
    value = os.environ.get(variable)
    if not value:
        raise SystemExit(
            f"set {variable} to {what}. See README.md in this directory for the "
            "archive paths these are downloaded from."
        )
    path = pathlib.Path(value)
    if not path.is_dir():
        raise SystemExit(f"{variable}={value} is not a directory")
    return path


CACHE = pathlib.Path(os.environ.get("OM_CACHE", pathlib.Path.home() / ".cache/openmethane"))

CORRECTION_PPB = 1e3 * (0.120333 - 0.000839)
PPM2PPB = 1e3

VGLVLS = np.array(
    [
        1.0,
        0.9938145,
        0.9859505,
        0.9760142,
        0.9635575,
        0.9480932,
        0.9291238,
        0.9061912,
        0.87894243,
        0.84720796,
        0.8110778,
        0.77094895,
        0.7275254,
        0.6817555,
        0.63450354,
        0.5860305,
        0.5366501,
        0.48673007,
        0.4366881,
        0.38698772,
        0.33812758,
        0.29062968,
        0.24502261,
        0.20182164,
        0.16150628,
        0.12705372,
        0.09814423,
        0.07388596,
        0.05353061,
        0.03645026,
        0.0221179,
        0.01009149,
        0.0,
    ]
)
DSIGMA = VGLVLS[:-1] - VGLVLS[1:]
VGTOP, PSURF = 5000.0, 98890.0  # PSURF is the observation-mean, for labelling only
PMID = (0.5 * (VGLVLS[:-1] + VGLVLS[1:]) * (PSURF - VGTOP) + VGTOP) / 100

BANDS = [
    (0, 20, "0-19   surface to ~330 hPa"),
    (20, 24, "20-23  330-160 hPa"),
    (24, 29, "24-28  160-85 hPa"),
    (29, 32, "29-31  85-50 hPa"),
]


def layer_means(path, cell_weight=None, variable="CH4"):
    """Domain-mean profile, or a mean weighted by where the soundings fall.

    The flat domain mean counts ocean and cloudy corners of the grid that the
    inversion never sees; weighting by the observation count per cell gives the
    profile the simulated columns are actually built from, and it is that one
    that matches the drift measured against the observations.
    """
    with netCDF4.Dataset(path) as ds:
        ds.set_auto_mask(False)
        field = np.squeeze(ds[variable][:]) * PPM2PPB
    if cell_weight is None:
        return field.reshape(field.shape[0], -1).mean(1)
    return (field * cell_weight[np.newaxis, :, :]).sum(axis=(1, 2))


def observation_density(cache, shape):
    """Share of the month's soundings falling in each grid cell.

    Sized from the model grid, not from the observations: the soundings do not
    reach every row and column, and the empty margin has to stay in the array
    for it to line up with the model field.
    """
    density = np.zeros(shape)
    np.add.at(density, (cache["row"].astype(int), cache["col"].astype(int)), 1.0)
    return density / density.sum()


def main(sampled=False):
    sandbox = _required_dir("OM_SANDBOX", "the downloaded run archives for one domain")
    cgrid_dir = sandbox / "experiment-244/baseline"
    icon_dir = sandbox / "monthly/2024/06/aust10km/daily/2024/06"
    cache = np.load(CACHE / "misfit_06.npz")
    weights = cache["vis"].astype(float).mean(0)
    density = None

    drift = {}
    for day in range(1, 31):
        cgrid = cgrid_dir / f"CGRID.202406{day:02d}.nc"
        icon = icon_dir / f"{day:02d}/cmaq/2024-06-{day:02d}/d01/ICON.d01.aust10km_v1.CH4only.nc"
        if not (cgrid.exists() and icon.exists()):
            continue
        if sampled and density is None:
            with netCDF4.Dataset(cgrid) as ds:
                density = observation_density(cache, np.squeeze(ds["CH4"][:]).shape[1:])
        # day 1's ICON was corrected in place; later days' were not
        reference = layer_means(icon, density) + (0.0 if day == 1 else CORRECTION_PPB)
        drift[day] = layer_means(cgrid, density) - reference

    days = np.array(sorted(drift), float)
    where = "sampled where the soundings are" if sampled else "domain mean"
    print(f"Monthly run minus the CAMS field driving it, by layer, {where} (ppb)\n")
    sample = [d for d in (1, 5, 10, 15, 20, 25, 30) if d in drift]
    print(f"{'lay':>4} {'p(hPa)':>8} " + "".join(f"{'d' + str(d):>9}" for d in sample))
    for layer in range(31, -1, -1):
        row = "".join(f"{drift[d][layer]:9.1f}" for d in sample)
        print(f"{layer:4d} {PMID[layer]:8.1f} {row}")

    print("\nColumn effect of that drift (ppb of simulated column)\n")
    header = f"{'day':>4} " + "".join(f"{name.split()[0]:>12}" for _, _, name in BANDS)
    print(header + f"{'total':>12}{'mass-wtd':>12}")
    for day in sorted(drift):
        parts = [float((weights[a:b] * drift[day][a:b]).sum()) for a, b, _ in BANDS]
        total = float((weights * drift[day]).sum())
        mass = float((DSIGMA * drift[day]).sum())
        print(f"{day:4d} " + "".join(f"{p:12.3f}" for p in parts) + f"{total:12.3f}{mass:12.3f}")

    print("\nTrends over the month (ppb of column per day)\n")
    for a, b, name in BANDS:
        series = np.array([float((weights[a:b] * drift[d][a:b]).sum()) for d in sorted(drift)])
        slope = np.polyfit(days, series, 1)[0]
        print(
            f"  {name:28s} {slope:+8.4f}   "
            f"(day 1 {series[0]:+7.2f} -> day 30 {series[-1]:+7.2f})"
        )
    total = np.array([float((weights * drift[d]).sum()) for d in sorted(drift)])
    mass = np.array([float((DSIGMA * drift[d]).sum()) for d in sorted(drift)])
    for name, series in (("operator-weighted total", total), ("mass-weighted total", mass)):
        slope, intercept = np.polyfit(days, series, 1)
        scatter = np.std(series - np.polyval((slope, intercept), days))
        print(
            f"  {name:28s} {slope:+8.4f}   (day 1 {series[0]:+7.2f} -> day 30 {series[-1]:+7.2f},"
            f" scatter {scatter:.2f})"
        )


if __name__ == "__main__":
    # --sampled weights each cell by how many soundings it holds, which is the
    # figure quoted in the issue; the default is the flat domain mean
    main(sampled="--sampled" in sys.argv)
