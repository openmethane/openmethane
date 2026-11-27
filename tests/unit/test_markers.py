"""Markers select the tests they're meant to."""

import re
import subprocess
import sys
from pathlib import Path

# The `-m` after `pytest`, so not python's own `-m pytest`
MARKER_OPTION = re.compile(r"""\s-m\s+(?:"([^"]*)"|'([^']*)'|([^\s"']+))""")
OPERATORS = {"and", "or", "not"}
WRF_TESTS = "tests/integration/wrf"
# Without the cache, so a read-only checkout can't fail the run with a warning
COLLECT_ONLY = ("--collect-only", "-q", "-p", "no:cacheprovider")


def files_running_pytest(root_dir: Path) -> list[Path]:
    return [
        root_dir / "Makefile",
        root_dir / "CLAUDE.md",
        *sorted((root_dir / ".github" / "workflows").glob("*.y*ml")),
        *sorted((root_dir / "docs").rglob("*.md")),
    ]


def marker_expressions(path: Path) -> list[str]:
    # Join shell line continuations, so an option on the next line still
    # belongs to its pytest command
    text = re.sub(r"\\\n", " ", path.read_text())
    expressions = []
    for line in text.splitlines():
        command = re.split(r"\bpytest\s", line, maxsplit=1)
        if len(command) == 2:
            expressions += ["".join(groups) for groups in MARKER_OPTION.findall(" " + command[1])]
    return expressions


def test_marker_expressions_name_registered_markers(root_dir, pytestconfig):
    """
    `--strict-markers` catches a misspelt marker on a test, but not in `-m`:
    `-m "not slw"` deselects nothing and silently runs everything.
    """
    """
    `--strict-markers` catches a misspelt marker on a test, but not in `-m`:
    `-m "not slw"` deselects nothing and silently runs everything.
    """
    registered = {
        line.split(":")[0].split("(")[0].strip() for line in pytestconfig.getini("markers")
    }
    expressions = {
        f"{path.relative_to(root_dir)}: {expression}"
        for path in files_running_pytest(root_dir)
        for expression in marker_expressions(path)
    }

    unknown = {
        where
        for where in expressions
        for name in re.findall(r"\w+", where.split(": ", 1)[1])
        if name not in OPERATORS and name not in registered
    }

    # Guards against the search above quietly matching nothing
    assert expressions
    assert not unknown, f"-m names markers that aren't registered: {sorted(unknown)}"


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
