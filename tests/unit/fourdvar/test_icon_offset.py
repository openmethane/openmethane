"""The initial condition offset: its file format, bounds, and how CMAQ reads it."""

import shutil

import netCDF4
import numpy as np
import pytest

from openmethane import bcon_map
from openmethane.fourdvar import user_driver
from openmethane.fourdvar.datadef import PhysicalAdjointData, PhysicalData
from openmethane.fourdvar.datadef.abstract import _physical_abstract_data
from openmethane.fourdvar.datadef.abstract._physical_abstract_data import PhysicalAbstractData
from openmethane.fourdvar.params import cmaq_config, input_defn
from openmethane.fourdvar.transfunc import prepare_model
from openmethane.fourdvar.util import cmaq_handle, cmaq_io_files, icon_offset

NROWS, NCOLS, NLAYS = 10, 10, 32
SPCS = ["CH4", "CH4B"]


def add_species(path, name, field):
    """Add a copy of CH4 to a CMAQ-style file, with new values."""
    with netCDF4.Dataset(path, "a") as nc:
        src = nc.variables["CH4"]
        var = nc.createVariable(name, src.dtype, src.dimensions)
        var[:] = field


@pytest.fixture
def icon_file(test_data_dir, tmp_path, monkeypatch):
    """A copy of the test ICON used as the staged ICON, with a second species."""
    path = tmp_path / "ICON.nc"
    shutil.copy(test_data_dir / "cmaq" / "template_icon_profile_CH4only_d01.nc", path)
    with netCDF4.Dataset(path, "a") as nc:
        ch4 = nc.variables["CH4"][:]
    add_species(path, "CH4B", 2 * ch4)
    monkeypatch.setattr(cmaq_config, "icon_file", str(path))
    return path


@pytest.fixture
def bcon_file(test_data_dir, tmp_path, monkeypatch):
    path = tmp_path / "BCON.nc"
    shutil.copy(test_data_dir / "cmaq" / "template_bcon_profile_CH4only_d01.nc", path)
    with netCDF4.Dataset(path, "a") as nc:
        ch4 = nc.variables["CH4"][:]
    add_species(path, "CH4B", ch4)
    monkeypatch.setattr(cmaq_config, "bcon_file", str(path))
    return path


@pytest.fixture
def physical_params(monkeypatch, tmp_path):
    monkeypatch.setattr(input_defn, "inc_icon", True)
    monkeypatch.setattr(_physical_abstract_data, "get_archive_path", lambda: str(tmp_path))
    region_map, _ = bcon_map.build_region_map(NCOLS, NROWS, NLAYS, 4, 4, [0, 11, 17, 22])
    nregion = region_map.max() + 1
    params = {
        "tday_emis": 1,
        "nstep_emis": 1,
        "nlays_emis": 1,
        "nrows": NROWS,
        "ncols": NCOLS,
        "spcs": SPCS,
        "emis_unc": {spc: np.full((1, 1, NROWS, NCOLS), 0.6) for spc in SPCS},
        "bcon_region": nregion,
        "nstep_bcon": 1,
        "bcon_region_map": region_map,
        "bcon_step_start": np.array([0]),
        "bcon_step_end": np.array([86400]),
        "bcon_unc": {spc: np.full((1, nregion), 0.02) for spc in SPCS},
        "icon_unc": {"CH4": 0.05, "CH4B": 0.08},
    }
    for name, val in params.items():
        monkeypatch.setattr(PhysicalAbstractData, name, val)
    return params


def make_physical(params, icon, cls=PhysicalData):
    emis = {spc: np.ones((1, 1, NROWS, NCOLS)) for spc in params["spcs"]}
    bcon = {spc: np.zeros((1, params["bcon_region"])) for spc in params["spcs"]}
    return cls(icon, emis, bcon)


def test_offset_lower_bound(icon_file):
    with netCDF4.Dataset(icon_file, "a") as nc:
        ch4 = nc.variables["CH4"][:]
        ch4[0, 31, 4, 6] = 0.3
        nc.variables["CH4"][:] = ch4

    assert icon_offset.offset_lower_bound("CH4") == pytest.approx(-0.3, rel=1e-6)
    # CH4B is twice the original CH4, so it has its own minimum
    with netCDF4.Dataset(icon_file) as nc:
        expected = -nc.variables["CH4B"][:].min()
    assert icon_offset.offset_lower_bound("CH4B") == pytest.approx(expected, rel=1e-6)

    # at the bound, the ICON CMAQ reads touches zero and goes no lower
    field = icon_offset.apply(ch4, icon_offset.offset_lower_bound("CH4"))
    assert np.isclose(field.min(), 0, atol=1e-6)


def test_icon_bounds_per_species(physical_params, icon_file, bcon_file):
    """Each species is bounded by its own staged ICON, scaled by its uncertainty."""
    bounds, is_bcon, is_icon = user_driver.get_bounds(PhysicalData, True)

    n_per_spc = 1 + NROWS * NCOLS + physical_params["bcon_region"]
    assert len(bounds) == len(SPCS) * n_per_spc
    assert np.flatnonzero(is_icon).tolist() == [0, n_per_spc]
    assert not (is_icon & is_bcon).any()

    with netCDF4.Dataset(icon_file) as nc:
        for i, spc in enumerate(SPCS):
            lower, upper = bounds[i * n_per_spc]
            expected = -nc.variables[spc][:].min() / physical_params["icon_unc"][spc]
            assert upper is None
            assert lower == pytest.approx(expected, rel=1e-6)
    # the two species have different minima, so their bounds differ
    assert bounds[0][0] != pytest.approx(bounds[n_per_spc][0])


def test_no_icon_bounds_when_off(physical_params, icon_file, bcon_file, monkeypatch):
    monkeypatch.setattr(input_defn, "inc_icon", False)
    bounds, _, is_icon = user_driver.get_bounds(PhysicalData, True)
    assert len(bounds) == len(SPCS) * (NROWS * NCOLS + physical_params["bcon_region"])
    assert not is_icon.any()


def test_apply_adjoint_is_the_adjoint(icon_file):
    """<P x, y> == <x, P^T y> for the map from x to the first day's CONC record 0.

    CONC record 0 is ICON + x, so its forcing f and the adjoint state at the
    initial time s both see the offset: P^T(s, f) = sum(s) + sum(f).
    """
    rng = np.random.default_rng(0)
    with netCDF4.Dataset(icon_file) as nc:
        base = np.asarray(nc.variables["CH4"][:], dtype=np.float64)
    x = 0.037
    # ADJ_LGRID at the initial time has ICON's (LAY, ROW, COL) shape
    s, f = rng.normal(size=(2, *base.shape[1:]))
    dconc0 = (icon_offset.apply(base, x) - base)[0]
    # the initial state and CONC record 0 are the same field, seen by both terms
    lhs = np.sum(dconc0 * s) + np.sum(dconc0 * f)
    rhs = x * icon_offset.apply_adjoint(s, f)
    assert lhs == pytest.approx(rhs, rel=1e-10)


def test_archive_round_trip(physical_params, icon_file, bcon_file, tmp_path, monkeypatch):
    path = tmp_path / "physical.nc"
    make_physical(physical_params, {"CH4": 0.012, "CH4B": -0.004}).archive(str(path))

    with netCDF4.Dataset(path) as nc:
        grp = nc.groups["icon"]
        assert grp.units == "ppm"
        assert grp.variables["CH4"].shape == ()
        assert float(grp.variables["CH4B_UNC"][:]) == pytest.approx(0.08)

    for name in physical_params:
        monkeypatch.setattr(PhysicalAbstractData, name, None)
    physical = PhysicalData.from_file(str(path))
    assert physical.icon["CH4"] == pytest.approx(0.012)
    assert physical.icon["CH4B"] == pytest.approx(-0.004)
    assert physical.icon_unc == pytest.approx({"CH4": 0.05, "CH4B": 0.08})


def test_adjoint_archive_is_rejected_as_prior(physical_params, tmp_path):
    path = tmp_path / "gradient.nc"
    make_physical(physical_params, {"CH4": 1.0, "CH4B": 1.0}, PhysicalAdjointData).archive(
        str(path)
    )
    with netCDF4.Dataset(path) as nc:
        assert nc.groups["icon"].units == "CF/ppm"

    with pytest.raises(ValueError, match="expected 'ppm'"):
        PhysicalData.from_file(str(path))


def test_icon_units_are_checked(physical_params, tmp_path):
    path = tmp_path / "physical.nc"
    make_physical(physical_params, {"CH4": 0.0, "CH4B": 0.0}).archive(str(path))
    with netCDF4.Dataset(path, "a") as nc:
        nc.groups["icon"].units = "1"

    with pytest.raises(ValueError, match="icon group has units '1'"):
        PhysicalData.from_file(str(path))


def test_prior_without_icon_is_rejected(physical_params, tmp_path, monkeypatch):
    path = tmp_path / "physical.nc"
    monkeypatch.setattr(input_defn, "inc_icon", False)
    make_physical(physical_params, None).archive(str(path))

    monkeypatch.setattr(input_defn, "inc_icon", True)
    with pytest.raises(ValueError, match="no icon group.*INC_ICON=false"):
        PhysicalData.from_file(str(path))


@pytest.fixture
def run_files(icon_file, bcon_file, tmp_path, monkeypatch):
    """Point the files prepare_model reads and writes at tmp_path, with a fresh file list."""
    monkeypatch.setattr(cmaq_config, "icon_run_file", str(tmp_path / "icon" / "ICON.nc"))
    monkeypatch.setattr(cmaq_config, "bcon_run_file", str(tmp_path / "bcon" / "BCON.<YYYYMMDD>.nc"))
    # make_template.py creates the emissions directory, prepare_model the others
    (tmp_path / "emis").mkdir()
    monkeypatch.setattr(cmaq_config, "emis_file", str(tmp_path / "emis" / "emis.<YYYY-MM-DD>.nc"))
    # the file list is built once, from the paths at the time
    monkeypatch.setattr(cmaq_io_files, "all_files", {})
    monkeypatch.setattr(cmaq_io_files, "firsttime", True)
    monkeypatch.setattr(cmaq_handle, "wipeout_fwd", lambda: None)
    return icon_file


@pytest.fixture
def ch4_only(physical_params, monkeypatch):
    """The test emission template only has CH4."""
    monkeypatch.setattr(PhysicalAbstractData, "spcs", ["CH4"])
    return {**physical_params, "spcs": ["CH4"]}


@pytest.mark.parametrize("inc_icon", (True, False))
def test_prepare_model_writes_icon_run_copy(ch4_only, run_files, monkeypatch, inc_icon):
    monkeypatch.setattr(input_defn, "inc_icon", inc_icon)
    offset = 0.021
    physical = make_physical(ch4_only, {"CH4": offset} if inc_icon else None)

    model_input = prepare_model(physical)

    run_icon = model_input.file_data["icon"]["actual"]
    assert run_icon == cmaq_config.icon_run_file
    with netCDF4.Dataset(run_files) as staged, netCDF4.Dataset(run_icon) as run:
        expected = staged.variables["CH4"][:] + (offset if inc_icon else 0.0)
        np.testing.assert_allclose(run.variables["CH4"][:], expected, rtol=1e-6)
        # ICON keeps its own time axis
        np.testing.assert_array_equal(run.variables["TFLAG"][:], staged.variables["TFLAG"][:])
