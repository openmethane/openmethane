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

import openmethane.fourdvar.util.date_handle as dt
from openmethane.fourdvar.params import (
    archive_defn,
    cmaq_config,
    date_defn,
    input_defn,
    template_defn,
)

all_files = {
    "ModelInputData": {},
    "ModelOutputData": {},
    "AdjointForcingData": {},
    "SensitivityData": {},
}

firsttime = True


def get_filedict(clsname):
    """Return dictionary of files needed for data class.

    input: string, name of dataclass
    output: dict, filedict has 3 keys: actual, template and archive
            actual: path to the file used by cmaq.
            template: path to the template file used to construct actual.
            archive: filename to use when saving an archived copy of file.
    """
    msg = "Must set date_handle.{}"
    assert date_defn.start_date is not None, msg.format("start_date")
    assert date_defn.end_date is not None, msg.format("end_date")
    global all_files
    global firsttime
    if firsttime is True:
        firsttime = False
        build_filedict()
    return all_files[clsname]


def build_filedict():
    """Constructed the dictionary of files for the required dates.
    input: None
    output: None.

    notes: should only be called once, after date_handle has defined dates.
    """
    global all_files

    model_input_files = {}
    model_output_files = {}
    adjoint_forcing_files = {}
    sensitivity_files = {}

    all_files["ModelInputData"] = model_input_files
    all_files["ModelOutputData"] = model_output_files
    all_files["AdjointForcingData"] = adjoint_forcing_files
    all_files["SensitivityData"] = sensitivity_files

    if input_defn.inc_icon is True:
        model_input_files["icon"] = {
            "actual": cmaq_config.icon_file,
            "template": template_defn.icon,
            "archive": archive_defn.icon_file,
            "date": None,
        }
        #'date': date_defn.start_date }

    for date in dt.get_datelist():
        ymd = dt.replace_date("<YYYYMMDD>", date)
        model_input_files["emis." + ymd] = {
            "actual": dt.replace_date(cmaq_config.emis_file, date),
            "template": dt.replace_date(template_defn.emis, date),
            "archive": dt.replace_date(archive_defn.emis_file, date),
            "date": date,
        }
        model_output_files["conc." + ymd] = {
            "actual": dt.replace_date(cmaq_config.conc_file, date),
            "template": template_defn.conc,
            "archive": dt.replace_date(archive_defn.conc_file, date),
            "date": date,
        }
        adjoint_forcing_files["force." + ymd] = {
            "actual": dt.replace_date(cmaq_config.force_file, date),
            "template": template_defn.force,
            "archive": dt.replace_date(archive_defn.force_file, date),
            "date": date,
        }
        sensitivity_files["emis." + ymd] = {
            "actual": dt.replace_date(cmaq_config.emis_sense_file, date),
            "template": template_defn.sense_emis,
            "archive": dt.replace_date(archive_defn.sens_emis_file, date),
            "date": date,
        }
        sensitivity_files["conc." + ymd] = {
            "actual": dt.replace_date(cmaq_config.conc_sense_file, date),
            "template": template_defn.sense_conc,
            "archive": dt.replace_date(archive_defn.sens_conc_file, date),
            "date": date,
        }
