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
        "CMAQdir": "/opt/cmaq/CMAQv5.0.2_notpollen/",
        "MCIPdir": "/opt/cmaq/CMAQv5.0.2_notpollen/scripts/mcip/src",
        "templateDir": "/opt/project/templateRunScripts",
        "metDir": "/opt/project/data/mcip/",
        "ctmDir": "/opt/project/data/cmaq/",
        "wrfDir": "/opt/project/data/runs/aust-test",
        "geoDir": "/opt/project/domains/aust-test/v1.0.0/",
        "inputCAMSFile": "/opt/project/data/inputs/cams_eac4_methane.nc",
        "sufadj": "output_newMet",
        "domains": ["d01"],
        "run": "openmethane",
        "startDate": "2022-07-01 00:00:00 UTC",
        "endDate": "2022-07-01 00:00:00 UTC",
        "nhoursPerRun": 24,
        "printFreqHours": 1,
        "mech": "CH4only",
        "mechCMAQ": "CH4only",
        "prepareICandBC": "True",
        "prepareRunScripts": "True",
        "add_qsnow": "False",
        "forceUpdateMcip": "False",
        "forceUpdateICandBC": "True",
        "forceUpdateRunScripts": "True",
        "scenarioTag": ["220701_aust-test"],
        "mapProjName": ["LamCon_34S_150E"],
        "gridName": ["openmethane"],
        "doCompress": "True",
        "compressScript": "/opt/project/nccopy_compress_output.sh",
        "scripts": {
            "mcipRun": {"path": "/opt/project/templateRunScripts/run.mcip"},
            "bconRun": {"path": "/opt/project/templateRunScripts/run.bcon"},
            "iconRun": {"path": "/opt/project/templateRunScripts/run.icon"},
            "cctmRun": {"path": "/opt/project/templateRunScripts/run.cctm"},
            "cmaqRun": {"path": "/opt/project/templateRunScripts/runCMAQ.sh"},
        },
        "cctmExec": "ADJOINT_FWD",
        "CAMSToCmaqBiasCorrect": 0.06700000000000017,
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
    cmaq_config_dict["mechCMAQ"] = value

    if expected_exception:
        with pytest.raises(expected_exception) as exc_info:
            create_cmaq_config_object(cmaq_config_dict)
        assert "Configuration value for mechCMAQ must be one of" in str(
            exc_info.value
        ), f"Test Failed: {test_id}"
    else:
        try:
            create_cmaq_config_object(cmaq_config_dict)
        except ValueError as e:
            pytest.fail(f"Unexpected ValueError raised for {test_id}: {e}")


@pytest.mark.parametrize(
    "attribute, value, error_string",
    [
        pytest.param(
            "scenarioTag",
            ["more_than_16_characters_long"],
            "16-character maximum length for configuration value",
            id="scenarioTag_more_than_16_characters_long",
        ),
        pytest.param("scenarioTag", "not_a_list", "must be a list", id="scenarioTag_not_a_list"),
        pytest.param(
            "gridName",
            ["more_than_16_characters_long"],
            "16-character maximum length for configuration value ",
            id="gridName_more_than_16_characters_long",
        ),
        pytest.param("gridName", "not_a_list", "must be a list", id="gridName_not_a_list"),
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
                "cctmRun": {"path": "some/path"},
                "cmaqRun": {"path": "some/path"},
            },
            "all_keys_present",
        ),
        (
            {
                "mcipRun": {"path": "unique/path1"},
                "bconRun": {"path": "unique/path2"},
                "iconRun": {"path": "unique/path3"},
                "cctmRun": {"path": "unique/path4"},
                "cmaqRun": {"path": "unique/path5"},
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
            {"mcipRun": {}, "bconRun": {}, "iconRun": {}, "cctmRun": {}, "cmaqRun": {}},
            "mcipRun in configuration value scripts must have the key 'path'",
            "missing_path_in_all",
        ),
        (
            {
                "mcipRun": {"path": "some/path"},
                "bconRun": {"path": "some/path"},
                "iconRun": {},
                "cctmRun": {"path": "some/path"},
                "cmaqRun": {"path": "some/path"},
            },
            "iconRun in configuration value scripts must have the key 'path'",
            "missing_path_in_one",
        ),
        (
            {"mcipRun": {"path": "some/path"}},
            "scripts must have the keys ['mcipRun', 'bconRun', 'iconRun', 'cctmRun', 'cmaqRun']",
            "missing_keys",
        ),
        (
            {},
            "scripts must have the keys ['mcipRun', 'bconRun', 'iconRun', 'cctmRun', 'cmaqRun']",
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
    "startDate, endDate, test_id",
    [
        ("2022-07-01 00:00:00 UTC", "2022-07-01 00:00:00 UTC", "test_same_day"),
        ("2022-07-01 00:00:00 UTC", "2022-07-02 00:00:00 UTC", "test_next_day"),
        ("2022-07-01 00:00:00 UTC", "2023-07-01 00:00:00 UTC", "test_next_year"),
    ],
    ids=lambda test_id: test_id,
)
def test_020_validator_endDate_after_startDate(startDate, endDate, test_id, cmaq_config_dict):
    cmaq_config_dict["startDate"] = startDate
    cmaq_config_dict["endDate"] = endDate

    cmaq_config_obj = create_cmaq_config_object(cmaq_config_dict)

    assert cmaq_config_obj.startDate

    assert cmaq_config_obj.endDate


# Error cases
@pytest.mark.parametrize(
    "startDate, endDate, test_id",
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
def test_021_validator_endDate_after_startDate_errors(
    startDate, endDate, test_id, cmaq_config_dict
):
    cmaq_config_dict["startDate"] = startDate
    cmaq_config_dict["endDate"] = endDate

    with pytest.raises(ValueError) as exc_info:
        create_cmaq_config_object(cmaq_config_dict)
    assert str(exc_info.value) == "End date must be after start date.", f"{test_id} failed."
