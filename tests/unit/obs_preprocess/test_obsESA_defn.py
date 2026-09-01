"""Tests for the observation uncertainty built by ObsSRON."""

import pytest

from openmethane.obs_preprocess.obsESA_defn import (
    DEFAULT_MODEL_UNCERTAINTY,
    PRECISION_INFLATION,
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
    """The formula applied in add_visibility, stated independently."""
    model_unc = 10.0
    precision = 2.0
    expected = (model_unc**2 + (PRECISION_INFLATION * precision) ** 2) ** 0.5

    assert expected == pytest.approx(((10.0**2) + (4.0**2)) ** 0.5)
    # the model term dominates at realistic TropOMI precisions
    assert model_unc < expected < model_unc * 1.1
