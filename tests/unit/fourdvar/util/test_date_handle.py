import datetime

import pytest

from openmethane.fourdvar.util import date_handle


def test_get_datelist(au_test_config):
    res = date_handle.get_datelist()
    assert res == [datetime.date(2022, 12, 7)]


def test_get_datelist_spans_the_configured_dates(au_test_config):
    au_test_config(START_DATE="2022-07-01", END_DATE="2022-07-02")

    res = date_handle.get_datelist()

    assert res == [datetime.date(2022, 7, 1), datetime.date(2022, 7, 2)]


@pytest.mark.parametrize(
    "date,inp,exp",
    [
        (datetime.date(2022, 7, 22), "<YYYYMMDD>", "20220722"),
        (datetime.date(2022, 7, 1), "<YYYYMMDD>", "20220701"),
        (datetime.date(2022, 7, 22), "<YYYY-MM-DD>", "2022-07-22"),
        (datetime.date(2022, 7, 22), "<YYYYDDD>", "2022203"),
        (datetime.date(2022, 7, 22), "test/<YYYYMMDD>/other", "test/20220722/other"),
        (datetime.date(2022, 7, 22), "test/<YYYYMMDD>/<YYYYMMDD>", "test/20220722/20220722"),
        (datetime.date(2022, 7, 22), "<YYYYMMDD>/<YYYY-MM-DD>", "20220722/2022-07-22"),
    ],
)
def test_replace_date(date, inp, exp):
    res = date_handle.replace_date(inp, date)

    assert res == exp
