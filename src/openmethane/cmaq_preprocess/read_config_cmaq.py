import datetime
import pathlib
import typing

import attrs.validators
from attrs import define, field, frozen

from openmethane.fourdvar.env import create_env


def validate_end_date(instance, attribute, value):
    if value < instance.start_date:
        raise ValueError("End date must be after start date.")


def process_date_string(value) -> datetime.date:
    if isinstance(value, datetime.datetime):
        return value.date()
    elif isinstance(value, datetime.date):
        return value
    elif isinstance(value, str):
        return datetime.date.fromisoformat(value)
    else:
        raise TypeError(f"Cannot process {value} as a date. {type(value)}")


@frozen
class Domain:
    index: int
    name: str = field(validator=attrs.validators.max_len(16))
    version: str
    map_projection: str = field(validator=attrs.validators.max_len(16))
    mcip_suffix: str = field(validator=attrs.validators.max_len(16))

    @property
    def id(self):
        return f"d{self.index:02}"


@define
class CMAQConfig:
    """
    Configuration used to generate the CMAQ setup and run scripts.
    """

    cmaq_source_dir: pathlib.Path
    """Base directory for the CMAQ model"""
    mcip_source_dir: pathlib.Path
    """Directory containing the MCIP executable"""
    met_dir: pathlib.Path
    """
    Base directory for the MCIP output.

    Convention for MCIP output is that we have data organised by day and domain,
     eg metDir/2016-11-29/d03"""
    ctm_dir: pathlib.Path
    """
    Base directory for the CCTM inputs and outputs.

    same convention for the CMAQ output as for the MCIP output, except with ctmDir"""
    wrf_dir: pathlib.Path
    """directory containing wrfout_* files, convention for WRF output,
     is wrfDir/2016112900/wrfout_d03_*"""
    geo_dir: pathlib.Path
    """directory containing geo_em.* files"""
    input_cams_file: pathlib.Path
    """Filepath to CAMS file.

    This file can be downloaded using `scripts/cmaq_preprocess/download_cams_input.py`.
    """
    start_date: datetime.date = field(
        converter=process_date_string,
        validator=attrs.validators.instance_of(datetime.date),
    )
    """
    Start of the first day

    Use ISO8061 formatted dates, e.g. 2022-07-22. All runs start at 00:00:00 UTC.
    """
    end_date: datetime.date = field(
        converter=process_date_string,
        validator=[
            attrs.validators.instance_of(datetime.date),
            validate_end_date,
        ],
    )
    """
    Last date to run

    Use ISO8061 formatted dates, e.g. 2022-07-22. All runs start at 00:00:00 UTC.
    """

    domain: Domain
    """
    Information about the domain
    """

    mech: str = field()
    """name of chemical mechanism to appear in filenames"""

    @mech.validator
    def check_mech(self, attribute, value):
        # TODO: The list of valid values for mech is outdated, "CH4only" was not
        #  in the list in the comment. Get a valid list or delete check.
        chemical_mechanisms = [
            "cb05e51_ae6_aq",
            "cb05mp51_ae6_aq",
            "cb05tucl_ae6_aq",
            "cb05tump_ae6_aq",
            "racm2_ae6_aq",
            "saprc07tb_ae6_aq",
            "saprc07tc_ae6_aq",
            "saprc07tic_ae6i_aq",
            "saprc07tic_ae6i_aqkmti",
            "CH4only",
        ]
        if value not in chemical_mechanisms:
            raise ValueError(
                f"Configuration value for {attribute.name} must be one of {chemical_mechanisms}"
            )

    prepare_ic_and_bc: bool
    """prepare the initial and boundary conditions from global CAMS output"""
    force_update: bool
    """
    Force the recreation of output

    If true, then any existing MCIP, IC and BC output is ignored.
    """
    scripts: dict[str, dict[str, str]] = field()
    """This is a dictionary with paths to each of the run-scripts. Elements of
    the dictionary should themselves be dictionaries, with the key 'path' and
    the value being the path to that file. The keys of the 'scripts'
    dictionary should be as follow:
    mcipRun - MCIP run script
    bconRun - BCON run script
    iconRun - ICON run script
    """

    @scripts.validator
    def check_scripts(self, attribute, value):
        expected_keys = [
            "mcipRun",
            "bconRun",
            "iconRun",
        ]
        if sorted(list(value.keys())) != sorted(expected_keys):
            raise ValueError(f"{attribute.name} must have the keys {expected_keys}")
        for key in value:
            if "path" not in value[key]:
                raise ValueError(
                    f"{key} in configuration value {attribute.name} must have the key 'path'"
                )

    cams_to_cmaq_bias: float
    """
    Bias between CAMS and CMAQ

    TODO: Create a script to calculate this

    Pre-set is (1.838 - 1.771)
    """
    boundary_trim: int
    """
    Number of grid cells to trim from the boundary of the domain

    5 is a good start for larger domains.
    """


def create_cmaq_config_object(config: dict[str, str | int | float]) -> CMAQConfig:
    """
    Creates a CMAQConfig object from the provided configuration.

    Parameters
    ----------
    config
        The configuration data to initialize the CMAQConfig object.

    Returns
    -------
    CMAQConfig
        An instance of CMAQConfig initialized with the provided configuration.
    """
    domain = Domain(
        index=config.pop("domain_index", 1),
        name=config.pop("domain_name"),
        version=config.pop("domain_version"),
        map_projection=config.pop("domain_map_projection", "LamCon_34S_150E"),
        mcip_suffix=config.pop("domain_mcip_suffix", "au-test_v1"),
    )

    return CMAQConfig(domain=domain, **config)


def load_config_from_env(**overrides: typing.Any) -> CMAQConfig:
    """
    Load the configuration from the environment variables

    This also loads environment variables from a local `.env` file.

    Returns
    -------
        Application configuration
    """
    # Loads the .env file as determined by TARGET
    env = create_env()

    root_dir = env.path("ROOT_DIR", pathlib.Path(__file__).parents[3])

    domain = Domain(
        index=env.int("DOMAIN_INDEX", 1),
        name=env.str("DOMAIN_NAME"),
        version=env.str("DOMAIN_VERSION"),
        map_projection=env.str("DOMAIN_MAP_PROJECTION", "LamCon_34S_150E"),
        mcip_suffix=env.str("DOMAIN_MCIP_SUFFIX", "LamCon_34S_150E"),
    )

    options = dict(
        prepare_ic_and_bc=True,
        force_update=env.bool("FORCE_UPDATE", True),
        cmaq_source_dir=env.path("CMAQ_SOURCE_DIR"),
        mcip_source_dir=env.path("MCIP_SOURCE_DIR"),
        met_dir=env.path("MET_DIR"),
        ctm_dir=env.path("CTM_DIR"),
        wrf_dir=env.path("WRF_DIR"),
        geo_dir=env.path("GEO_DIR"),
        input_cams_file=env.path("CAMS_FILE"),
        start_date=env.date("START_DATE"),
        end_date=env.date("END_DATE"),
        mech="CH4only",
        scripts={
            "mcipRun": {"path": root_dir / "templates" / "cmaq_preprocess/run.mcip"},
            "bconRun": {"path": root_dir / "templates" / "cmaq_preprocess/run.bcon"},
            "iconRun": {"path": root_dir / "templates" / "cmaq_preprocess/run.icon"},
        },
        cams_to_cmaq_bias=env.float("CAMS_TO_CMAQ_BIAS", 0.0),
        boundary_trim=env.int("BOUNDARY_TRIM", 5),
    )

    return CMAQConfig(domain=domain, **{**options, **overrides})
