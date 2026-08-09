import os

import pytest
from click.testing import CliRunner
from scripts.obs_preprocess import fetch_tropomi

# A window covering two consecutive orbits over the au-test domain. Orbit 24426
# passes to the west of the domain and is discarded; orbit 24427 crosses it and
# is kept. Kept deliberately narrow so the test downloads two granules rather
# than a whole day's worth.
START = "2022-07-01T01:30:00"
END = "2022-07-01T03:00:00"
OUTPUT_DIR = "2022-07-01T0130_2022-07-01T0300_148.0_-23.5_150.0_-22.0"
EXPECTED_GRANULE = (
    "S5P_OFFL_L2__CH4____20220701T024730_20220701T042859_24427_02_020301_20220702T182808.nc4"
)


# This hits the S3 bucket
def test_fetch(tmpdir, root_dir):
    runner = CliRunner()
    result = runner.invoke(
        fetch_tropomi.fetch_data,
        [
            "-c",
            str(root_dir / "config" / "obs_preprocess" / "config.austtest.json"),
            "-s",
            START,
            "-e",
            END,
            str(tmpdir),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Data fetched successfully!" in result.output

    # The granule that misses the domain is downloaded, then discarded
    assert "no overlap with the bounding box, discarded" in result.output

    # Check that the expected files are created
    assert os.listdir(tmpdir) == [OUTPUT_DIR]
    assert os.listdir(tmpdir / OUTPUT_DIR) == [EXPECTED_GRANULE]


# This hits the S3 bucket with a period the archive does not cover
def test_fetch_no_granules(tmpdir, root_dir):
    runner = CliRunner()
    result = runner.invoke(
        fetch_tropomi.fetch_data,
        [
            "-c",
            str(root_dir / "config" / "obs_preprocess" / "config.austtest.json"),
            "-s",
            "1900-07-01",
            "-e",
            "1900-07-02",
            str(tmpdir),
        ],
    )

    assert result.exit_code == 1, result.output
    assert "No granules found" in result.output


@pytest.mark.parametrize("env_var", ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"])
def test_fetch_ignores_aws_credentials(monkeypatch, env_var):
    """The bucket is public, so requests must be unsigned even if keys are set"""
    monkeypatch.setenv(env_var, "not-a-real-credential")

    client = fetch_tropomi.create_client()

    assert client.meta.config.signature_version is fetch_tropomi.UNSIGNED
