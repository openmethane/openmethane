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

import datetime as dt
import os
from copy import deepcopy

import numpy as np
import pyproj
from netCDF4 import Dataset

from fourdvar.params import cmaq_config, date_defn, template_defn
from fourdvar.util import date_handle
from obs_preprocess.ray_trace import Grid


# convert HHMMSS into sec
def tosec(t):
    return 3600 * (int(t) // 10000) + 60 * (int(t) // 100 % 100) + int(t) % 100


# No.seconds in a day
daysec = tosec(240000)
# radius of the Earth, in meters
earth_rad = 6370000


class ModelSpace:
    gridmeta_keys = (
        "STIME",
        "TSTEP",
        "GDTYP",
        "P_ALP",
        "P_BET",
        "P_GAM",
        "XCENT",
        "YCENT",
        "XORIG",
        "YORIG",
        "XCELL",
        "YCELL",
        "NROWS",
        "NCOLS",
        "NLAYS",
        "VGTYP",
        "VGTOP",
        "VGLVLS",
        "NVARS",
        "VAR-LIST",
    )

    @classmethod
    def create_from_fourdvar(cls):
        sdate = date_defn.start_date
        edate = date_defn.end_date
        METCRO3D = date_handle.replace_date(cmaq_config.met_cro_3d, sdate)
        METCRO2D = cmaq_config.met_cro_2d
        CONC = template_defn.conc
        date_range = [sdate, edate]
        return cls(METCRO3D, METCRO2D, CONC, date_range)

    def __init__(self, METCRO3D, METCRO2D, CONC, date_range):
        """METCRO3D = path to any single METCRO3D file
        METCRO2D = path to any single METCRO2D file
        CONC = path to any concentration file output by CMAQ
        date_range = [ start_date, end_date ] (as datetime objects).
        """
        # read netCDF files
        self.gridmeta = {}
        with Dataset(METCRO3D, "r") as f:
            for key in self.gridmeta_keys:
                self.gridmeta[key] = f.getncattr(key)
            zf = f.variables["ZF"][:].mean(axis=(0, 2, 3))
            layer_height = np.append(np.zeros(1), zf)

        self.psurf_file = METCRO2D
        self.psurf_date = None
        self.psurf_arr = None

        # date co-ords are int YYYYMMDD format
        self.sdate = int(date_range[0].strftime("%Y%m%d"))
        self.edate = int(date_range[1].strftime("%Y%m%d"))

        # Only works on one type of vertical projection
        assert self.gridmeta["VGTYP"] == 7, "Invalid VGTYP"

        # record dimensional data
        self.ncol = self.gridmeta["NCOLS"]
        self.nrow = self.gridmeta["NROWS"]
        self.nlay = self.gridmeta["NLAYS"]
        self.spcs = self.gridmeta["VAR-LIST"].split()
        tsec = tosec(self.gridmeta["TSTEP"])
        assert daysec % tsec == 0, f"invalid TSTEP in {METCRO3D}"
        self.nstep = (daysec // tsec) + 1
        self.max_height = layer_height[self.nlay]

        # construct grid for ray-tracing
        xoffset = self.gridmeta["XORIG"]
        yoffset = self.gridmeta["YORIG"]
        zoffset = 0.0
        xspace = self.gridmeta["XCELL"] * np.ones(self.ncol)
        yspace = self.gridmeta["YCELL"] * np.ones(self.nrow)
        zspace = np.diff(layer_height[: self.nlay + 1])
        offset = (xoffset, yoffset, zoffset)
        spacing = (xspace, yspace, zspace)
        self.grid = Grid(offset, spacing)

        # construct projection for lat-lon conversion
        # assumes/forces use of LCC projection
        assert self.gridmeta["GDTYP"] == 2, "Invalid GDTYP"
        alp = float(self.gridmeta["P_ALP"])
        bet = float(self.gridmeta["P_BET"])
        gam = float(self.gridmeta["P_GAM"])
        ycent = float(self.gridmeta["YCENT"])
        # TODO: Verify that is what WRF thinks that the proj string is
        proj_str = "+proj=lcc +lat_1={0} +lat_2={1} +lat_0={3} +lon_0={2} +a={4} +b={4}"
        self.proj = pyproj.Proj(proj_str.format(alp, bet, gam, ycent, earth_rad))
        # first generate edges
        xEdge = (
            self.gridmeta["XCELL"] * np.arange(self.ncol + 1)
            + xoffset
            - 0.5 * self.gridmeta["XCELL"]
        )
        yEdge = (
            self.gridmeta["YCELL"] * np.arange(self.nrow + 1)
            + yoffset
            - 0.5 * self.gridmeta["YCELL"]
        )
        # stack them to make 2d grids
        xCorners = np.repeat(xEdge[np.newaxis, :], self.nrow + 1, axis=0)
        yCorners = np.repeat(yEdge[:, np.newaxis], self.ncol + 1, axis=1)
        lonCorners, latCorners = self.proj(xCorners, yCorners, inverse=True)
        self.lat_bounds = (latCorners.min(), latCorners.max())
        self.lon_bounds = (lonCorners.min(), lonCorners.max())

    def valid_coord(self, coord):
        """Return True if a coord is within the grid."""
        date, step, lay, row, col, spc = coord
        if not (self.sdate <= date <= self.edate):
            return False
        # fourdvar doesn't allow obs at t0 (move to previous day instead)
        if not (1 <= step < self.nstep):
            return False
        if not (0 <= lay < self.nlay):
            return False
        if not (0 <= row < self.nrow):
            return False
        if not (0 <= col < self.ncol):
            return False
        if spc is not None:
            if spc not in self.spcs:
                return False
        return True

    def get_step(self, cdate, ctime):
        # convert ctime (HHMMSS) into timestep index
        stime = self.gridmeta["STIME"]
        tstep = self.gridmeta["TSTEP"]
        step = (tosec(ctime) - tosec(stime)) // tosec(tstep)
        if step <= 0:
            # move step to previous day
            cdate = int(
                (dt.datetime.strptime(str(cdate), "%Y%m%d") - dt.timedelta(days=1)).strftime(
                    "%Y%m%d"
                )
            )
            step = (daysec // tosec(tstep)) - step
        return (cdate, step)

    def get_step_pos(self, ctime):
        # return ctime's position with its step (.0=start, .5=halfway, etc)
        stime = self.gridmeta["STIME"]
        tstep = self.gridmeta["TSTEP"]
        return (float(tosec(ctime) - tosec(stime)) / tosec(tstep)) % 1

    def next_step(self, cdate, cstep):
        assert 0 <= cstep < self.nstep, "invalid step"
        cstep = cstep + 1
        if cstep == self.nstep:
            cstep = 1
            cdate = int(
                (dt.datetime.strptime(str(cdate), "%Y%m%d") + dt.timedelta(days=1)).strftime(
                    "%Y%m%d"
                )
            )
        return (cdate, cstep)

    def update_psurf(self, date_int):
        # replace the psurf array with the new file
        new_date = dt.datetime.strptime(str(date_int), "%Y%m%d")
        new_file = date_handle.replace_date(self.psurf_file, new_date)
        with Dataset(new_file, "r") as f:
            self.psurf_arr = f.variables["PRSFC"][:, 0, :, :]
        self.psurf_date = date_int

    def get_pressure_bounds(self, target_coord):
        date = target_coord[0]
        time = target_coord[1]
        row = target_coord[3]
        col = target_coord[4]
        if date != self.psurf_date:
            self.update_psurf(date)
        vgbot = self.psurf_arr[time, row, col]
        vglvl = np.array(self.gridmeta["VGLVLS"])
        vgtop = float(self.gridmeta["VGTOP"])
        return vglvl[:] * (vgbot - vgtop) + vgtop

    def get_pressure_weight(self, target_coord):
        pbound = self.get_pressure_bounds(target_coord)
        # calculate pressure weight per layer
        pdiff = pbound[:-1] - pbound[1:]
        pweight = pdiff / (pbound[0] - pbound[-1])
        return pweight

    def pressure_interp(self, obs_pressure, obs_value, target_coord):
        obs_pressure = np.array(obs_pressure)
        obs_value = np.array(obs_value)
        if np.all(np.diff(obs_pressure) > 0.0):
            pass
        elif np.all(np.diff(obs_pressure) < 0.0):
            obs_pressure = obs_pressure[::-1]
            obs_value = obs_value[::-1]
        else:
            raise ValueError("obs pressure levels not in sorted order!")
        cmaq_pbound = self.get_pressure_bounds(target_coord)
        # interpolate from low pressure to high then flip back afterwards
        cmaq_plvl = 0.5 * (cmaq_pbound[:-1] + cmaq_pbound[1:])[::-1]
        assert np.all(np.diff(cmaq_plvl) > 0.0)
        cmaq_val = np.zeros(cmaq_plvl.size)
        for cmaq_i, p in enumerate(cmaq_plvl):
            if p <= obs_pressure[0]:
                cmaq_val[cmaq_i] = obs_value[0]
            elif p >= obs_pressure[-1]:
                cmaq_val[cmaq_i] = obs_value[-1]
            else:
                i = np.searchsorted(obs_pressure, p)
                obs_p_low = obs_pressure[i - 1]
                obs_p_high = obs_pressure[i]
                obs_v_low = obs_value[i - 1]
                obs_v_high = obs_value[i]
                pos = (p - obs_p_low) / (obs_p_high - obs_p_low)
                cmaq_val[cmaq_i] = obs_v_low + pos * (obs_v_high - obs_v_low)
        # flip cmaq_val back so values are surface-to-top
        return cmaq_val[::-1]

    def get_xy(self, lat, lon):
        return self.proj(lon, lat)

    def get_ray_top(self, start, zenith, azimuth):
        """Get the (x,y,z) point where a ray leaves the top of the model
        start = (x,y,z) start point
        zenith = zenith angle (radians)
        azimuth = azimuth angle (angle east of north) (radians).

        notes: function does not care about the horizontal domain of the model
        """
        assert 0 <= zenith < (0.5 * np.pi), "invalid zenith angle (must be radians)"
        assert 0 <= azimuth <= (2 * np.pi), "invalid azimuth angle (must be radians)"
        x0, y0, z0 = start
        assert 0 <= z0 < self.max_height, "invalid vertical start coordinate"
        v_dist = self.max_height - z0
        h_dist = v_dist * np.tan(zenith)
        xd = h_dist * np.sin(azimuth)
        yd = h_dist * np.cos(azimuth)
        top_point = (x0 + xd, y0 + yd, self.max_height)
        return top_point

    def get_domain(self):
        domain = deepcopy(self.gridmeta)
        domain["SDATE"] = self.sdate
        domain["EDATE"] = self.edate
        domain["openmethane_version"] = os.getenv("OPENMETHANE_VERSION")
        return domain
