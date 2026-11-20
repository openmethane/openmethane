import logging

import pytest

from openmethane.wrf import cli, pipeline


@pytest.fixture(autouse=True)
def restore_root_logger():
    """Put back the root logger, which the command configures."""
    root = logging.getLogger()
    level, handlers = root.level, list(root.handlers)
    yield
    root.handlers[:] = handlers
    root.setLevel(level)


@pytest.fixture
def production_env(monkeypatch, tmp_path):
    for name, value in {
        "START_DATE": "2022-12-07",
        "DOMAIN_NAME": "au-test",
        "DOMAIN_VERSION": "v1",
        "STORE_PATH": str(tmp_path / "store"),
        "CHK_PATH": str(tmp_path / "chk"),
    }.items():
        monkeypatch.setenv(name, value)


def test_an_invalid_configuration_exits_2(monkeypatch, capsys):
    monkeypatch.delenv("START_DATE", raising=False)
    monkeypatch.setenv("DOMAIN_NAME", "au-test")
    monkeypatch.setenv("DOMAIN_VERSION", "v1")

    code = cli.main(["run"])

    assert code == 2
    # The command configures logging to stderr itself
    assert "START_DATE is required" in capsys.readouterr().err


def test_a_failed_run_exits_1(production_env, monkeypatch):
    def fail(config):
        raise RuntimeError("a stage failed")

    monkeypatch.setattr(pipeline, "run", fail)

    code = cli.main(["run"])

    assert code == 1


def test_run_passes_force_through(production_env, monkeypatch):
    seen = []
    monkeypatch.setattr(pipeline, "run", lambda config: seen.append(config.force))

    code = cli.main(["run", "--force"])

    assert code == 0
    assert seen == [True]


def test_an_unknown_subcommand_is_a_usage_error():
    with pytest.raises(SystemExit) as raised:
        cli.main(["sprint"])

    assert raised.value.code != 0
