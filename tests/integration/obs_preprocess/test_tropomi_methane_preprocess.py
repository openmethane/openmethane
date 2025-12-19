import numpy as np
from click.testing import CliRunner
from scripts.obs_preprocess import tropomi_methane_preprocess

from openmethane.fourdvar.util.file_handle import load_list


def clean(value):
    """
    Clean values for regression testing

    Converts any numpy values to raw ints/floats/lists
    """

    if isinstance(value, np.ndarray):
        value = clean(value.tolist())
    elif hasattr(value, "item"):
        value = value.item()
    elif isinstance(value, dict):
        value = {key: clean(item) for key, item in value.items()}
    elif isinstance(value, tuple | list):
        value = [clean(item) for item in value]

    if isinstance(value, float):
        if value > 1e10 or value < 1e-10:
            # Use scientific notation for large/small numbers
            value = float(f"{value:.3g}")
        else:
            value = round(value, 3)
    return value

def test_preprocess(tmp_path, root_dir, test_data_dir, target_environment, data_regression):
    target_environment("docker-test")

    output_file = tmp_path / "out.pkl.gz"
    runner = CliRunner()
    result = runner.invoke(
        tropomi_methane_preprocess.run_tropomi_preprocess,
        [
            "--source",
            str(test_data_dir / "tropomi" / "2022-12-07*" / "*.nc4"),
            "--output-file",
            str(output_file),
        ],
    )

    assert result.exit_code == 0, result.output
    assert output_file.exists()

    obs_list = load_list(output_file)
    assert len(obs_list) == 166

    # First item is the domain
    domain = clean(obs_list[0])
    # version is dynamic, so remove it from this test
    del domain["openmethane_version"]
    data_regression.check(domain, basename="tropomi_methane_domain")

    # Rest are observations
    obs = obs_list[1]

    data_regression.check(list(obs.keys()), basename="tropomi_methane_obs")
