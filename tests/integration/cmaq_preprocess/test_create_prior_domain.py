import pathlib
from unittest.mock import patch

from click.testing import CliRunner
from scripts.cmaq_preprocess.create_prior_domain import main as create_prior_domain


def test_empty():
    runner = CliRunner()
    result = runner.invoke(create_prior_domain, [])
    assert result.exit_code == 2
    expected_output = """Usage: create_prior_domain [OPTIONS]
Try 'create_prior_domain --help' for help.

Error: Missing option '--name'.
"""
    assert result.output == expected_output


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
        pathlib.Path("/geom/aust-test/v1.0.0"),
        pathlib.Path("/out/aust-test/v1.0.0"),
    )
    runner = CliRunner()
    result = runner.invoke(
        create_prior_domain,
        [
            "--name",
            "aust-test",
            "--version",
            "v1.0.0",
            "--dot",
            test_data_dir / "mcip/2022-07-22/d01/GRIDDOT2D_aust-test_v1",
            "--cross",
            test_data_dir / "mcip/2022-07-22/d01/GRIDCRO2D_aust-test_v1",
        ],
    )
    assert result.exit_code == 0

    mock_clean.assert_called_once_with(None, None, "aust-test", "v1.0.0")
    mock_create.assert_called_once_with(
        geometry_file=pathlib.Path("/geom/aust-test/v1.0.0") / "geo_em.d01.nc",
        cross_file=test_data_dir / "mcip/2022-07-22/d01/GRIDCRO2D_aust-test_v1",
        dot_file=test_data_dir / "mcip/2022-07-22/d01/GRIDDOT2D_aust-test_v1",
    )
    mock_write.assert_called_once_with(
        mock_create.return_value,
        pathlib.Path("/out/aust-test/v1.0.0") / "prior_domain_aust-test_v1.0.0.d01.nc",
    )


def test_run(test_data_dir, root_dir, tmp_path, compare_dataset):
    runner = CliRunner()
    result = runner.invoke(
        create_prior_domain,
        [
            "--name",
            "aust-test",
            "--version",
            "v1.0.0",
            "--dot",
            test_data_dir / "mcip/2022-07-22/d01/GRIDDOT2D_aust-test_v1",
            "--cross",
            test_data_dir / "mcip/2022-07-22/d01/GRIDCRO2D_aust-test_v1",
            "--output-directory",
            tmp_path,
        ],
    )
    assert result.exit_code == 0

    expected_output = tmp_path / "prior_domain_aust-test_v1.0.0.d01.nc"
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
