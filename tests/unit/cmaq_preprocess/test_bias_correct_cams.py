"""Tests that the bias is zero after correcting it."""

import datetime
import shutil

import numpy as np
import pytest
import xarray as xr

import openmethane.fourdvar.datadef as d
from openmethane.cmaq_preprocess.bias import (
    calculate_icon_bias,
    correct_icon_bcon,
    mean_weight_sum,
    ppm2ppb,
    simulate_static_columns,
)

START_DATE = datetime.date(2022, 12, 7)
END_DATE = datetime.date(2022, 12, 7)
OBS_FILE_NAME = "test_obs_2022-12-07.pic.gz"
ICON_FILE_NAME = "template_icon_profile_CH4only_d01.nc"
BCON_FILE_NAMES = ["template_bcon_profile_CH4only_d01.nc"]


def copy_cmaq_files(test_data_dir, tmp_path):
    """Copy the icon/bcon templates somewhere they can be corrected in place."""
    icon_file = tmp_path / ICON_FILE_NAME
    shutil.copy(test_data_dir / "cmaq" / ICON_FILE_NAME, icon_file)
    bcon_files = []
    for name in BCON_FILE_NAMES:
        bcon_file = tmp_path / name
        shutil.copy(test_data_dir / "cmaq" / name, bcon_file)
        bcon_files.append(bcon_file)
    return icon_file, bcon_files


def test_bias_zero_after_correct(test_data_dir, tmp_path, monkeypatch):
    # setup test data
    monkeypatch.setenv("START_DATE", "2022-12-07")
    monkeypatch.setenv("END_DATE", "2022-12-07")

    icon_file, bcon_files = copy_cmaq_files(test_data_dir, tmp_path)
    obs_file = test_data_dir / "obs" / OBS_FILE_NAME

    # calculate bias
    bias = calculate_icon_bias(
        icon_files=[icon_file],
        obs_file=obs_file,
        start_date=START_DATE,
        end_date=END_DATE,
    )

    # pre-existing bias has to be larger than almost zero, otherwise the later
    # assert is meaningless
    assert abs(bias) > 1e-6

    # correct bias
    correct_icon_bcon(
        species="CH4",
        bias=bias,
        icon_files=[icon_file],
        bcon_files=bcon_files,
    )

    # calculate new bias - should be zero
    new_bias = calculate_icon_bias(
        icon_files=[icon_file],
        obs_file=obs_file,
        start_date=START_DATE,
        end_date=END_DATE,
    )
    assert abs(new_bias) <= 1e-6


def test_simulate_static_columns_matches_observation_operator(test_data_dir, tmp_path, monkeypatch):
    """The background columns must be built the way the inversion builds its own.

    `fourdvar.transfunc.obs_operator` simulates an observation as
    `ppm2ppb * sum(weight_grid * conc) + offset_term`; anything the bias
    correction compares the satellite against has to include that offset, or the
    correction it applies is wrong by the mean offset (about -13 ppb for
    TROPOMI CH4).
    """
    monkeypatch.setenv("START_DATE", "2022-12-07")
    monkeypatch.setenv("END_DATE", "2022-12-07")

    icon_file, _ = copy_cmaq_files(test_data_dir, tmp_path)
    obs = d.ObservationData.from_file(test_data_dir / "obs" / OBS_FILE_NAME)
    indices = obs.ind_by_date["20221207"]
    assert len(indices) > 0

    field = xr.open_dataset(icon_file)["CH4"].to_numpy()[0]
    expected = np.array(
        [
            ppm2ppb * sum(w * field[c[2], c[3], c[4]] for c, w in obs.weight_grid[i].items())
            + obs.offset_term[i]
            for i in indices
        ]
    )

    simulated = simulate_static_columns(icon_file, obs, indices)

    np.testing.assert_allclose(simulated, expected)
    # the offset is what distinguishes this from a plain weighted column mean,
    # and it is large enough to matter
    offsets = np.array([obs.offset_term[i] for i in indices])
    assert abs(offsets.mean()) > 1.0


def test_correction_closes_the_gap_in_observation_space(test_data_dir, tmp_path, monkeypatch):
    """Applying the bias must make the simulated columns match the satellite mean.

    This is the quantity `fourdvar` reports as `bias`, so it is the one that has
    to go to zero.
    """
    monkeypatch.setenv("START_DATE", "2022-12-07")
    monkeypatch.setenv("END_DATE", "2022-12-07")

    icon_file, bcon_files = copy_cmaq_files(test_data_dir, tmp_path)
    obs_file = test_data_dir / "obs" / OBS_FILE_NAME

    bias = calculate_icon_bias(
        icon_files=[icon_file],
        obs_file=obs_file,
        start_date=START_DATE,
        end_date=END_DATE,
    )
    correct_icon_bcon(
        species="CH4",
        bias=bias,
        icon_files=[icon_file],
        bcon_files=bcon_files,
    )

    obs = d.ObservationData.from_file(obs_file)
    indices = obs.ind_by_date["20221207"]
    simulated = simulate_static_columns(icon_file, obs, indices)
    observed = np.array(obs.value)[indices]

    # the residual fourdvar would report, in ppb
    assert abs((observed - simulated).mean()) < 1e-3


def test_mean_weight_sum(test_data_dir, monkeypatch):
    monkeypatch.setenv("START_DATE", "2022-12-07")
    monkeypatch.setenv("END_DATE", "2022-12-07")

    obs = d.ObservationData.from_file(test_data_dir / "obs" / OBS_FILE_NAME)

    # the operational TROPOMI column kernel is normalised against the pressure
    # weights, so the operator puts a total weight of one on the model
    assert mean_weight_sum(obs) == pytest.approx(1.0, abs=1e-6)
