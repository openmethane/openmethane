"""Measure the monthly run's accumulated drift against same-day fresh runs.

    python3 accumulation.py

The monthly run is one continuous 30-day simulation: day 1 reads ICON, every
later day restarts from the previous day's CGRID. The daily runs that fed the
same month are single-day forward passes from that day's own CAMS ICON. For a
given day both runs see the same meteorology, the same observations and the same
operator, so differencing their simulated columns isolates what the monthly run
has accumulated since it was initialised -- with no surrogate and no assumption
about transport.

One known offset has to be removed. `bias_correct_cams.py` adds a constant to
the monthly run's ICON and BCON; the daily runs do not bias-correct at all
(checked directly: their ICON and BCON carry raw CAMS values). The operator is
affine, so that constant moves a simulated column by `1000 * sum(weights) *
bias` ppb, which is exact per sounding and is subtracted here.

Day 1 is the control. Both runs start from the same field that morning, so the
accumulated drift there must come out near zero.

Observations are paired by (time, latitude, longitude), never by position in
file.
"""

import gzip
import hashlib
import os
import pathlib
import pickle

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


# icon_bias - emissions_bias from the monthly run's bias-correction log, in ppm
CORRECTION_PPM = 0.120333 - 0.000839
PPM2PPB = 1e3


def stream(path):
    with gzip.open(path, "rb") as f:
        while True:
            try:
                yield pickle.load(f, encoding="latin1")  # noqa: S301
            except EOFError:
                return


def key(record):
    text = (
        f"{record['time']}|{round(float(record['latitude_center']), 6)}"
        f"|{round(float(record['longitude_center']), 6)}"
    )
    return hashlib.blake2b(text.encode(), digest_size=12).digest()


def main():
    sandbox = _required_dir("OM_SANDBOX", "the downloaded run archives for one domain")
    monthly_file = sandbox / "monthly/2024/06/archive/openmethane/simulobs_first_guess.pic.gz"
    daily_dir = sandbox / "daily/2024/06"
    days = sorted(p.name for p in daily_dir.iterdir() if (p / "simulobs.pic.gz").exists())
    if not days:
        raise SystemExit(f"no daily simulobs under {daily_dir}")
    wanted = set(days)

    monthly = {}
    for i, record in enumerate(stream(monthly_file)):
        if i == 0:
            continue
        if f"{record['lite_coord'][0]}"[-2:] in wanted:
            monthly[key(record)] = (float(record["value"]), float(np.sum(record["model_vis"])))
    print(f"monthly: {len(monthly):,} simulated observations on the {len(days)} selected days\n")

    print(
        f"{'day':>4} {'paired':>9} {'monthly-daily':>14} {'correction':>11}"
        f" {'accumulated':>12} {'sd':>8}"
    )
    rows = []
    for day in days:
        pairs = []
        for i, record in enumerate(stream(daily_dir / day / "simulobs.pic.gz")):
            if i == 0:
                continue
            found = monthly.get(key(record))
            if found is not None:
                pairs.append((found[0], float(record["value"]), found[1]))
        if not pairs:
            print(f"{day:>4} {'0':>9}  no overlap")
            continue
        month_sim, day_sim, weight = (np.array(x, float) for x in zip(*pairs))
        correction = PPM2PPB * CORRECTION_PPM * weight
        drift = month_sim - day_sim - correction
        rows.append((int(day), drift.mean(), drift.std(), len(drift)))
        print(
            f"{day:>4} {len(drift):>9,} {np.mean(month_sim - day_sim):>14.3f} "
            f"{correction.mean():>11.3f} {drift.mean():>12.3f} {drift.std():>8.3f}"
        )

    table = np.array(rows, float)
    fit = np.polyfit(table[:, 0], table[:, 1], 1)
    print(
        f"\naccumulated drift: trend {fit[0]:+.3f} ppb/day, "
        f"day 1 fitted {np.polyval(fit, 1):+.2f}, day 30 fitted {np.polyval(fit, 30):+.2f}"
    )
    print(f"  scatter about the trend {np.std(table[:, 1] - np.polyval(fit, table[:, 0])):.2f} ppb")
    print(
        f"  day 1 measured {table[0, 1]:+.3f} ppb -- both runs start from the same"
        " field, so this is the control"
    )


if __name__ == "__main__":
    main()
