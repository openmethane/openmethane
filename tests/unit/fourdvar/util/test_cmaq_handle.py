import pytest

from openmethane.fourdvar.params import cmaq_config
from openmethane.fourdvar.util import cmaq_handle


def test_checkpointing_disabled_restores_the_previous_setting(monkeypatch):
    monkeypatch.setattr(cmaq_config, "create_chk", True)

    with cmaq_handle.checkpointing_disabled():
        assert cmaq_config.create_chk is False

    assert cmaq_config.create_chk is True


def test_checkpointing_disabled_restores_after_a_failed_run(monkeypatch):
    """A failed forward run must not leave checkpointing off for the inversion."""
    monkeypatch.setattr(cmaq_config, "create_chk", True)

    with pytest.raises(ValueError, match="ADJOINT_FWD failed"):
        with cmaq_handle.checkpointing_disabled():
            assert cmaq_config.create_chk is False

            raise ValueError("ADJOINT_FWD failed")

    assert cmaq_config.create_chk is True


def test_checkpoints_are_written_by_default(target_environment):
    """ADJOINT_BWD replays these, so the inversion cannot run without them."""
    target_environment("docker")

    assert cmaq_config.create_chk is True
