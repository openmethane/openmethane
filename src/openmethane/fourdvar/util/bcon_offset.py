"""Apply the boundary condition offset to the run's BCON files, and its adjoint.

The offset unknowns, `PhysicalData.bcon`, are added to the staged BCON file of
each day (`cmaq_config.bcon_file`, never modified) to give the BCON that CMAQ
reads. The gradient comes back from ADJOINT_BWD's `ADJ_LGRID_BC`, which has the
same layout as BCON. The mapping itself is in `openmethane.bcon_map`.
"""

import numpy as np

import openmethane.fourdvar.util.date_handle as dt
import openmethane.fourdvar.util.netcdf_handle as ncf
from openmethane import bcon_map
from openmethane.fourdvar.params import cmaq_config, date_defn


def record_steps(path, step_start, step_end) -> np.ndarray:
    """Control step of each record of a BCON-shaped file."""
    record_seconds = bcon_map.file_record_seconds(path, date_defn.start_date)
    return bcon_map.record_steps(record_seconds, step_start, step_end)


def check_grid(path, region_map) -> None:
    """Fail clearly if the boundary map does not fit a BCON-shaped file."""
    nlays = int(ncf.get_attr(path, "NLAYS"))
    ncols = int(ncf.get_attr(path, "NCOLS"))
    nrows = int(ncf.get_attr(path, "NROWS"))
    expected = (nlays, bcon_map.perimeter_size(ncols, nrows))
    if region_map.shape != expected:
        raise ValueError(
            f"boundary map has shape (LAY, PERIM) = {region_map.shape}, but {path} "
            f"needs {expected}"
        )


def base_bcon_files() -> list[tuple[str, str]]:
    """(label date YYYYMMDD, staged BCON path) for each day of the run."""
    return [
        (dt.replace_date("<YYYYMMDD>", date), dt.replace_date(cmaq_config.bcon_file, date))
        for date in dt.get_datelist()
    ]


def offset_lower_bound(spc, region_map, step_start, step_end, nregion) -> np.ndarray:
    """Lowest allowed offset for each (step, region), so BCON stays non-negative.

    That is minus the smallest staged BCON value the offset is added to, over
    every record, cell and day. Entries no cell uses are -inf.
    """
    minimum = np.full((len(step_start), nregion), np.inf)
    for _, path in base_bcon_files():
        rec_step = record_steps(path, step_start, step_end)
        field = ncf.get_variable(path, spc)
        bcon_map.accumulate_minimum(minimum, field, region_map, rec_step)
    return -minimum
