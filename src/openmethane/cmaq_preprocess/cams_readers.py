"""Read CAMS methane products into one structure for the CMAQ interpolation

Each product has its own file layout, units and vertical coordinate. A reader hides
all of that behind `profile`, which returns methane in ppmV together with the pressure
of every level, so the interpolation to CMAQ needs no knowledge of the product.
"""

import datetime
import pathlib

import netCDF4
import numpy
from attrs import frozen

MOLAR_MASS_AIR = 28.96
MOLAR_MASS_CH4 = 16.0


@frozen
class CamsProfile:
    """Methane on the vertical levels of a CAMS grid at one time"""

    ch4_ppmv: numpy.ndarray
    """Dry mole fraction of CH4 in ppmV, shape (level, lat, lon)"""
    pressure_pa: numpy.ndarray
    """Pressure of each level in Pa, shape (level, lat, lon)"""


class CamsReader:
    """An open CAMS file, read through a common interface

    Subclasses declare the file layout and implement `profile`.
    """

    product: str
    time_variable: str
    required_variables: tuple[str, ...]

    def __init__(self, path: pathlib.Path):
        self.path = pathlib.Path(path)
        self.dataset = netCDF4.Dataset(self.path, "r", format="NETCDF4")
        missing = [
            name
            for name in ("latitude", "longitude", self.time_variable, *self.required_variables)
            if name not in self.dataset.variables
        ]
        if missing:
            self.close()
            raise ValueError(
                f"{self.path} is not a CAMS {self.product} file: it has no {', '.join(missing)}"
            )

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

    def close(self):
        self.dataset.close()

    @property
    def times(self):
        variable = self.dataset.variables[self.time_variable]
        return netCDF4.num2date(variable[:], variable.getncattr("units"))

    @property
    def lat(self) -> numpy.ndarray:
        return self.dataset.variables["latitude"][:].squeeze()

    @property
    def lon(self) -> numpy.ndarray:
        return self.dataset.variables["longitude"][:].squeeze()

    @property
    def release(self) -> str | None:
        """The release of the product, for products that are re-processed between releases"""
        return None

    def profile(self, itime: int) -> CamsProfile:
        raise NotImplementedError

    def require_dates(self, dates: list[datetime.date]):
        """Raise a clear error if the file does not span the requested dates"""
        times = self.times
        first = datetime.date(times[0].year, times[0].month, times[0].day)
        last = datetime.date(times[-1].year, times[-1].month, times[-1].day)
        missing = [date for date in dates if date < first or date > last]
        if missing:
            raise ValueError(
                f"The CAMS {self.product} file {self.path} covers {first} to {last} but the run "
                f"needs {missing[0]} to {missing[-1]}. {self.coverage_hint}"
            )

    coverage_hint = "Download the CAMS file again for the dates of the run."


class Eac4Reader(CamsReader):
    """CAMS global reanalysis (EAC4) on fixed pressure levels, as kg/kg"""

    product = "eac4"
    time_variable = "valid_time"
    required_variables = ("ch4_c", "pressure_level")

    def profile(self, itime: int) -> CamsProfile:
        mass_mixing_ratio = self.dataset.variables["ch4_c"][itime]
        ch4_ppmv = mass_mixing_ratio * (MOLAR_MASS_AIR / MOLAR_MASS_CH4 * 1e6)
        hpa = numpy.asarray(self.dataset.variables["pressure_level"][:], dtype=float)
        pressure_pa = numpy.broadcast_to((hpa * 100.0)[:, None, None], ch4_ppmv.shape)
        return CamsProfile(ch4_ppmv=ch4_ppmv, pressure_pa=pressure_pa)


class InversionReader(CamsReader):
    """CAMS greenhouse gas inversion on hybrid sigma-pressure levels, as ppb"""

    product = "inversion"
    time_variable = "time"
    required_variables = ("CH4", "ps", "hyam", "hybm")
    coverage_hint = (
        "The inversion adds a year of data about once a year; "
        "use CAMS_PRODUCT=eac4 for dates it does not cover yet."
    )

    @property
    def release(self) -> str | None:
        return getattr(self.dataset, "cams_release", None) or getattr(
            self.dataset, "release", "unknown"
        )

    def profile(self, itime: int) -> CamsProfile:
        ch4_ppmv = self.dataset.variables["CH4"][itime] * 1e-3
        ps = self.dataset.variables["ps"][itime]
        hyam = numpy.asarray(self.dataset.variables["hyam"][:], dtype=float)
        hybm = numpy.asarray(self.dataset.variables["hybm"][:], dtype=float)
        pressure_pa = hyam[:, None, None] + hybm[:, None, None] * ps[None]
        return CamsProfile(ch4_ppmv=ch4_ppmv, pressure_pa=pressure_pa)


READERS = {reader.product: reader for reader in (Eac4Reader, InversionReader)}


def open_cams(path: pathlib.Path, product: str) -> CamsReader:
    """Open a CAMS file of the given product ("eac4" or "inversion")"""
    return READERS[product](path)
