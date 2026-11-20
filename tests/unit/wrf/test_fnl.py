import datetime

import pytest

from openmethane.wrf.fnl import fetch_analyses, fnl_file_name, fnl_url


def test_url_of_an_analysis():
    url = fnl_url(datetime.datetime(2022, 12, 7, 6))

    assert url == (
        "https://data.gdex.ucar.edu/d083003/2022/202212/gdas1.fnl0p25.2022120706.f00.grib2"
    )


def test_the_dataset_root_can_be_overridden():
    url = fnl_url(datetime.datetime(2022, 12, 7, 6), "https://mirror.example/fnl/")

    assert url == "https://mirror.example/fnl/2022/202212/gdas1.fnl0p25.2022120706.f00.grib2"


@pytest.mark.parametrize(
    "time, message",
    (
        (datetime.datetime(2022, 12, 7, 3), "00, 06, 12 and 18Z"),
        (datetime.datetime(2022, 12, 7, 6, 30), "00, 06, 12 and 18Z"),
        (datetime.datetime(2015, 7, 8), "start after 2015-07-08"),
    ),
)
def test_there_is_no_analysis_at_other_times(time, message):
    with pytest.raises(ValueError, match=message):
        fnl_url(time)


def test_file_name():
    assert fnl_file_name(datetime.datetime(2022, 12, 7, 18)) == "gdas1.fnl0p25.2022120718.f00.grib2"


def test_analyses_in_the_cache_are_not_downloaded_again(tmp_path):
    times = [datetime.datetime(2022, 12, 7, hour) for hour in (0, 6)]
    for time in times:
        (tmp_path / fnl_file_name(time)).write_text("cached")

    # A repeated time is fetched once, and the result is in time order
    paths = fetch_analyses([times[1], times[0], times[1]], tmp_path, "https://unreachable.invalid")

    assert paths == [tmp_path / fnl_file_name(time) for time in times]
