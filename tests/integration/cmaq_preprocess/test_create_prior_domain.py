import os
import pathlib
from unittest.mock import patch

from click.testing import CliRunner
from scripts.cmaq_preprocess.create_prior_domain import clean_directories
from scripts.cmaq_preprocess.create_prior_domain import main as create_prior_domain


def test_empty():
    runner = CliRunner()
    result = runner.invoke(create_prior_domain, [])
    assert result.exit_code == 2
    expected_output = """Usage: create_prior_domain [OPTIONS]
Try 'create_prior_domain --help' for help.
"""
    assert expected_output in result.output


def test_help(file_regression):
    runner = CliRunner()
    result = runner.invoke(create_prior_domain, ["--help"])
    assert result.exit_code == 0

    file_regression.check(result.output, encoding="utf-8")


@patch("scripts.cmaq_preprocess.create_prior_domain.write_domain_info")
@patch("scripts.cmaq_preprocess.create_prior_domain.create_domain_info")
@patch("scripts.cmaq_preprocess.create_prior_domain.clean_directories")
def test_mocked_run(mock_clean, mock_create, mock_write, test_data_dir, root_dir):
    mock_clean.return_value = (
        pathlib.Path("/geom/aust-test/v1"),
        pathlib.Path("/out/aust-test/v1"),
    )
    runner = CliRunner()
    result = runner.invoke(
        create_prior_domain,
        [
            "--name",
            "aust-test",
            "--version",
            "v1",
            "--dot",
            test_data_dir / "mcip/2022-07-22/d01/GRIDDOT2D_aust-test_v1",
            "--cross",
            test_data_dir / "mcip/2022-07-22/d01/GRIDCRO2D_aust-test_v1",
        ],
    )
    assert result.exit_code == 0

    mock_clean.assert_called_once_with(
        "/opt/project/data/domains/aust-test/v1", None, "aust-test", "v1"
    )
    mock_create.assert_called_once_with(
        geometry_file=pathlib.Path("/geom/aust-test/v1") / "geo_em.d01.nc",
        cross_file=test_data_dir / "mcip/2022-07-22/d01/GRIDCRO2D_aust-test_v1",
        dot_file=test_data_dir / "mcip/2022-07-22/d01/GRIDDOT2D_aust-test_v1",
    )
    mock_write.assert_called_once_with(
        mock_create.return_value,
        pathlib.Path("/out/aust-test/v1") / "prior_domain_aust-test_v1.d01.nc",
    )


@patch("scripts.cmaq_preprocess.create_prior_domain.write_domain_info")
@patch("scripts.cmaq_preprocess.create_prior_domain.create_domain_info")
@patch("scripts.cmaq_preprocess.create_prior_domain.clean_directories", wraps=clean_directories)
def test_mocked_run_with_envs(
    mock_clean, mock_create, mock_write, test_data_dir, root_dir, monkeypatch, target_environment
):
    # Set DOMAIN_NAME, DOMAIN_VERSION, MET_DIR
    target_environment("docker-test")

    geo_dir = os.environ["GEO_DIR"]
    domain = os.environ["DOMAIN_NAME"]
    version = os.environ["DOMAIN_VERSION"]

    runner = CliRunner()
    result = runner.invoke(
        create_prior_domain,
        [],
    )
    assert result.exit_code == 0, result.output

    mock_clean.assert_called_once_with(geo_dir, None, domain, version)
    mock_create.assert_called_once_with(
        geometry_file=pathlib.Path(geo_dir) / "geo_em.d01.nc",
        cross_file=test_data_dir / "mcip/2022-07-22/d01/GRIDCRO2D_aust-test_v1",
        dot_file=test_data_dir / "mcip/2022-07-22/d01/GRIDDOT2D_aust-test_v1",
    )
    mock_write.assert_called_once_with(
        mock_create.return_value,
        pathlib.Path(geo_dir) / f"prior_domain_{domain}_{version}.d01.nc",
    )


def test_run(test_data_dir, root_dir, tmp_path, compare_dataset):
    runner = CliRunner()
    result = runner.invoke(
        create_prior_domain,
        [
            "--name",
            "aust-test",
            "--version",
            "v1",
            "--dot",
            test_data_dir / "mcip/2022-07-22/d01/GRIDDOT2D_aust-test_v1",
            "--cross",
            test_data_dir / "mcip/2022-07-22/d01/GRIDCRO2D_aust-test_v1",
            "--output-directory",
            tmp_path,
        ],
    )
    assert result.exit_code == 0, result.output

    expected_output = tmp_path / "prior_domain_aust-test_v1.d01.nc"
    assert expected_output.exists()

    compare_dataset(expected_output)


def test_bad_version(test_data_dir, root_dir, tmp_path, compare_dataset):
    runner = CliRunner()
    result = runner.invoke(
        create_prior_domain,
        [
            "--name",
            "aust-test",
            "--version",
            "1.0.0",
            "--dot",
            test_data_dir / "mcip/2022-07-22/d01/GRIDDOT2D_aust-test_v1",
            "--cross",
            test_data_dir / "mcip/2022-07-22/d01/GRIDCRO2D_aust-test_v1",
        ],
    )
    assert result.exit_code == 2
    assert "Invalid value: Version should not start with v" in result.stdout


def test_bad_grid(test_data_dir, root_dir, tmp_path, compare_dataset):
    runner = CliRunner()
    result = runner.invoke(
        create_prior_domain,
        [
            "--name",
            "aust-test",
            "--version",
            "v1",
            "--dot",
            test_data_dir / "mcip/2022-07-22/missing/GRIDDOT2D_aust-test_v1",
        ],
    )
    assert result.exit_code == 2
    assert (
        "Path '/opt/project/tests/test-data/mcip/2022-07-22/missing/GRIDDOT2D_aust-test_v1' does not exist"
        in result.stdout
    )
