"""
testplane.py: testing for plane.py

Copyright 2023 Superpower Institute.
Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and limitations under the License.
"""
from plane import Plane, Polyhedron
import numpy as np
import itertools
polyCorners = [[0.,0.,-3.],[1.,1.,3.]]
polyVertices = np.array(list(itertools.product(*zip(polyCorners[0],polyCorners[1]))))
faces = [ Plane.from_points( polyVertices[l]) for l in [[0,2,1], [4,0,5], [6,4,7], [2,6,3]]]
poly=Polyhedron( faces, nSamplePoints=200)
c1=[[.2,.2,.2],[.4,.4,.4]]
print('checking isInside:',poly.isInside([.5,.5,.5]),poly.isInside([.5,1.5,.5]),poly.isInside([.5,.5,3.5]))
print(poly.intersectionPrismVolume([[.1,.1,.1],[.5,.5,.5]]))
print(poly.intersectionPrismVolume([[-.1,-.1,-.1],[.5,.5,.5]]))
