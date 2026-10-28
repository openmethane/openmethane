"""The boundary offset as a PhysicalData term: its file format and its bounds."""

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
from openmethane.fourdvar.util import bcon_offset

NROWS, NCOLS, NLAYS = 10, 10, 32
NPERIM = bcon_map.perimeter_size(NCOLS, NROWS)


@pytest.fixture
def bcon_file(test_data_dir, tmp_path, monkeypatch):
    """A copy of the test BCON with known values, used as the staged BCON."""
    path = tmp_path / "BCON.nc"
    shutil.copy(test_data_dir / "cmaq" / "template_bcon_profile_CH4only_d01.nc", path)
    monkeypatch.setattr(cmaq_config, "bcon_file", str(path))
    return path


@pytest.fixture
def physical_params(monkeypatch, tmp_path):
    # archive() otherwise sets up the archive directory under STORE_PATH
    monkeypatch.setattr(_physical_abstract_data, "get_archive_path", lambda: str(tmp_path))
    rng = np.random.default_rng(0)
    region_map, _ = bcon_map.build_region_map(NCOLS, NROWS, NLAYS, 4, 4, [0, 11, 17, 22])
    nregion = region_map.max() + 1
    params = {
        "tday_emis": 1,
        "nstep_emis": 1,
        "nlays_emis": 1,
        "nrows": NROWS,
        "ncols": NCOLS,
        "spcs": ["CH4"],
        "emis_unc": {"CH4": np.full((1, 1, NROWS, NCOLS), 0.6)},
        "bcon_region": nregion,
        "nstep_bcon": 1,
        "bcon_region_map": region_map,
        "bcon_step_start": np.array([0]),
        "bcon_step_end": np.array([86400]),
        "bcon_unc": {"CH4": rng.uniform(0.01, 0.03, (1, nregion))},
    }
    if input_defn.inc_icon is True:
        params["icon_unc"] = {"CH4": 1.5}
    for name, val in params.items():
        monkeypatch.setattr(PhysicalAbstractData, name, val)
    return params


def make_physical(params, bcon_value=0.0):
    emis = {"CH4": np.ones((1, 1, NROWS, NCOLS))}
    bcon = {"CH4": np.full((1, params["bcon_region"]), bcon_value)}
    icon = {"CH4": 1.0} if input_defn.inc_icon else None
    return PhysicalData(icon, emis, bcon)


def test_archive_round_trip(physical_params, bcon_file, tmp_path, monkeypatch):
    path = tmp_path / "physical.nc"
    make_physical(physical_params, bcon_value=0.005).archive(str(path))

    with netCDF4.Dataset(path) as nc:
        grp = nc.groups["bcon"]
        assert grp.units == "ppm"
        assert grp.variables["STEP_START"].units == "seconds since 2022-12-07 00:00:00"

    # from_file refuses to change parameters that are already set
    for name in physical_params:
        monkeypatch.setattr(PhysicalAbstractData, name, None)
    physical = PhysicalData.from_file(str(path))
    np.testing.assert_array_equal(physical.bcon_region_map, physical_params["bcon_region_map"])
    np.testing.assert_allclose(physical.bcon["CH4"], 0.005)
    assert physical.bcon_step_end.tolist() == [86400]
    np.testing.assert_allclose(
        physical.bcon_unc["CH4"], physical_params["bcon_unc"]["CH4"], rtol=1e-6
    )


def test_adjoint_archive_units(physical_params, tmp_path):
    """A gradient's bcon is per ppm of offset, so it can't pass as a prior."""
    path = tmp_path / "gradient.nc"
    bcon = {"CH4": np.zeros((1, physical_params["bcon_region"]))}
    icon = {"CH4": 1.0} if input_defn.inc_icon else None
    PhysicalAdjointData(icon, {"CH4": np.ones((1, 1, NROWS, NCOLS))}, bcon).archive(str(path))
    with netCDF4.Dataset(path) as nc:
        assert nc.groups["bcon"].units == "CF/ppm"

    with pytest.raises(ValueError, match="expected 'ppm'"):
        PhysicalData.from_file(str(path))


def test_wrong_layer_count_is_rejected(physical_params, bcon_file, tmp_path, monkeypatch):
    path = tmp_path / "physical.nc"
    params = dict(physical_params)
    params["bcon_region_map"], _ = bcon_map.build_region_map(
        NCOLS, NROWS, NLAYS - 1, 4, 4, [0, 11, 17, 22]
    )
    monkeypatch.setattr(PhysicalAbstractData, "bcon_region_map", params["bcon_region_map"])
    make_physical(params).archive(str(path))

    for name in physical_params:
        monkeypatch.setattr(PhysicalAbstractData, name, None)
    with pytest.raises(ValueError, match="BCON_REGION has shape"):
        PhysicalData.from_file(str(path))


def test_old_prior_is_rejected(physical_params, tmp_path):
    path = tmp_path / "physical.nc"
    make_physical(physical_params).archive(str(path))
    with netCDF4.Dataset(path, "a") as nc:
        nc.groups["bcon"].delncattr("units")

    with pytest.raises(ValueError, match="regenerate the prior"):
        PhysicalData.from_file(str(path))


def test_offset_lower_bound(physical_params, bcon_file):
    region_map = physical_params["bcon_region_map"]
    with netCDF4.Dataset(bcon_file, "a") as nc:
        ch4 = nc.variables["CH4"][:]
        ch4[:] = 1.9
        ch4[0, 3, 2] = 1.2  # region 0: S edge, first segment, lowest band
        ch4[0, 30, 15] = 0.4  # E edge, top band
        ch4[0, :, bcon_map.corner_indices(NCOLS, NROWS)] = 0.0  # never read
        nc.variables["CH4"][:] = ch4

    lower = bcon_offset.offset_lower_bound(
        "CH4", region_map, [0], [86400], physical_params["bcon_region"]
    )
    expected = np.full((1, physical_params["bcon_region"]), -1.9)
    expected[0, region_map[3, 2]] = -1.2
    expected[0, region_map[30, 15]] = -0.4
    np.testing.assert_allclose(lower, expected, rtol=1e-6)

    # at the bound, the BCON CMAQ reads touches zero and goes no lower
    field = ch4 + bcon_map.expand(lower, region_map, np.array([0]))
    mapped = np.broadcast_to(region_map >= 0, field.shape)
    assert np.isclose(field[mapped].min(), 0, atol=1e-6)
    assert field[mapped].min() >= -1e-6


@pytest.mark.parametrize("allow_negative_emissions", (True, False))
def test_bounds_follow_condition_layout(physical_params, bcon_file, allow_negative_emissions):
    bounds, is_bcon = user_driver.get_bounds(PhysicalData, allow_negative_emissions)

    n_emis = NROWS * NCOLS
    n_icon = 1 if input_defn.inc_icon else 0
    nregion = physical_params["bcon_region"]
    assert len(bounds) == n_icon + n_emis + nregion
    assert is_bcon.tolist() == [False] * (n_icon + n_emis) + [True] * nregion

    emis_bounds = bounds[n_icon : n_icon + n_emis]
    expected = (None, None) if allow_negative_emissions else (0, None)
    assert set(emis_bounds) == {expected}

    # the boundary offsets are bounded either way, scaled like their unknowns
    with netCDF4.Dataset(bcon_file) as nc:
        base_min = nc.variables["CH4"][:].min(axis=0)
    unc = physical_params["bcon_unc"]["CH4"][0]
    region_map = physical_params["bcon_region_map"]
    for r, (lower, upper) in enumerate(bounds[n_icon + n_emis :]):
        assert upper is None
        assert lower == pytest.approx(-base_min[region_map == r].min() / unc[r], rel=1e-6)
