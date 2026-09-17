"""The observation geometry that the observation files do not keep.

`obsESA_defn.py` uses each sounding's solar and viewing angles to trace rays
through the model grid and then discards them, so an archived run's
`observed.pickle` records the pixel's timestamp, centre and corners but none of
the angles the retrieval reported. Anything that needs to know how obliquely a
sounding was lit or viewed has to work them out again, which these functions do
from what the records do keep.

- `solar_zenith(when, lat, lon)` -- the sun's position follows from the
  timestamp and the pixel centre, and comes back within 0.15 degrees of the
  reported angle.
- `footprint(lat_corners, lon_corners, lat, lon)` -- the ground pixel's two edge
  lengths, across-track first.
- `viewing_zenith(across_km)` -- inverts the across-track width back into the
  viewing zenith angle. The angle itself is poor near nadir, where a wider pixel
  barely moves it, but `sec(vza)` -- which is what enters an air mass factor,
  and which is flat at 1 in exactly that region -- comes back unbiased to a
  thousandth with a scatter of 0.014 against a mean of 1.32.

Accuracies are measured in `tests/unit/analysis/test_sounding_geometry.py`,
against a granule that still carries the reported angles.
"""

import math

import numpy as np

EARTH_RADIUS_KM = 6371.0
ORBIT_HEIGHT_KM = 824.0  # Sentinel-5P

# The nadir across-track ground pixel, in the units `footprint` measures in.
# TropOMI's is documented as 7 km; 7.4 is what makes `viewing_zenith` reproduce
# the angles the granules report, absorbing the small error in measuring a
# corner polygon on a flat-Earth approximation.
NADIR_ACROSS_KM = 7.4


def solar_zenith(when, lat, lon):
    """Solar zenith angle in degrees, by NOAA's low-precision formulae.

    Good to a hundredth of a degree in its own terms, which is far finer than
    the quarter-degree spread that reconstructing rather than reading the angle
    costs.
    """
    fraction = when.hour + when.minute / 60 + when.second / 3600
    gamma = 2 * math.pi / 365.0 * (when.timetuple().tm_yday - 1 + (fraction - 12) / 24)
    equation_of_time = 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2 * gamma)
        - 0.040849 * math.sin(2 * gamma)
    )
    declination = (
        0.006918
        - 0.399912 * math.cos(gamma)
        + 0.070257 * math.sin(gamma)
        - 0.006758 * math.cos(2 * gamma)
        + 0.000907 * math.sin(2 * gamma)
        - 0.002697 * math.cos(3 * gamma)
        + 0.00148 * math.sin(3 * gamma)
    )
    true_solar = fraction * 60 + equation_of_time + 4 * lon
    hour_angle = math.radians(true_solar / 4 - 180)
    radians = math.radians(lat)
    cosine = math.sin(radians) * math.sin(declination) + math.cos(radians) * math.cos(
        declination
    ) * math.cos(hour_angle)
    return math.degrees(math.acos(min(1.0, max(-1.0, cosine))))


def footprint(lat_corners, lon_corners, lat, lon):
    """The ground pixel's two edge lengths in km, across-track first.

    TropOMI's along-track edge is fixed by the integration time at 5.5 km; the
    across-track edge is set by the detector column's fixed angular width and so
    grows from about 7 km at nadir to several times that at the swath edge. The
    longer of the two is therefore the across-track one.

    Longitudes are unwrapped onto the pixel centre first, so that a pixel
    straddling the antimeridian does not come out hundreds of km wide.
    """
    longitudes = np.asarray(lon_corners, float)
    longitudes -= 360.0 * np.round((longitudes - lon) / 360.0)
    x = longitudes * (111.320 * math.cos(math.radians(lat)))
    y = np.asarray(lat_corners, float) * 110.574
    sides = np.hypot(np.roll(x, -1) - x, np.roll(y, -1) - y)
    pair_one, pair_two = (sides[0] + sides[2]) / 2, (sides[1] + sides[3]) / 2
    return max(pair_one, pair_two), min(pair_one, pair_two)


def viewing_zenith(across_km):
    """Viewing zenith angle in degrees, from how wide the ground pixel is.

    A pushbroom detector column subtends a fixed angle, so the strip of ground
    it covers is set by the slant range and by how obliquely the ray meets the
    surface -- both functions of the viewing zenith angle alone. Inverting that
    recovers the angle from the width.
    """
    angle = np.radians(np.linspace(1e-6, 72.0, 4000))
    scan = np.arcsin(np.sin(angle) * EARTH_RADIUS_KM / (EARTH_RADIUS_KM + ORBIT_HEIGHT_KM))
    slant = EARTH_RADIUS_KM * np.sin(angle - scan) / np.sin(scan)
    widening = (slant / ORBIT_HEIGHT_KM) / np.cos(angle)
    return np.interp(np.asarray(across_km) / NADIR_ACROSS_KM, widening, np.degrees(angle))
