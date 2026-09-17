"""Does the aerosol dependence in the observed columns follow the light path?

    python3 ../sounding_cache.py 06 && python3 light_path.py 06 01

[#249](https://github.com/openmethane/openmethane/issues/249) measures the
observed column falling about 290 ppb per unit of retrieved SWIR aerosol optical
depth while the simulated column does not move, and leaves open whether that is
the retrieval or real methane that happens to anti-correlate with aerosol.

Geometry separates the two. Aerosol biases a shortwave retrieval by changing how
far the sunlight travelled: photons scattered back by an aerosol layer never
reach the ground, so they miss the methane in the lowest part of the column and
the retrieval reads low. How much of the light that does depends on the aerosol
the light met, which is the optical depth along the slant path rather than
straight up -- so per unit of the *vertical* optical depth the retrieval
reports, the artefact has to grow with the air mass factor. Methane in the air
carries no such dependence: a plume is the same plume whether it is viewed from
directly overhead or from the edge of the swath.

The two halves of the air mass factor make very different tests, so they are
kept apart:

1. The viewing path. Which detector column saw a sounding has nothing to do
   with where the sounding is, so binning by viewing zenith angle varies the
   path with the geography, the land cover and the sources left alone. This is
   the test that can settle it.
2. The solar path. Within one month the sun angle is mostly latitude, which is
   also land cover and sources, so it is only worth reading with latitude held
   fixed -- either inside a latitude band, where what is left is the hour and a
   half of overpass time the swath spans, or between June and January over the
   same ground.

Every slope is fitted inside 200 km, one-day blocks with the block mean
removed: within a block the model field is smooth and cannot vary in step with
one sounding's retrieval. Standard errors are clustered on the block, so the
many soundings sharing one are not counted as independent evidence.

`sounding_cache.py` must have run first, and must have been the version that
records the geometry.
"""

import itertools
import os
import pathlib
import sys

import numpy as np

from analysis.sounding_geometry import viewing_zenith

CACHE = pathlib.Path(os.environ.get("OM_CACHE", pathlib.Path.home() / ".cache/openmethane"))

BLOCK = 20  # 200 km at 10 km cells
MIN_PER_BLOCK = 50
MIN_IN_SUBSET = 20_000

# The middle of the AOD range, used where bins have to be compared at a matched
# optical depth. It holds about three quarters of the soundings.
MATCHED_AOD = (0.010, 0.045)


def load(month):
    """The per-sounding cache, with the geometry worked out."""
    path = CACHE / f"soundings_{month}.npz"
    if not path.exists():
        raise SystemExit(f"missing {path}; run analysis/sounding_cache.py {month} first")
    data = np.load(path)
    if "sza" not in data.files:
        raise SystemExit(
            f"{path} predates the geometry fields; re-run analysis/sounding_cache.py {month}"
        )
    d = {k: data[k].astype(float) for k in data.files}
    d["residual"] = d["obs"] - d["sim"]
    d["day"] = data["day"].astype(int)
    d["sec_sza"] = 1.0 / np.cos(np.radians(d["sza"]))
    d["vza"] = viewing_zenith(d["across_km"])
    d["sec_vza"] = 1.0 / np.cos(np.radians(d["vza"]))
    d["air_mass"] = d["sec_sza"] + d["sec_vza"]
    d["block"] = (
        d["day"].astype(np.int64) * 10**9
        + (data["row"].astype(np.int64) // BLOCK) * 100000
        + (data["col"].astype(np.int64) // BLOCK)
    )
    return d


def blocks(d, subset):
    """Renumber the day/200 km blocks over a subset, dropping the thin ones."""
    rows = np.flatnonzero(subset)
    _, index, count = np.unique(d["block"][rows], return_inverse=True, return_counts=True)
    keep = count[index] >= MIN_PER_BLOCK
    _, index = np.unique(index[keep], return_inverse=True)
    return rows[keep], index


def fixed_effects(index, target, columns):
    """Slopes within block, with standard errors clustered on the block.

    Removing each block's mean is what makes the model field a constant the fit
    cannot see. Clustering the errors on the same blocks stops the hundreds of
    soundings sharing one of them from being read as hundreds of independent
    measurements, which is the difference between an honest error bar here and
    one several times too small.
    """
    count = np.bincount(index)

    def centre(v):
        return v - (np.bincount(index, weights=v) / count)[index]

    design = np.column_stack([centre(c) for c in columns])
    y = centre(target)
    gram = np.linalg.inv(design.T @ design)
    beta = gram @ (design.T @ y)
    scores = design * (y - design @ beta)[:, None]
    per_block = np.stack(
        [np.bincount(index, weights=column, minlength=count.size) for column in scores.T],
        axis=1,
    )
    groups, rows, terms = count.size, len(y), design.shape[1]
    correction = groups / (groups - 1) * (rows - 1) / (rows - terms)
    covariance = gram @ (per_block.T @ per_block) @ gram * correction
    return beta, np.sqrt(np.diag(covariance)), covariance


def slope(d, subset, side="residual", extra=()):
    """ppb per unit AOD within a block, fitted alongside albedo and any extras."""
    rows, index = blocks(d, subset)
    aod = d["aod"][rows]
    columns = [aod, d["albedo"][rows]] + [term(d, rows, aod) for term in extra]
    beta, error, _ = fixed_effects(index, d[side][rows], columns)
    return beta[0], error[0], len(rows)


def curvature(d, subset):
    """The same fit with a quadratic term, to see whether the slope is a slope."""
    rows, index = blocks(d, subset)
    aod = d["aod"][rows]
    beta, error, _ = fixed_effects(index, d["residual"][rows], [aod, aod**2, d["albedo"][rows]])
    return beta[1], error[1]


def bins(d, name, edges, subset=None):
    """Walk bins of some property, yielding the subset each one selects."""
    base = np.ones(len(d["residual"]), bool) if subset is None else subset
    for low, high in itertools.pairwise(edges):
        chosen = base & (d[name] >= low) & (d[name] < high)
        if chosen.sum() >= MIN_IN_SUBSET:
            yield low, high, chosen


def quantile_edges(values, n):
    return np.unique(np.quantile(values, np.linspace(0, 1, n + 1)))


def swath(d, month):
    """The viewing path, with the geography held still."""
    print(f"--- 1. {month}: across the swath ---")
    print("  which detector column saw a sounding is unrelated to where it is, so")
    print("  this varies the light path with the geography left alone")
    print(
        f"  correlation of sec(vza) with latitude: {np.corrcoef(d['sec_vza'], d['lat'])[0, 1]:+.3f}"
    )
    matched = (d["aod"] >= MATCHED_AOD[0]) & (d["aod"] < MATCHED_AOD[1])
    print(
        f"\n  {'viewing zenith':>18s} {'soundings':>10s} {'sec(vza)':>9s} {'AOD':>7s}"
        f" {'observed':>16s} {'simulated':>13s} {'AOD ' + str(MATCHED_AOD):>22s}"
    )
    out = []
    for low, high, chosen in bins(d, "vza", quantile_edges(d["vza"], 5)):
        observed, error, rows = slope(d, chosen, "obs")
        simulated = slope(d, chosen, "sim")[0]
        even, even_error, _ = slope(d, chosen & matched, "obs")
        out.append((d["air_mass"][chosen].mean(), d["sec_vza"][chosen].mean(), observed, error))
        print(
            f"  {low:7.1f}-{high:<10.1f} {rows:10,d} {d['sec_vza'][chosen].mean():9.3f}"
            f" {d['aod'][chosen].mean():7.4f} {observed:10.0f} +/-{error:4.0f}"
            f" {simulated:9.0f} {even:15.0f} +/-{even_error:4.0f}"
        )
    quadratic, quadratic_error = curvature(d, np.ones(len(d["residual"]), bool))
    print(
        f"\n  the AOD response is close to straight, so the bins are comparable:"
        f" quadratic term {quadratic:+,.0f} +/- {quadratic_error:,.0f} ppb per unit AOD squared"
    )
    return out


def sun(d, month, band=(-32, -20)):
    """The solar path, inside one latitude band so that it is not latitude."""
    print(f"\n--- 2. {month}: solar zenith angle inside {band[0]} to {band[1]} deg ---")
    print("  at a fixed latitude the sun angle is the hour and a half of overpass")
    print("  time the swath spans, which has nothing to do with the ground below")
    inside = (d["lat"] >= band[0]) & (d["lat"] < band[1])
    print(
        f"  {inside.sum():,} soundings; correlation of sec(sza) with latitude inside the"
        f" band {np.corrcoef(d['sec_sza'][inside], d['lat'][inside])[0, 1]:+.3f}"
    )
    print(
        f"\n  {'solar zenith':>18s} {'soundings':>10s} {'sec(sza)':>9s} {'sec(vza)':>9s}"
        f" {'AOD':>7s} {'observed':>16s}"
    )
    out = []
    for low, high, chosen in bins(d, "sza", quantile_edges(d["sza"][inside], 4), inside):
        observed, error, rows = slope(d, chosen, "obs")
        out.append((d["air_mass"][chosen].mean(), d["sec_sza"][chosen].mean(), observed, error))
        print(
            f"  {low:7.1f}-{high:<10.1f} {rows:10,d} {d['sec_sza'][chosen].mean():9.3f}"
            f" {d['sec_vza'][chosen].mean():9.3f} {d['aod'][chosen].mean():7.4f}"
            f" {observed:10.0f} +/-{error:4.0f}"
        )
    return out


def interaction(d, month):
    """One fit, with the geometry carried as terms rather than as bins.

    The geometry is all but constant inside a 200 km block on one day, so each
    product term is the aerosol anomaly scaled by the block's own geometry, and
    its coefficient is how much steeper the aerosol slope gets per unit of that
    geometry. Latitude is carried the same way, so the solar term is identified
    from overpass time at a fixed latitude rather than from latitude itself.

    Reported precision is carried alongside for the obvious objection to the
    viewing term: the retrieval is weaker at the swath edge, so an aerosol slope
    that only tracked how badly constrained the retrieval was would look like a
    slope that tracked the viewing path.
    """
    print(f"\n--- 3. {month}: the geometry as terms in one fit ---")
    rows, index = blocks(d, np.ones(len(d["residual"]), bool))
    aod = d["aod"][rows]
    terms = {
        "per unit AOD, at nadir at noon": aod,
        "  x sec(vza) - 1": aod * (d["sec_vza"][rows] - 1.0),
        "  x sec(sza) - 1": aod * (d["sec_sza"][rows] - 1.0),
        "  x latitude + 25 deg": aod * (d["lat"][rows] + 25.0),
        "  x precision - 1.5 ppb": aod * (d["precision"][rows] - 1.5),
        "per unit albedo": d["albedo"][rows],
        "per ppb of precision": d["precision"][rows],
    }
    beta, error, covariance = fixed_effects(index, d["obs"][rows], list(terms.values()))
    print(f"  observed column, {len(rows):,} soundings in {index.max() + 1:,} blocks")
    for name, value, spread in zip(terms, beta, error):
        print(f"    {name:32s} {value:10.0f} +/-{spread:6.0f}  (t={value / spread:5.1f})")

    # The aerosol slope the fit implies where this month's soundings actually
    # sit, which is the number #249 measured; the path terms carry most of it,
    # and they are the difference between the two months.
    here = np.array(
        [
            1.0,
            d["sec_vza"][rows].mean() - 1.0,
            d["sec_sza"][rows].mean() - 1.0,
            d["lat"][rows].mean() + 25.0,
            d["precision"][rows].mean() - 1.5,
            0.0,
            0.0,
        ]
    )
    at_mean = here @ beta
    path = here[1] * beta[1] + here[2] * beta[2]
    print(
        f"\n  at this month's own mean geometry, sec(vza) {d['sec_vza'][rows].mean():.2f} and"
        f" sec(sza) {d['sec_sza'][rows].mean():.2f}:"
        f"\n    {at_mean:10.0f} +/-{np.sqrt(here @ covariance @ here):5.0f} ppb per unit AOD,"
        f" of which the two path terms carry {path:.0f}"
    )


def seasons(loaded, bands=((-45, -35), (-35, -30), (-30, -25), (-25, -20), (-20, -10))):
    """The same ground in each month: same land cover, same sources, different sun."""
    print("\n--- 4. the same latitudes in each month ---")
    print("  the ground, the land cover and the sources are the same; the sun is not")
    header = "".join(f"{month + '/2024':>30s}" for month in loaded)
    print(f"\n  {'latitude':>14s}{header}")
    print(
        f"  {'':>14s}"
        + "".join(f"{'sec(sza)':>10s}{'sec(vza)':>10s}{'ppb / AOD':>10s}" for _ in loaded)
    )
    for low, high in bands:
        line = f"  {low:6.0f}..{high:<6.0f}"
        for d in loaded.values():
            inside = (d["lat"] >= low) & (d["lat"] < high)
            if inside.sum() < MIN_IN_SUBSET:
                line += f"{'-':>10s}{'-':>10s}{'-':>10s}"
                continue
            observed = slope(d, inside, "obs")[0]
            line += (
                f"{d['sec_sza'][inside].mean():10.3f}{d['sec_vza'][inside].mean():10.3f}"
                f"{observed:10.0f}"
            )
        print(line)


def against_path(points, name, label):
    """Is the slope proportional to the path, or flat?

    A light-path artefact is zero when there is no path to modify, so the
    prediction is a line through the origin in the air mass factor. Methane that
    happens to anti-correlate with aerosol predicts a flat line instead.
    """
    path = np.array([p[0 if name == "air mass" else 1] for p in points])
    observed = np.array([p[2] for p in points])
    weight = 1.0 / np.array([p[3] for p in points]) ** 2
    design = np.column_stack([np.ones_like(path), path])
    fit = np.linalg.lstsq(
        design * np.sqrt(weight)[:, None], observed * np.sqrt(weight), rcond=None
    )[0]
    left = observed - design @ fit
    error = np.sqrt(
        np.diag(np.linalg.inv((design * weight[:, None]).T @ design))
        * np.sum(weight * left**2)
        / max(len(path) - 2, 1)
    )
    flat = np.sum(weight * observed) / np.sum(weight)
    print(f"\n  {label}, {len(path)} bins spanning {path.min():.2f} to {path.max():.2f}")
    print(
        f"    slope   {fit[1]:9.0f} +/-{error[1]:6.0f} ppb per unit AOD per unit of {name}"
        f"  (t={fit[1] / error[1]:5.1f})"
    )
    print(f"    at zero {fit[0]:9.0f} +/-{error[0]:6.0f} ppb per unit AOD")
    print(
        f"    weighted sum of squares about a flat line"
        f" {np.sum(weight * (observed - flat) ** 2):8.1f}, about this one"
        f" {np.sum(weight * left**2):8.1f} ({len(path) - 1} and {len(path) - 2} dof)"
    )


def main(months):
    loaded = {}
    viewing, solar = [], []
    for month in months:
        d = load(month)
        loaded[month] = d
        print(f"=== {month}/2024, {len(d['residual']):,} soundings ===")
        print(
            f"  solar zenith {d['sza'].min():.1f}-{d['sza'].max():.1f} deg, mean"
            f" {d['sza'].mean():.1f}; viewing zenith to {d['vza'].max():.1f} deg;"
            f" air mass factor {d['air_mass'].mean():.2f}\n"
        )
        viewing += swath(d, month)
        solar += sun(d, month)
        interaction(d, month)
        print()
    if len(loaded) > 1:
        seasons(loaded)
    print("\n--- 5. the binned slopes against the path they were measured over ---")
    against_path(viewing, "sec(vza)", "the swath bins")
    against_path(solar, "sec(sza)", "the within-band solar bins")
    against_path(viewing + solar, "air mass", "both sets against the air mass factor")


if __name__ == "__main__":
    main(sys.argv[1:] or ["06", "01"])
