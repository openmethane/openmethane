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
import os

import numpy as np

import fourdvar.params.template_defn as template
import fourdvar.util.date_handle as dt
import fourdvar.util.file_handle as fh
import fourdvar.util.netcdf_handle as ncf
from fourdvar.logging import setup_logging
from fourdvar.params import cmaq_config
from fourdvar.util import cmaq_handle


def copy_file(src_template: str, dest_template: str, date: datetime.date | None):
    """
    Copy a (potentially) templated file to another location

    This additionally compresses the resulting file
    """
    src = dt.replace_date(src_template, date) if date else src_template
    dest = dt.replace_date(dest_template, date) if date else dest_template

    fh.ensure_path(os.path.dirname(dest))
    ncf.copy_compress(src, dest)


setup_logging()

# Copy a template emissions file into the input directory
emis_file = dt.replace_date(cmaq_config.emis_file, dt.start_date)
copy_file(template.emis, cmaq_config.emis_file, dt.start_date)

# define cmaq filenames for first day of model run.
icon_file = dt.replace_date(cmaq_config.icon_file, dt.start_date)
conc_file = dt.replace_date(cmaq_config.conc_file, dt.start_date)
force_file = dt.replace_date(cmaq_config.force_file, dt.start_date)

# Prepare CMAQ run directories
fh.ensure_path(os.path.dirname(force_file))
fh.ensure_path(cmaq_config.chk_path)

# redefine any cmaq_config variables dependent on template files
if str(cmaq_config.emis_lays).lower() == "template":
    emis_lay = int(ncf.get_attr(emis_file, "NLAYS"))
    cmaq_config.emis_lays = str(emis_lay)

if str(cmaq_config.conc_out_lays).lower() == "template":
    conc_lay = int(ncf.get_attr(icon_file, "NLAYS"))
    cmaq_config.conc_out_lays = f"1 {conc_lay}"

if str(cmaq_config.avg_conc_out_lays).lower() == "template":
    conc_lay = int(ncf.get_attr(icon_file, "NLAYS"))
    cmaq_config.avg_conc_out_lays = f"1 {conc_lay}"

if str(cmaq_config.conc_spcs).lower() == "template":
    conc_spcs = ncf.get_attr(icon_file, "VAR-LIST").split()
    cmaq_config.conc_spcs = " ".join(conc_spcs)

if str(cmaq_config.avg_conc_spcs).lower() == "template":
    conc_spcs = ncf.get_attr(icon_file, "VAR-LIST").split()
    cmaq_config.avg_conc_spcs = " ".join(conc_spcs)

if str(cmaq_config.force_lays).lower() == "template":
    force_lay = int(ncf.get_attr(icon_file, "NLAYS"))
    cmaq_config.force_lays = str(force_lay)

if str(cmaq_config.sense_emis_lays).lower() == "template":
    sense_lay = int(ncf.get_attr(icon_file, "NLAYS"))
    cmaq_config.sense_emis_lays = str(sense_lay)

# generate sample files by running 1 day of cmaq (fwd & bwd)
cmaq_handle.wipeout_fwd()
cmaq_handle.run_fwd_single(dt.start_date, is_first=True)

# make force file with same attr as conc and all data zeroed
conc_spcs = ncf.get_attr(conc_file, "VAR-LIST").split()
conc_data = ncf.get_variable(conc_file, conc_spcs)
force_data = {k: np.zeros(v.shape) for k, v in conc_data.items()}
ncf.create_from_template(conc_file, force_file, force_data)
cmaq_handle.run_bwd_single(dt.start_date, is_first=True)

# create record for icon & emis files
copy_file(cmaq_config.icon_file, template.icon, dt.start_date)

# create template for conc, force & sense files
# The template files don't have a date in their names
copy_file(conc_file, template.conc, None)
copy_file(force_file, template.force, None)
copy_file(cmaq_config.emis_sense_file, template.sense_emis, dt.start_date)
copy_file(cmaq_config.conc_sense_file, template.sense_conc, dt.start_date)

# clean up files created by cmaq
cmaq_handle.wipeout_fwd()