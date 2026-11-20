import pathlib

import pytest

from openmethane.wrf.install import InstallError, WrfInstall

RUNTIME_FILES = (
    "wrf/main/real.exe",
    "wrf/main/wrf.exe",
    "wrf/run/LANDUSE.TBL",
    "wps/ungrib.exe",
    "wps/metgrid.exe",
    "wps/link_grib.csh",
    "wps/metgrid/METGRID.TBL",
    "wps/ungrib/Variable_Tables/Vtable.GFS",
)


@pytest.fixture
def installed(tmp_path) -> pathlib.Path:
    """A folder laid out like the image's /opt, with every runtime file."""
    for name in RUNTIME_FILES:
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).touch()
    return tmp_path


def test_defaults_to_the_image_paths():
    install = WrfInstall()

    assert install.wrf_exe == pathlib.Path("/opt/wrf/main/wrf.exe")
    assert install.ungrib_exe == pathlib.Path("/opt/wps/ungrib.exe")
    assert install.fnl_vtable == pathlib.Path("/opt/wps/ungrib/Variable_Tables/Vtable.GFS")


def test_a_complete_install_validates(installed):
    install = WrfInstall(wrf_dir=installed / "wrf", wps_dir=installed / "wps")

    install.validate()

    assert install.missing() == []


def test_every_missing_file_is_named_at_once(installed):
    (installed / "wrf/main/real.exe").unlink()
    (installed / "wps/metgrid/METGRID.TBL").unlink()
    (installed / "wrf/run/LANDUSE.TBL").unlink()
    install = WrfInstall(wrf_dir=installed / "wrf", wps_dir=installed / "wps")

    with pytest.raises(InstallError) as raised:
        install.validate()

    message = str(raised.value)
    assert str(installed / "wrf/main/real.exe") in message
    assert str(installed / "wps/metgrid/METGRID.TBL") in message
    # An empty run/ folder counts as missing.
    assert str(installed / "wrf/run") in message
