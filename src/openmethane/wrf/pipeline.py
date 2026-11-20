"""Run the WRF step: prepare, fetch, wps, real, wrf, average, publish.

Work happens in the scratch folder, one working folder per run window. Output
is published to the output folder at the end:
- on success, each window's averaged output, namelists and logs, the met_em
  cache and the geo_em files, and scratch is removed;
- on failure, only logs and the met_em cache, whose files are complete by
  construction, and scratch is left in place.

A retry reuses whatever earlier work it finds: FNL analyses in the cache,
met_em files in the met_em cache or published by an earlier run, and
real.exe's output in a window's folder. They come from the same inputs, so
they can't be stale. In the openmethane image the entrypoint empties
`CHK_PATH` when the command ends, so there only the FNL cache and published
met_em files survive to a retry.
"""

import logging
import pathlib
import shutil

import f90nml
import requests

from openmethane.util.download import create_session, download
from openmethane.wrf import averaging, fnl, model, namelists, outputs, wps
from openmethane.wrf.config import WrfConfig
from openmethane.wrf.mpi import physical_cpu_count, safe_mpi_ranks
from openmethane.wrf.windows import RunWindow, run_windows

logger = logging.getLogger(__name__)

DOMAIN_URL_ROOT = "https://openmethane.s3.amazonaws.com/domains"
"""Where published domains, and their geo_em files, are"""

LOG_DIR = "logs"
"""Each window's program logs, in its working folder"""

# Files from a window's working folder that are published beside its output
PUBLISHED_FILES = ("namelist.wps", "namelist.input", "rsl.*")
PUBLISHED_FOLDERS = (LOG_DIR, model.REAL_RSL_DIR)


def windows_for(config: WrfConfig) -> list[RunWindow]:
    """The run windows covering the configured period."""
    return run_windows(
        config.start_date, config.end_date, config.num_hours_per_run, config.num_hours_spin_up
    )


def window_dir(config: WrfConfig, window: RunWindow) -> pathlib.Path:
    """A window's working folder in scratch, named for its first kept hour."""
    return config.scratch_path / window.name


def geo_em_path(config: WrfConfig, domain_id: str) -> pathlib.Path:
    """Where a domain's geo_em file is kept in scratch."""
    return config.scratch_path / f"geo_em.{domain_id}.nc"


def is_complete(config: WrfConfig) -> bool:
    """Whether every day in the period has complete output for every domain."""
    return all(
        outputs.is_complete(config.output_path, config.domains, window.first_kept.date())
        for window in windows_for(config)
    )


def run(config: WrfConfig, session: requests.Session | None = None) -> bool:
    """
    Run every stage for the configured period, and publish the output.

    Parameters
    ----------
    config
        The run's configuration.
    session
        HTTP session for downloads. Defaults to one from `create_session`.

    Returns
    -------
    False if the output was already complete and nothing was run, else True.
    """
    if not config.force and is_complete(config):
        logger.info(f"output in {config.output_path} is already complete, nothing to do")
        return False

    session = session or create_session()
    windows = prepare(config, session)
    try:
        fetch(config, windows)
        for window in windows:
            run_wps(config, window)
            run_real(config, window)
            run_wrf(config, window)
            average(config, window)
    except BaseException:
        logger.exception("the WRF step failed, publishing logs only")
        publish(config, windows, succeeded=False)
        raise
    publish(config, windows, succeeded=True)
    return True


def prepare(config: WrfConfig, session: requests.Session) -> list[RunWindow]:
    """
    Check the install, fetch geo_em files, and set up each window's working folder.

    Copies the met_em files and geo_em files of an earlier run from the output
    folder, so they are reused rather than remade.
    """
    config.install.validate()
    config.scratch_path.mkdir(parents=True, exist_ok=True)
    _restore_from_output(config)

    for domain in config.domains:
        path = geo_em_path(config, domain.id)
        if not path.exists():
            download(
                f"{DOMAIN_URL_ROOT}/{domain.name}/{domain.version}/geo_em.d01.nc",
                path,
                session=session,
            )

    windows = windows_for(config)
    for window in windows:
        folder = window_dir(config, window)
        (folder / LOG_DIR).mkdir(parents=True, exist_ok=True)
        namelists.build_wps_namelist(config.domains, window).write(
            folder / "namelist.wps", force=True
        )
        for domain in config.domains:
            wps.link_into(folder, geo_em_path(config, domain.id))
        (folder / namelists.IOFIELDS_FILE).write_bytes(
            namelists.model_config_file(namelists.IOFIELDS_FILE).read_bytes()
        )
        model.link_run_files(folder, config.install)
    return windows


def needs_wps(config: WrfConfig, window: RunWindow) -> bool:
    """Whether a window still needs met_em files made: real.exe hasn't run, and some are missing."""
    if all(
        path.exists() for path in model.real_outputs(window_dir(config, window), config.domains)
    ):
        return False
    return bool(
        wps.missing_met_em(config.met_em_cache_path, config.domains, window.analysis_times())
    )


def fetch(config: WrfConfig, windows: list[RunWindow]) -> None:
    """Download the analyses for every window that still needs WPS run."""
    times = [
        time for window in windows if needs_wps(config, window) for time in window.analysis_times()
    ]
    if not times:
        logger.info("no window needs analyses")
        return
    fnl.fetch_analyses(times, config.fnl_cache_path, config.fnl_dataset_root)


def run_wps(config: WrfConfig, window: RunWindow) -> None:
    """Make a window's met_em files, unless they are cached or real.exe has already run."""
    if not needs_wps(config, window):
        logger.info(f"{window.name}: met_em files are ready, skipping WPS")
        return
    folder = window_dir(config, window)
    analyses = [config.fnl_cache_path / fnl.fnl_file_name(time) for time in window.analysis_times()]
    wps.run_wps(folder, analyses, config.install, config.met_em_cache_path, folder / LOG_DIR)


def run_real(config: WrfConfig, window: RunWindow) -> None:
    """Write namelist.input and run real.exe, unless its output is already there."""
    folder = window_dir(config, window)
    if all(path.exists() for path in model.real_outputs(folder, config.domains)):
        logger.info(f"{window.name}: real.exe's output is already there, skipping real.exe")
        if not (folder / "namelist.input").exists():
            raise FileNotFoundError(f"{folder}/namelist.input is missing, so wrf.exe can't run")
        return

    needed = wps.needed_met_em(config.domains, window.analysis_times())
    for name in needed:
        wps.link_into(folder, config.met_em_cache_path / name)
    levels, soil_levels = model.metgrid_levels(config.met_em_cache_path / needed[0])
    namelists.build_wrf_namelist(
        config.domains,
        window,
        num_metgrid_levels=levels,
        num_metgrid_soil_levels=soil_levels,
    ).write(folder / "namelist.input", force=True)

    try:
        model.run_real(folder, config.install, folder / LOG_DIR)
    except BaseException:
        # real.exe may have written some of its output before failing, which a
        # retry would otherwise take as finished
        for path in model.real_outputs(folder, config.domains):
            path.unlink(missing_ok=True)
        raise
    for name in needed:
        (folder / name).unlink()


def mpi_ranks(config: WrfConfig) -> int:
    """The ranks to run wrf.exe on: as configured, or worked out from the grids and cores."""
    if config.mpi_ranks is not None:
        return config.mpi_ranks
    return safe_mpi_ranks(config.domains.grid_cells(), physical_cpu_count())


def run_wrf(config: WrfConfig, window: RunWindow) -> None:
    """Run wrf.exe for a window."""
    folder = window_dir(config, window)
    model.run_wrf(folder, config.install, mpi_ranks(config), folder / LOG_DIR)


def average(config: WrfConfig, window: RunWindow) -> None:
    """Average a window's raw output, with the frame count from its namelist."""
    folder = window_dir(config, window)
    frames = f90nml.read(folder / "namelist.input")["time_control"]["frames_per_outfile"]
    # One value per domain; they must agree, since one count is checked
    frame_counts = set(frames) if isinstance(frames, list) else {frames}
    if len(frame_counts) != 1:
        raise averaging.AveragingError(f"frames_per_outfile differs between domains: {frames}")
    averaging.average_window(folder, frame_counts.pop(), window.first_kept, window.end)


def publish(config: WrfConfig, windows: list[RunWindow], succeeded: bool) -> None:
    """
    Copy output from scratch to the output folder.

    After a failure only logs and the met_em cache are copied, and scratch is
    kept. After success everything is copied, and scratch is removed.
    """
    config.output_path.mkdir(parents=True, exist_ok=True)
    # Only this run's met_em files, in case the cache is shared with other runs
    needed = {
        name
        for window in windows
        for name in wps.needed_met_em(config.domains, window.analysis_times())
    }
    _copy_files(
        (config.met_em_cache_path / name for name in sorted(needed)), config.output_path / "metem"
    )

    for window in windows:
        folder = window_dir(config, window)
        if not folder.is_dir():
            continue
        destination = outputs.day_folder(config.output_path, window.first_kept.date())
        for name in PUBLISHED_FOLDERS:
            if (folder / name).is_dir():
                shutil.copytree(folder / name, destination / name, dirs_exist_ok=True)
        _copy_files(
            (path for pattern in PUBLISHED_FILES for path in folder.glob(pattern)), destination
        )
        if succeeded:
            _copy_files(folder.glob("WRFOUT_*.nc"), destination)
            # Raw output from an earlier failed run would leave the day incomplete
            for stale in destination.glob("wrfout_*"):
                stale.unlink()

    if not succeeded:
        logger.info(f"kept {config.scratch_path} for a retry")
        return

    _copy_files((geo_em_path(config, domain.id) for domain in config.domains), config.output_path)
    shutil.rmtree(config.scratch_path)
    logger.info(f"published to {config.output_path} and removed {config.scratch_path}")


def _restore_from_output(config: WrfConfig) -> None:
    """Copy published met_em and geo_em files back into scratch, if they aren't there."""
    published_met_em = config.output_path / "metem"
    if published_met_em.is_dir():
        _copy_files(published_met_em.glob("met_em.*.nc"), config.met_em_cache_path, replace=False)
    _copy_files(
        (config.output_path / geo_em_path(config, domain.id).name for domain in config.domains),
        config.scratch_path,
        replace=False,
    )


def _copy_files(paths, destination: pathlib.Path, replace: bool = True) -> None:
    """Copy each existing file into a folder, following links."""
    destination.mkdir(parents=True, exist_ok=True)
    for path in paths:
        target = destination / path.name
        if not path.is_file() or (target.exists() and not replace):
            continue
        if path.resolve() != target.resolve():
            shutil.copy2(path, target)
