import os.path
from importlib import reload

import pytest

from fourdvar.params import (
    _env,
    archive_defn,
    cmaq_config,
    data_access,
    date_defn,
    input_defn,
    root_path_defn,
    template_defn,
)

targets = pytest.mark.parametrize("target", ("nci", "docker"))

@pytest.fixture
def target_environment(monkeypatch):
    initial_env = dict(os.environ)
    def run( target: str):
        monkeypatch.setenv("HOME", "{HOME}")
        monkeypatch.setenv("TARGET", target)

        reload(_env)
        reload(root_path_defn)
        reload(input_defn)
        reload(date_defn)
        reload(archive_defn)
        reload(template_defn)
        reload(data_access)
        reload(cmaq_config)

    yield run

    os.environ.clear()
    os.environ.update(initial_env)


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
    target_environment( target)

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
    }

    cwd = os.getcwd()
    assert cmaq_config.curdir == os.getcwd()
    cmaq_config.curdir = "/path/to/curdir"

    assert all(log_file.startswith(cwd) for log_file in cmaq_config.cwd_logs)
    cmaq_config.cwd_logs = [
        log_file.replace(cwd, cmaq_config.curdir) for log_file in cmaq_config.cwd_logs
    ]

    data_regression.check(_extract_params(cmaq_config, attributes))
