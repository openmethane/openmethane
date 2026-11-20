"""Where the WRF and WPS programs and their data files are installed."""

import pathlib

import attrs


class InstallError(RuntimeError):
    """Files the WRF step needs are missing from the WRF or WPS install."""


@attrs.frozen
class WrfInstall:
    """
    The WRF and WPS installs, at the paths the openmethane image puts them.

    Every path is derived from the two install folders, as in the image built
    from the docker-wrf image.
    """

    wrf_dir: pathlib.Path = attrs.field(default=pathlib.Path("/opt/wrf"), converter=pathlib.Path)
    """WRF's install folder"""
    wps_dir: pathlib.Path = attrs.field(default=pathlib.Path("/opt/wps"), converter=pathlib.Path)
    """WPS's install folder"""

    @property
    def real_exe(self) -> pathlib.Path:
        return self.wrf_dir / "main" / "real.exe"

    @property
    def wrf_exe(self) -> pathlib.Path:
        return self.wrf_dir / "main" / "wrf.exe"

    @property
    def run_dir(self) -> pathlib.Path:
        """WRF's data files and tables, every one linked into each run folder."""
        return self.wrf_dir / "run"

    @property
    def ungrib_exe(self) -> pathlib.Path:
        return self.wps_dir / "ungrib.exe"

    @property
    def metgrid_exe(self) -> pathlib.Path:
        return self.wps_dir / "metgrid.exe"

    @property
    def geogrid_exe(self) -> pathlib.Path:
        return self.wps_dir / "geogrid.exe"

    @property
    def link_grib(self) -> pathlib.Path:
        return self.wps_dir / "link_grib.csh"

    @property
    def metgrid_table(self) -> pathlib.Path:
        return self.wps_dir / "metgrid" / "METGRID.TBL"

    @property
    def geogrid_table(self) -> pathlib.Path:
        return self.wps_dir / "geogrid" / "GEOGRID.TBL"

    @property
    def fnl_vtable(self) -> pathlib.Path:
        """The Vtable ungrib reads GDAS/FNL analyses with."""
        return self.wps_dir / "ungrib" / "Variable_Tables" / "Vtable.GFS"

    def missing(self) -> list[pathlib.Path]:
        """The files a WRF run needs that don't exist."""
        needed = [
            self.real_exe,
            self.wrf_exe,
            self.ungrib_exe,
            self.metgrid_exe,
            self.link_grib,
            self.metgrid_table,
            self.fnl_vtable,
        ]
        missing = [path for path in needed if not path.is_file()]
        if not self.run_dir.is_dir() or not any(self.run_dir.iterdir()):
            missing.append(self.run_dir)
        return missing

    def validate(self) -> None:
        """
        Check that everything a WRF run needs is installed.

        Raises
        ------
        InstallError
            Naming every missing file, so they can all be fixed at once.
        """
        missing = self.missing()
        if missing:
            listed = "\n".join(f"  {path}" for path in missing)
            raise InstallError(f"WRF or WPS files are missing:\n{listed}")
