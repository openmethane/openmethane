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


# Each test starts the root logger at CRITICAL, a level none of them expects
# to end at, so a test passes only if configure_logging changed the level.


def test_sets_the_level_it_is_given():
    root = logging.getLogger()
    root.setLevel(logging.CRITICAL)

    configure_logging("DEBUG")

    assert root.level == logging.DEBUG


def test_accepts_a_level_number():
    root = logging.getLogger()
    root.setLevel(logging.CRITICAL)

    configure_logging(logging.WARNING)

    assert root.level == logging.WARNING


def test_accepts_a_lower_case_name():
    root = logging.getLogger()
    root.setLevel(logging.CRITICAL)

    configure_logging("error")

    assert root.level == logging.ERROR


def test_reads_log_level_when_called(monkeypatch):
    root = logging.getLogger()
    root.setLevel(logging.CRITICAL)
    monkeypatch.setenv("LOG_LEVEL", "ERROR")

    configure_logging()

    assert root.level == logging.ERROR


def test_defaults_to_info(monkeypatch):
    root = logging.getLogger()
    root.setLevel(logging.CRITICAL)
    monkeypatch.delenv("LOG_LEVEL", raising=False)

    configure_logging()

    assert root.level == logging.INFO


def test_rejects_an_unknown_level():
    root = logging.getLogger()
    root.setLevel(logging.CRITICAL)

    with pytest.raises(ValueError, match="Unknown log level 'VERBOSE'"):
        configure_logging("VERBOSE")

    assert root.level == logging.CRITICAL


def test_replaces_the_handlers_already_on_the_root_logger():
    root = logging.getLogger()
    existing = [logging.NullHandler(), logging.NullHandler()]
    root.handlers[:] = existing

    configure_logging("INFO")

    assert len(root.handlers) == 1
    assert root.handlers[0] not in existing


def test_configuring_twice_does_not_duplicate_output():
    root = logging.getLogger()
    root.handlers.clear()

    configure_logging("INFO")
    configure_logging("DEBUG")

    assert len(root.handlers) == 1
    assert root.level == logging.DEBUG
