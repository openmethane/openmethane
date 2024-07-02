import json
import os

import pytest
from attrs import asdict

from cmaq_preprocess.config_read_functions import (
    boolean_converter,
    load_json,
    process_date_string,
)
from cmaq_preprocess.read_config_cmaq import (
    create_cmaq_config_object,
    load_cmaq_config,
)


@pytest.fixture
def config_path_cmaq_nci(root_dir):
    return os.path.join(root_dir, "config/cmaq_preprocess/config.nci.json")


@pytest.fixture
def config_path_cmaq_docker(root_dir):
    return os.path.join(root_dir, "config/cmaq_preprocess/config.docker.json")


# Define a fixture for creating and deleting a temporary config file
@pytest.fixture
def temp_config_file(tmp_path, request):
    content = request.param
    temp_file = tmp_path / "temp_config.json"
    temp_file.write_text(content)
    return str(temp_file)


def test_007_parse_boolean_keys():
    config = {
        "test_key_1": "t",
        "test_key_2": "1",
        "test_key_3": "true",
        "test_key_4": "y",
        "test_key_5": "yes",
        "test_key_6": "false",
        "test_key_7": "0",
        "test_key_8": "f",
        "test_key_9": "n",
        "test_key_10": "no",
        "test_key_11": "True",
        "test_key_12": "False",
    }

    expected = {
        "test_key_1": True,
        "test_key_2": True,
        "test_key_3": True,
        "test_key_4": True,
        "test_key_5": True,
        "test_key_6": False,
        "test_key_7": False,
        "test_key_8": False,
        "test_key_9": False,
        "test_key_10": False,
        "test_key_11": True,
        "test_key_12": False,
    }

    out = {k: boolean_converter(v) for k, v in config.items()}

    assert out == expected


@pytest.mark.parametrize(
    "datestring, expected",
    [
        pytest.param("2024-01-01 00:00:00 UTC", "2024-01-01 00:00:00+00:00", id="UTC time zone"),
        pytest.param("2024-01-01 00:00:00", "2024-01-01 00:00:00+00:00", id="no time zone"),
    ],
)
def test_008_process_date_string(datestring, expected):
    out = process_date_string(datestring)

    assert str(out) == expected


def test_013_valid_CMAQ_NCI_config_file(config_path_cmaq_nci, data_regression):
    cmaq_config = load_cmaq_config(config_path_cmaq_nci)
    data = asdict(cmaq_config)
    data_regression.check(data)


def test_014_valid_CMAQ_Docker_config_file(data_regression, config_path_cmaq_docker):
    cmaq_config = load_cmaq_config(config_path_cmaq_docker)
    data = asdict(cmaq_config)
    data_regression.check(data)


@pytest.fixture
def cmaq_config_dict():
    return {
        "cmaq_dir": "/opt/cmaq/CMAQv5.0.2_notpollen/",
        "mcip_dir": "/opt/cmaq/CMAQv5.0.2_notpollen/scripts/mcip/src",
        "met_dir": "/opt/project/data/mcip/",
        "ctm_dir": "/opt/project/data/cmaq/",
        "wrf_dir": "/opt/project/data/runs/aust-test",
        "geo_dir": "/opt/project/domains/aust-test/",
        "input_cams_file": "/opt/project/data/inputs/cams_eac4_methane.nc",
        "domains": ["d01"],
        "run": "openmethane",
        "start_date": "2022-07-01 00:00:00 UTC",
        "end_date": "2022-07-01 00:00:00 UTC",
        "n_hours_per_run": 24,
        "print_freq_hours": 1,
        "mech": "CH4only",
        "mech_cmaq": "CH4only",
        "prepare_ic_and_bc": "True",
        "force_update": True,
        "scenario_tag": ["220701_aust-test"],
        "map_projection_name": ["LamCon_34S_150E"],
        "grid_name": ["openmethane"],
        "scripts": {
            "mcipRun": {"path": "/opt/project/templateRunScripts/run.mcip"},
            "bconRun": {"path": "/opt/project/templateRunScripts/run.bcon"},
            "iconRun": {"path": "/opt/project/templateRunScripts/run.icon"},
        },
        "cams_to_cmaq_bias": 0.06700000000000017,
    }


# Test the validation for CMAQ object creation
@pytest.mark.parametrize(
    "value, expected_exception, test_id",
    [
        # Valid config tests
        ("cb05e51_ae6_aq", None, "valid_value_cb05e51"),
        ("cb05mp51_ae6_aq", None, "valid_value_cb05mp51"),
        ("saprc07tic_ae6i_aqkmti", None, "valid_value_saprc07tic"),
        ("CH4only", None, "valid_value_CH4only"),
        # Error cases
        ("cb06e51_ae6_aqooo", ValueError, "error_typo_in_value"),
        ("", ValueError, "error_empty_string"),
        ("unknown_mechanism", ValueError, "error_unknown_value"),
        (123, ValueError, "error_non_string_value"),
    ],
    ids=lambda test_id: test_id,
)
def test_015_mechCMAQ_validator(value, expected_exception, test_id, cmaq_config_dict):
    cmaq_config_dict["mech_cmaq"] = value

    if expected_exception:
        match = "Configuration value for mech_cmaq must be one of"
        with pytest.raises(expected_exception, match=match):
            create_cmaq_config_object(cmaq_config_dict)
    else:
        assert create_cmaq_config_object(cmaq_config_dict)


@pytest.mark.parametrize(
    "attribute, value, error_string",
    [
        pytest.param(
            "scenario_tag",
            ["more_than_16_characters_long"],
            "16-character maximum length for configuration value",
            id="scenario_tag_more_than_16_characters_long",
        ),
        pytest.param("scenario_tag", "not_a_list", "must be a list", id="scenario_tag_not_a_list"),
        pytest.param(
            "grid_name",
            ["more_than_16_characters_long"],
            "16-character maximum length for configuration value ",
            id="grid_name_more_than_16_characters_long",
        ),
        pytest.param("grid_name", "not_a_list", "must be a list", id="grid_name_not_a_list"),
    ],
)
def test_016_validators_more_than_16_characters(attribute, value, error_string, cmaq_config_dict):
    cmaq_config_dict[attribute] = value

    with pytest.raises(ValueError) as exc_info:
        create_cmaq_config_object(cmaq_config_dict)
    assert error_string in str(exc_info.value)


# Parametrized test for happy path scenarios
@pytest.mark.parametrize(
    "input_value, test_id",
    [
        (
            {
                "mcipRun": {"path": "some/path"},
                "bconRun": {"path": "some/path"},
                "iconRun": {"path": "some/path"},
            },
            "all_keys_present",
        ),
        (
            {
                "mcipRun": {"path": "unique/path1"},
                "bconRun": {"path": "unique/path2"},
                "iconRun": {"path": "unique/path3"},
            },
            "unique_paths_for_all",
        ),
    ],
    ids=lambda test_id: test_id,
)
def test_017_scripts_validator(input_value, test_id, cmaq_config_dict):
    cmaq_config_dict["scripts"] = input_value

    try:
        create_cmaq_config_object(cmaq_config_dict)
    except ValueError:
        pytest.fail("Unexpected ValueError raised.")


@pytest.mark.parametrize(
    "input_value, expected_exception_message, test_id",
    [
        (
            {
                "mcipRun": {},
                "bconRun": {},
                "iconRun": {},
            },
            "mcipRun in configuration value scripts must have the key 'path'",
            "missing_path_in_all",
        ),
        (
            {
                "mcipRun": {"path": "some/path"},
                "bconRun": {"path": "some/path"},
                "iconRun": {},
            },
            "iconRun in configuration value scripts must have the key 'path'",
            "missing_path_in_one",
        ),
        (
            {"mcipRun": {"path": "some/path"}},
            "scripts must have the keys ['mcipRun', 'bconRun', 'iconRun']",
            "missing_keys",
        ),
        (
            {},
            "scripts must have the keys ['mcipRun', 'bconRun', 'iconRun']",
            "empty_dict",
        ),
    ],
    ids=lambda test_id: test_id,
)
def test_018_scripts_validator_error_cases(
    input_value, expected_exception_message, test_id, cmaq_config_dict
):
    cmaq_config_dict["scripts"] = input_value

    with pytest.raises(ValueError) as exc_info:
        create_cmaq_config_object(cmaq_config_dict)
    assert expected_exception_message in str(exc_info.value), f"Test ID: {test_id}"


@pytest.mark.parametrize(
    "test_input, expected",
    [
        pytest.param("test_json_1.json", {"key": "value"}, id="simple_content"),
        pytest.param(
            "test_json_2.json",
            {
                "more_complex": "content",
                "int": 1,
                "nested_dict": {"nested": "dict", "bool": "True"},
            },
            id="more_complex_content",
        ),
    ],
)
def test_019_read_cmaq_json_config(test_input, expected, tmp_path):
    # Create a temporary directory and write the test data to a file
    test_file = tmp_path / test_input
    with open(test_file, "w") as f:
        json.dump(expected, f)
    expected_path = str(test_file)

    result = load_json(expected_path)

    assert result == expected, f"Failed to load or match JSON content for {test_input}"


@pytest.mark.parametrize(
    "start_date, end_date, test_id",
    [
        ("2022-07-01 00:00:00 UTC", "2022-07-01 00:00:00 UTC", "test_same_day"),
        ("2022-07-01 00:00:00 UTC", "2022-07-02 00:00:00 UTC", "test_next_day"),
        ("2022-07-01 00:00:00 UTC", "2023-07-01 00:00:00 UTC", "test_next_year"),
    ],
    ids=lambda test_id: test_id,
)
def test_020_validator_end_date_after_start_date(start_date, end_date, test_id, cmaq_config_dict):
    cmaq_config_dict["start_date"] = start_date
    cmaq_config_dict["end_date"] = end_date

    cmaq_config_obj = create_cmaq_config_object(cmaq_config_dict)

    assert cmaq_config_obj.start_date

    assert cmaq_config_obj.end_date


# Error cases
@pytest.mark.parametrize(
    "start_date, end_date, test_id",
    [
        (
            "2022-07-02 00:00:00 UTC",
            "2022-07-01 00:00:00 UTC",
            "test_error_previous_day",
        ),
        (
            "2022-08-01 00:00:00 UTC",
            "2022-07-02 00:00:00 UTC",
            "test_error_previous_month",
        ),
        (
            "2024-07-01 00:00:00 UTC",
            "2023-07-01 00:00:00 UTC",
            "test_error_previous_year",
        ),
    ],
    ids=lambda test_id: test_id,
)
def test_021_validator_end_date_after_start_date_errors(
    start_date, end_date, test_id, cmaq_config_dict
):
    cmaq_config_dict["start_date"] = start_date
    cmaq_config_dict["end_date"] = end_date

    with pytest.raises(ValueError) as exc_info:
        create_cmaq_config_object(cmaq_config_dict)
    assert str(exc_info.value) == "End date must be after start date.", f"{test_id} failed."
