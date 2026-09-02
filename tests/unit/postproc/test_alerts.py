import numpy as np
import pytest

from openmethane.postproc.alerts import map_enhance

NEAR_THRESHOLD = 0.2
FAR_THRESHOLD = 1.0


def reference_map_enhance(lat, lon, land_mask, concs, near_threshold, far_threshold): # noqa: PLR0913
    """
    Straightforward implementation of map_enhance: scan every observation once
    per land cell. Too slow for a real domain, but unambiguous, so the
    vectorised implementation is pinned against it.
    """
    n_concs = concs.shape[1] - 2
    near_field = np.full((n_concs, *land_mask.shape), np.nan)
    far_field = np.full((n_concs, *land_mask.shape), np.nan)

    for i in range(land_mask.shape[0]):
        for j in range(land_mask.shape[1]):
            if land_mask[i, j] < 0.5:
                continue
            diff = concs[:, 0:2] - np.array((lat[i, j], lon[i, j]))
            dist = (diff[:, 0] ** 2 + diff[:, 1] ** 2) ** 0.5
            near = dist < near_threshold
            far = (dist > near_threshold) & (dist < far_threshold)
            if near.sum() == 0 or far.sum() == 0:
                continue
            near_field[:, i, j] = concs[near, 2:].mean(axis=0)
            far_field[:, i, j] = concs[far, 2:].mean(axis=0)

    return near_field, far_field


def make_domain(n_rows=24, n_cols=28, seed=0):
    rng = np.random.default_rng(seed)
    lat = (np.linspace(-40, -12, n_rows)[:, None] * np.ones((1, n_cols))).astype("float32")
    lon = (np.linspace(115, 152, n_cols)[None, :] * np.ones((n_rows, 1))).astype("float32")
    # a mix of land and ocean, so masked cells are exercised
    land_mask = (rng.random((n_rows, n_cols)) < 0.6).astype("int64")
    return lat, lon, land_mask


def make_concs(lat, lon, n_obs, seed=1, n_records=2):
    rng = np.random.default_rng(seed)
    columns = [
        rng.uniform(lat.min(), lat.max(), n_obs),
        rng.uniform(lon.min(), lon.max(), n_obs),
    ]
    columns += [rng.normal(1900, 20, n_obs) for _ in range(n_records)]
    return np.column_stack(columns)


@pytest.mark.parametrize("n_obs", [50, 500])
@pytest.mark.parametrize("chunk_size", [7, 4096])
def test_map_enhance_matches_reference(n_obs, chunk_size):
    lat, lon, land_mask = make_domain()
    concs = make_concs(lat, lon, n_obs)

    near, far = map_enhance(
        lat, lon, land_mask, concs, NEAR_THRESHOLD, FAR_THRESHOLD, chunk_size=chunk_size
    )
    expected_near, expected_far = reference_map_enhance(
        lat, lon, land_mask, concs, NEAR_THRESHOLD, FAR_THRESHOLD
    )

    np.testing.assert_allclose(near, expected_near, rtol=1e-12, equal_nan=True)
    np.testing.assert_allclose(far, expected_far, rtol=1e-12, equal_nan=True)


def test_map_enhance_handles_observation_on_a_cell_centre():
    """A zero distance still has to be counted in the near field."""
    lat, lon, land_mask = make_domain()
    land_mask[...] = 1
    concs = make_concs(lat, lon, 200, seed=2)
    # move some observations exactly onto cell centres
    for n, (i, j) in enumerate([(0, 0), (5, 9), (11, 3)]):
        concs[n, 0] = lat[i, j]
        concs[n, 1] = lon[i, j]

    near, far = map_enhance(lat, lon, land_mask, concs, NEAR_THRESHOLD, FAR_THRESHOLD)
    expected_near, expected_far = reference_map_enhance(
        lat, lon, land_mask, concs, NEAR_THRESHOLD, FAR_THRESHOLD
    )

    np.testing.assert_allclose(near, expected_near, rtol=1e-12, equal_nan=True)
    np.testing.assert_allclose(far, expected_far, rtol=1e-12, equal_nan=True)


def test_map_enhance_is_all_nan_without_observations():
    lat, lon, land_mask = make_domain()
    concs = np.empty((0, 4))

    near, far = map_enhance(lat, lon, land_mask, concs, NEAR_THRESHOLD, FAR_THRESHOLD)

    assert near.shape == (2, *land_mask.shape)
    assert np.isnan(near).all()
    assert np.isnan(far).all()


def test_map_enhance_leaves_ocean_cells_undefined():
    lat, lon, land_mask = make_domain()
    concs = make_concs(lat, lon, 500, seed=3)

    near, far = map_enhance(lat, lon, land_mask, concs, NEAR_THRESHOLD, FAR_THRESHOLD)

    ocean = land_mask < 0.5
    assert np.isnan(near[:, ocean]).all()
    assert np.isnan(far[:, ocean]).all()


def test_map_enhance_masks_near_and_far_fields_consistently():
    """
    create_alerts_baseline rejects inconsistent masking between the two fields,
    so a cell must either have both fields or neither.
    """
    lat, lon, land_mask = make_domain()
    concs = make_concs(lat, lon, 120, seed=4)

    near, far = map_enhance(lat, lon, land_mask, concs, NEAR_THRESHOLD, FAR_THRESHOLD)

    assert (np.isnan(near) == np.isnan(far)).all()
