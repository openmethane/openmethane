"""Tests for downloading CAMS products."""

import datetime
import http.server
import threading

import numpy as np
import xarray as xr

from openmethane.cmaq_preprocess.cams_download import (
    download_in_ranges,
    download_pressure_levels,
    forecasts_by_valid_time,
    months_in_range,
)


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


def ads_forecasts():
    """Two daily 00Z forecasts with four leads, in the layout the ADS delivers

    Each value is the hour since the first forecast started, so it names its valid time.
    """
    reference_times = np.array(["2026-01-01", "2026-01-02"], dtype="datetime64[ns]")
    leads = np.array([0, 6, 12, 18], dtype="timedelta64[h]").astype("timedelta64[ns]")
    hours = (np.arange(2)[:, None] * 24 + np.arange(0, 24, 6)[None, :]).astype(float)
    return xr.Dataset(
        {
            "ch4": (
                ("forecast_period", "forecast_reference_time", "pressure_level", "latitude",
                 "longitude"),
                np.broadcast_to(hours.T[:, :, None, None, None], (4, 2, 2, 3, 2)).copy(),
                {"units": "kg kg**-1"},
            )
        },
        coords={
            "forecast_reference_time": reference_times,
            "forecast_period": leads,
            "valid_time": (
                ("forecast_reference_time", "forecast_period"),
                reference_times[:, None] + leads[None, :],
            ),
            "pressure_level": [1000.0, 500.0],
            "latitude": [-20.0, -20.1, -20.2],
            "longitude": [140.0, 140.1],
        },
    )  # fmt: skip


def test_forecasts_by_valid_time_puts_each_lead_at_its_valid_time():
    forecasts = ads_forecasts()

    flat = forecasts_by_valid_time(forecasts)

    assert flat["ch4"].dims == ("valid_time", "pressure_level", "latitude", "longitude")
    expected_times = np.datetime64("2026-01-01") + np.arange(0, 48, 6).astype("timedelta64[h]")
    np.testing.assert_array_equal(flat["valid_time"].values, expected_times)
    np.testing.assert_array_equal(flat["ch4"].values[:, 0, 0, 0], np.arange(0, 48, 6))
    assert flat["ch4"].attrs["units"] == "kg kg**-1"


class FakeClient:
    """Records the request, and delivers `delivered` in place of the ADS"""

    def __init__(self, delivered: xr.Dataset | None = None):
        self.delivered = delivered
        self.requests = []

    def retrieve(self, dataset, request, target):
        self.requests.append((dataset, request))
        if self.delivered is not None:
            self.delivered.to_netcdf(target)


def test_eac4_request_is_unchanged_from_the_download_script(tmp_path):
    client = FakeClient()

    download_pressure_levels(
        "eac4",
        datetime.date(2024, 12, 7),
        datetime.date(2024, 12, 8),
        tmp_path / "eac4.nc",
        client=client,
    )

    # fmt: off
    assert client.requests == [(
        "cams-global-reanalysis-eac4",
        {
            "variable": "methane_chemistry",
            "pressure_level": [
                "1", "2", "3", "5", "7", "10", "20",
                "30", "50", "70", "100", "150", "200",
                "250", "300", "400", "500", "600", "700",
                "800", "850", "900", "925", "950", "1000",
            ],
            "date": "2024-12-07/2024-12-08",
            "time": [f"{hour:02d}:00" for hour in range(0, 24, 3)],
            "format": "netcdf",
        },
    )]
    # fmt: on


def test_forecasts_are_requested_at_leads_of_the_00z_forecast(tmp_path):
    client = FakeClient(delivered=ads_forecasts())

    download_pressure_levels(
        "forecasts",
        datetime.date(2026, 1, 1),
        datetime.date(2026, 1, 2),
        tmp_path / "forecasts.nc",
        client=client,
    )

    [(dataset, request)] = client.requests
    assert dataset == "cams-global-greenhouse-gas-forecasts"
    assert request["date"] == "2026-01-01/2026-01-02"
    assert request["leadtime_hour"] == ["0", "6", "12", "18"]
    assert request["pressure_level"][0] == "50"


def test_forecasts_are_saved_on_one_valid_time_axis(tmp_path):
    client = FakeClient(delivered=ads_forecasts())
    destination = tmp_path / "forecasts.nc"

    download_pressure_levels(
        "forecasts",
        datetime.date(2026, 1, 1),
        datetime.date(2026, 1, 2),
        destination,
        client=client,
    )

    with xr.open_dataset(destination) as saved:
        assert saved["ch4"].dims == ("valid_time", "pressure_level", "latitude", "longitude")
        assert len(saved["valid_time"]) == 8
        assert saved.attrs["cams_product"] == "forecasts"
