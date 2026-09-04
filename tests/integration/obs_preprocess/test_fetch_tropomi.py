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


# This documents a real granule found empty in the mirror (reported to MEEO);
# if it ever starts passing without the CDSE fallback, the mirror has been
# fixed and this can be replaced with a mocked case instead.
EMPTY_IN_MIRROR_GRANULE = (
    "S5P_OFFL_L2__CH4____20240108T035030_20240108T053200_32316_03_020600_20240109T200605.nc"
)
EMPTY_IN_MIRROR_SIZE = 68_690_723  # the granule's real size, per the CDSE catalogue


def _has_cdse_credentials() -> bool:
    return bool(fetch_tropomi.env.str("CDSE_USERNAME", None))


# This hits the CDSE catalogue, the S3 bucket, and CDSE's own download API
@pytest.mark.skipif(not _has_cdse_credentials(), reason="CDSE_USERNAME/CDSE_PASSWORD not set")
def test_fetch_falls_back_to_cdse_for_a_granule_empty_in_the_mirror(tmpdir, au_test_domain):
    runner = CliRunner()
    result = runner.invoke(
        fetch_tropomi.fetch_data,
        ["-s", "2024-01-08T00:00:00", "-e", "2024-01-09T00:00:00", str(tmpdir)],
    )

    assert result.exit_code == 0, result.output
    assert "is an empty (0 byte) object" in result.output
    assert "Falling back to CDSE" in result.output

    downloaded = tmpdir / EMPTY_IN_MIRROR_GRANULE
    assert downloaded.size() == EMPTY_IN_MIRROR_SIZE


# This documents a real granule whose mirror object is not empty, but is still the
# wrong size (a partial sync from ESA, reported to MEEO); if it ever starts passing
# without the CDSE fallback, the mirror has been fixed and this can be replaced with
# a mocked case instead. It does not cross the au-test domain used by the other
# fetch_data tests, so it is exercised directly rather than through the CLI.
WRONG_SIZE_IN_MIRROR_GRANULE = (
    "S5P_OFFL_L2__CH4____20240117T060410_20240117T074540_32445_03_020600_20240118T222604.nc"
)
WRONG_SIZE_IN_MIRROR_KEY = fetch_tropomi.object_key(WRONG_SIZE_IN_MIRROR_GRANULE)
WRONG_SIZE_IN_MIRROR_SIZE = 69_528_923  # the granule's real size, per the CDSE catalogue


# This hits the S3 bucket
def test_download_from_mirror_raises_for_a_granule_the_wrong_size_in_the_mirror():
    client = fetch_tropomi.create_client()

    with pytest.raises(fetch_tropomi.UnreliableMirrorObject, match="in the meeo-s5p mirror but"):
        fetch_tropomi.download_from_mirror(
            client, WRONG_SIZE_IN_MIRROR_KEY, "unused.nc", WRONG_SIZE_IN_MIRROR_SIZE
        )


# This hits CDSE's own download API
@pytest.mark.skipif(not _has_cdse_credentials(), reason="CDSE_USERNAME/CDSE_PASSWORD not set")
def test_download_from_cdse_recovers_a_granule_the_wrong_size_in_the_mirror(tmp_path):
    session = fetch_tropomi.create_session()
    token = fetch_tropomi.cdse_access_token(session)
    outfn = tmp_path / "out.nc"

    fetch_tropomi.download_from_cdse(session, token, WRONG_SIZE_IN_MIRROR_KEY, str(outfn))

    assert outfn.stat().st_size == WRONG_SIZE_IN_MIRROR_SIZE


# This hits the CDSE catalogue and the S3 bucket
@pytest.mark.skip(reason="Target date data fixed in S3 mirror")
def test_fetch_reports_a_clear_error_when_cdse_has_no_credentials(
    tmpdir, au_test_domain, monkeypatch
):
    monkeypatch.delenv("CDSE_USERNAME", raising=False)
    monkeypatch.delenv("CDSE_PASSWORD", raising=False)

    runner = CliRunner()
    result = runner.invoke(
        fetch_tropomi.fetch_data,
        ["-s", "2024-01-08T00:00:00", "-e", "2024-01-09T00:00:00", str(tmpdir)],
    )

    assert result.exit_code == 1, result.output
    assert "CDSE_USERNAME" in result.output
    assert EMPTY_IN_MIRROR_GRANULE not in os.listdir(tmpdir)


# This hits the CDSE catalogue with a period outside the archive
def test_fetch_no_granules(tmpdir, au_test_domain):
    """A day with no granules (outage, or outside the archive) must not fail the run"""
    runner = CliRunner()
    result = runner.invoke(
        fetch_tropomi.fetch_data,
        ["-s", "1900-07-01", "-e", "1900-07-02", str(tmpdir)],
    )

    assert result.exit_code == 0, result.output
    assert "No granules found" in result.output
    assert os.listdir(tmpdir) == []


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
    granules = fetch_tropomi.search_granules(
        fetch_tropomi.create_session(), start, start + dt.timedelta(days=1), AUST_BOX
    )

    assert granules

    orbits = [fetch_tropomi.granule_orbit(os.path.basename(key)) for key, _ in granules]
    assert len(orbits) == len(set(orbits))

    # NRTI granules would resolve to their own prefix
    assert all(key.startswith(("OFFL/", "RPRO/")) for key, _ in granules)

    # Each granule's real size comes along with it, for comparison against the mirror
    assert all(size > 0 for _, size in granules)


@pytest.mark.parametrize("env_var", ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"])
def test_fetch_ignores_aws_credentials(monkeypatch, env_var):
    """The bucket is public, so requests must be unsigned even if keys are set"""
    monkeypatch.setenv(env_var, "not-a-real-credential")

    client = fetch_tropomi.create_client()

    assert client.meta.config.signature_version is fetch_tropomi.UNSIGNED
