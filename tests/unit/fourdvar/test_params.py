import datetime
import os.path

import pytest

from fourdvar.params import (
    archive_defn,
    cmaq_config,
    data_access,
    date_defn,
    input_defn,
    root_path_defn,
    template_defn,
)

targets = pytest.mark.parametrize("target", ("nci", "docker"))


def _extract_params(module, attributes):
    return {param: getattr(module, param) for param in attributes}


@targets
def test_root_data_defn(data_regression, target_environment, target):
    target_environment(target)

    data_regression.check(_extract_params(root_path_defn, ["store_path"]))


@targets
def test_input_defn(data_regression, target_environment, target):
    target_environment(target)

    data_regression.check(_extract_params(input_defn, ["prior_file", "obs_file", "inc_icon"]))


@targets
def test_date_defn(data_regression, target_environment, target):
    target_environment(target)

    data_regression.check(_extract_params(date_defn, ["start_date", "end_date"]))


@targets
def test_archive_defn(data_regression, target_environment, target):
    target_environment(target)

    data_regression.check(
        _extract_params(
            archive_defn,
            [
                "archive_path",
                "iter_model_output",
                "iter_obs_lite",
                "experiment",
                "description",
                "desc_name",
                "overwrite",
                "extension",
                "icon_file",
                "emis_file",
                "conc_file",
                "force_file",
                "sens_conc_file",
                "sens_emis_file",
            ],
        )
    )


@targets
def test_template_defn(data_regression, target_environment, target):
    target_environment(target)

    data_regression.check(
        _extract_params(
            template_defn,
            [
                "template_dir",
                "conc",
                "force",
                "sense_emis",
                "sense_conc",
                "emis",
                "icon",
            ],
        )
    )


@targets
def test_data_access(data_regression, target_environment, target):
    target_environment(target)

    data_regression.check(
        _extract_params(
            data_access,
            [
                "allow_fwd_skip",
                "prev_vector",
            ],
        )
    )


def test_overrides(target_environment):
    target = "nci"

    target_environment(target)

    assert date_defn.end_date == datetime.date(2022, 7, 22)

    os.environ.clear()
    os.environ["END_DATE"] = (
        "2024-01-01"  # This value will take precedence over the value in .env.nci
    )

    # Reload the params, but don't clear the environment first which would negate the line above
    target_environment(target, clear=False)

    assert date_defn.end_date == datetime.date(2024, 1, 1)


@targets
def test_cmaq_config(data_regression, target_environment, target):
    target_environment(target)

    # Extract attributes from module
    # There are alot of attributes in cmaq_config,
    # so manually specifying the attributes is prone to error/flux
    attributes = set([item for item in dir(cmaq_config) if not item.startswith("_")]) - {
        "env",
        "os",
        "store_path",
        "logger",
        "get_logger",
    }

    cwd = os.getcwd()
    assert cmaq_config.curdir == os.getcwd()
    cmaq_config.curdir = "/path/to/curdir"

    assert all(log_file.startswith(cwd) for log_file in cmaq_config.cwd_logs)
    cmaq_config.cwd_logs = [
        log_file.replace(cwd, cmaq_config.curdir) for log_file in cmaq_config.cwd_logs
    ]

    data_regression.check(_extract_params(cmaq_config, attributes))
