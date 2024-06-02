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
import itertools

import numpy as np

from obs_preprocess.plane import Plane, Polyhedron


def test_plane():
    poly_corners = [[0.0, 0.0, -3.0], [1.0, 1.0, 3.0]]
    poly_vertices = np.array(list(itertools.product(*zip(poly_corners[0], poly_corners[1]))))
    faces = [
        Plane.from_points(poly_vertices[face]) for face in [[0, 2, 1], [4, 0, 5], [6, 4, 7], [2, 6, 3]]
    ]
    poly = Polyhedron(faces, nSamplePoints=200)

    assert poly.isInside([0.5, 0.5, 0.5])
    assert not poly.isInside([0.5, 1.5, 0.5])
    assert not poly.isInside([0.5, 1.5, 3.5])


    print(poly.intersectionPrismVolume([[0.1, 0.1, 0.1], [0.5, 0.5, 0.5]]))
    print(poly.intersectionPrismVolume([[-0.1, -0.1, -0.1], [0.5, 0.5, 0.5]]))
