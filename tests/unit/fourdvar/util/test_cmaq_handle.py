import pytest

from openmethane.fourdvar.params import cmaq_config
from openmethane.fourdvar.util import cmaq_handle
from openmethane.fourdvar.util.decomposition import Decomposition, resolve_decomposition


@pytest.fixture
def decomposition(monkeypatch):
    """Run CMAQ with a given decomposition, without resolving one."""

    def use(npcol: int, nprow: int) -> None:
        monkeypatch.setattr(
            "openmethane.fourdvar.util.cmaq_handle.resolve_decomposition",
            lambda: Decomposition(npcol, nprow),
        )

    resolve_decomposition.cache_clear()
    yield use
    resolve_decomposition.cache_clear()


def test_a_single_rank_runs_the_binary_directly(decomposition):
    decomposition(1, 1)

    cmd = cmaq_handle.build_cmd("ADJOINT_FWD", "logs/fwd_stdout.log")

    assert "mpirun" not in cmd
    assert cmd.endswith("ADJOINT_FWD")


def test_more_than_one_rank_runs_under_mpirun(decomposition):
    decomposition(6, 4)

    cmd = cmaq_handle.build_cmd("ADJOINT_FWD", "logs/fwd_stdout.log")

    # One rank per subdomain, so -np is the product of the decomposition.
    assert "mpirun -np 24 " in cmd
    assert "-errfile-pattern=logs/fwd_stdout.log.%r-%h.stderr" in cmd
    assert cmd.endswith("ADJOINT_FWD")


@pytest.mark.parametrize("npcol, nprow", ((1, 4), (4, 1)))
def test_a_decomposition_in_one_direction_still_uses_mpirun(decomposition, npcol, nprow):
    decomposition(npcol, nprow)

    cmd = cmaq_handle.build_cmd("ADJOINT_FWD", "logs/fwd_stdout.log")

    assert "mpirun -np 4 " in cmd


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
