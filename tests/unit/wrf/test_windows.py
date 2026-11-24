import datetime

import pytest

from openmethane.wrf.windows import RunWindow, run_windows


def test_one_day_is_one_window_with_spin_up():
    windows = run_windows(
        datetime.date(2022, 12, 7), datetime.date(2022, 12, 7), hours_per_run=24, hours_spin_up=12
    )

    assert windows == [
        RunWindow(
            start=datetime.datetime(2022, 12, 6, 12),
            first_kept=datetime.datetime(2022, 12, 7),
            end=datetime.datetime(2022, 12, 8),
        )
    ]
    assert windows[0].name == "2022120700"
    assert windows[0].spin_up_hours == 12


def test_each_day_is_its_own_window():
    windows = run_windows(
        datetime.date(2022, 12, 30), datetime.date(2023, 1, 1), hours_per_run=24, hours_spin_up=12
    )

    assert [window.name for window in windows] == ["2022123000", "2022123100", "2023010100"]
    # Each window's spin-up overlaps the previous window's kept hours.
    assert windows[1].start == datetime.datetime(2022, 12, 30, 12)


def test_a_period_that_isnt_whole_windows_runs_past_the_end():
    windows = run_windows(
        datetime.date(2022, 12, 7), datetime.date(2022, 12, 8), hours_per_run=36, hours_spin_up=0
    )

    assert [window.end for window in windows] == [
        datetime.datetime(2022, 12, 8, 12),
        datetime.datetime(2022, 12, 10),
    ]


def test_a_window_needs_an_analysis_every_six_hours_from_the_start_of_spin_up():
    window = RunWindow(
        start=datetime.datetime(2022, 12, 6, 12),
        first_kept=datetime.datetime(2022, 12, 7),
        end=datetime.datetime(2022, 12, 8),
    )

    times = window.analysis_times()

    assert times == [
        datetime.datetime(2022, 12, 6, 12) + datetime.timedelta(hours=6 * n) for n in range(7)
    ]


def test_rejects_an_end_before_the_start():
    with pytest.raises(ValueError, match="before start_date"):
        run_windows(
            datetime.date(2022, 12, 7),
            datetime.date(2022, 12, 6),
            hours_per_run=24,
            hours_spin_up=12,
        )


def test_rejects_windows_of_no_hours():
    with pytest.raises(ValueError, match="hours_per_run must be positive"):
        run_windows(
            datetime.date(2022, 12, 7),
            datetime.date(2022, 12, 7),
            hours_per_run=0,
            hours_spin_up=12,
        )
