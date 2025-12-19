#
# Copyright 2025 The Superpower Institute
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
import xarray as xr

def get_grid_mappings(ds: xr.Dataset) -> list[str]:
    grid_mapping_vars = []
    for var_name in ds.data_vars:
        if "grid_mapping_name" in ds.variables[var_name].attrs:
            grid_mapping_vars.append(var_name)
    return grid_mapping_vars
