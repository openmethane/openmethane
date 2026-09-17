"""`sounding_geometry` against the angles TropOMI itself reports.

The observation files an archived run leaves behind keep each sounding's
timestamp and corner coordinates but drop the solar and viewing zenith angles
the retrieval reported, so both are reconstructed from what is left. These
check the reconstructions against a granule that still carries the reported
angles, and pin down how accurate they are.
"""

import datetime as dt

import numpy as np
import pytest
from netCDF4 import Dataset

from analysis.sounding_geometry import footprint, solar_zenith, viewing_zenith

GRANULE = (
    "tropomi/2022-12-07T0000_2022-12-07T2359_104.0_-47.0_162.0_-6.0/"
    "S5P_OFFL_L2__CH4____20221207T025418_20221207T043548_26683_03_020400_20221213T140313.SUB.nc4"
)


@pytest.fixture
def reported(test_data_dir):
    """Every valid sounding of the granule, sampled across the full swath."""
    with Dataset(test_data_dir / GRANULE) as ds:
        product = ds["/PRODUCT"]
        geolocation = ds["/PRODUCT/SUPPORT_DATA/GEOLOCATIONS"]
        latitude = product["latitude"][:].squeeze()
        longitude = product["longitude"][:].squeeze()
        stamps = product["time_utc"][:].squeeze()
        fields = {
            name: geolocation[name][:].squeeze()
            for name in (
                "solar_zenith_angle",
                "viewing_zenith_angle",
                "latitude_bounds",
                "longitude_bounds",
            )
        }

    rows = range(0, latitude.shape[0], 7)
    columns = range(0, latitude.shape[1], 3)
    sampled = []
    for i in rows:
        when = dt.datetime.strptime(str(stamps[i])[0:19], "%Y-%m-%dT%H:%M:%S")
        for j in columns:
            if np.ma.is_masked(latitude[i, j]):
                continue
            across, along = footprint(
                fields["latitude_bounds"][i, j],
                fields["longitude_bounds"][i, j],
                float(latitude[i, j]),
                float(longitude[i, j]),
            )
            sampled.append(
                (
                    solar_zenith(when, float(latitude[i, j]), float(longitude[i, j])),
                    float(fields["solar_zenith_angle"][i, j]),
                    float(viewing_zenith(across)),
                    float(fields["viewing_zenith_angle"][i, j]),
                    along,
                )
            )
    assert len(sampled) > 5000
    return np.array(sampled)


def test_solar_zenith_matches_the_granule(reported):
    """The sun's position follows from the timestamp and the pixel centre alone."""
    error = reported[:, 0] - reported[:, 1]
    assert abs(error.mean()) < 0.2
    assert np.abs(error).max() < 0.5


def test_viewing_zenith_spans_the_swath(reported):
    """The footprint has to resolve nadir from swath edge to be worth anything."""
    assert reported[:, 3].min() < 5
    assert reported[:, 3].max() > 60
    assert np.corrcoef(reported[:, 2], reported[:, 3])[0, 1] > 0.99


def test_viewing_air_mass_is_unbiased(reported):
    """sec(vza) is what enters the air mass factor, so it is what has to be right.

    The angle itself is reconstructed poorly near nadir, where a wider pixel
    barely moves it; that region is also where sec(vza) is flat at 1, so it does
    not matter to the quantity being used.
    """
    error = 1 / np.cos(np.radians(reported[:, 2])) - 1 / np.cos(np.radians(reported[:, 3]))
    assert abs(error.mean()) < 0.005
    assert error.std() < 0.03


def test_along_track_edge_is_the_fixed_one(reported):
    """TropOMI's along-track size is set by integration time, not by the optics.

    Its constancy is what licenses taking the longer edge as the across-track
    one, so a change that broke the pairing would show up here.
    """
    along = reported[:, 4]
    assert 5.0 < along.mean() < 6.0
    assert along.std() / along.mean() < 0.02
