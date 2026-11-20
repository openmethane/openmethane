"""The `wrf` command.

`wrf run` runs the whole WRF step, as production does. The other subcommands
run one stage over every window, for development: each prepares the working
folders first, and finds earlier stages' output where they left it.

Configuration comes from the environment (see `WrfConfig.from_env`). The exit
code is 0 on success, 1 if a stage fails and 2 if the configuration is invalid.
"""

import logging
import os
import sys

import attrs
import cyclopts

from openmethane.util.download import create_session
from openmethane.util.logging import configure_logging
from openmethane.wrf import pipeline
from openmethane.wrf.config import WrfConfig, WrfConfigError

logger = logging.getLogger(__name__)

app = cyclopts.App(name="wrf", help="Run the WRF weather model for Open Methane.")

EXIT_FAILED = 1
EXIT_BAD_CONFIG = 2


class _BadConfig(Exception):
    pass


def _load_config(force: bool = False) -> WrfConfig:
    configure_logging()
    try:
        config = WrfConfig.from_env(os.environ)
    except WrfConfigError as error:
        # The problems are the whole message; a traceback would only hide them
        logger.error(str(error))  # noqa: TRY400
        raise _BadConfig from error
    if force:
        config = attrs.evolve(config, force=True)
    logger.info(f"configuration: {config}")
    return config


@app.command
def run(*, force: bool = False) -> None:
    """
    Run every stage and publish the output.

    Exits early if every day's output is already complete.

    Parameters
    ----------
    force
        Run even if the output is complete. The same as FORCE_WRF=true.
    """
    pipeline.run(_load_config(force))


def _stage(stage) -> None:
    config = _load_config()
    windows = pipeline.prepare(config, create_session())
    if stage is pipeline.fetch:
        pipeline.fetch(config, windows)
        return
    for window in windows:
        stage(config, window)


@app.command
def prepare() -> None:
    """Set up each window's working folder: namelist.wps, geo_em and WRF's tables."""
    config = _load_config()
    pipeline.prepare(config, create_session())


@app.command
def fetch() -> None:
    """Download the FNL analyses the windows need."""
    _stage(pipeline.fetch)


@app.command
def wps() -> None:
    """Run ungrib and metgrid for each window that needs met_em files."""
    _stage(pipeline.run_wps)


@app.command
def real() -> None:
    """Run real.exe for each window."""
    _stage(pipeline.run_real)


@app.command(name="wrf")
def wrf_exe() -> None:
    """Run wrf.exe for each window."""
    _stage(pipeline.run_wrf)


@app.command
def average() -> None:
    """Average each window's raw output."""
    _stage(pipeline.average)


def main(argv: list[str] | None = None) -> int:
    """Entry point for the `wrf` console script. Returns the exit code."""
    try:
        app(argv if argv is not None else sys.argv[1:], exit_on_error=True)
    except _BadConfig:
        return EXIT_BAD_CONFIG
    except Exception:
        logger.exception("the WRF step failed")
        return EXIT_FAILED
    return 0


if __name__ == "__main__":
    sys.exit(main())
