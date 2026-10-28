"""
Build the map from boundary-condition offset unknowns to the BCON grid

The 4D-Var boundary unknowns are additive offsets, in ppm, on the lateral
boundary condition. Each covers one region of the boundary for one control
time step. This script cuts the boundary into segments of about
`--segment-km` along each edge, the column into `--nbands` bands of roughly
equal air mass, and the run into steps of about `--step-days`, and writes the
result as a netCDF map file that `make_prior.py` reads via `BCON_MAP_FILE`.

Lengths rarely divide exactly. `--remainder spread` (the default) uses the
nearest whole number of pieces, sized as equally as possible (31 days by 5 ->
5,5,5,5,5,6). `--remainder end` uses full-length pieces plus one shorter piece
(31 days by 5 -> 5,5,5,5,5,5,1).

The file can be edited by hand afterwards, e.g. to change `BCON_UNC` on one
edge or to redraw regions; it is validated when the prior is made.

Defaults come from the BCON_* environment variables (see
docs/reference/parameters.md), and the run dates from START_DATE and END_DATE.
"""

import datetime
import pathlib

import click
import numpy as np

from openmethane import bcon_map
from openmethane.fourdvar.params import cmaq_config, date_defn, input_defn
from openmethane.fourdvar.util import date_handle as dt


def make_bcon_map(
    output: pathlib.Path,
    bcon_file: str,
    start_date: datetime.date,
    end_date: datetime.date,
    **settings,
) -> None:
    ds = bcon_map.build_bcon_map(bcon_file, start_date, end_date, **settings)
    output.parent.mkdir(parents=True, exist_ok=True)
    ds.to_netcdf(output)

    nregion = ds.sizes["REGION"]
    nstep = ds.sizes["STEP"]
    print(f"Wrote {output}: {nregion} regions x {nstep} steps = {nregion * nstep} unknowns")
    print(f"  band start layers: {list(ds.attrs['band_start_layers'])}")
    for edge, name in enumerate(bcon_map.EDGES):
        cells = ds["REGION_NCELLS"].values[
            (ds["REGION_EDGE"].values == edge) & (ds["REGION_BAND"].values == 0)
        ]
        if cells.size:
            print(f"  {name} segment lengths (cells): {cells.tolist()}")
    days = (ds["STEP_END"].values - ds["STEP_START"].values) / np.timedelta64(1, "h") / 24
    print(f"  step lengths (days): {[round(d, 3) for d in days.tolist()]}")


@click.command(help=__doc__)
@click.option("--output", type=click.Path(path_type=pathlib.Path), required=True)
@click.option(
    "--bcon-file",
    help="BCON file giving the grid and layers. Default: BCON_FILE for START_DATE.",
)
@click.option("--start-date", type=click.DateTime(["%Y-%m-%d"]), default=None)
@click.option("--end-date", type=click.DateTime(["%Y-%m-%d"]), default=None)
@click.option("--segment-km", type=float, default=input_defn.bcon_segment_km, show_default=True)
@click.option("--step-days", type=float, default=input_defn.bcon_step_days, show_default=True)
@click.option("--nbands", type=int, default=input_defn.bcon_nbands, show_default=True)
@click.option(
    "--layer-bands",
    help="Comma-separated 1-based start layer of each band, e.g. 1,9,17,25. Overrides --nbands.",
)
@click.option(
    "--remainder",
    type=click.Choice(bcon_map.REMAINDER_RULES),
    default=input_defn.bcon_remainder,
    show_default=True,
)
@click.option(
    "--min-fraction",
    type=float,
    default=0.0,
    show_default=True,
    help="With --remainder end, merge a leftover shorter than this fraction of a piece.",
)
@click.option("--unc", type=float, default=input_defn.bcon_unc, show_default=True, help="ppm")
@click.option("--wrap", is_flag=True, help="Cut the perimeter as one loop, across corners.")
def main(output, bcon_file, start_date, end_date, layer_bands, **settings):
    start = start_date.date() if start_date else date_defn.start_date
    end = end_date.date() if end_date else date_defn.end_date
    if bcon_file is None:
        bcon_file = dt.replace_date(cmaq_config.bcon_file, start)
    if layer_bands:
        settings["layer_bands"] = [int(b) for b in layer_bands.split(",")]
    make_bcon_map(output, bcon_file, start, end, **settings)


if __name__ == "__main__":
    main()
