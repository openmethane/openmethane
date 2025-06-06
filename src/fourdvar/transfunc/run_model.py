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
import fourdvar.util.cmaq_handle as cmaq
from fourdvar.datadef import ModelInputData, ModelOutputData
from util.logger import get_logger

logger = get_logger(__name__)


def run_model(model_input):
    """application: run the forward model, save result to ModelOutputData
    input: ModelInputData
    output: ModelOutputData.
    """
    # run the forward model
    assert isinstance(model_input, ModelInputData)
    cmaq.wipeout_fwd()
    cmaq.run_fwd()
    try:
        ModelOutputData()
    except AssertionError:
        logger.exception("cmaq_fwd_failed. logs exported.")
        raise
    return ModelOutputData()
