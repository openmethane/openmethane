"""Where the #242 misfit comes from: diagnostics on an archived monthly run.

    python3 extract.py 06 && python3 analyse.py 06

`extract.py` must have run first; this reads only the cache it writes plus the
daily background means in the run's own `cmaq_preprocess-bias_correct` log.

Four questions, in order:

1. How does the model's simulated column compare with the CAMS background that
   drives it, day by day? The bias-correction log records, per day, the mean
   observed column and the mean column the operator simulates from that day's
   CAMS ICON field. The forward model's mean is in the cache. The three are on
   the same footing -- same soundings, same operator -- so differencing them is
   exact.

2. How does the residual split between a whole-domain day effect and a
   time-invariant spatial pattern? Both are fitted together so that a day whose
   orbits happen to cross a biased region is not read as a bad day.

3. What per-sounding retrieval properties does the residual track? Aerosol and
   albedo are tested inside 200 km / one-day blocks, where the model field
   cannot vary in step with a single sounding's retrieval, so a dependence that
   survives belongs to the retrieval.

4. Does the model's excess grow with distance into the domain -- the signature
   of something that accumulates in air the longer it stays inside.
"""

import os
import pathlib
import re
import sys

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
NROWS, NCOLS = 430, 454
BLOCK = 20  # 200 km at 10 km cells
PPM2PPB = 1e3


def background_log(month):
    """Per-day mean observed and CAMS-simulated columns, and the correction applied.

    `calculate_icon_bias` skips days with no observations, so the arrays are
    indexed by *day that has observations*, not by day of month; they are
    matched to the cache's own day list by the caller.
    """
    root = _required_dir("OM_MONTHLY_ROOT", "the archived monthly runs, one directory per month")
    path = root / month / "logs" / "cmaq_preprocess-bias_correct.0.log"
    text = path.read_text()

    def array(tag):
        start = text.index(tag) + len(tag)
        body = re.sub(r"\d{4}-\d{2}-\d{2}T[\d:.]+:", " ", text[start : text.index("]", start)])
        return np.array([float(x) for x in body.replace("[", " ").split()])

    def scalar(tag):
        return float(re.search(re.escape(tag) + r"([-\d.eE+]+)", text).group(1))

    correction = scalar("icon_bias=") - scalar("emissions_bias=")
    weight = scalar("mean operator weight: ")
    return array("icon column means (ppb):"), correction * PPM2PPB * weight, weight


def load(month):
    data = np.load(CACHE / f"misfit_{month}.npz")
    out = {k: data[k].astype(float) for k in data.files}
    out["residual"] = out["obs"] - out["sim"]
    out["day"] = data["day"].astype(int)
    out["row"] = data["row"].astype(int)
    out["col"] = data["col"].astype(int)
    # the retrieval grid is 12 layers of equal pressure thickness, so the model's
    # coverage of the topmost one fixes the retrieval's surface pressure exactly
    out["psurf"] = 60000.0 / (1.0 - out["cov"][:, 0])
    return out


def group(key):
    unique, index = np.unique(key, return_inverse=True)
    return unique, index, np.bincount(index)


def block_id(row, col, size=BLOCK):
    return (row // size).astype(np.int64) * 100000 + (col // size)


def background_gap(d, month):
    """The forward model's column minus the CAMS field it was started from."""
    icon, correction, _ = background_log(month)
    days = np.unique(d["day"])
    if len(icon) != len(days):
        sys.exit(f"{month}: {len(icon)} logged days but {len(days)} days of observations")
    print(f"bias correction applied to ICON and BCON: {correction:+.2f} ppb of column\n")
    print(
        f"{'day':>4} {'CAMS+corr':>10} {'model':>10} {'obs':>10}"
        f" {'model-CAMS':>12} {'obs-model':>10}"
    )
    gap = []
    for i, day in enumerate(days):
        m = d["day"] == day
        reference = icon[i] + correction
        model, observed = d["sim"][m].mean(), d["obs"][m].mean()
        gap.append(model - reference)
        print(
            f"{day:4d} {reference:10.2f} {model:10.2f} {observed:10.2f} "
            f"{model - reference:12.2f} {observed - model:10.2f}"
        )
    gap = np.array(gap)
    fit = np.polyfit(days.astype(float), gap, 1)
    print(
        f"\nmodel - CAMS background: mean {gap.mean():+.2f} ppb, "
        f"trend {fit[0]:+.3f} ppb/day ({fit[0] * (days[-1] - days[0]):+.1f} over the run), "
        f"scatter about the trend {np.std(gap - np.polyval(fit, days)):.2f} ppb"
    )
    print(
        f"  fitted day {days[0]} {np.polyval(fit, days[0]):+.2f} -> "
        f"day {days[-1]} {np.polyval(fit, days[-1]):+.2f} ppb"
    )
    print("  the prior emissions account for a roughly constant part of this; the rest is spurious")


def day_and_space(d):
    """Split the residual into a whole-domain day effect and a spatial pattern.

    Fitted jointly by alternating projection so that the day effect is not
    contaminated by which part of the domain that day's orbits happened to
    cross, which is what a raw daily mean would confound it with.
    """
    r = d["residual"]
    days, di, dc = group(d["day"])
    _, bi, bc = group(block_id(d["row"], d["col"]))
    day_effect = np.zeros(len(days))
    block_effect = np.zeros(len(bc))
    mean = r.mean()
    for _ in range(200):
        day_effect = np.bincount(di, weights=r - mean - block_effect[bi]) / dc
        day_effect -= day_effect.mean()
        block_effect = np.bincount(bi, weights=r - mean - day_effect[di]) / bc
    left = r - mean - day_effect[di] - block_effect[bi]
    print(f"  total sd of the residual        {r.std():7.3f} ppb")
    print(f"  sd of the day effect            {day_effect[di].std():7.3f}")
    print(f"  sd of the spatial pattern       {block_effect[bi].std():7.3f}")
    print(f"  sd of what is left              {left.std():7.3f}")
    fit = np.polyfit(days.astype(float), day_effect, 1)
    print(
        f"\n  day effect trend {fit[0]:+.3f} ppb/day, "
        f"sd about that trend {np.std(day_effect - np.polyval(fit, days)):.3f} ppb"
    )
    print("\n  day effect (ppb), sampling-controlled:")
    for day, value in zip(days, day_effect):
        print(f"    {day:02d}  {value:+7.3f}")


def retrieval_terms(d):
    """Test aerosol and albedo inside 200 km / one-day blocks.

    Within a block the model field is smooth and cannot vary in step with an
    individual sounding's retrieved aerosol, so a surviving dependence is the
    retrieval's, not the model's. Both sides are reported separately to show
    which one moves.
    """
    key = d["day"].astype(np.int64) * 10**9 + block_id(d["row"], d["col"])
    _, index, count = group(key)
    keep = count[index] >= 50

    def anomaly(x):
        return (x - (np.bincount(index, weights=x) / count)[index])[keep]

    for name in ("aod", "albedo"):
        a = anomaly(d[name])
        print(f"  per unit {name}, within a block:")
        for side in ("obs", "sim", "residual"):
            slope = np.polyfit(a, anomaly(d[side]), 1)[0]
            print(f"      {side:9s} {slope:9.1f} ppb")


def inland(d):
    """Does the model's excess grow with distance into the domain?

    Distance to the nearest domain edge stands in for how long air has been
    inside. Surface albedo, aerosol, surface pressure, retrieval quality and
    latitude are carried alongside so the distance term is not just reading a
    property of the arid interior.
    """
    ids, index, count = group(block_id(d["row"], d["col"]))
    keep = count >= 300

    def mean(x):
        return (np.bincount(index, weights=x) / count)[keep]

    br, bc = ids // 100000, ids % 100000
    centre_row, centre_col = br * BLOCK + BLOCK / 2, bc * BLOCK + BLOCK / 2
    edge = np.minimum.reduce([centre_row, NROWS - centre_row, centre_col, NCOLS - centre_col])[keep]

    terms = [
        ("albedo", mean(d["albedo"])),
        ("aod", mean(d["aod"])),
        ("psurf/1000 Pa", mean(d["psurf"]) / 1000),
        ("qa", mean(d["qa"])),
        ("lat", mean(d["lat"])),
        ("per 100 cells inland", edge / 100.0),
    ]
    y, w = mean(d["residual"]), count[keep]
    X = np.column_stack([np.ones_like(y)] + [v for _, v in terms])
    beta = np.linalg.lstsq(X * np.sqrt(w)[:, None], y * np.sqrt(w), rcond=None)[0]
    left = y - X @ beta
    covariance = np.linalg.inv((X * w[:, None]).T @ X) * np.sum(w * left**2) / (len(y) - X.shape[1])
    error = np.sqrt(np.diag(covariance))
    print(f"  block-mean residual, {keep.sum()} blocks of 200 km, weighted by observation count")
    for name, value, err in zip(["const"] + [n for n, _ in terms], beta, error):
        print(f"    {name:22s} {value:10.3f} +/- {err:8.3f}  (t={value / err:5.1f})")


def main(month):
    d = load(month)
    print(f"=== {month}/2024, {len(d['residual']):,} observations ===")
    print(
        f"residual (obs - model): mean {d['residual'].mean():+.3f} ppb,"
        f" sd {d['residual'].std():.3f}\n"
    )
    print("--- 1. the model against the CAMS background that drives it ---")
    background_gap(d, month)
    print("\n--- 2. how the residual splits between time and space ---")
    day_and_space(d)
    print("\n--- 3. retrieval terms, tested within 200 km / one day ---")
    retrieval_terms(d)
    print("\n--- 4. does the model's excess grow with distance into the domain? ---")
    inland(d)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "06")
