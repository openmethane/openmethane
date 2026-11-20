import datetime
import pathlib
import sys
import textwrap

import pytest

from openmethane.wrf.config import WrfConfig
from openmethane.wrf.geometry import DomainSet
from openmethane.wrf.install import WrfInstall

# Stand-ins for the WRF and WPS programs. Each appends its name to calls.log,
# fails if its name is in the STUB_FAIL environment variable, and otherwise
# writes the files and success lines the real program would.
STUB_HEADER = f"""#!{sys.executable}
import datetime, os, pathlib, sys
import f90nml, netCDF4, numpy
name = pathlib.Path(sys.argv[0]).name
with open(os.environ["STUB_CALLS"], "a") as calls:
    calls.write(name + "\\n")
if name in os.environ.get("STUB_FAIL", "").split(","):
    print(f"{{name}} failed on request")
    sys.exit(1)
"""

STUBS = {
    "wps/link_grib.csh": """
for number, path in enumerate(sys.argv[1:]):
    os.symlink(path, f"GRIBFILE.AA{chr(ord('A') + number)}")
""",
    "wps/ungrib.exe": """
print("!  Successful completion of ungrib.   !")
""",
    "wps/metgrid.exe": """
share = f90nml.read("namelist.wps")["share"]
start = share["start_date"][0] if isinstance(share["start_date"], list) else share["start_date"]
end = share["end_date"][0] if isinstance(share["end_date"], list) else share["end_date"]
time = datetime.datetime.strptime(start, "%Y-%m-%d_%H:%M:%S")
end = datetime.datetime.strptime(end, "%Y-%m-%d_%H:%M:%S")
while time <= end:
    for index in range(1, share["max_dom"] + 1):
        with netCDF4.Dataset(f"met_em.d{index:02d}.{time:%Y-%m-%d_%H:%M:%S}.nc", "w") as met_em:
            met_em.createDimension("num_metgrid_levels", 34)
            met_em.createDimension("num_st_layers", 4)
    time += datetime.timedelta(hours=6)
print("!  Successful completion of metgrid.  !")
""",
    "wrf/main/real.exe": """
max_dom = f90nml.read("namelist.input")["domains"]["max_dom"]
pathlib.Path("wrfbdy_d01").touch()
for index in range(1, max_dom + 1):
    pathlib.Path(f"wrfinput_d{index:02d}").touch()
    pathlib.Path(f"wrflowinp_d{index:02d}").touch()
pathlib.Path("rsl.out.0000").write_text("real_em: SUCCESS COMPLETE REAL_EM INIT\\n")
""",
    "wrf/main/wrf.exe": """
time_control = f90nml.read("namelist.input")["time_control"]
def first(value):
    return value[0] if isinstance(value, list) else value
units = ("year", "month", "day", "hour")
start = datetime.datetime(*(first(time_control[f"start_{unit}"]) for unit in units))
end = datetime.datetime(*(first(time_control[f"end_{unit}"]) for unit in units))
time = start + datetime.timedelta(hours=first(time_control["history_begin_h"]))
frames = first(time_control["frames_per_outfile"])
while time <= end:
    count = 1 if time == end else frames
    name = f"wrfout_d01_{time:%Y-%m-%d_%H:%M:%S}"
    with netCDF4.Dataset(name, "w", format="NETCDF3_64BIT_OFFSET") as out:
        out.createDimension("Time", None)
        out.createDimension("DateStrLen", 19)
        out.createDimension("south_north", 2)
        out.createDimension("west_east", 2)
        out.createVariable("Times", "S1", ("Time", "DateStrLen"))
        temperature = out.createVariable("T2", "f4", ("Time", "south_north", "west_east"))
        temperature[:] = numpy.arange(count * 4, dtype="f4").reshape(count, 2, 2)
    time += datetime.timedelta(hours=1)
pathlib.Path("wrfrst_d01_final").touch()
pathlib.Path("rsl.out.0000").write_text("wrf: SUCCESS COMPLETE WRF\\n")
""",
    "bin/mpirun": """
# mpirun -np N program: run the program in place of N ranks
os.execv(sys.argv[3], sys.argv[3:])
""",
}

DATA_FILES = (
    "wrf/run/LANDUSE.TBL",
    "wrf/run/namelist.input",
    "wps/metgrid/METGRID.TBL",
    "wps/ungrib/Variable_Tables/Vtable.GFS",
)


@pytest.fixture
def stub_install(tmp_path, monkeypatch) -> WrfInstall:
    """An install of stub programs, with mpirun on PATH and calls logged to calls.log."""
    root = tmp_path / "opt"
    for relative, body in STUBS.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(STUB_HEADER + textwrap.dedent(body))
        path.chmod(0o755)
    for relative in DATA_FILES:
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        (root / relative).touch()
    monkeypatch.setenv("PATH", f"{root / 'bin'}:{pathlib.os.environ['PATH']}")
    monkeypatch.setenv("STUB_CALLS", str(tmp_path / "calls.log"))
    monkeypatch.delenv("STUB_FAIL", raising=False)
    return WrfInstall(wrf_dir=root / "wrf", wps_dir=root / "wps")


@pytest.fixture
def stub_config(tmp_path, stub_install) -> WrfConfig:
    """
    A one-day au-test run of the stub install, with every download already done.

    The FNL cache holds empty analyses and scratch holds an empty geo_em, so
    nothing is fetched over the network.
    """
    config = WrfConfig(
        start_date=datetime.date(2022, 12, 7),
        end_date=datetime.date(2022, 12, 7),
        domains=DomainSet.load([("au-test", "v1")]),
        output_path=tmp_path / "store" / "wrf" / "au-test",
        scratch_path=tmp_path / "chk" / "wrf" / "au-test",
        met_em_cache_path=tmp_path / "chk" / "wrf" / "au-test" / "metem",
        fnl_cache_path=tmp_path / "fnl",
        mpi_ranks=1,
        install=stub_install,
    )
    config.fnl_cache_path.mkdir()
    start = datetime.datetime(2022, 12, 6, 12)
    for step in range(7):
        time = start + datetime.timedelta(hours=6 * step)
        (config.fnl_cache_path / time.strftime("gdas1.fnl0p25.%Y%m%d%H.f00.grib2")).touch()
    config.scratch_path.mkdir(parents=True)
    (config.scratch_path / "geo_em.d01.nc").touch()
    return config
