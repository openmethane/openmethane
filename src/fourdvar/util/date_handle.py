#
# Copyright 2016 University of Melbourne.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import datetime

from fourdvar.params import date_defn

# map string tags to date conversion functions
tag_map = {
    "<YYYYMMDD>": lambda date: date.strftime("%Y%m%d"),
    "<YYYYDDD>": lambda date: date.strftime("%Y%j"),
    "<YYYY-MM-DD>": lambda date: date.strftime("%Y-%m-%d"),
    "<YYYY>": lambda date: date.strftime("%Y"),
    "<MM>": lambda date: date.strftime("%m"),
    "<DD>": lambda date: date.strftime("%d"),
}


def add_days(date: datetime.date, ndays: int) -> datetime.date:
    """Return the date ndays before/after date.
    input: datetime.date, int (-ve for bwd in time)
    output: datetime.date.
    """
    return date + datetime.timedelta(days=ndays)


def get_datelist() -> list[datetime.date]:
    """Get the list of dates which the model runs over.

    output: list of datetime.date objects.

    notes: require start_date & end_date to already be defined
    """
    if date_defn.start_date is None or date_defn.end_date is None:
        raise ValueError("Need to define start_date and end_date.")
    days = (date_defn.end_date - date_defn.start_date).days + 1
    datelist = [add_days(date_defn.start_date, i) for i in range(days)]
    return datelist


def replace_date(src: str, date: datetime.date | datetime.datetime | tuple[int, int, int]) -> str:
    """Replace date tags with date data.

    input: string, date representation
    output: string.

    notes: date can be a datetime.date, datetime.datetime or a [year,month,day]
    """
    # force date into type datetime.date
    if isinstance(date, datetime.date):
        pass
    elif isinstance(date, datetime.datetime):
        date = date.date()
    else:
        date = datetime.date(date[0], date[1], date[2])

    # replace all date tags
    for tag in tag_map.keys():
        if tag in src:
            src = src.replace(tag, tag_map[tag](date))
        mtag = tag[:-1] + "#"
        while mtag in src:
            tstart = src.index(mtag) + len(mtag)
            tend = src.index(">", tstart)
            ndays = int(src[tstart:tend])
            mdate = add_days(date, ndays)
            src = src[: tstart - 1] + src[tend:]
            src = src.replace(tag, tag_map[tag](mdate))
    return src


def move_tag(src_str: str, ndays: int | float) -> str:
    """Add a day modifier to a date tag.

    input: string, integer
    output: string.
    """
    modifier = f"{int(ndays):+}"
    for tag in tag_map.keys():
        if tag in src_str:
            new_tag = f"<{tag[1:-1]}#{modifier}>"
            src_str = src_str.replace(tag, new_tag)
    return src_str
