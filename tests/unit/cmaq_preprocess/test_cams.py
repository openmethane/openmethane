"""Tests for reading CAMS products onto CMAQ columns."""

import datetime
import pathlib

import netCDF4
import numpy as np
import pytest

from openmethane.cmaq_preprocess.cams import (
    cmaq_layer_pressures,
    interpolate_columns,
    interpolate_from_cams_to_cmaq_grid,
)
from openmethane.cmaq_preprocess.cams_readers import CamsProfile, open_cams
from openmethane.cmaq_preprocess.read_config_cmaq import Domain

TEST_DATA = pathlib.Path(__file__).parents[2] / "test-data"
INVERSION_FILE = TEST_DATA / "cams" / "cams_inversion_v25r1_2022-12-07.nc"
EAC4_FILE = TEST_DATA / "cams" / "cams_eac4_methane_2022-12-07.nc"
DOMAIN = Domain(1, "au-test", "v1", "LamCon_34S_150E", "au-test_v1")

# One CAMS column of three levels, ordered from the surface up, in ppmV and Pa
PROFILE_FROM_SURFACE = CamsProfile(
    ch4_ppmv=np.array([[[1.9]], [[1.85]], [[1.8]]]),
    pressure_pa=np.array([[[100000.0]], [[70000.0]], [[40000.0]]]),
)
PROFILE_FROM_TOP = CamsProfile(
    ch4_ppmv=np.array([[[1.8]], [[1.85]], [[1.9]]]),
    pressure_pa=np.array([[[40000.0]], [[70000.0]], [[100000.0]]]),
)


def test_cmaq_layer_pressures_are_interface_midpoints():
    sigma = [1.0, 0.5, 0.0]
    pressure = cmaq_layer_pressures(np.array([100000.0, 90000.0]), sigma, 5000.0)

    # interfaces for the first column are 100000, 52500 and 5000 Pa
    assert pressure.shape == (2, 2)
    np.testing.assert_allclose(pressure[:, 0], [76250.0, 28750.0])
    assert (pressure[:, 1] < pressure[:, 0]).all()


def test_interpolation_is_exact_at_cams_pressures():
    out = interpolate_columns(
        PROFILE_FROM_SURFACE,
        np.array([0]),
        np.array([0]),
        np.array([[100000.0], [70000.0], [40000.0]]),
    )

    np.testing.assert_allclose(out[:, 0], [1.9, 1.85, 1.8], rtol=1e-6)


def test_interpolation_is_linear_in_log_pressure():
    halfway_in_log_pressure = np.sqrt(100000.0 * 70000.0)

    out = interpolate_columns(
        PROFILE_FROM_SURFACE,
        np.array([0]),
        np.array([0]),
        np.array([[halfway_in_log_pressure]]),
    )

    np.testing.assert_allclose(out[0, 0], 1.875, rtol=1e-6)


def test_interpolation_holds_the_nearest_level_beyond_the_column():
    out = interpolate_columns(
        PROFILE_FROM_SURFACE,
        np.array([0]),
        np.array([0]),
        np.array([[101000.0], [1000.0]]),
    )

    np.testing.assert_allclose(out[:, 0], [1.9, 1.8], rtol=1e-6)


def test_interpolation_accepts_levels_ordered_from_the_top():
    cmaq_pressure = np.array([[90000.0], [50000.0]])

    from_surface = interpolate_columns(
        PROFILE_FROM_SURFACE, np.array([0]), np.array([0]), cmaq_pressure
    )
    from_top = interpolate_columns(PROFILE_FROM_TOP, np.array([0]), np.array([0]), cmaq_pressure)

    np.testing.assert_allclose(from_top, from_surface)


def test_interpolation_uses_each_columns_own_pressures():
    # the same 70000 Pa is the second level of the first column, and between the
    # first and second levels of the second column, whose levels sit lower
    two_columns = CamsProfile(
        ch4_ppmv=np.array([[[1.9, 1.9]], [[1.85, 1.85]], [[1.8, 1.8]]]),
        pressure_pa=np.array([[[100000.0, 80000.0]], [[70000.0, 60000.0]], [[40000.0, 40000.0]]]),
    )

    out = interpolate_columns(
        two_columns,
        np.array([0, 0]),
        np.array([0, 1]),
        np.array([[70000.0, 70000.0]]),
    )

    np.testing.assert_allclose(out[0, 0], 1.85, rtol=1e-6)
    expected_second = 1.9 + (1.85 - 1.9) * np.log(70000 / 80000) / np.log(60000 / 80000)
    np.testing.assert_allclose(out[0, 1], expected_second, rtol=1e-6)


def test_inversion_reader_returns_ppmv_and_pressure_for_each_level():
    with open_cams(INVERSION_FILE, "inversion") as cams:
        profile = cams.profile(0)
        grid_shape = (len(cams.lat), len(cams.lon))

    assert profile.ch4_ppmv.shape == (34, *grid_shape)
    assert profile.pressure_pa.shape == (34, *grid_shape)
    # level 0 is nearest the surface, where the troposphere is about 1.9 ppm
    assert 1.75 < profile.ch4_ppmv[0].mean() < 2.0
    assert np.all(np.diff(profile.pressure_pa[:, 0, 0]) < 0)


def test_eac4_reader_returns_ppmv_and_pressure_for_each_level():
    with open_cams(EAC4_FILE, "eac4") as cams:
        profile = cams.profile(0)
        grid_shape = (len(cams.lat), len(cams.lon))

    assert profile.ch4_ppmv.shape == (25, *grid_shape)
    assert profile.pressure_pa.shape == (25, *grid_shape)
    # level 0 is 1000 hPa, where the troposphere is about 1.8 ppm
    assert 1.65 < profile.ch4_ppmv[0].mean() < 1.9
    assert profile.pressure_pa[0, 0, 0] == 100000.0
    assert np.all(np.diff(profile.pressure_pa[:, 0, 0]) < 0)


def test_inversion_reader_reports_the_release():
    with open_cams(INVERSION_FILE, "inversion") as cams:
        assert cams.release == "v25r1"


def test_eac4_reader_has_no_release():
    with open_cams(EAC4_FILE, "eac4") as cams:
        assert cams.release is None


def test_an_inversion_file_is_rejected_as_eac4():
    with pytest.raises(ValueError, match="not a CAMS eac4 file.*ch4_c"):
        open_cams(INVERSION_FILE, "eac4")


def test_an_eac4_file_is_rejected_as_inversion():
    with pytest.raises(ValueError, match="not a CAMS inversion file.*CH4"):
        open_cams(EAC4_FILE, "inversion")


def test_coverage_error_names_the_dates_and_the_fallback():
    with open_cams(INVERSION_FILE, "inversion") as cams:
        with pytest.raises(ValueError, match="2026-03-01.*CAMS_PRODUCT=eac4"):
            cams.require_dates([datetime.date(2026, 3, 1)])


def test_dates_inside_the_file_are_accepted():
    with open_cams(INVERSION_FILE, "inversion") as cams:
        cams.require_dates([datetime.date(2022, 12, 7)])


@pytest.fixture
def mcip_columns():
    """Sigma levels, model top and surface pressure of the tracked test MCIP columns"""
    mcip_dir = TEST_DATA / "mcip" / "2022-12-07" / "d01"
    with (
        netCDF4.Dataset(mcip_dir / "METCRO3D_au-test_v1") as met,
        netCDF4.Dataset(mcip_dir / "METCRO2D_au-test_v1") as surface,
    ):
        sigma = np.array(met.getncattr("VGLVLS"))
        model_top = met.getncattr("VGTOP")
        surface_pressure = np.array(surface.variables["PRSFC"][0, 0]).ravel()
    return sigma, model_top, surface_pressure


@pytest.mark.parametrize(
    "product, path",
    [("inversion", INVERSION_FILE), ("eac4", EAC4_FILE)],
)
def test_interpolation_preserves_the_pressure_weighted_column_mean(product, path, mcip_columns):
    sigma, model_top, surface_pressure = mcip_columns
    with open_cams(path, product) as cams:
        profile = cams.profile(0)
        grid_shape = (len(cams.lat), len(cams.lon))
    # a distinct CAMS cell for each CMAQ column, so every CAMS column is exercised
    cells = np.arange(len(surface_pressure)) % (grid_shape[0] * grid_shape[1])
    ilat, ilon = np.divmod(cells, grid_shape[1])
    layer_pressure = cmaq_layer_pressures(surface_pressure, sigma, model_top)

    out = interpolate_columns(profile, ilat, ilon, layer_pressure)

    interfaces = (surface_pressure - model_top) * sigma[:, None] + model_top
    thickness = -np.diff(interfaces, axis=0)
    cmaq_column_mean = (out * thickness).sum(axis=0) / thickness.sum(axis=0)
    # the same CAMS column, integrated on a fine log-pressure grid so that it carries
    # none of the discretisation of the CMAQ layers
    cams_column_mean = np.empty(len(surface_pressure))
    for column in range(len(surface_pressure)):
        cams_pressure = profile.pressure_pa[:, ilat[column], ilon[column]]
        cams_ch4 = profile.ch4_ppmv[:, ilat[column], ilon[column]]
        order = np.argsort(cams_pressure)
        fine = np.linspace(np.log(model_top), np.log(surface_pressure[column]), 20001)
        fine_ch4 = np.interp(fine, np.log(cams_pressure[order]), cams_ch4[order])
        weighted = 0.5 * (fine_ch4[1:] * np.exp(fine[1:]) + fine_ch4[:-1] * np.exp(fine[:-1]))
        weights = 0.5 * (np.exp(fine[1:]) + np.exp(fine[:-1]))
        cams_column_mean[column] = (weighted * np.diff(fine)).sum() / (
            weights * np.diff(fine)
        ).sum()

    # within 0.5 ppb of a column of about 1.8 ppm
    np.testing.assert_allclose(cmaq_column_mean, cams_column_mean, atol=5e-4)


# The surface-layer mean of ICON and BCON built from each fixture, measured when the
# fixtures were made. EAC4 is about 130 ppb lower than the inversion at the surface.
@pytest.mark.parametrize(
    "product, path, release, surface_ppmv",
    [
        ("inversion", INVERSION_FILE, "v25r1", 1.904),
        ("eac4", EAC4_FILE, None, 1.772),
    ],
)
def test_icon_and_bcon_are_filled_in_ppmv_and_record_the_product(
    tmp_path, product, path, release, surface_ppmv
):
    interpolate_from_cams_to_cmaq_grid(
        dates=[datetime.date(2022, 12, 7)],
        domain=DOMAIN,
        mech="CH4only",
        input_cams_file=path,
        template_icon_file=TEST_DATA / "cmaq" / "template_icon_profile_CH4only_d01.nc",
        template_bcon_file=TEST_DATA / "cmaq" / "template_bcon_profile_CH4only_d01.nc",
        met_dir=TEST_DATA / "mcip",
        ctm_dir=tmp_path,
        force_update=True,
        cams_product=product,
    )

    for kind in ("ICON", "BCON"):
        with netCDF4.Dataset(
            tmp_path / "2022-12-07" / "d01" / f"{kind}.d01.au-test_v1.CH4only.nc"
        ) as out:
            surface_layer = out.variables["CH4"][:, 0]
            assert surface_layer.mean() == pytest.approx(surface_ppmv, abs=0.01)
            assert out.getncattr("CAMS_PRODUCT") == product
            assert getattr(out, "CAMS_RELEASE", None) == release


def test_dates_outside_the_file_fail_before_anything_is_written(tmp_path):
    with pytest.raises(ValueError, match="CAMS_PRODUCT=eac4"):
        interpolate_from_cams_to_cmaq_grid(
            dates=[datetime.date(2030, 1, 1)],
            domain=DOMAIN,
            mech="CH4only",
            input_cams_file=INVERSION_FILE,
            template_icon_file=TEST_DATA / "cmaq" / "template_icon_profile_CH4only_d01.nc",
            template_bcon_file=TEST_DATA / "cmaq" / "template_bcon_profile_CH4only_d01.nc",
            met_dir=TEST_DATA / "mcip",
            ctm_dir=tmp_path,
            force_update=True,
            cams_product="inversion",
        )

    assert list(tmp_path.iterdir()) == []
