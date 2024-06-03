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

from ._env import env

# full path to the top level of the repository
# TODO: Not sure if this needs an env variable
root_path = env.str("ROOT_PATH")

# full path to the branch-specific data
store_path = env.str("STORE_PATH")
