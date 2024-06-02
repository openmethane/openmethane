import os.path
from importlib import reload

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

setups = pytest.mark.parametrize("setup", ("nci",))


@pytest.fixture()
def static_environment(monkeypatch):
    monkeypatch.setenv("HOME", "{HOME}")

    reload(root_path_defn)
    reload(input_defn)
    reload(date_defn)
    reload(archive_defn)
    reload(template_defn)
    reload(data_access)
    reload(cmaq_config)


def _extract_params(module, attributes):
    return {param: getattr(module, param) for param in attributes}


@setups
def test_root_data_defn(data_regression, static_environment, setup):
    data_regression.check(_extract_params(root_path_defn, ["root_path", "store_path"]))


@setups
def test_input_defn(data_regression, static_environment, setup):
    data_regression.check(_extract_params(input_defn, ["prior_file", "obs_file", "inc_icon"]))


@setups
def test_date_defn(data_regression, static_environment, setup):
    data_regression.check(_extract_params(date_defn, ["start_date", "end_date"]))


@setups
def test_archive_defn(data_regression, static_environment, setup):
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


@setups
def test_template_defn(data_regression, static_environment, setup):
    data_regression.check(
        _extract_params(
            template_defn,
            [
                "template_path",
                "conc",
                "force",
                "sense_emis",
                "sense_conc",
                "emis",
                "icon",
                "diurnal",
            ],
        )
    )


@setups
def test_data_access(data_regression, static_environment, setup):
    data_regression.check(
        _extract_params(
            data_access,
            [
                "allow_fwd_skip",
                "prev_vector",
            ],
        )
    )


@setups
def test_cmaq_config(data_regression, static_environment, setup):
    # Extract attributes from module
    # There are alot of attributes in cmaq_config,
    # so manually specifying the attributes is prone to error/flux
    attributes = set([item for item in dir(cmaq_config) if not item.startswith("_")]) - {
        "os",
        "store_path",
    }

    cwd = os.getcwd()
    assert cmaq_config.curdir == os.getcwd()
    cmaq_config.curdir = "/path/to/curdir"

    assert all(log_file.startswith(cwd) for log_file in cmaq_config.cwd_logs)
    cmaq_config.cwd_logs = [
        log_file.replace(cwd, cmaq_config.curdir) for log_file in cmaq_config.cwd_logs
    ]

    data_regression.check(_extract_params(cmaq_config, attributes))
