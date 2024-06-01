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
"""Routines for handling planes."""

import numpy as np
import itertools


class Plane:
    """planes are defined by a unit normal vector and an anchoring point"""

    def __init__(self, normal, anchor, orthogonalityTolerance=1e-6):
        """initialise directly with defining attributes"""
        self.normal = np.array(
            normal
        ).squeeze()  # convert from sequence and remove irrelevant indices
        self.anchor = np.array(anchor).squeeze()  # and again
        assert self.normal.ndim == 1, "normal must be one dimensional"
        assert self.anchor.ndim == 1, "anchor must be one-dimensional"
        assert self.anchor.shape == self.normal.shape, "anchor and normal must be same dimension"
        self.orthogonalityTolerance = orthogonalityTolerance

    @classmethod
    def from_points(cls, pointsList):
        """create a plane in R^3 from a list of 3 points"""
        vectors = np.array(pointsList).squeeze()
        assert vectors.shape == (3, 3), "only works for 3 points in R^3"
        normal = np.cross((vectors[1] - vectors[0]), (vectors[2] - vectors[0]))
        normal /= np.linalg.norm(normal)
        anchor = vectors[0]
        return cls(normal, anchor)

    def isUp(self, point):
        """determines whether a point is on the "up" side of a plane i.e in the direction of rather than opposed to the defined normal. Allow a slight user-defined tolerance for the common case where the point lies in the plane of self"""
        vector = np.array(point).squeeze()  # cannonicalise input
        assert vector.shape == self.normal.shape, "point and plane have incompatible dimensions"
        diff = vector - self.anchor
        dist = np.linalg.norm(diff)
        if dist < self.orthogonalityTolerance:  # point and self.anchor are probably the same
            return True
        else:
            isUp = np.dot(self.normal, diff) / dist
            return True if isUp > -self.orthogonalityTolerance else False


class Polyhedron:
    """defined as a list of planes with no requirement that they form a closed shape, e.g. an open square tube is valid"""

    def __init__(self, faces, nSamplePoints=100):
        """each face is a plane"""
        self.faces = list(faces)
        # for convex poly all points should be "up" from every face, let's see
        if not np.all([np.all([f1.isUp(f2.anchor) for f2 in self.faces]) for f1 in self.faces]):
            raise ValueError("polyhedron not convex")
        self.rng = np.random.default_rng()  # needed for later montecarlo
        self.nSamplePoints = nSamplePoints

    def isInside(self, point):
        """check if a point is inside a polyhedron"""
        return np.all([face.isUp(point) for face in self.faces])

    def contains(self, vertices):
        """check if a polyhedron defined by a set ov ertices is completely contained in self"""
        return np.all([self.isInside(v) for v in vertices])

    def intersectionPrismVolume(self, corners):
        """calculate the volume of intersection between self and a prism defined by its corners defined as a tuple of sequences"""
        vMin = np.array(corners[0]).squeeze()
        vMax = np.array(corners[1]).squeeze()
        # first check if the prism is contained in self,
        # generate vertices (trick from stackexchange)
        prismVertices = np.array(list(itertools.product(*zip(vMin, vMax))))
        # now if all prism vertices lie outside any face of self there is no intersection
        if np.any([np.all([not f.isUp(v) for v in prismVertices]) for f in self.faces]):
            return 0.0
        elif self.contains(prismVertices):
            return (vMax - vMin).prod()  # rectangular volume
        else:
            return self.montecarloVolume(corners)

    def montecarloVolume(self, corners):
        """use montecarlo sampling to estimate the volume of intersection between prism (given by corners) and self"""
        vMin = np.array(corners[0]).squeeze()
        vMax = np.array(corners[1]).squeeze()
        points = self.rng.uniform(vMin, vMax, size=(self.nSamplePoints, vMin.size))
        nInsidePoints = [self.isInside(p) for p in points].count(True)
        prismVolume = (vMax - vMin).prod()
        return prismVolume * float(nInsidePoints) / float(self.nSamplePoints)
