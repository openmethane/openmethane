import datetime as dt
import os

import pytest
import xarray as xr
from click.testing import CliRunner
from scripts.obs_preprocess import fetch_tropomi

from openmethane.util.domain import domain_bounding_box

AUST_BOX = [104.963, -47.056, 161.641, -6.621]

# One orbit crosses the au-test domain on each of these dates. The catalogue
# filters on the swath footprint, so only that orbit is returned and downloaded.
#
# The two dates sit either side of the July 2022 handover, where ESA's full
# mission reprocessing stops and the offline products take over, so between them
# they cover both products the catalogue can serve.
FETCH_CASES = [
    pytest.param(
        (
            "2022-07-01",
            "2022-07-02",
            "S5P_RPRO_L2__CH4____20220701T024730_20220701T042859_24427_03_020400"
            "_20230131T104028.nc",
        ),
        id="reprocessed",
    ),
    pytest.param(
        (
            "2022-12-07",
            "2022-12-08",
            "S5P_OFFL_L2__CH4____20221207T025418_20221207T043548_26683_03_020400"
            "_20221213T140313.nc",
        ),
        id="offline",
    ),
]


@pytest.fixture
def au_test_domain(root_dir, monkeypatch):
    """Point DOMAIN_FILE at the au-test domain, as the docker-test target does"""
    domain_file = root_dir / "data" / "domains" / "au-test" / "v1" / "domain.au-test.nc"
    if not domain_file.exists():
        pytest.skip(f"{domain_file} is missing; run `make fetch-test-data`")

    monkeypatch.setenv("DOMAIN_FILE", str(domain_file))

    return domain_file


def test_domain_bounding_box_covers_the_real_domain(au_test_domain):
    """
    The box has to cover the whole domain, not just its cell centres

    tropomi_methane_preprocess.py accepts observations out to the outermost cell
    corners, so a box drawn through the centres would exclude granules that only
    clip the edge of the domain.
    """
    with xr.open_dataset(au_test_domain) as ds:
        latitude = ds["lat"].to_numpy()
        longitude = ds["lon"].to_numpy()

    lon_min, lat_min, lon_max, lat_max = domain_bounding_box(
        au_test_domain, fetch_tropomi.CATALOGUE_CRS
    )

    assert lon_min < longitude.min()
    assert lat_min < latitude.min()
    assert lon_max > longitude.max()
    assert lat_max > latitude.max()


# These hit the CDSE catalogue and the S3 bucket
@pytest.mark.parametrize("case", FETCH_CASES)
def test_fetch(tmpdir, au_test_domain, case):
    start, end, expected_granule = case

    runner = CliRunner()
    result = runner.invoke(
        fetch_tropomi.fetch_data,
        ["-s", f"{start}T00:00:00", "-e", f"{end}T00:00:00", str(tmpdir)],
    )

    assert result.exit_code == 0, result.output
    assert "Data fetched successfully!" in result.output

    # Granules keep their name from the bucket, directly in the output directory
    assert os.listdir(tmpdir) == [expected_granule]


# This hits the CDSE catalogue and the S3 bucket
def test_fetch_skips_granules_already_present(tmpdir, au_test_domain):
    """A granule already downloaded is left alone, so a rerun costs nothing"""
    start, end, expected_granule = FETCH_CASES[1].values[0]
    arguments = ["-s", f"{start}T00:00:00", "-e", f"{end}T00:00:00", str(tmpdir)]

    runner = CliRunner()
    assert runner.invoke(fetch_tropomi.fetch_data, arguments).exit_code == 0

    downloaded = tmpdir / expected_granule
    before = (downloaded.stat().size, downloaded.stat().mtime)

    result = runner.invoke(fetch_tropomi.fetch_data, arguments)

    assert result.exit_code == 0, result.output
    assert "already present, skipping" in result.output
    assert (downloaded.stat().size, downloaded.stat().mtime) == before


# This hits the CDSE catalogue with a period outside the archive
def test_fetch_no_granules(tmpdir, au_test_domain):
    runner = CliRunner()
    result = runner.invoke(
        fetch_tropomi.fetch_data,
        ["-s", "1900-07-01", "-e", "1900-07-02", str(tmpdir)],
    )

    assert result.exit_code == 1, result.output
    assert "No granules found" in result.output


# These hit the CDSE catalogue
@pytest.mark.parametrize(
    "start",
    [
        # Only reprocessed products exist
        dt.datetime(2018, 7, 1),
        # Reprocessed products, where the bucket itself holds duplicate orbits
        dt.datetime(2019, 6, 15),
        # Offline products
        dt.datetime(2024, 6, 15),
        # Offline products, with near real time products also published
        dt.datetime(2026, 8, 1),
    ],
)
def test_search_returns_one_product_per_orbit(start):
    """
    The catalogue must not return two products covering the same orbit

    Each product covers a whole orbit, so two products for one orbit would put
    the same observations into the inversion twice. Near real time products are
    the likeliest source, since they cover the same orbits as the offline ones in
    much shorter granules.
    """
    keys = fetch_tropomi.search_granules(
        fetch_tropomi.create_session(), start, start + dt.timedelta(days=1), AUST_BOX
    )

    assert keys

    orbits = [fetch_tropomi.granule_orbit(os.path.basename(key)) for key in keys]
    assert len(orbits) == len(set(orbits))

    # NRTI granules would resolve to their own prefix
    assert all(key.startswith(("OFFL/", "RPRO/")) for key in keys)


@pytest.mark.parametrize("env_var", ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"])
def test_fetch_ignores_aws_credentials(monkeypatch, env_var):
    """The bucket is public, so requests must be unsigned even if keys are set"""
    monkeypatch.setenv(env_var, "not-a-real-credential")

    client = fetch_tropomi.create_client()

    assert client.meta.config.signature_version is fetch_tropomi.UNSIGNED
