import os

import click
import earthaccess
import pytest
from click.testing import CliRunner
from scripts.obs_preprocess import fetch_tropomi

EARTHDATA_ENV_VARS = ("EARTHDATA_USERNAME", "EARTHDATA_PASSWORD", "EARTHDATA_TOKEN")


@pytest.fixture
def fresh_login(monkeypatch):
    """
    Discard any cached Earthdata login

    earthaccess caches a successful login on a module-level singleton, so
    without resetting it a later login attempt succeeds no matter which
    credentials are available.
    """
    monkeypatch.setattr(earthaccess, "__auth__", earthaccess.Auth())


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


def test_create_session(fresh_login):
    # This should come from the .env file
    assert os.environ.get("EARTHDATA_USERNAME") and os.environ.get("EARTHDATA_PASSWORD")

    session = fetch_tropomi.create_session()

    # The credentials are exchanged for a bearer token rather than written to disk
    assert session.headers["Authorization"].startswith("Bearer ")


@pytest.mark.parametrize("env_var", ["EARTHDATA_USERNAME", "EARTHDATA_PASSWORD"])
def test_create_session_missing_creds(fresh_login, monkeypatch, env_var):
    monkeypatch.delenv(env_var)
    monkeypatch.delenv("EARTHDATA_TOKEN", raising=False)

    with pytest.raises(
        click.ClickException,
        match="Set EARTHDATA_TOKEN, or both EARTHDATA_USERNAME and EARTHDATA_PASSWORD",
    ):
        fetch_tropomi.create_session()


# This hits the api with a period that has no data
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
            "1901-07-02",
            str(tmpdir),
        ],
    )

    # A period predating the mission returns no granules rather than an error
    assert result.exit_code == 0, result.output
    assert "Found 0 granules" in result.output
    assert os.listdir(tmpdir / "1900-07-01T0000_1901-07-02T0000_148.0_-23.5_150.0_-22.0") == []
