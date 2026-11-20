import datetime

from openmethane.wrf.geometry import DomainGeometry, DomainSet
from openmethane.wrf.outputs import (
    averaged_file_name,
    day_folder,
    expected_files,
    is_complete,
    missing_files,
)

DAY = datetime.date(2022, 12, 7)
PROJECTION = {
    "map_proj": "lambert",
    "ref_lat": -33.5,
    "ref_lon": 150.0,
    "truelat1": -15.0,
    "truelat2": -40.0,
    "stand_lon": 133.302,
    "geog_data_res": "usgs_30s+default",
}
OUTER = DomainGeometry(name="outer", e_we=40, e_sn=40, dx=10000, dy=10000, **PROJECTION)
NEST = DomainGeometry(
    name="nest", e_we=31, e_sn=31, dx=10000 / 3, dy=10000 / 3, parent="outer",
    parent_grid_ratio=3, i_parent_start=8, j_parent_start=8, **PROJECTION,
)  # fmt: skip


def test_names_match_the_files_mcip_reads(test_data_dir):
    committed = sorted(
        path.name for path in (test_data_dir / "wrf" / "au-test" / "2022120700").iterdir()
    )

    names = expected_files(DomainSet.load([("au-test", "v1")]), DAY)

    assert sorted(names) == committed


def test_a_day_has_25_files_per_domain():
    names = expected_files(DomainSet.from_geometries([OUTER, NEST]), DAY)

    assert len(names) == 50
    assert names[0] == "WRFOUT_d01_2022-12-07T0000Z.nc"
    assert names[24] == "WRFOUT_d01_2022-12-08T0000Z.nc"
    assert names[25] == "WRFOUT_d02_2022-12-07T0000Z.nc"


def test_averaged_file_name():
    assert averaged_file_name("d02", datetime.datetime(2022, 12, 7, 13)) == (
        "WRFOUT_d02_2022-12-07T1300Z.nc"
    )


def test_the_day_folder_is_named_for_its_first_hour(tmp_path):
    assert day_folder(tmp_path, DAY) == tmp_path / "2022120700"


def test_a_day_with_every_file_is_complete(tmp_path):
    domains = DomainSet.from_geometries([OUTER, NEST])
    folder = tmp_path / "2022120700"
    folder.mkdir()
    for name in expected_files(domains, DAY):
        (folder / name).touch()

    assert is_complete(tmp_path, domains, DAY)
    assert missing_files(tmp_path, domains, DAY) == []


def test_one_missing_file_in_one_domain_makes_the_day_incomplete(tmp_path):
    domains = DomainSet.from_geometries([OUTER, NEST])
    folder = tmp_path / "2022120700"
    folder.mkdir()
    for name in expected_files(domains, DAY):
        (folder / name).touch()
    (folder / "WRFOUT_d02_2022-12-07T1300Z.nc").unlink()

    assert not is_complete(tmp_path, domains, DAY)
    assert missing_files(tmp_path, domains, DAY) == ["WRFOUT_d02_2022-12-07T1300Z.nc"]


def test_raw_output_left_over_makes_the_day_incomplete(tmp_path):
    domains = DomainSet.from_geometries([OUTER])
    folder = tmp_path / "2022120700"
    folder.mkdir()
    for name in expected_files(domains, DAY):
        (folder / name).touch()
    (folder / "wrfout_d01_2022-12-07_13:00:00").touch()

    assert missing_files(tmp_path, domains, DAY) == ["wrfout_d01_2022-12-07_13:00:00"]


def test_a_day_with_no_folder_is_missing_everything(tmp_path):
    domains = DomainSet.from_geometries([OUTER])

    assert len(missing_files(tmp_path, domains, DAY)) == 25
