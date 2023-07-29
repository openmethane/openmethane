"""
plain.py: Some routines for handling plains

Copyright 2023 Superpower Institute.
Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and limitations under the License.
"""

import numpy as np
class Plain( object):
    """ plains are defined by a unit normal vector and an anchoring point """
    def __init__( self, normal, anchor):
        """ initialise directly with defining attributes """
        self.normal = np.array( normal).squeeze() # convert from sequence and remove irrelevant indices
        self.anchor = np.array( anchor).squeeze() # and again
        assert self.normal.ndim == 1, 'normal must be one dimensional'
        assert self.anchor.ndim == 1, 'anchor must be one-dimensional'
        assert self.anchor.shape == self.normal.shape, 'anchor and normal must be same dimension'
        return None
    def from_points( self, pointsList):
        """ create a plain in R^3 from a list of 3 points """
        vectors = np.array( pointsList).squeeze()
        assert vectors.shape == (3,3), 'only works for 3 points in R^3'
        self.normal = np.cross((vectors[1] -vectors[0]), (vectors[2] -vectors[0]))
        self.normal /= np.norm( self.normal)
        saelf.anchor = vectors[0]
        return None
    
    def isup(self, point):
        """ determines whether a point is on the "up" side of a plane i.e in the direction of rather than opposed to the defined normal """
        vector = np.array( point).squeeze() # cannonicalise input
        assert vector.shape == self.normal.shape, 'point and plain have incompatible dimensions'
        isUp = np.dot( self.normal, (vector -self.anchor))
        return True if isUp >= 0 else False
