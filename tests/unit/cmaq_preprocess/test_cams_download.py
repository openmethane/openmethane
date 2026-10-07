"""Tests for downloading CAMS products."""

import datetime
import http.server
import threading

import numpy as np

from openmethane.cmaq_preprocess.cams_download import download_in_ranges, months_in_range


def test_months_in_range_spans_the_year_end():
    months = months_in_range(datetime.date(2023, 12, 30), datetime.date(2024, 2, 1))

    assert months == [(2023, 12), (2024, 1), (2024, 2)]


def test_download_in_ranges_reassembles_the_file(tmp_path):
    payload = np.random.default_rng(0).bytes(10_000)

    class RangeHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            start, end = self.headers["Range"].removeprefix("bytes=").split("-")
            chunk = payload[int(start) : int(end) + 1]
            self.send_response(206)
            self.send_header("Content-Length", str(len(chunk)))
            self.end_headers()
            self.wfile.write(chunk)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), RangeHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        destination = tmp_path / "out.bin"
        download_in_ranges(
            f"http://127.0.0.1:{server.server_port}/file",
            destination,
            len(payload),
            connections=3,
            chunk_bytes=999,
        )
    finally:
        server.shutdown()
        server.server_close()

    assert destination.read_bytes() == payload
