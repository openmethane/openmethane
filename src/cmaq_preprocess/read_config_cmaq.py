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

    CMAQdir: str
    """Base directory for the CMAQ model"""
    MCIPdir: str
    """Directory containing the MCIP executable"""
    metDir: str
    """
    Base directory for the MCIP output.

    Convention for MCIP output is that we have data organised by day and domain,
     eg metDir/2016-11-29/d03"""
    ctmDir: str
    """
    Base directory for the CCTM inputs and outputs. 
    
    same convention for the CMAQ output as for the MCIP output, except with ctmDir"""
    wrfDir: str
    """directory containing wrfout_* files, convention for WRF output,
     is wrfDir/2016112900/wrfout_d03_*"""
    geoDir: str
    """directory containing geo_em.* files"""
    inputCAMSFile: str
    """Filepath to CAMS file."""
    domains: list[str]
    """which domains should be run?"""
    run: str
    # TODO: Clarify what is meant by *short* - longer!
    """name of the simulation, appears in some filenames (keep this *short* - longer)"""
    startDate: datetime.datetime = field(converter=process_date_string)
    """this is the START of the FIRST day, use the format
    2022-07-01 00:00:00 UTC (time zone optional)"""
    endDate: datetime.datetime = field(converter=process_date_string)
    """this is the START of the LAST day, use the format
    2022-07-01 00:00:00 UTC (time zone optional)"""

    @endDate.validator
    def check_endDate(self, attribute, value):
        if value < self.startDate:
            raise ValueError("End date must be after start date.")

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

    prepareICandBC: bool = field(converter=boolean_converter)
    """prepare the initial and boundary conditions from global CAMS output"""
    forceUpdate: bool = field(converter=boolean_converter)
    """
    Force the recreation of output

    If true, then any existing MCIP, IC and BC output is ignored.
    """
    scenarioTag: list[str] = field()
    """MCIP option: scenario tag. 16-character maximum"""

    @scenarioTag.validator
    def check_scenarioTag(self, attribute, value):
        if len(value[0]) > 16:
            raise ValueError(
                f"16-character maximum length for configuration value {attribute.name}"
            )
        if not isinstance(value, list):
            raise ValueError(f"Configuration value for {attribute.name} must be a list")

    mapProjName: list[str]
    """MCIP option: Map projection name. """
    gridName: list[str] = field()
    """MCIP option: Grid name. 16-character maximum"""

    @gridName.validator
    def check_gridName(self, attribute, value):
        if len(value[0]) > 16:
            raise ValueError(
                f"16-character maximum length for configuration value {attribute.name}"
            )
        if not isinstance(value, list):
            raise ValueError(f"Configuration value for {attribute.name} must be a list")

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

    CAMSToCmaqBiasCorrect: float
    """Pre-set is (1.838 - 1.771)"""
    # TODO: Add description for CAMSToCmaqBiasCorrect?


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
