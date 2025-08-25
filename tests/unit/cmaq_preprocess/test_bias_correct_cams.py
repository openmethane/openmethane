"""Tests that the bias is zero after correcting it."""

import datetime
import shutil

import xarray as xr

import cmaq_preprocess
import cmaq_preprocess.bias
import cmaq_preprocess.read_config_cmaq
import cmaq_preprocess.utils


def test_bias_zero_after_correct(test_data_dir, tmp_path, monkeypatch, metcro3d_file):
    # setup test data
    start_date = datetime.date(2022, 12, 7)
    end_date = datetime.date(2022, 12, 7)
    monkeypatch.setenv("START_DATE", "2022-12-07")
    monkeypatch.setenv("END_DATE", "2022-12-07")

    icon_file_name = "template_icon_profile_CH4only_d01.nc"
    icon_file_src = test_data_dir / "cmaq" / icon_file_name
    icon_file = tmp_path / icon_file_name
    shutil.copy(icon_file_src, icon_file)
    bcon_file_names = ["template_bcon_profile_CH4only_d01.nc"]
    bcon_files_src = [test_data_dir / "cmaq" / n for n in bcon_file_names]
    bcon_files = [tmp_path / n for n in bcon_file_names]
    for i, fname in enumerate(bcon_files):
        shutil.copy(bcon_files_src[i], fname)
    obs_file = test_data_dir / "obs" / "test_obs_2022-12-07.pic.gz"

    levels = xr.open_dataset(metcro3d_file).attrs["VGLVLS"]

    # calculate bias
    bias = cmaq_preprocess.bias.calculate_icon_bias(
        icon_files=[icon_file],
        obs_file=obs_file,
        levels=levels,
        start_date=start_date,
        end_date=end_date,
    )

    # pre-existing bias has to be larger than almost zero, otherwise the later
    # assert is meaningless
    assert abs(bias) > 1e-6

    # correct bias
    cmaq_preprocess.bias.correct_icon_bcon(
        species="CH4",
        bias=bias,
        icon_files=[icon_file],
        bcon_files=bcon_files,
    )

    # calculate new bias - should be zero
    new_bias = cmaq_preprocess.bias.calculate_icon_bias(
        icon_files=[icon_file],
        obs_file=obs_file,
        levels=levels,
        start_date=start_date,
        end_date=end_date,
    )
    assert abs(new_bias) <= 1e-6
