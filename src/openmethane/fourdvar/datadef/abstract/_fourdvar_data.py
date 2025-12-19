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
import numpy as np

import openmethane.fourdvar.util.netcdf_handle as ncf
from openmethane.fourdvar.util.cmaq_io_files import get_filedict


class FourDVarData:
    """framework: the abstarct global class for all FourDVar data structures."""

    def get_vector(self):
        """
        Concatenated vector of all emissions

        The names in the varlist attribute from the actual item from each record
        """
        file_data = get_filedict(self.__class__.__name__)
        result = []
        for label, record in file_data.items():
            varList = ncf.get_attr(record["actual"], "VAR-LIST")
            vars = varList.split()
            for v in vars:
                result.append(ncf.get_variable(record["actual"], v).astype("float64"))
        return np.array(result).flatten()

    @classmethod
    def load_from_vector_template(cls, vector):
        """
        Create a record from a vector templates

        See Also
        --------
        get_vector
        """
        file_data = get_filedict(cls.__name__)

        # first set up dimensions for reshaping vector
        record = next(iter(file_data.values()))["actual"]
        varList = ncf.get_attr(record, "VAR-LIST")
        vars = varList.split()
        if len(vars) > 1:
            raise ValueError("only works for one variable")
        var_shape = ncf.get_variable(record, vars[0]).shape
        vector_shape = (len(file_data), *var_shape)
        vector_reshape = vector.reshape(vector_shape)
        for i, record in enumerate(file_data.values()):
            for var in vars:
                ncf.create_from_template(
                    record["template"],
                    record["actual"],
                    var_change={var: vector_reshape[i, ...]},
                    date=record["date"],
                )
        return cls()

    def sum_squares(self):
        return (self.get_vector() ** 2).sum() / 2.0

    def cleanup(self):
        """framework: generic cleanup function
        input: None
        output: None.

        notes: currently only a stub, allows no-op cleanup.
        """
        pass
