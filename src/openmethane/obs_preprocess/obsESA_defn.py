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

from openmethane.obs_preprocess.column_operator import (
    FILL_PRIOR_OFFSET,
    build_column_operator,
)
from openmethane.obs_preprocess.obs_defn import ObsMultiRay
from openmethane.obs_preprocess.ray_trace import Point, Ray

# mol mol-1 to ppb, for the retrieval prior
ppb_scale = 1e9


class ObsSRON(ObsMultiRay):
    """Single observation of CH4 from TROPOMI instrument, processed by ESA.

    This observation class only works for 1 species.
    """

    required = ("value", "uncertainty", "weight_grid", "offset_term")

    @classmethod
    def create(cls, **kwargs):
        """Kwargs comes from variables in S5P file.

        min. requirements for kwargs:
        - time : datetime-obj (datetime)
        - latitude_center : float (degrees)
        - longitude_center : float (degrees)
        - latitude_corners : array[ float ] (length=4, units=degrees)
        - longitude_corners : array[ float ] (length=4, units=degrees)
        - solar_zenith_angle : float (degrees)
        - viewing_zenith_angle : float (degrees)
        - solar_azimuth_angle : float (degrees)
        - viewing_azimuth_angle : float (degrees)
        - pressure_levels : array[ float ] (length=levels, units=Pa, top of
          atmosphere first)
        - ch4_column : float (ppb)
        - ch4_column_precision : float (ppb)
        - ch4_profile_apriori : array[ float ] (length=layers, units=mol m-2)
        - dry_air_subcolumns : array[ float ] (length=layers, units=mol m-2)
        - obs_kernel : array[ float ] (length=layers, unitless)
        - qa_value : float (unitless)
        - surface_albedo_SWIR : float (unitless).
        """
        newobs = cls(obstype="ESA_co_obs")

        newobs.out_dict["value"] = kwargs["ch4_column"]
        newobs.out_dict["uncertainty"] = kwargs["ch4_column_precision"]
        newobs.out_dict["time"] = kwargs["time"]
        newobs.out_dict["qa_value"] = kwargs["qa_value"]
        newobs.out_dict["surface_albedo_SWIR"] = kwargs["surface_albedo_SWIR"]
        newobs.out_dict["aerosol_aod_SWIR"] = kwargs["aerosol_aod_SWIR"]
        newobs.out_dict["latitude_corners"] = kwargs["latitude_corners"]
        newobs.out_dict["longitude_corners"] = kwargs["longitude_corners"]
        newobs.out_dict["latitude_center"] = kwargs["latitude_center"]
        newobs.out_dict["longitude_center"] = kwargs["longitude_center"]
        newobs.spcs = "CH4"
        newobs.src_data = kwargs.copy()
        return newobs

    def prior_profile(self):
        """The retrieval a-priori profile as a dry-air mole fraction in ppb.

        Uses the retrieval's own dry air subcolumns, so no assumption about the
        water vapour content of the column is needed.
        """
        prior_mole = np.asarray(self.src_data["ch4_profile_apriori"], dtype=float)
        dry_air = np.asarray(self.src_data["dry_air_subcolumns"], dtype=float)
        return ppb_scale * prior_mole / dry_air

    def model_process(self, model_space):
        ObsMultiRay.model_process(self, model_space)
        # set lite_coord to surface cell containing lat/lon center
        if "weight_grid" in list(self.out_dict.keys()):
            day, time, _, _, _, spc = next(iter(self.out_dict["weight_grid"].keys()))
            x, y = model_space.get_xy(
                self.src_data["latitude_center"], self.src_data["longitude_center"]
            )
            col, row, lay = model_space.grid.get_cell(Point((x, y, 0)))
            self.out_dict["lite_coord"] = (
                day,
                time,
                lay,
                row,
                col,
                spc,
            )
            self.ready = True

    def add_visibility(self, proportion, model_space):
        """Apply the column averaging kernel to the light-path weights.

        `proportion` gives the fraction of the observation's light path that
        falls in each model cell, normalised so that the whole path sums to one.
        This method replaces those proportions with the weights of the column
        operator, so that the simulated observation is

            sum(weight_grid values * concentration) + offset_term

        See `openmethane.obs_preprocess.column_operator` for the operator
        itself. The averaging kernel, the pressure weights and the a-priori
        profile all belong to the retrieval, so the model is mapped onto the
        retrieval's vertical grid rather than the other way around.
        """
        # a sample model coordinate at the surface, used to locate the column of
        # CMAQ layer pressures this sounding is compared against
        coord = next(c for c in proportion if c[2] == 0)
        model_edge = model_space.get_pressure_bounds(coord)

        prior = self.prior_profile()
        operator = build_column_operator(
            sat_edge=self.src_data["pressure_levels"],
            avker=self.src_data["obs_kernel"],
            prior=prior,
            model_edge=model_edge,
            fill=FILL_PRIOR_OFFSET,
        )

        # this is the parameter that is used for the next process
        model_unc = 20.0  # arbitrary constant unc in ppb
        self.out_dict["uncertainty"] = model_unc

        self.out_dict["offset_term"] = operator.offset
        self.out_dict["obs_kernel"] = np.asarray(self.src_data["obs_kernel"])
        self.out_dict["prior_profile"] = prior
        self.out_dict["sat_pressure_weight"] = operator.pressure_weight
        self.out_dict["model_coverage"] = operator.coverage
        self.out_dict["model_vis"] = operator.weights

        # spread each layer's weight over the cells the light path crosses in
        # that layer, keeping the layer total equal to the operator weight
        weight_grid = {}
        for lay, weight in enumerate(operator.weights):
            layer_slice = {c: v for c, v in proportion.items() if c[2] == lay}
            layer_sum = sum(layer_slice.values())
            if layer_sum == 0.0:
                # the light path misses this layer entirely; nothing to spread
                weight_grid.update(dict.fromkeys(layer_slice, 0.0))
                continue
            weight_slice = {c: weight * v / layer_sum for c, v in layer_slice.items()}
            weight_grid.update(weight_slice)

        self.out_dict["weight_grid"] = weight_grid

        return weight_grid

    def map_location(self, model_space):
        assert model_space.gridmeta["GDTYP"] == 2, "invalid GDTYP"
        # convert source location data into a list of spacial points
        lat_list = self.src_data["latitude_corners"]
        lon_list = self.src_data["longitude_corners"]
        p0_zenith = np.radians(self.src_data["solar_zenith_angle"])
        p0_azimuth = np.radians(self.src_data["solar_azimuth_angle"])
        if p0_azimuth < 0.0:
            p0_azimuth += 2 * np.pi
        p2_zenith = np.radians(self.src_data["viewing_zenith_angle"])
        p2_azimuth = np.radians(self.src_data["viewing_azimuth_angle"])
        if p2_azimuth < 0.0:
            p2_azimuth += 2 * np.pi

        rays_in = []
        rays_out = []
        ###pdb.set_trace()
        for lat, lon in zip(lat_list, lon_list):
            x1, y1 = model_space.get_xy(lat, lon)
            p1 = (
                x1,
                y1,
                0,
            )
            p0 = model_space.get_ray_top(p1, p0_zenith, p0_azimuth)
            p2 = model_space.get_ray_top(p1, p2_zenith, p2_azimuth)
            rays_in.append(Ray(p1, p0))
            rays_out.append(Ray(p1, p2))

        try:
            in_dict = model_space.grid.get_beam_intersection_volume(rays_in)
            out_dict = model_space.grid.get_beam_intersection_volume(rays_out)
        except AssertionError:
            self.coord_fail("outside grid area")
            return None

        area_dict = in_dict.copy()
        for coord, val in list(out_dict.items()):
            area_dict[coord] = area_dict.get(coord, 0) + val
        tarea = sum(area_dict.values())

        # convert x-y-z into lay-row-col and scale values so they sum to 1
        result = {
            (lay, row, col): val / tarea
            for [
                (
                    col,
                    row,
                    lay,
                ),
                val,
            ] in list(area_dict.items())
            if val > 0.0
        }
        return result

    def map_time(self, model_space):
        # convert source time into [ int(YYYYMMDD), int(HHMMSS) ]
        fulltime = self.src_data["time"]
        day = int(fulltime.strftime("%Y%m%d"))
        time = int(fulltime.strftime("%H%M%S"))
        self.time = [day, time]
        # use generalized function
        return ObsMultiRay.map_time(self, model_space)
