from fourdvar.datadef.observation_data import ObservationData


def test_observation_data(test_data_dir, target_environment):
    target_environment('docker-test')

    ObservationData.from_file(test_data_dir / "obs" / "test_obs.pkl.gz")
