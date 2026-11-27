import hashlib
import http.server
import io
import tarfile
import threading

import attrs
import pytest
import requests

from openmethane.util.download import (
    DownloadFailed,
    create_session,
    download,
    fetch_archive,
    fetch_missing,
)


@attrs.frozen
class Reply:
    """One response from the test server."""

    status: int = 200
    body: bytes = b""
    content_length: int | None = None
    """Content-Length to declare, if not the body's length"""


@attrs.define
class FileServer:
    """A local HTTP server that answers each path with a queue of replies."""

    base_url: str
    replies: dict[str, list[Reply]] = attrs.field(factory=dict)
    requested: list[str] = attrs.field(factory=list)

    def url(self, path: str) -> str:
        return f"{self.base_url}{path}"


@pytest.fixture
def server():
    """Serve replies over HTTP on localhost. A path's last reply repeats."""

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            file_server.requested.append(self.path)
            queue = file_server.replies.get(self.path, [Reply(404)])
            reply = queue.pop(0) if len(queue) > 1 else queue[0]

            self.send_response(reply.status)
            length = len(reply.body) if reply.content_length is None else reply.content_length
            self.send_header("Content-Length", str(length))
            self.end_headers()
            self.wfile.write(reply.body)

        def log_message(self, format, *args):
            pass

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    file_server = FileServer(base_url=f"http://127.0.0.1:{httpd.server_port}")
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield file_server
    httpd.shutdown()
    httpd.server_close()


@pytest.fixture
def session():
    """A session that retries without waiting, to keep the tests fast."""
    with create_session(retries=2, backoff_factor=0) as session:
        yield session


def test_downloads_a_file_to_its_destination(server, session, tmp_path):
    server.replies["/data.grib2"] = [Reply(body=b"GRIB data")]
    dest = tmp_path / "data.grib2"

    result = download(server.url("/data.grib2"), dest, session=session)

    assert result == dest
    assert dest.read_bytes() == b"GRIB data"
    assert list(tmp_path.iterdir()) == [dest]


def test_retries_a_transient_server_error(server, session, tmp_path):
    server.replies["/data.grib2"] = [Reply(503), Reply(502), Reply(body=b"GRIB data")]
    dest = tmp_path / "data.grib2"

    download(server.url("/data.grib2"), dest, session=session)

    assert dest.read_bytes() == b"GRIB data"
    assert server.requested == ["/data.grib2"] * 3


def test_fails_once_the_retries_run_out(server, session, tmp_path):
    server.replies["/data.grib2"] = [Reply(503)]
    dest = tmp_path / "data.grib2"

    with pytest.raises(DownloadFailed, match="Could not download .*/data.grib2"):
        download(server.url("/data.grib2"), dest, session=session)

    # The first request and two retries.
    assert server.requested == ["/data.grib2"] * 3
    assert list(tmp_path.iterdir()) == []


def test_does_not_retry_a_missing_file(server, session, tmp_path):
    dest = tmp_path / "data.grib2"

    with pytest.raises(DownloadFailed, match="404"):
        download(server.url("/data.grib2"), dest, session=session)

    assert server.requested == ["/data.grib2"]


def test_a_truncated_response_leaves_no_file(server, session, tmp_path):
    server.replies["/data.grib2"] = [Reply(body=b"GRIB", content_length=100)]
    dest = tmp_path / "data.grib2"

    with pytest.raises(DownloadFailed):
        download(server.url("/data.grib2"), dest, session=session)

    assert list(tmp_path.iterdir()) == []


def test_a_response_shorter_than_its_content_length_fails(tmp_path, monkeypatch):
    # urllib3 normally catches a short body itself, so this reaches the
    # Content-Length check only through a response that skips urllib3.
    response = requests.Response()
    response.status_code = 200
    response.headers["Content-Length"] = "100"
    response.raw = io.BytesIO(b"GRIB")
    session = requests.Session()
    monkeypatch.setattr(session, "get", lambda *args, **kwargs: response)
    dest = tmp_path / "data.grib2"

    with pytest.raises(DownloadFailed, match="expected 100 bytes, received 4"):
        download("https://example.invalid/data.grib2", dest, session=session)

    assert list(tmp_path.iterdir()) == []


def test_another_download_in_progress_is_left_alone(server, session, tmp_path):
    server.replies["/data.grib2"] = [Reply(body=b"GRIB data")]
    dest = tmp_path / "data.grib2"
    # Another run downloading the same file into a shared directory.
    other = tmp_path / "data.grib2.0123456789abcdef.part"
    other.write_bytes(b"another run's partial download")

    download(server.url("/data.grib2"), dest, session=session)

    assert dest.read_bytes() == b"GRIB data"
    assert other.read_bytes() == b"another run's partial download"
    assert sorted(tmp_path.iterdir()) == [dest, other]


def test_fetch_missing_downloads_every_file_in_order(server, session, tmp_path):
    names = [f"gdas1.fnl0p25.20221207{hour:02d}.f00.grib2" for hour in (0, 6, 12, 18)]
    for name in names:
        server.replies[f"/2022/202212/{name}"] = [Reply(body=name.encode())]
    urls = [server.url(f"/2022/202212/{name}") for name in names]
    dest_dir = tmp_path / "fnl"

    paths = fetch_missing(urls, dest_dir, session=session, max_workers=2)

    assert paths == [dest_dir / name for name in names]
    assert [path.read_bytes() for path in paths] == [name.encode() for name in names]


def test_fetch_missing_skips_files_already_present(server, session, tmp_path):
    server.replies["/present.grib2"] = [Reply(body=b"new")]
    server.replies["/missing.grib2"] = [Reply(body=b"new")]
    (tmp_path / "present.grib2").write_bytes(b"cached")

    paths = fetch_missing(
        [server.url("/present.grib2"), server.url("/missing.grib2")], tmp_path, session=session
    )

    assert paths == [tmp_path / "present.grib2", tmp_path / "missing.grib2"]
    assert (tmp_path / "present.grib2").read_bytes() == b"cached"
    assert (tmp_path / "missing.grib2").read_bytes() == b"new"
    assert server.requested == ["/missing.grib2"]


def test_fetch_missing_fails_if_any_download_fails(server, session, tmp_path):
    server.replies["/good.grib2"] = [Reply(body=b"GRIB data")]

    with pytest.raises(DownloadFailed, match="missing.grib2"):
        fetch_missing(
            [server.url("/good.grib2"), server.url("/missing.grib2")], tmp_path, session=session
        )

    assert not (tmp_path / "missing.grib2").exists()


def test_fetch_missing_rejects_urls_with_the_same_file_name(session, tmp_path):
    urls = ["https://example.invalid/a/data.grib2", "https://example.invalid/b/data.grib2"]

    with pytest.raises(ValueError, match="share a file name"):
        fetch_missing(urls, tmp_path, session=session)


def tarball(files: dict[str, bytes]) -> bytes:
    """A gzipped tarball holding each relative path with its content."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for name, content in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


def test_fetch_archive_unpacks_into_the_folder(server, session, tmp_path):
    body = tarball({"README.md": b"read me", "au-test/a.nc": b"data"})
    server.replies["/bundle.tar.gz"] = [Reply(body=body)]
    dest = tmp_path / "cache" / "wrf"

    result = fetch_archive(
        server.url("/bundle.tar.gz"), hashlib.sha256(body).hexdigest(), dest, session=session
    )

    assert result == dest
    assert (dest / "README.md").read_bytes() == b"read me"
    assert (dest / "au-test" / "a.nc").read_bytes() == b"data"
    # Nothing is left beside it
    assert [path.name for path in dest.parent.iterdir()] == ["wrf"]


def test_fetch_archive_reuses_a_folder_unpacked_from_the_same_archive(server, session, tmp_path):
    body = tarball({"a.nc": b"data"})
    server.replies["/bundle.tar.gz"] = [Reply(body=body)]
    sha256 = hashlib.sha256(body).hexdigest()
    dest = tmp_path / "wrf"
    fetch_archive(server.url("/bundle.tar.gz"), sha256, dest, session=session)
    server.requested.clear()

    fetch_archive(server.url("/bundle.tar.gz"), sha256, dest, session=session)

    assert server.requested == []
    assert (dest / "a.nc").read_bytes() == b"data"


def test_fetch_archive_replaces_a_folder_unpacked_from_another_archive(server, session, tmp_path):
    old = tarball({"old.nc": b"old"})
    new = tarball({"new.nc": b"new"})
    server.replies["/old.tar.gz"] = [Reply(body=old)]
    server.replies["/new.tar.gz"] = [Reply(body=new)]
    dest = tmp_path / "wrf"
    fetch_archive(server.url("/old.tar.gz"), hashlib.sha256(old).hexdigest(), dest, session=session)

    fetch_archive(server.url("/new.tar.gz"), hashlib.sha256(new).hexdigest(), dest, session=session)

    assert sorted(path.name for path in dest.iterdir()) == [".sha256", "new.nc"]


def test_fetch_archive_rejects_an_archive_with_the_wrong_hash(server, session, tmp_path):
    body = tarball({"a.nc": b"data"})
    server.replies["/bundle.tar.gz"] = [Reply(body=body)]
    dest = tmp_path / "wrf"

    with pytest.raises(DownloadFailed, match="SHA-256"):
        fetch_archive(server.url("/bundle.tar.gz"), "0" * 64, dest, session=session)

    assert list(tmp_path.iterdir()) == []


def test_fetch_archive_replaces_a_folder_with_no_record_of_its_archive(server, session, tmp_path):
    body = tarball({"new.nc": b"new"})
    server.replies["/bundle.tar.gz"] = [Reply(body=body)]
    dest = tmp_path / "wrf"
    dest.mkdir()
    (dest / "left-behind.nc").write_bytes(b"old")

    fetch_archive(
        server.url("/bundle.tar.gz"), hashlib.sha256(body).hexdigest(), dest, session=session
    )

    assert sorted(path.name for path in dest.iterdir()) == [".sha256", "new.nc"]


def test_fetch_archive_fails_if_the_archive_cannot_be_downloaded(server, session, tmp_path):
    dest = tmp_path / "wrf"

    with pytest.raises(DownloadFailed):
        fetch_archive(server.url("/missing.tar.gz"), "0" * 64, dest, session=session)

    assert list(tmp_path.iterdir()) == []
