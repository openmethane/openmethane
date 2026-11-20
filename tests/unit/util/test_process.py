import pathlib
import sys

import pytest

from openmethane.util.process import TAIL_LINES, ProgramFailed, run_program


def python(code: str) -> list[str]:
    """Arguments that run a snippet of Python as an external program."""
    return [sys.executable, "-c", code]


def test_a_program_that_exits_0_succeeds_and_logs_its_output(tmp_path):
    log_path = tmp_path / "logs" / "program.log"

    run_program(python("print('hello')"), cwd=tmp_path, log_path=log_path)

    assert log_path.read_text() == "hello\n"


def test_a_program_that_exits_non_zero_fails_with_the_end_of_its_log(tmp_path):
    log_path = tmp_path / "program.log"
    code = "import sys\nfor i in range(100): print(f'line {i}')\nsys.exit(3)"

    with pytest.raises(ProgramFailed) as raised:
        run_program(python(code), cwd=tmp_path, log_path=log_path)

    assert raised.value.exit_code == 3
    assert raised.value.program == pathlib.Path(sys.executable).name
    assert raised.value.log_path == log_path
    assert raised.value.tail == [f"line {i}\n" for i in range(100 - TAIL_LINES, 100)]
    assert "exited with code 3" in str(raised.value)
    assert "line 99" in str(raised.value)
    assert str(log_path) in str(raised.value)


def test_output_on_stderr_is_not_a_failure(tmp_path):
    log_path = tmp_path / "program.log"
    code = "import sys\nprint('to stdout', flush=True)\nprint('to stderr', file=sys.stderr)"

    run_program(python(code), cwd=tmp_path, log_path=log_path)

    assert log_path.read_text() == "to stdout\nto stderr\n"


def test_a_program_that_exits_0_without_its_success_line_fails(tmp_path):
    log_path = tmp_path / "program.log"

    with pytest.raises(ProgramFailed) as raised:
        run_program(
            python("print('ERROR: something went wrong')"),
            cwd=tmp_path,
            log_path=log_path,
            success_text="SUCCESS COMPLETE",
        )

    assert raised.value.exit_code == 0
    assert raised.value.missing_success_text == "SUCCESS COMPLETE"
    assert "did not print 'SUCCESS COMPLETE'" in str(raised.value)
    assert "ERROR: something went wrong" in str(raised.value)


def test_a_program_that_prints_its_success_line_succeeds(tmp_path):
    log_path = tmp_path / "program.log"

    run_program(
        python("print('d01 SUCCESS COMPLETE WRF')"),
        cwd=tmp_path,
        log_path=log_path,
        success_text="SUCCESS COMPLETE WRF",
    )

    assert "SUCCESS COMPLETE WRF" in log_path.read_text()


def test_the_program_runs_in_the_given_directory(tmp_path):
    workdir = tmp_path / "work"
    workdir.mkdir()
    log_path = tmp_path / "program.log"

    run_program(python("import os; print(os.getcwd())"), cwd=workdir, log_path=log_path)

    assert log_path.read_text().strip() == str(workdir)


def test_env_is_added_to_the_current_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("FROM_PARENT", "inherited")
    log_path = tmp_path / "program.log"
    code = "import os; print(os.environ['FROM_PARENT'], os.environ['FROM_CALLER'])"

    run_program(python(code), cwd=tmp_path, log_path=log_path, env={"FROM_CALLER": "added"})

    assert log_path.read_text() == "inherited added\n"


def test_arguments_with_spaces_are_passed_whole(tmp_path):
    log_path = tmp_path / "program.log"
    args = [*python("import sys; print(sys.argv[1:])"), "a path/with spaces", tmp_path / "b c"]

    run_program(args, cwd=tmp_path, log_path=log_path)

    assert log_path.read_text() == f"{['a path/with spaces', str(tmp_path / 'b c')]}\n"


def test_a_missing_program_is_reported_as_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        run_program(
            [tmp_path / "no-such-program.exe"], cwd=tmp_path, log_path=tmp_path / "program.log"
        )
