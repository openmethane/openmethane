import os
from pathlib import Path

import click
import pytest
from click.testing import CliRunner
from scripts.obs_preprocess import fetch_tropomi

# This hits the api
def test_fetch(tmpdir, root_dir):
    runner = CliRunner()
    result = runner.invoke(
        fetch_tropomi.fetch_data,
        [
            "-c",
            str(root_dir / "config" / "obs_preprocess" / "config.austtest.json"),
            "-s",
            "2022-07-01",
            "-e",
            "2022-07-02",
            str(tmpdir),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Data fetched successfully!" in result.output

    # Check that the expected files are created
    assert os.listdir(tmpdir) == ["2022-07-01T0000_2022-07-02T0000_148.0_-23.5_150.0_-22.0"]
    assert os.listdir(tmpdir / "2022-07-01T0000_2022-07-02T0000_148.0_-23.5_150.0_-22.0") == [
        "S5P_RPRO_L2__CH4____20220701T024730_20220701T042859_24427_03_020400_20230131T104028.SUB.nc4"
    ]


@pytest.mark.parametrize("env_var", ["EARTHDATA_USERNAME", "EARTHDATA_PASSWORD"])
def test_fetch_missing_creds(monkeypatch, env_var):
    # This should come from the .env file
    assert env_var in os.environ

    expected_cred_file = Path("~/.netrc").expanduser()
    if expected_cred_file.exists():
        os.remove(expected_cred_file)

    fetch_tropomi.create_session()

    assert expected_cred_file.exists()

    monkeypatch.delenv(env_var)

    # Still works if the ~/.netrc file exists
    fetch_tropomi.create_session()

    # Exception is raised if the ~/.netrc file is removed and env variables aren't available
    os.remove(expected_cred_file)
    with pytest.raises(
        click.ClickException,
        match="EARTHDATA_USERNAME or EARTHDATA_PASSWORD environment variables missing",
    ):
        fetch_tropomi.create_session()


# This hits the api with invalid data
def test_fetch_invalid_date(tmpdir, root_dir):
    runner = CliRunner()
    result = runner.invoke(
        fetch_tropomi.fetch_data,
        [
            "-c",
            str(root_dir / "config" / "obs_preprocess" / "config.austtest.json"),
            "-s",
            "1900-07-01",
            "-e",
            "1901-07-02",
            str(tmpdir),
        ],
    )

    assert result.exit_code == 1, result.output
    assert str(result.exception) == '500 Server Error: Internal Server Error for url: https://disc.gsfc.nasa.gov/service/subset/jsonwsp'

