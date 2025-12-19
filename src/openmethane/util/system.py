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
import datetime
import importlib
import os
import sys


def get_command():
    return " ".join(sys.argv)


def get_timestamped_command():
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    return f"{now_utc.isoformat(sep=' ', timespec='seconds')}: {get_command()}"


def get_version():
    return os.getenv('OPENMETHANE_VERSION', importlib.metadata.version('openmethane'))
