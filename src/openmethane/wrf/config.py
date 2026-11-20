"""Configuration of the WRF step.

`WrfConfig` holds every setting in its final form. It is built by a
constructor for each source of configuration, so the rest of the WRF code
never knows which was used:
- `from_env`: the environment the production WRF job sets today.
- `from_dict`: the run configuration's `wrf` section, once #299 defines it
  (#326).
"""

import datetime
import pathlib
from collections.abc import Mapping

import attrs
import attrs.validators

from openmethane.wrf.geometry import DomainSet, GeometryError
from openmethane.wrf.install import WrfInstall

DEFAULT_STORE_PATH = "/app/data"
DEFAULT_CHK_PATH = "/mnt/scratch"
DEFAULT_FNL_CACHE_PATH = "/app/data/fnl"


class WrfConfigError(ValueError):
    """The WRF step's configuration has problems. Lists every one found."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        """Each problem, in words"""
        listed = "\n".join(f"  - {problem}" for problem in problems)
        super().__init__(f"Invalid WRF configuration:\n{listed}")


def _optional_positive(instance, attribute, value):
    if value is not None and value < 1:
        raise ValueError(f"{attribute.name} must be positive, got {value}")


@attrs.frozen
class WrfConfig:
    """Everything the WRF step needs to know about a run."""

    start_date: datetime.date
    """First day to produce output for"""
    end_date: datetime.date
    """Last day to produce output for, inclusive"""
    domain_version: str
    """Version of the published domains, for fetching their geo_em files"""
    domains: DomainSet
    """The domains that run together, numbered for WRF"""
    output_path: pathlib.Path
    """Where finished output is published, one folder per day"""
    scratch_path: pathlib.Path
    """Fast working space for the run, removed once output is published"""
    met_em_cache_path: pathlib.Path
    """Where met_em files are kept between windows and reused if present"""
    fnl_cache_path: pathlib.Path
    """Where downloaded FNL analyses are kept, shared between runs"""
    num_hours_spin_up: int = attrs.field(default=12, validator=attrs.validators.ge(0))
    """Hours each window runs before its first kept hour"""
    num_hours_per_run: int = attrs.field(default=24, validator=attrs.validators.gt(0))
    """Hours of output kept from each window"""
    mpi_ranks: int | None = attrs.field(default=None, validator=_optional_positive)
    """Ranks to run wrf.exe on. None works them out from the grid and the cores"""
    force: bool = False
    """Run even if the output is already complete"""
    install: WrfInstall = attrs.field(factory=WrfInstall)
    """Where the WRF and WPS programs are"""

    def __attrs_post_init__(self):
        if self.end_date < self.start_date:
            raise ValueError(f"end_date {self.end_date} is before start_date {self.start_date}")

    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> "WrfConfig":
        """
        Build the configuration from the variables the production WRF job sets.

        | Variable | Meaning | Default |
        | --- | --- | --- |
        | `START_DATE` | The day to run, YYYY-MM-DD. One day is run | required |
        | `DOMAIN_NAME` | The domain to run | required |
        | `DOMAIN_VERSION` | Its published version | required |
        | `STORE_PATH` | Output goes in `${STORE_PATH}/wrf/${DOMAIN_NAME}` | `/app/data` |
        | `CHK_PATH` | Scratch is `${CHK_PATH}/wrf/${DOMAIN_NAME}` | `/mnt/scratch` |
        | `FORCE_WRF` | `true` to rerun a day whose output is complete | `false` |
        | `NCPUS` | MPI ranks for wrf.exe | worked out |
        | `FNL_CACHE_PATH` | Where FNL analyses are kept | `/app/data/fnl` |
        | `MET_EM_CACHE_PATH` | Where met_em files are kept | `<scratch>/metem` |

        `END_DATE` is ignored, as setup-wrf ignores it: the job runs one day.

        Parameters
        ----------
        environ
            The environment, such as `os.environ`. Passed in rather than read,
            so nothing is read on import and tests can pass a dict.

        Raises
        ------
        WrfConfigError
            Listing every problem found, so they can all be fixed at once.
        """
        problems = []

        def required(name: str) -> str | None:
            value = environ.get(name, "").strip()
            if not value:
                problems.append(f"{name} is required")
                return None
            return value

        start_date = None
        start_text = required("START_DATE")
        if start_text is not None:
            try:
                start_date = datetime.date.fromisoformat(start_text)
            except ValueError:
                problems.append(f"START_DATE must be a date as YYYY-MM-DD, got {start_text!r}")

        domain_name = required("DOMAIN_NAME")
        domain_version = required("DOMAIN_VERSION")
        domains = None
        if domain_name is not None and domain_version is not None:
            try:
                domains = DomainSet.load([(domain_name, domain_version)])
            except GeometryError as error:
                problems.append(str(error))

        force_text = environ.get("FORCE_WRF", "").strip().lower()
        if force_text not in ("", "true", "false"):
            problems.append(f"FORCE_WRF must be true or false, got {environ['FORCE_WRF']!r}")

        mpi_ranks = None
        ncpus_text = environ.get("NCPUS", "").strip()
        if ncpus_text:
            try:
                mpi_ranks = int(ncpus_text)
            except ValueError:
                mpi_ranks = 0
            if mpi_ranks < 1:
                problems.append(f"NCPUS must be a positive whole number, got {ncpus_text!r}")

        if problems:
            raise WrfConfigError(problems)

        output_path = pathlib.Path(environ.get("STORE_PATH") or DEFAULT_STORE_PATH)
        scratch_path = pathlib.Path(environ.get("CHK_PATH") or DEFAULT_CHK_PATH)
        output_path = output_path / "wrf" / domain_name
        scratch_path = scratch_path / "wrf" / domain_name
        return cls(
            start_date=start_date,
            end_date=start_date,
            domain_version=domain_version,
            domains=domains,
            output_path=output_path,
            scratch_path=scratch_path,
            met_em_cache_path=pathlib.Path(
                environ.get("MET_EM_CACHE_PATH") or scratch_path / "metem"
            ),
            fnl_cache_path=pathlib.Path(environ.get("FNL_CACHE_PATH") or DEFAULT_FNL_CACHE_PATH),
            mpi_ranks=mpi_ranks,
            force=force_text == "true",
        )
