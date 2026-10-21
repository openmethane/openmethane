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

from openmethane.fourdvar.datadef import PhysicalAdjointData, PhysicalData
from openmethane.fourdvar.params.input_defn import inc_icon


def uncondition(unknown):
    """application: undo pre-conditioning of PhysicalData, add back any lost metadata
    input: UnknownData
    output: PhysicalData.

    notes: this function must apply the prior error covariance
    """
    return unk_to_phys(unknown, False)


def uncondition_adjoint(unknown_gradient):
    """application: undo pre-conditioning of a gradient, the inverse of condition_adjoint
    input: UnknownData (gradient of the cost with respect to the unknowns)
    output: PhysicalAdjointData.

    notes: this function must apply the inverse prior error covariance
    """
    return unk_to_phys(unknown_gradient, True)


def unk_to_phys(unknown, is_adjoint):
    """application: undo pre-conditioning of UnknownData
    input: UnknownData
    output: PhysicalData, or PhysicalAdjointData if is_adjoint.
    """
    PhysicalData.assert_params()

    # weighting function changes if is_adjoint
    if is_adjoint is True:
        output_class = PhysicalAdjointData

        def weight(val, sd):
            return val / sd
    else:
        output_class = PhysicalData

        def weight(val, sd):
            return val * sd

    p = PhysicalData
    emis_shape = (
        p.nstep_emis,
        p.nlays_emis,
        p.nrows,
        p.ncols,
    )
    emis_len = p.nstep_emis * p.nlays_emis * p.nrows * p.ncols
    bcon_shape = (
        p.nstep_bcon,
        p.bcon_region,
    )
    bcon_len = np.prod(bcon_shape)
    del p

    vals = unknown.get_vector()
    if inc_icon is True:
        icon_dict = {}
    emis_dict = {}
    bcon_dict = {}
    i = 0
    for spc in PhysicalData.spcs:
        if inc_icon is True:
            icon = vals[i]
            i += 1
            icon_dict[spc] = weight(icon, PhysicalData.icon_unc[spc])

        emis = vals[i : i + emis_len]
        emis = emis.reshape(emis_shape)
        emis_dict[spc] = weight(emis, PhysicalData.emis_unc[spc])
        i += emis_len

        bcon = vals[i : i + bcon_len]
        bcon = bcon.reshape(bcon_shape)
        bcon_dict[spc] = weight(bcon, PhysicalData.bcon_unc[spc])
        i += bcon_len

    assert i == len(vals), "Some physical data left unassigned!"

    if inc_icon is False:
        icon_dict = None
    return output_class(icon_dict, emis_dict, bcon_dict)
