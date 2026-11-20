import logging

import pytest

from openmethane.util.logging import configure_logging


@pytest.fixture(autouse=True)
def restore_root_logger():
    """Put back the root logger's level and handlers, which pytest relies on."""
    root = logging.getLogger()
    level, handlers = root.level, list(root.handlers)
    yield
    root.handlers[:] = handlers
    root.setLevel(level)


def test_sets_the_level_it_is_given():
    configure_logging("DEBUG")

    assert logging.getLogger().level == logging.DEBUG


def test_accepts_a_level_number_and_a_lower_case_name():
    configure_logging(logging.WARNING)
    assert logging.getLogger().level == logging.WARNING

    configure_logging("error")
    assert logging.getLogger().level == logging.ERROR


def test_reads_log_level_when_called(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "WARNING")

    configure_logging()

    assert logging.getLogger().level == logging.WARNING


def test_defaults_to_info(monkeypatch):
    monkeypatch.delenv("LOG_LEVEL", raising=False)

    configure_logging()

    assert logging.getLogger().level == logging.INFO


def test_rejects_an_unknown_level():
    with pytest.raises(ValueError, match="Unknown log level 'VERBOSE'"):
        configure_logging("VERBOSE")


def test_configuring_twice_does_not_duplicate_output():
    configure_logging("INFO")

    configure_logging("DEBUG")

    assert len(logging.getLogger().handlers) == 1
    assert logging.getLogger().level == logging.DEBUG
