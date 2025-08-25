import datetime

import pytest

from fourdvar.datadef.observation_data import ObservationData, load_observations_from_file


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

    # not sure what I should check

    obs.length == 1575


def test_observation_data_missing(test_data_dir, target_environment):
    target_environment("docker-test")

    inp_file = test_data_dir / "obs" / "test_obs_2022-12-07.pic.gz.missing"
    with pytest.raises(
        FileNotFoundError, match=f"No valid observations files found matching {inp_file}"
    ):
        ObservationData.from_file(inp_file)
