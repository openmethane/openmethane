import datetime
import logging

import numpy as np
import pytest

from openmethane.fourdvar.datadef.observation_data import (
    OBS_OPERATOR_VERSION,
    ObservationData,
    load_observations_from_file,
)


@pytest.mark.parametrize(
    "fname",
    ["test_obs_2022-12-08.pic.gz", "test_obs_2022-*-08.*", "test_obs_2022-*"],
)
def test_load_observations_from_file(test_data_dir, fname):
    obs = load_observations_from_file(
        test_data_dir / "obs" / fname,
        start_date=datetime.date(2022, 12, 8),
        end_date=datetime.date(2022, 12, 8),
    )
    assert obs.domain["SDATE"] == 20221208
    assert obs.domain["EDATE"] == 20221208
    assert obs.domain["TSTEP"] == 10000

    assert len(obs.observations) == 73
    obs_0 = obs.observations[0]

    assert isinstance(obs_0, dict)
    assert obs_0["qa_value"] == 1.0
    # test_obs_2022-12-08.pic.gz predates the column averaging kernel operator
    # and is kept in the old format; there is no TROPOMI test data for that day
    # to regenerate it from. It doubles as coverage of the legacy read path.
    expected_keys = [
        "aerosol_aod_SWIR",
        "alpha_scale",
        "latitude_center",
        "latitude_corners",
        "lite_coord",
        "longitude_center",
        "longitude_corners",
        "model_pweight",
        "model_vis",
        "obs_kernel",
        "qa_value",
        "ref_profile",
        "surface_albedo_SWIR",
        "time",
        "type",
        "uncertainty",
        "value",
        "weight_grid",
    ]
    assert sorted(obs_0.keys()) == expected_keys


def test_load_observations_from_multiple_files(test_data_dir):
    obs = load_observations_from_file(
        test_data_dir / "obs" / "test_obs_2022-12-*.pic.gz",
        start_date=datetime.date(2022, 12, 7),
        end_date=datetime.date(2022, 12, 8),
    )
    # Note that the end date is 2022-12-07, not 2022-12-08
    assert obs.domain["SDATE"] == 20221207
    assert obs.domain["EDATE"] == 20221208
    assert obs.domain["TSTEP"] == 10000

    assert len(obs.observations) == 238


def test_observation_data(test_data_dir, target_environment):
    target_environment("docker-test")

    obs = ObservationData.from_file(test_data_dir / "obs" / "test_obs_2022-12-07.pic.gz")
    obs.assert_params()

    assert obs.length == 165
    assert len(obs.offset_term) == obs.length
    assert len(obs.weight_grid) == obs.length


def test_observation_data_column_operator(test_data_dir, target_environment):
    """The stored weights and offset must describe the full column operator."""
    target_environment("docker-test")

    obs = ObservationData.from_file(test_data_dir / "obs" / "test_obs_2022-12-07.pic.gz")

    for i in range(obs.length):
        meta = obs.misc_meta[i]
        avker = np.asarray(meta["obs_kernel"])
        pressure_weight = np.asarray(meta["sat_pressure_weight"])

        # TROPOMI column kernels are normalised so that their pressure-weighted
        # mean is one; the model weights inherit that, since the part of the
        # column above the model top is filled from the model's own top layer
        assert sum(obs.weight_grid[i].values()) == pytest.approx(
            float(pressure_weight @ avker), rel=1e-6
        )

        # the offset is the retrieval prior's contribution, which is nowhere
        # near zero once the kernel is applied
        assert obs.offset_term[i] != 0.0
        assert -50.0 < obs.offset_term[i] < 50.0

        # part of the retrieval column sits above the CMAQ model top
        coverage = np.asarray(meta["model_coverage"])
        assert coverage[0] < 1.0
        assert np.all(coverage[1:] == pytest.approx(1.0))


def test_observation_data_retains_retrieval_precision(test_data_dir, target_environment):
    """The retrieval precision must survive into the loaded observations."""
    target_environment("docker-test")

    obs = ObservationData.from_file(test_data_dir / "obs" / "test_obs_2022-12-07.pic.gz")

    precision = [meta["ch4_column_precision"] for meta in obs.misc_meta]
    assert len(precision) == obs.length
    assert all(0.0 < value < 100.0 for value in precision)

    # it is kept alongside, not in place of, the uncertainty the inversion uses,
    # which is a constant standing in for the whole error budget
    assert set(obs.uncertainty) == {20.0}
    assert any(value != 20.0 for value in precision)


def test_observation_data_legacy_file_warns(test_data_dir, target_environment, caplog):
    """A file written before the kernel was applied must be flagged loudly."""
    target_environment("docker-test")

    with caplog.at_level(logging.WARNING):
        obs = ObservationData.from_file(test_data_dir / "obs" / "test_obs_2022-12-08.pic.gz")

    assert f"this is version {OBS_OPERATOR_VERSION}" in caplog.text
    assert "column averaging kernel" in caplog.text
    # legacy files carry no offset term, so they fall back to a purely linear
    # operator. Nothing survives the docker-test date range here, but the
    # default is what any observation that did survive would get.
    assert all(offset == 0.0 for offset in obs.offset_term)

    legacy = load_observations_from_file(
        test_data_dir / "obs" / "test_obs_2022-12-08.pic.gz",
        start_date=datetime.date(2022, 12, 8),
        end_date=datetime.date(2022, 12, 8),
    )
    assert all("offset_term" not in observation for observation in legacy.observations)


def test_observation_data_missing(test_data_dir, target_environment):
    target_environment("docker-test")

    inp_file = test_data_dir / "obs" / "test_obs_2022-12-07.pic.gz.missing"
    with pytest.raises(
        FileNotFoundError, match=f"No valid observations files found matching {inp_file}"
    ):
        ObservationData.from_file(inp_file)
