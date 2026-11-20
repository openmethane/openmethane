"""Split a period into WRF run windows.

Each window runs WRF for `hours_per_run` hours, starting `hours_spin_up` hours
early so the model has settled by the first hour that is kept. Windows don't
overlap in the hours they keep, but each one's spin-up overlaps the previous
window. This is setup-wrf's job loop.
"""

import datetime
import math

import attrs

ANALYSIS_INTERVAL_HOURS = 6
"""Hours between FNL analyses, and so between met_em files"""


@attrs.frozen
class RunWindow:
    """One WRF run, from the start of spin-up to the end of the kept hours."""

    start: datetime.datetime
    """When WRF starts, including spin-up"""
    first_kept: datetime.datetime
    """The first hour whose output is kept"""
    end: datetime.datetime
    """When WRF stops. Output at this time is kept too"""

    @property
    def name(self) -> str:
        """The window's folder name, its first kept hour as YYYYMMDDHH."""
        return self.first_kept.strftime("%Y%m%d%H")

    @property
    def spin_up_hours(self) -> int:
        return int((self.first_kept - self.start) / datetime.timedelta(hours=1))

    def analysis_times(self) -> list[datetime.datetime]:
        """The times of the analyses, and so the met_em files, the window needs."""
        count = round((self.end - self.start) / datetime.timedelta(hours=ANALYSIS_INTERVAL_HOURS))
        return [
            self.start + datetime.timedelta(hours=ANALYSIS_INTERVAL_HOURS * step)
            for step in range(count + 1)
        ]


def run_windows(
    start_date: datetime.date,
    end_date: datetime.date,
    hours_per_run: int,
    hours_spin_up: int,
) -> list[RunWindow]:
    """
    Split the days from `start_date` to `end_date`, inclusive, into run windows.

    The period runs from 00Z on `start_date` to 00Z on the day after
    `end_date`. If it isn't a whole number of windows, the last window runs
    past the end, as setup-wrf's did.

    Parameters
    ----------
    start_date
        First day to produce output for.
    end_date
        Last day to produce output for, inclusive.
    hours_per_run
        Hours kept from each window.
    hours_spin_up
        Hours each window starts before its first kept hour.
    """
    if end_date < start_date:
        raise ValueError(f"end_date {end_date} is before start_date {start_date}")
    if hours_per_run <= 0 or hours_spin_up < 0:
        raise ValueError(
            f"hours_per_run must be positive and hours_spin_up not negative,"
            f" got {hours_per_run} and {hours_spin_up}"
        )

    period_start = datetime.datetime.combine(start_date, datetime.time())
    period_hours = ((end_date - start_date).days + 1) * 24
    count = math.ceil(period_hours / hours_per_run)

    windows = []
    for index in range(count):
        first_kept = period_start + datetime.timedelta(hours=index * hours_per_run)
        windows.append(
            RunWindow(
                start=first_kept - datetime.timedelta(hours=hours_spin_up),
                first_kept=first_kept,
                end=first_kept + datetime.timedelta(hours=hours_per_run),
            )
        )
    return windows
