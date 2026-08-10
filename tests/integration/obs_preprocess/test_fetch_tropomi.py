import datetime as dt
import os

import pytest
from click.testing import CliRunner
from scripts.obs_preprocess import fetch_tropomi

AUST_BOX = [104.0, -47.0, 162.0, -6.0]

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
            "2022-07-01T0000_2022-07-02T0000_148.0_-23.5_150.0_-22.0",
            "S5P_RPRO_L2__CH4____20220701T024730_20220701T042859_24427_03_020400"
            "_20230131T104028.nc4",
        ),
        id="reprocessed",
    ),
    pytest.param(
        (
            "2022-12-07",
            "2022-12-08",
            "2022-12-07T0000_2022-12-08T0000_148.0_-23.5_150.0_-22.0",
            "S5P_OFFL_L2__CH4____20221207T025418_20221207T043548_26683_03_020400"
            "_20221213T140313.nc4",
        ),
        id="offline",
    ),
]


# These hit the CDSE catalogue and the S3 bucket
@pytest.mark.parametrize("case", FETCH_CASES)
def test_fetch(tmpdir, root_dir, case):
    start, end, output_dir, expected_granule = case

    runner = CliRunner()
    result = runner.invoke(
        fetch_tropomi.fetch_data,
        [
            "-c",
            str(root_dir / "config" / "obs_preprocess" / "config.austtest.json"),
            "-s",
            f"{start}T00:00:00",
            "-e",
            f"{end}T00:00:00",
            str(tmpdir),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Data fetched successfully!" in result.output

    # Check that the expected files are created
    assert os.listdir(tmpdir) == [output_dir]
    assert os.listdir(tmpdir / output_dir) == [expected_granule]


# This hits the CDSE catalogue with a period outside the archive
def test_fetch_no_granules(tmpdir, root_dir):
    runner = CliRunner()
    result = runner.invoke(
        fetch_tropomi.fetch_data,
        [
            "-c",
            str(root_dir / "config" / "obs_preprocess" / "config.austtest.json"),
            "-s",
            "1900-07-01",
            "-e",
            "1900-07-02",
            str(tmpdir),
        ],
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
