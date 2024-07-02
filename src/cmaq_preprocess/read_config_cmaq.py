import datetime

from attrs import define, field

from cmaq_preprocess.config_read_functions import (
    boolean_converter,
    load_json,
    process_date_string,
)


@define
class CMAQConfig:
    """
    Configuration used to generate the CMAQ setup and run scripts.
    """

    cmaq_dir: str
    """Base directory for the CMAQ model"""
    mcip_dir: str
    """Directory containing the MCIP executable"""
    met_dir: str
    """
    Base directory for the MCIP output.

    convention for MCIP output is that we have data organised by day and domain,
     eg metDir/2016-11-29/d03"""
    ctm_dir: str
    """Output directory for the CCTM inputs and outputs."""
    wrf_dir: str
    """directory containing wrfout_* files, convention for WRF output,
     is wrfDir/2016112900/wrfout_d03_*"""
    geo_dir: str
    """directory containing geo_em.* files"""
    input_cams_file: str
    """Filepath to CAMS file.

    This file should be downloaded using `scripts/cmaq_preprocess/download_cams_input.py` and
    should cover the period of interest.
    """
    domains: list[str]
    """Domains to be run"""
    run: str
    """Name of the simulation

    This should be less than 16 characters and appears in some filenames.
    """
    start_date: datetime.datetime = field(converter=process_date_string)
    """this is the START of the FIRST day, use the format
    2022-07-01 00:00:00 UTC (time zone optional)"""
    end_date: datetime.datetime = field(converter=process_date_string)
    """this is the START of the LAST day, use the format
    2022-07-01 00:00:00 UTC (time zone optional)"""

    @end_date.validator
    def check_end_date(self, attribute, value):
        if value < self.start_date:
            raise ValueError("End date must be after start date.")

    # TODO: Check if int is the right type. Perhaps time units between full hours are supported.
    n_hours_per_run: int
    """number of hours to run at a time (24 means run a whole day at once)"""
    print_freq_hours: int
    """frequency of the CMAQ output (1 means hourly output)
    - so far it is not set up to run for sub-hourly"""
    mech: str
    """name of chemical mechanism to appear in filenames"""
    mech_cmaq: str = field()
    """name of chemical mechanism given to CMAQ """

    # TODO: The list of valid values for mechCMAQ is outdated, "CH4only" was not
    #  in the list in the comment. Get a valid list or delete check.
    @mech_cmaq.validator
    def check_mech_cmaq(self, attribute, value):
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

    prepare_ic_and_bc: bool = field(converter=boolean_converter)
    """prepare the initial and boundary conditions from global CAMS output"""
    force_update: bool = field(converter=boolean_converter)
    """Force reprocesssing of results even if the output files already exist"""
    scenario_tag: list[str] = field()
    """MCIP option: scenario tag. 16-character maximum"""

    @scenario_tag.validator
    def check_scenario_tag(self, attribute, value):
        if len(value[0]) > 16:
            raise ValueError(
                f"16-character maximum length for configuration value {attribute.name}"
            )
        if not isinstance(value, list):
            raise ValueError(f"Configuration value for {attribute.name} must be a list")

    map_projection_name: list[str]
    """MCIP option: Map projection name. """
    grid_name: list[str] = field()
    """MCIP option: Grid name. 16-character maximum"""

    @grid_name.validator
    def check_grid_name(self, attribute, value):
        if len(value[0]) > 16:
            raise ValueError(
                f"16-character maximum length for configuration value {attribute.name}"
            )
        if not isinstance(value, list):
            raise ValueError(f"Configuration value for {attribute.name} must be a list")

    scripts: dict[str, dict[str, str]] = field()
    """Template run scripts

    Elements of the dictionary should themselves be dictionaries, with the key 'path' and
    the value being the path to that file. The keys of the 'scripts'
    dictionary should be as follow:

    mcipRun - MCIP run script
    bconRun - BCON run script
    iconRun - ICON run script
    """

    @scripts.validator
    def check_scripts(self, attribute, value):
        expected_keys = ["mcipRun", "bconRun", "iconRun"]
        if sorted(list(value.keys())) != sorted(expected_keys):
            raise ValueError(f"{attribute.name} must have the keys {expected_keys}")
        for key in value:
            if "path" not in value[key]:
                raise ValueError(
                    f"{key} in configuration value {attribute.name} must have the key 'path'"
                )

    cams_to_cmaq_bias: float
    """Bias correction to apply to the CAMS data

    TODO: Generate/document how to calculate this value

    Pre-set is (1.838 - 1.771)"""


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
    return CMAQConfig(**config)


def load_cmaq_config(filepath: str) -> CMAQConfig:
    """
    Load a CMAQ configuration from a JSON file and create a CMAQConfig object.

    Parameters
    ----------
    filepath
        The path to the JSON file containing the CMAQ configuration.

    Returns
    -------
    CMAQConfig
        An instance of CMAQConfig initialized with the loaded configuration.
    """
    config = load_json(filepath)

    return create_cmaq_config_object(config)
