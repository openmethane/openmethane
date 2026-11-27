"""Markers select the tests they're meant to."""

import subprocess
import sys

WRF_TESTS = "tests/integration/wrf"
# Without the cache, so a read-only checkout can't fail the run with a warning
COLLECT_ONLY = ("--collect-only", "-q", "-p", "no:cacheprovider")


def test_fixture_markers_reach_the_tests_using_them(root_dir):
    """
    FIXTURE_MARKERS names fixtures defined elsewhere, so renaming one would
    quietly drop its markers: `-m "not network"` would then download FNL.
    """
    collected = subprocess.run(
        [sys.executable, "-m", "pytest", *COLLECT_ONLY, "-m", "network", WRF_TESTS],  # noqa: S603
        cwd=root_dir,
        capture_output=True,
        text=True,
        check=False,
    )

    assert collected.returncode == 0, collected.stdout + collected.stderr
    assert "test_wrf_run.py::test_publishes_a_complete_day_in_the_layout_mcip_reads" in (
        collected.stdout
    )
