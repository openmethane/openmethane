import datetime
import json
import pathlib

import pytest
from attrs import asdict
from pytest_regressions.data_regression import RegressionYamlDumper

from openmethane.cmaq_preprocess.config_read_functions import load_json
from openmethane.cmaq_preprocess.read_config_cmaq import (
    create_cmaq_config_object,
    load_config_from_env,
)


# Add support for dumping paths to YAML
def path_representer(dumper, obj):
    return dumper.represent_scalar("tag:yaml.org,2002:str", str(obj))


RegressionYamlDumper.add_representer(
    type(pathlib.Path()),
    path_representer,
)


# Define a fixture for creating and deleting a temporary config file
@pytest.fixture
def temp_config_file(tmp_path, request):
    content = request.param
    temp_file = tmp_path / "temp_config.json"
    temp_file.write_text(content)
    return str(temp_file)


@pytest.mark.parametrize("target", ["nci", "docker", "nci-test", "docker-test"])
def test_013_valid_config_file(target, data_regression, target_environment):
    target_environment(target)

    cmaq_config = load_config_from_env()
    data = asdict(cmaq_config)
    data_regression.check(data, basename=f"config_{target}")


@pytest.fixture
def cmaq_config_dict():
    return {
        "cmaq_bin_dir": "/opt/cmaq/bin/",
        "cmaq_scripts_dir": "/opt/project/scripts/cmaq",
        "met_dir": "/opt/project/data/mcip/",
        "ctm_dir": "/opt/project/data/cmaq/",
        "wrf_dir": "/opt/project/data/runs/au-test",
        "geo_dir": "/opt/project/domains/au-test/v1.0.0/",
        "input_cams_file": "/opt/project/data/inputs/cams_eac4_methane.nc",
        "start_date": "2022-07-01",
        "end_date": "2022-07-01",
        "mech": "CH4only",
        "prepare_ic_and_bc": True,
        "force_update": True,
        "cams_to_cmaq_bias": 0.06700000000000017,
        "boundary_trim": 5,
        "domain_name": "au-test",
        "domain_version": "v1",
        "domain_mcip_suffix": "au-test_v1",
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
def test_015_mech_validator(value, expected_exception, test_id, cmaq_config_dict):
    cmaq_config_dict["mech"] = value

    if expected_exception:
        match = "Configuration value for mech must be one of"
        with pytest.raises(expected_exception, match=match):
            create_cmaq_config_object(cmaq_config_dict)
    else:
        config = create_cmaq_config_object(cmaq_config_dict)
        assert config is not None


@pytest.mark.parametrize("attribute", ["map_projection", "name", "mcip_suffix"])
def test_016_domain_validators_more_than_16_characters(attribute, cmaq_config_dict):
    cmaq_config_dict[f"domain_{attribute}"] = "a_string_longer_than_16_characters"

    with pytest.raises(ValueError, match=f"Length of '{attribute}' must be <= 16"):
        create_cmaq_config_object(cmaq_config_dict)

@pytest.mark.parametrize(
    "test_input, expected",
    [
        pytest.param("test_json_1.json", {"key": "value"}, id="simple_content"),
        pytest.param(
            "test_json_2.json",
            {
                "more_complex": "content",
                "int": 1,
                "nested_dict": {"nested": "dict", "bool": True},
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
        ("2022-07-01", "2022-07-01", "test_same_day"),
        ("2022-07-01", "2022-07-02", "test_next_day"),
        ("2022-07-01", "2023-07-01", "test_next_year"),
    ],
    ids=lambda test_id: test_id,
)
def test_020_validator_end_date_after_start_date(start_date, end_date, test_id, cmaq_config_dict):
    cmaq_config_dict["start_date"] = start_date
    cmaq_config_dict["end_date"] = end_date

    cmaq_config_obj = create_cmaq_config_object(cmaq_config_dict)

    assert isinstance(cmaq_config_obj.start_date, datetime.date)
    assert isinstance(cmaq_config_obj.end_date, datetime.date)


# Error cases
@pytest.mark.parametrize(
    "start_date, end_date, test_id",
    [
        (
            "2022-07-02",
            "2022-07-01",
            "test_error_previous_day",
        ),
        (
            "2022-08-01",
            "2022-07-02",
            "test_error_previous_month",
        ),
        (
            "2024-07-01",
            "2023-07-01",
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

    with pytest.raises(ValueError, match="End date must be after start date."):
        create_cmaq_config_object(cmaq_config_dict)
