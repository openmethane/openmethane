"""Tests for the observation uncertainty built by ObsSRON."""

import pytest

from openmethane.obs_preprocess.obsESA_defn import (
    DEFAULT_AEROSOL_UNCERTAINTY,
    DEFAULT_MODEL_UNCERTAINTY,
    PRECISION_INFLATION,
    aerosol_uncertainty,
    aerosol_uncertainty_scale,
    air_mass_factor,
    model_uncertainty,
)


def test_model_uncertainty_default(monkeypatch):
    monkeypatch.delenv("OPENMETHANE_MODEL_UNCERTAINTY", raising=False)
    assert model_uncertainty() == DEFAULT_MODEL_UNCERTAINTY == 10.0


def test_model_uncertainty_from_environment(monkeypatch):
    monkeypatch.setenv("OPENMETHANE_MODEL_UNCERTAINTY", "17.5")
    assert model_uncertainty() == 17.5


def test_model_uncertainty_is_read_on_each_call(monkeypatch):
    """It must not be captured at import time, or a run cannot configure it."""
    monkeypatch.setenv("OPENMETHANE_MODEL_UNCERTAINTY", "5")
    assert model_uncertainty() == 5.0
    monkeypatch.setenv("OPENMETHANE_MODEL_UNCERTAINTY", "30")
    assert model_uncertainty() == 30.0


def test_uncertainty_combines_model_and_precision_in_quadrature():
    """The aerosol-free part of the budget, stated independently."""
    model_unc = 10.0
    precision = 2.0
    expected = (model_unc**2 + (PRECISION_INFLATION * precision) ** 2) ** 0.5

    assert expected == pytest.approx(((10.0**2) + (4.0**2)) ** 0.5)
    # the model term dominates at realistic TropOMI precisions
    assert model_unc < expected < model_unc * 1.1


def test_aerosol_uncertainty_scale_default(monkeypatch):
    monkeypatch.delenv("OPENMETHANE_AEROSOL_UNCERTAINTY", raising=False)
    assert aerosol_uncertainty_scale() == DEFAULT_AEROSOL_UNCERTAINTY == 103.0


def test_aerosol_uncertainty_scale_from_environment(monkeypatch):
    monkeypatch.setenv("OPENMETHANE_AEROSOL_UNCERTAINTY", "50")
    assert aerosol_uncertainty_scale() == 50.0


def test_air_mass_factor_is_two_at_nadir_with_the_sun_overhead():
    assert air_mass_factor(0.0, 0.0) == pytest.approx(2.0)


def test_air_mass_factor_adds_the_two_secants():
    """Down the solar path and back up the viewing path."""
    assert air_mass_factor(60.0, 0.0) == pytest.approx(3.0)
    assert air_mass_factor(0.0, 60.0) == pytest.approx(3.0)
    assert air_mass_factor(60.0, 60.0) == pytest.approx(4.0)


def test_air_mass_factor_over_the_june_domain():
    """June 2024 aust10km: mean solar zenith 52.9 deg, mean air mass 2.92."""
    assert air_mass_factor(52.9, 22.0) == pytest.approx(2.73, abs=0.01)


@pytest.mark.parametrize("angle", [0.0, 30.0, 52.9, 70.0])
def test_aerosol_uncertainty_is_zero_without_aerosol(angle, monkeypatch):
    """No aerosol, no artefact, however long the path."""
    monkeypatch.delenv("OPENMETHANE_AEROSOL_UNCERTAINTY", raising=False)
    assert aerosol_uncertainty(0.0, angle, angle) == 0.0


def test_aerosol_uncertainty_grows_with_the_path(monkeypatch):
    """The point of the term: the same aerosol costs more seen obliquely."""
    monkeypatch.delenv("OPENMETHANE_AEROSOL_UNCERTAINTY", raising=False)
    nadir = aerosol_uncertainty(0.0225, 52.9, 0.0)
    swath_edge = aerosol_uncertainty(0.0225, 52.9, 60.0)

    assert nadir == pytest.approx(6.2, abs=0.1)
    assert swath_edge == pytest.approx(8.5, abs=0.1)
    assert swath_edge / nadir == pytest.approx(1.4, abs=0.05)


def test_aerosol_uncertainty_treats_a_negative_retrieved_aod_as_aerosol(monkeypatch):
    """AOD is a fitted parameter and can come back slightly negative."""
    monkeypatch.delenv("OPENMETHANE_AEROSOL_UNCERTAINTY", raising=False)
    assert aerosol_uncertainty(-0.01, 40.0, 10.0) == aerosol_uncertainty(0.01, 40.0, 10.0)


def test_aerosol_uncertainty_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("OPENMETHANE_AEROSOL_UNCERTAINTY", "0")
    assert aerosol_uncertainty(0.05, 52.9, 45.0) == 0.0


def test_uncertainty_combines_all_three_terms_in_quadrature(monkeypatch):
    """The formula applied in add_visibility, stated independently."""
    monkeypatch.delenv("OPENMETHANE_AEROSOL_UNCERTAINTY", raising=False)
    model_unc = 10.0
    precision = 2.0
    aerosol_unc = aerosol_uncertainty(0.0225, 52.9, 22.0)
    expected = (model_unc**2 + (PRECISION_INFLATION * precision) ** 2 + aerosol_unc**2) ** 0.5

    # a typical June sounding, against 10.77 ppb without the aerosol term
    assert expected == pytest.approx(12.50, abs=0.01)
