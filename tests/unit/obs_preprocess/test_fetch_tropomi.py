import datetime as dt
from unittest import mock

import pytest
from click.testing import CliRunner
from scripts.obs_preprocess import fetch_tropomi

OFFL = "S5P_OFFL_L2__CH4____20221207T025418_20221207T043548_26683_03_020400_20221213T140313.nc"
RPRO = "S5P_RPRO_L2__CH4____20220701T024730_20220701T042859_24427_03_020400_20230131T104028.nc"


def test_granule_period():
    assert fetch_tropomi.granule_period(OFFL) == (
        dt.datetime(2022, 12, 7, 2, 54, 18),
        dt.datetime(2022, 12, 7, 4, 35, 48),
    )


def test_granule_period_unparseable():
    with pytest.raises(RuntimeError, match="Could not read a sensing period"):
        fetch_tropomi.granule_period("not-a-granule.nc")


def test_granule_orbit():
    assert fetch_tropomi.granule_orbit(OFFL) == "26683"
    assert fetch_tropomi.granule_orbit(RPRO) == "24427"


def test_object_key_offl():
    assert fetch_tropomi.object_key(OFFL) == f"OFFL/L2__CH4___/2022/12/07/{OFFL}"


def test_object_key_rpro():
    """The timeliness comes from the filename, so RPRO resolves to its own prefix"""
    assert fetch_tropomi.object_key(RPRO) == f"RPRO/L2__CH4___/2022/07/01/{RPRO}"


def test_select_one_per_orbit_keeps_distinct_orbits():
    assert fetch_tropomi.select_one_per_orbit([OFFL, RPRO]) == [OFFL, RPRO]


def test_select_one_per_orbit_prefers_the_later_processor_version(capsys):
    """Two products for one orbit would put the same observations in twice"""
    superseded = RPRO.replace("_03_020400_", "_02_020301_")

    assert fetch_tropomi.select_one_per_orbit([superseded, RPRO]) == [RPRO]
    assert "2 products for orbit 24427" in capsys.readouterr().out


def test_select_one_per_orbit_prefers_reprocessed_at_the_same_version():
    """An offline and a reprocessed product of one orbit resolve to the latter"""
    offline = RPRO.replace("_RPRO_", "_OFFL_")

    assert fetch_tropomi.select_one_per_orbit([offline, RPRO]) == [RPRO]
    assert fetch_tropomi.select_one_per_orbit([RPRO, offline]) == [RPRO]


def test_download_from_mirror_raises_on_empty_object(tmp_path):
    """A zero-byte object in the mirror is a known failure mode, not a transfer to retry"""
    client = mock.Mock()
    client.head_object.return_value = {"ContentLength": 0}

    with pytest.raises(fetch_tropomi.UnreliableMirrorObjectError, match="some/key.nc"):
        fetch_tropomi.download_from_mirror(client, "some/key.nc", str(tmp_path / "out.nc"))

    client.download_file.assert_not_called()


def test_download_from_mirror_raises_on_a_size_mismatch_with_the_catalogue(tmp_path):
    """A non-zero but wrong-sized object in the mirror is also a known failure mode"""
    client = mock.Mock()
    client.head_object.return_value = {"ContentLength": 4}

    with pytest.raises(fetch_tropomi.UnreliableMirrorObjectError, match="4 bytes.*40 bytes"):
        fetch_tropomi.download_from_mirror(
            client, "some/key.nc", str(tmp_path / "out.nc"), expected_size=40
        )

    client.download_file.assert_not_called()


def test_download_from_mirror_accepts_a_correctly_sized_download(tmp_path):
    outfn = tmp_path / "out.nc"
    client = mock.Mock()
    client.head_object.return_value = {"ContentLength": 4}
    client.download_file.side_effect = lambda bucket, key, path: open(path, "wb").write(b"data")

    fetch_tropomi.download_from_mirror(client, "some/key.nc", str(outfn), expected_size=4)

    assert outfn.read_bytes() == b"data"
    assert client.download_file.call_count == 1


def test_download_from_mirror_retries_a_short_download_once(tmp_path):
    """A download that lands short of the expected size is retried once before failing"""
    outfn = tmp_path / "out.nc"
    client = mock.Mock()
    client.head_object.return_value = {"ContentLength": 4}
    client.download_file.side_effect = lambda bucket, key, path: open(path, "wb").write(b"da")

    with pytest.raises(RuntimeError, match="did not download to its expected size"):
        fetch_tropomi.download_from_mirror(client, "some/key.nc", str(outfn))

    assert client.download_file.call_count == 2
    assert not outfn.exists()


def test_cdse_access_token_requires_credentials(monkeypatch):
    monkeypatch.delenv("CDSE_USERNAME", raising=False)
    monkeypatch.delenv("CDSE_PASSWORD", raising=False)

    with pytest.raises(fetch_tropomi.click.ClickException, match="CDSE_USERNAME"):
        fetch_tropomi.cdse_access_token(mock.Mock())


def test_cdse_access_token_posts_credentials_from_the_environment(monkeypatch):
    monkeypatch.setenv("CDSE_USERNAME", "someone@example.com")
    monkeypatch.setenv("CDSE_PASSWORD", "hunter2")

    session = mock.Mock()
    session.post.return_value.json.return_value = {"access_token": "a-token"}

    assert fetch_tropomi.cdse_access_token(session) == "a-token"

    _, kwargs = session.post.call_args
    assert kwargs["data"]["username"] == "someone@example.com"
    assert kwargs["data"]["password"] == "hunter2"  # noqa: S105 - a test fixture, not a real secret


def test_find_product_id_raises_when_not_found():
    session = mock.Mock()
    session.get.return_value.json.return_value = {"value": []}

    with pytest.raises(fetch_tropomi.click.ClickException, match="not found in the CDSE"):
        fetch_tropomi.find_product_id(session, "missing.nc")


def test_download_from_cdse_writes_the_response_body(tmp_path):
    outfn = tmp_path / "out.nc"

    session = mock.Mock()
    session.get.return_value.json.return_value = {"value": [{"Id": "some-id"}]}
    session.get.return_value.iter_content.return_value = [b"chunk-a", b"chunk-b"]

    fetch_tropomi.download_from_cdse(
        session, "a-token", "OFFL/L2__CH4___/2024/01/08/x.nc", str(outfn)
    )

    assert outfn.read_bytes() == b"chunk-achunk-b"
    assert not (tmp_path / "out.nc.part").exists()

    download_call = session.get.call_args_list[-1]
    assert download_call.kwargs["headers"] == {"Authorization": "Bearer a-token"}


# The orchestration in fetch_data - falling back to CDSE, caching the token,
# reporting what could not be recovered - is exercised here rather than against
# the real mirror. The failure modes it handles are rare, upstream data quality
# bugs that get fixed without notice, so pinning tests to a granule that happens
# to be broken today means the suite goes red when MEEO does the right thing.
# tests/integration/obs_preprocess/test_fetch_tropomi.py covers the happy paths
# against the real services.

GRANULE_BODY = b"granule-bytes"
GRANULE_SIZE = len(GRANULE_BODY)
OFFL_KEY = fetch_tropomi.object_key(OFFL)
RPRO_KEY = fetch_tropomi.object_key(RPRO)

# The period is only passed through to the catalogue, which is stubbed out, so
# any valid pair of dates will do.
FETCH_ARGS = ["-s", "2024-01-08T00:00:00", "-e", "2024-01-09T00:00:00"]


def _mirror_writes(body: bytes):
    """Stand in for download_from_mirror, writing body to outfn"""

    def download(client, key, outfn, expected_size=None):
        with open(outfn, "wb") as fh:
            fh.write(body)

    return download


def _cdse_writes(body: bytes):
    """Stand in for download_from_cdse, writing body to outfn"""

    def download(session, token, key, outfn):
        with open(outfn, "wb") as fh:
            fh.write(body)

    return download


def _raises(exc: Exception):
    def fail(*args):
        raise exc

    return fail


@pytest.fixture
def output(tmp_path):
    """The directory a run is told to download into"""
    return tmp_path / "out"


@pytest.fixture
def catalogue_holds(monkeypatch, tmp_path):
    """
    Report the given (key, size) granules from the catalogue, and nothing else

    The domain file, the S3 client and the HTTP session are stood in for at the
    same time. None of them is what these tests are about, and a run cannot
    reach any of them offline.
    """
    monkeypatch.setenv("DOMAIN_FILE", str(tmp_path / "domain.nc"))
    monkeypatch.setattr(fetch_tropomi, "domain_bounding_box", lambda *_: [1.0, -2.0, 3.0, -4.0])
    monkeypatch.setattr(fetch_tropomi, "create_session", lambda: mock.Mock())
    monkeypatch.setattr(fetch_tropomi, "create_client", lambda: mock.Mock())

    def holds(*granules: tuple[str, int]):
        monkeypatch.setattr(fetch_tropomi, "search_granules", lambda *_: list(granules))

    return holds


def test_fetch_downloads_from_the_mirror_when_it_is_healthy(catalogue_holds, output, monkeypatch):
    catalogue_holds((OFFL_KEY, GRANULE_SIZE))
    from_cdse = mock.Mock()
    monkeypatch.setattr(fetch_tropomi, "download_from_mirror", _mirror_writes(GRANULE_BODY))
    monkeypatch.setattr(fetch_tropomi, "download_from_cdse", from_cdse)

    result = CliRunner().invoke(fetch_tropomi.fetch_data, [*FETCH_ARGS, str(output)])

    assert result.exit_code == 0, result.output
    assert "Data fetched successfully!" in result.output
    assert (output / OFFL).read_bytes() == GRANULE_BODY
    from_cdse.assert_not_called()


def test_fetch_falls_back_to_cdse_for_an_unreliable_mirror_object(
    catalogue_holds, output, monkeypatch
):
    """A granule the mirror cannot be trusted for is downloaded from CDSE instead"""
    catalogue_holds((OFFL_KEY, GRANULE_SIZE))
    monkeypatch.setenv("CDSE_USERNAME", "someone@example.com")
    monkeypatch.setenv("CDSE_PASSWORD", "hunter2")
    monkeypatch.setattr(
        fetch_tropomi,
        "download_from_mirror",
        _raises(fetch_tropomi.UnreliableMirrorObjectError("an empty (0 byte) object")),
    )
    monkeypatch.setattr(fetch_tropomi, "cdse_access_token", lambda _: "a-token")
    monkeypatch.setattr(fetch_tropomi, "download_from_cdse", _cdse_writes(GRANULE_BODY))

    result = CliRunner().invoke(fetch_tropomi.fetch_data, [*FETCH_ARGS, str(output)])

    assert result.exit_code == 0, result.output
    assert "an empty (0 byte) object" in result.output
    assert f"Falling back to CDSE for {OFFL}" in result.output
    assert "[via CDSE]" in result.output
    assert (output / OFFL).read_bytes() == GRANULE_BODY


def test_fetch_requests_one_cdse_token_for_the_whole_run(catalogue_holds, output, monkeypatch):
    """The token is bought once, however many granules end up needing it"""
    catalogue_holds((OFFL_KEY, GRANULE_SIZE), (RPRO_KEY, GRANULE_SIZE))
    token = mock.Mock(return_value="a-token")
    monkeypatch.setattr(
        fetch_tropomi,
        "download_from_mirror",
        _raises(fetch_tropomi.UnreliableMirrorObjectError("unreliable")),
    )
    monkeypatch.setattr(fetch_tropomi, "cdse_access_token", token)
    monkeypatch.setattr(fetch_tropomi, "download_from_cdse", _cdse_writes(GRANULE_BODY))

    result = CliRunner().invoke(fetch_tropomi.fetch_data, [*FETCH_ARGS, str(output)])

    assert result.exit_code == 0, result.output
    assert token.call_count == 1


def test_fetch_reports_a_clear_error_when_cdse_has_no_credentials(
    catalogue_holds, output, monkeypatch
):
    """Without credentials the fallback cannot run, and the run must say why"""
    catalogue_holds((OFFL_KEY, GRANULE_SIZE))
    monkeypatch.delenv("CDSE_USERNAME", raising=False)
    monkeypatch.delenv("CDSE_PASSWORD", raising=False)
    monkeypatch.setattr(
        fetch_tropomi,
        "download_from_mirror",
        _raises(fetch_tropomi.UnreliableMirrorObjectError("unreliable")),
    )

    result = CliRunner().invoke(fetch_tropomi.fetch_data, [*FETCH_ARGS, str(output)])

    assert result.exit_code == 1, result.output
    assert "CDSE_USERNAME" in result.output
    assert not (output / OFFL).exists()


def test_fetch_reports_every_granule_it_could_not_recover(catalogue_holds, output, monkeypatch):
    """One granule failing both sources must not hide another that did too"""
    catalogue_holds((OFFL_KEY, GRANULE_SIZE), (RPRO_KEY, GRANULE_SIZE))
    monkeypatch.setattr(
        fetch_tropomi,
        "download_from_mirror",
        _raises(fetch_tropomi.UnreliableMirrorObjectError("unreliable")),
    )
    monkeypatch.setattr(fetch_tropomi, "cdse_access_token", lambda _: "a-token")
    monkeypatch.setattr(fetch_tropomi, "download_from_cdse", _raises(RuntimeError("CDSE said no")))

    result = CliRunner().invoke(fetch_tropomi.fetch_data, [*FETCH_ARGS, str(output)])

    assert result.exit_code == 1, result.output
    assert "could not be downloaded from CDSE either" in result.output
    assert OFFL_KEY in result.output
    assert RPRO_KEY in result.output


def test_fetch_skips_a_granule_already_downloaded(catalogue_holds, output, monkeypatch):
    catalogue_holds((OFFL_KEY, GRANULE_SIZE))
    from_mirror = mock.Mock()
    monkeypatch.setattr(fetch_tropomi, "download_from_mirror", from_mirror)

    output.mkdir()
    (output / OFFL).write_bytes(GRANULE_BODY)

    result = CliRunner().invoke(fetch_tropomi.fetch_data, [*FETCH_ARGS, str(output)])

    assert result.exit_code == 0, result.output
    assert "already present, skipping" in result.output
    from_mirror.assert_not_called()


def test_fetch_retries_a_zero_byte_file_left_behind(catalogue_holds, output, monkeypatch):
    """A stale empty file must never be mistaken for a completed download"""
    catalogue_holds((OFFL_KEY, GRANULE_SIZE))
    monkeypatch.setattr(fetch_tropomi, "download_from_mirror", _mirror_writes(GRANULE_BODY))

    output.mkdir()
    (output / OFFL).write_bytes(b"")

    result = CliRunner().invoke(fetch_tropomi.fetch_data, [*FETCH_ARGS, str(output)])

    assert result.exit_code == 0, result.output
    assert "already present, skipping" not in result.output
    assert (output / OFFL).read_bytes() == GRANULE_BODY
