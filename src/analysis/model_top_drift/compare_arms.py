"""Compare two arms of the #248 model-top experiment, per sounding.

    python3 compare_arms.py --baseline <dir> --perturbed <dir>

Each directory is one arm's archive, holding the `simulobs.pic.gz` that
`scripts/fourdvar/run_daily_step.py` wrote. The arms are forward-only months over
the same period that read the same staged inputs and the same observations, and
differ only in `scripts/cmaq_preprocess/scale_top_gradient.py --scale`, so
differencing them per sounding cancels everything else: the meteorology, the
emissions, the CAMS bias correction, the observation operator and the retrieval.

This is decision criterion 3. Rescaling the profile shifts the simulated column
by a constant at t = 0 -- flattening the gradient above layer 23 adds about
8 ppb -- and the hypothesis is about what happens to that difference *afterwards*.
So the trend is what is read, not the level.

Under the hypothesis the baseline drifts up at about +0.20 ppb/day and the
flattened arm does not, so `perturbed - baseline` should fall at that rate. If it
is flat, the gradient at the model top is not what drives the drift.

Observations are paired by (time, latitude, longitude), never by position in
file: run orders are not guaranteed to match.
"""

import argparse
import gzip
import hashlib
import pathlib
import pickle

import numpy as np


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


def read_arm(path):
    """Simulated column and day of month for every sounding in one arm."""
    columns, days = {}, {}
    for i, record in enumerate(stream(path)):
        if i == 0:
            continue
        identity = key(record)
        columns[identity] = float(record["value"])
        days[identity] = int(f"{record['lite_coord'][0]}"[-2:])
    return columns, days


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--baseline", required=True, type=pathlib.Path, help="the --scale 1 arm's archive directory"
    )
    parser.add_argument(
        "--perturbed",
        required=True,
        type=pathlib.Path,
        help="the --scale 0 arm's archive directory",
    )
    args = parser.parse_args()

    baseline, days = read_arm(args.baseline / "simulobs.pic.gz")
    perturbed, _ = read_arm(args.perturbed / "simulobs.pic.gz")

    shared = sorted(set(baseline) & set(perturbed))
    missing = len(baseline) - len(shared)
    if missing:
        raise SystemExit(
            f"{missing} of {len(baseline)} baseline soundings are absent from the "
            "perturbed arm; the runs do not share an observation set"
        )
    print(f"{len(shared):,} soundings paired\n")

    day = np.array([days[k] for k in shared], float)
    difference = np.array([perturbed[k] - baseline[k] for k in shared])

    print(f"{'day':>4} {'soundings':>10} {'perturbed - baseline':>22}")
    means, present = [], []
    for value in np.unique(day):
        selected = difference[day == value]
        means.append(selected.mean())
        present.append(value)
        print(f"{int(value):4d} {selected.size:10,} {selected.mean():22.3f}")

    means, present = np.array(means), np.array(present)
    slope, intercept = np.polyfit(present, means, 1)
    scatter = np.std(means - np.polyval((slope, intercept), present))
    # the standard error of a slope fitted to n daily means
    error = scatter / (np.std(present) * np.sqrt(len(present)))

    print(
        f"\nlevel on day {int(present[0])}: {means[0]:+.2f} ppb "
        "-- the constant the rescaling adds at t = 0, which is not the result"
    )
    print(f"trend: {slope:+.3f} +/- {error:.3f} ppb/day, scatter about it {scatter:.2f} ppb")
    print(
        f"  fitted day {int(present[0])} {np.polyval((slope, intercept), present[0]):+.2f}"
        f" -> day {int(present[-1])} {np.polyval((slope, intercept), present[-1]):+.2f} ppb"
    )
    print("\nthe baseline's own drift is +0.20 ppb/day, so the hypothesis predicts a")
    print("trend here of about -0.20 ppb/day; a trend near zero refutes it")


if __name__ == "__main__":
    main()
