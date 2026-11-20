"""Run external programs, with their output in a log file.

Failure is decided by the exit code, and optionally by a line the program
prints when it finishes successfully. Output on stderr is never treated as
failure, because the models write warnings and progress there.
"""

import collections
import logging
import os
import pathlib
import subprocess
from collections.abc import Mapping, Sequence

logger = logging.getLogger(__name__)

TAIL_LINES = 20
"""Number of lines from the end of the log quoted in a `ProgramFailed`"""


class ProgramFailed(RuntimeError):
    """An external program exited with an error, or without its success line."""

    def __init__(  # noqa: PLR0913
        self,
        program: str,
        exit_code: int,
        log_path: pathlib.Path,
        tail: list[str],
        missing_success_text: str | None = None,
    ):
        self.program = program
        """Name of the program, without its path"""
        self.exit_code = exit_code
        """The program's exit code, negative if it was killed by a signal"""
        self.log_path = log_path
        """File holding the program's stdout and stderr"""
        self.tail = tail
        """The last lines of the log"""
        self.missing_success_text = missing_success_text
        """The success line that was expected but not found, if that is the failure"""

        if missing_success_text is None:
            reason = f"exited with code {exit_code}"
        else:
            reason = f"exited with code {exit_code} but did not print {missing_success_text!r}"
        tail_text = "".join(tail) or "(empty)\n"
        super().__init__(f"{program} {reason}. Full output in {log_path}. Last lines:\n{tail_text}")


def run_program(
    args: Sequence[str | os.PathLike],
    *,
    cwd: str | os.PathLike,
    log_path: str | os.PathLike,
    env: Mapping[str, str] | None = None,
    success_text: str | None = None,
) -> None:
    """
    Run a program to completion, writing its output to a log file.

    stdout and stderr go to the same file, interleaved as the program writes
    them, so the log is complete even if the job is killed mid-run.

    Parameters
    ----------
    args
        The program and its arguments, one item each. Never a single string
        split on spaces, which breaks paths and arguments containing them.
    cwd
        Directory to run the program in.
    log_path
        File to write the program's output to, replacing any existing file.
        Its directory is created if needed.
    env
        Variables to set for the program, on top of the current environment.
    success_text
        Text the program prints only when it succeeds, such as WRF's
        "SUCCESS COMPLETE WRF". If given, a run whose output lacks it fails
        even with exit code 0, since some programs exit 0 after an error.

    Raises
    ------
    ProgramFailed
        If the exit code is not 0, or `success_text` is not in the output.
    FileNotFoundError
        If the program does not exist.
    """
    args = [os.fspath(arg) for arg in args]
    program = pathlib.Path(args[0]).name
    log_path = pathlib.Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"running {program} in {cwd}, logging to {log_path}")
    with log_path.open("wb") as log_file:
        result = subprocess.run(
            # Running the caller's program is the point of this function.
            args,  # noqa: S603
            cwd=cwd,
            env={**os.environ, **env} if env is not None else None,
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            check=False,
        )

    if result.returncode != 0:
        raise ProgramFailed(program, result.returncode, log_path, _tail(log_path))

    if success_text is not None and not _contains(log_path, success_text):
        raise ProgramFailed(program, result.returncode, log_path, _tail(log_path), success_text)

    logger.info(f"{program} finished")


def _tail(path: pathlib.Path, lines: int = TAIL_LINES) -> list[str]:
    """Read the last lines of a file without holding the whole file in memory."""
    with path.open(errors="replace") as file:
        return list(collections.deque(file, maxlen=lines))


def _contains(path: pathlib.Path, text: str) -> bool:
    """Whether a line of the file contains the text."""
    with path.open(errors="replace") as file:
        return any(text in line for line in file)
