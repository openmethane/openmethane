"""Download files over HTTP, retrying transient failures.

A file only appears at its destination once it has downloaded completely, so a
file that is present can be trusted and is never fetched again.
"""

import concurrent.futures
import logging
import os
import pathlib
import urllib.parse
import uuid
from collections.abc import Iterable

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

logger = logging.getLogger(__name__)

RETRY_STATUSES = (408, 429, 500, 502, 503, 504)
"""HTTP statuses that a server may stop returning if asked again"""

TIMEOUT_SECONDS = (30, 300)
"""Seconds to wait to connect, and then between bytes of the response"""

CHUNK_BYTES = 1024 * 1024


class DownloadFailed(RuntimeError):
    """A file could not be downloaded, even after retrying."""


def create_session(retries: int = 5, backoff_factor: float = 1.0) -> requests.Session:
    """
    Create a session that retries failed connections and transient HTTP errors.

    Parameters
    ----------
    retries
        Most times to retry one request.
    backoff_factor
        Scales the wait between retries. urllib3 retries the first failure at
        once, then waits `backoff_factor * 2 ** (n - 1)` seconds before retry
        n, or as long as a Retry-After header asks. 0 never waits.
    """
    retry = Retry(
        total=retries,
        backoff_factor=backoff_factor,
        status_forcelist=RETRY_STATUSES,
        allowed_methods=("GET",),
    )
    adapter = HTTPAdapter(max_retries=retry)

    session = requests.Session()
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def download(url: str, dest: str | os.PathLike, *, session: requests.Session) -> pathlib.Path:
    """
    Download a URL to a file.

    The response is written to a temporary `<dest>.<random>.part` file in the
    same directory and moved to `dest` only once it is complete, so an
    interrupted download never leaves a truncated file that a later run would
    take as finished. The temporary name is unique, so two runs downloading
    the same file into a shared directory don't write into each other's. An
    existing file at `dest` is replaced.

    Parameters
    ----------
    url
        URL to download.
    dest
        File to save it as. Its directory must exist.
    session
        Session to download with, normally from `create_session`.

    Returns
    -------
    The path the file was saved to.

    Raises
    ------
    DownloadFailed
        If the server can't be reached or returns an error after retrying, or
        the response is shorter or longer than its Content-Length.
    """
    dest = pathlib.Path(dest)
    partial = dest.with_name(f"{dest.name}.{uuid.uuid4().hex}.part")

    try:
        with session.get(url, stream=True, timeout=TIMEOUT_SECONDS) as response:
            response.raise_for_status()
            with partial.open("wb") as file:
                for chunk in response.iter_content(chunk_size=CHUNK_BYTES):
                    file.write(chunk)

            # Content-Length counts the encoded bytes, so it can only be
            # compared when the body wasn't compressed in transit.
            expected = response.headers.get("Content-Length")
            received = partial.stat().st_size
            if (
                expected is not None
                and "Content-Encoding" not in response.headers
                and int(expected) != received
            ):
                raise DownloadFailed(
                    f"Incomplete download of {url}: expected {expected} bytes,"
                    f" received {received}"
                )

        partial.replace(dest)
    except requests.RequestException as error:
        raise DownloadFailed(f"Could not download {url}: {error}") from error
    finally:
        partial.unlink(missing_ok=True)

    return dest


def fetch_missing(
    urls: Iterable[str],
    dest_dir: str | os.PathLike,
    *,
    session: requests.Session | None = None,
    max_workers: int = 8,
) -> list[pathlib.Path]:
    """
    Download each URL into a directory, unless the file is already there.

    Each file is named after the last part of its URL's path. Downloads run in
    parallel, up to `max_workers` at a time.

    Parameters
    ----------
    urls
        URLs to download. Their file names must be distinct.
    dest_dir
        Directory to save the files in, created if needed.
    session
        Session to download with. Defaults to one from `create_session`.
    max_workers
        Most downloads to run at once.

    Returns
    -------
    The path of every file, in the order of `urls`, whether it was downloaded
    or already present.

    Raises
    ------
    DownloadFailed
        If any download fails. Downloads already running are left to finish,
        and any not yet started are cancelled. Other errors, such as a full
        disk, are raised as they are, also cancelling the rest.
    ValueError
        If two URLs would be saved under the same file name.
    """
    dest_dir = pathlib.Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    session = session or create_session()

    urls = list(urls)
    paths = [dest_dir / _file_name(url) for url in urls]
    if len(set(paths)) != len(paths):
        raise ValueError(f"URLs share a file name, so would overwrite each other: {urls}")

    missing = [(url, path) for url, path in zip(urls, paths) if not path.exists()]
    logger.info(f"{len(paths) - len(missing)} of {len(paths)} files already in {dest_dir}")

    # The session is shared between threads. Its connection pool is thread-safe,
    # and these requests use no cookies or other per-request session state.
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(download, url, path, session=session) for url, path in missing]
        try:
            for future in concurrent.futures.as_completed(futures):
                logger.info(f"downloaded {future.result()}")
        except Exception:
            for future in futures:
                future.cancel()
            raise

    return paths


def _file_name(url: str) -> str:
    """The last part of a URL's path, which is the name to save it under."""
    name = pathlib.PurePosixPath(urllib.parse.urlparse(url).path).name
    if not name:
        raise ValueError(f"URL has no file name: {url}")
    return name
