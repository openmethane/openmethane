"""
Tests for the temporary debugging entrypoint.

It wraps the real entrypoint, and so every step of a run, meaning a mistake in
it breaks everything at once. These run it directly rather than through Docker:
the metrics it logs come from the cgroup it happens to be in, so the values are
whatever the test machine is doing, and only the shape of the output is
checked.
"""

import json
import pathlib
import subprocess

import pytest

ENTRYPOINT = pathlib.Path(__file__).parents[2] / "scripts" / "docker-entrypoint-debug.sh"

METRICS_PREFIX = "[om-metrics] "


def run_entrypoint(*command, env=None, timeout=60):
    return subprocess.run(
        ["/bin/bash", str(ENTRYPOINT), *command],  # noqa: S603
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "OM_METRICS_INTERVAL": "1", **(env or {})},
        timeout=timeout,
        check=False,
    )


def metrics(result) -> dict[str, dict]:
    """Metrics lines from a run, keyed by their event."""
    lines = [
        json.loads(line[len(METRICS_PREFIX) :])
        for line in result.stdout.splitlines()
        if line.startswith(METRICS_PREFIX)
    ]
    return {line["event"]: line for line in lines}


def test_runs_the_command():
    result = run_entrypoint("echo", "hello")

    assert result.returncode == 0
    assert "hello" in result.stdout


def test_reports_a_failing_command():
    result = run_entrypoint("bash", "-c", "exit 7")

    # The entrypoint reports any failure as 1, so that is what is measured here
    # rather than the command's own status.
    assert result.returncode == 1
    assert "Failed to run the command" in result.stdout
    assert metrics(result)["finish"]["exit_code"] == 1


def test_logs_metrics_for_a_successful_command():
    result = run_entrypoint("bash", "-c", "sleep 1")
    logged = metrics(result)

    assert logged["start"]["cpus_visible"] >= 1
    assert logged["finish"]["exit_code"] == 0
    assert logged["finish"]["wall_seconds"] >= 1


@pytest.mark.parametrize(
    "event, field",
    [
        ("start", "cpus_visible"),
        ("start", "cpus_physical"),
        ("start", "cpus_quota"),
        ("start", "memory_limit_bytes"),
        ("start", "chk_path_free_bytes"),
        ("finish", "exit_code"),
        ("finish", "wall_seconds"),
        ("finish", "cpu_seconds"),
        ("finish", "mean_parallelism"),
        ("finish", "cpu_throttled_seconds"),
        ("finish", "memory_anon_bytes"),
        ("finish", "memory_peak_bytes"),
        ("finish", "memory_events"),
        ("finish", "chk_path_free_bytes"),
    ],
)
def test_metrics_line_carries_every_field(event, field):
    # Values the kernel does not provide are logged as null, so that a field is
    # never simply missing.
    assert field in metrics(run_entrypoint("true"))[event]


def test_metrics_can_be_disabled():
    result = run_entrypoint("true", env={"OM_METRICS": "0"})

    assert METRICS_PREFIX not in result.stdout


def test_clears_the_scratch_directory(tmp_path):
    scratch = tmp_path / "chk"
    scratch.mkdir()
    (scratch / "checkpoint").touch()

    result = run_entrypoint("true", env={"CHK_PATH": str(scratch)})

    assert result.returncode == 0
    assert list(scratch.iterdir()) == []


def test_clears_the_scratch_directory_after_a_failure(tmp_path):
    scratch = tmp_path / "chk"
    scratch.mkdir()
    (scratch / "checkpoint").touch()

    result = run_entrypoint("false", env={"CHK_PATH": str(scratch)})

    assert result.returncode == 1
    assert list(scratch.iterdir()) == []


def test_keeps_the_scratch_directory_while_the_command_runs(tmp_path):
    """The memory sampler is a forked copy of the shell, traps included."""
    scratch = tmp_path / "chk"
    scratch.mkdir()
    (scratch / "checkpoint").touch()

    result = run_entrypoint(
        "bash",
        "-c",
        f"sleep 2; ls {scratch}",
        env={"CHK_PATH": str(scratch)},
    )

    assert "checkpoint" in result.stdout
