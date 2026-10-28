"""Apply the initial condition offset to the run's ICON file, and its adjoint.

The offset unknown, `PhysicalData.icon`, is one value per species (ppm) added to
every record, layer and cell of the staged ICON for the start date
(`cmaq_config.icon_file`, never modified) to give the ICON that CMAQ reads on
the first day.

The first CONC record of the first day is the initial condition itself, and
ADJOINT_BWD's `ADJ_LGRID` at the initial time does not include the forcing on
that record. The gradient is therefore the sum of both: `ADJ_LGRID` and
`ADJ_FORCE` at record 0 of the first day. A finite-difference check through
CMAQ agrees with this sum, and not with `ADJ_LGRID` alone.
"""

import numpy as np

import openmethane.fourdvar.util.date_handle as dt
import openmethane.fourdvar.util.netcdf_handle as ncf
from openmethane.fourdvar.params import cmaq_config, date_defn


def base_icon_file() -> str:
    """The staged ICON for the start date."""
    return dt.replace_date(cmaq_config.icon_file, date_defn.start_date)


def apply(base: np.ndarray, offset: float) -> np.ndarray:
    """The ICON CMAQ reads: the staged ICON plus the offset in every cell."""
    return base + offset


def apply_adjoint(sense: np.ndarray, force: np.ndarray) -> float:
    """Gradient with respect to the offset, from the first day's record 0.

    sense is `ADJ_LGRID` at the initial time and force is `ADJ_FORCE` on the
    first CONC record, both (LAY, ROW, COL) in CF/ppm.
    """
    return float(np.sum(sense, dtype=np.float64) + np.sum(force, dtype=np.float64))


def offset_lower_bound(spc) -> float:
    """Lowest allowed offset, so the ICON CMAQ reads stays non-negative.

    That is minus the smallest staged ICON value, over every record, layer and cell.
    """
    return -float(np.min(ncf.get_variable(base_icon_file(), spc)))
