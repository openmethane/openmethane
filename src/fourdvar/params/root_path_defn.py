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

"""
Common path definitions

These definitions are used in other parameter definitions.
"""

from pathlib import Path

from ._env import env

ROOT_DIR = Path(__file__).resolve().parents[3]

# full path to the top level of the repository
root_path = str(ROOT_DIR)

# full path to the branch-specific data
store_path = env.str("STORE_PATH")
