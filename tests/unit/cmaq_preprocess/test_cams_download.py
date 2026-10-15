"""Tests for downloading CAMS products."""

import datetime
import http.server
import threading
import zipfile

import numpy as np
import pytest
import xarray as xr

from openmethane.cmaq_preprocess import cams_download
from openmethane.cmaq_preprocess.cams_download import (
    download_in_ranges,
    download_pressure_levels,
    forecasts_by_valid_time,
    months_in_range,
    padded_domain_bounds,
)


class FakeResult:
    location = "https://ads.example/result.zip"
    content_length = 1


class FakeClient:
    """Records each request in place of the ADS"""

    def __init__(self):
        self.requests = []

    def retrieve(self, dataset, request):
        self.requests.append((dataset, request))
        return FakeResult()


@pytest.fixture
def domain_file(tmp_path):
    path = tmp_path / "domain.nc"
    xr.Dataset(coords={"lat": [-30.0, -20.0], "lon": [140.0, 150.0]}).to_netcdf(path)
    return path


@pytest.fixture
def ads_delivers(monkeypatch, tmp_path):
    """Make every range download deliver a zip of the given dataset"""

    def deliver(dataset: xr.Dataset):
        netcdf = tmp_path / "delivered.nc"
        dataset.to_netcdf(netcdf)

        def fake_download_in_ranges(url, destination, size):
            with zipfile.ZipFile(destination, "w") as archive:
                archive.write(netcdf, "data_plev.nc")

        monkeypatch.setattr(cams_download, "download_in_ranges", fake_download_in_ranges)

    return deliver


@pytest.fixture
def ads_eac4():
    """One day of EAC4, in the layout the ADS delivers"""
    times = np.datetime64("2024-12-07") + np.arange(0, 24, 3).astype("timedelta64[h]")
    return xr.Dataset(
        {
            "ch4_c": (
                ("valid_time", "pressure_level", "latitude", "longitude"),
                np.ones((8, 2, 3, 2)),
            )
        },
        coords={
            "valid_time": times.astype("datetime64[ns]"),
            "pressure_level": [1000.0, 500.0],
            "latitude": [-20.0, -25.0, -30.0],
            "longitude": [140.0, 145.0],
        },
    )


@pytest.fixture
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


def test_months_in_range_spans_the_year_end():
    months = months_in_range(datetime.date(2023, 12, 30), datetime.date(2024, 2, 1))

    assert months == [(2023, 12), (2024, 1), (2024, 2)]


def test_padded_domain_bounds_widens_each_edge_by_the_padding(tmp_path):
    domain_file = tmp_path / "domain.nc"
    xr.Dataset(coords={"lat": [-30.0, -20.0], "lon": [140.0, 150.0]}).to_netcdf(domain_file)

    bounds = padded_domain_bounds(domain_file, padding=1.5)

    assert bounds == (-31.5, -18.5, 138.5, 151.5)


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


def test_forecasts_by_valid_time_puts_each_lead_at_its_valid_time(ads_forecasts):
    flat = forecasts_by_valid_time(ads_forecasts)

    assert flat["ch4"].dims == ("valid_time", "pressure_level", "latitude", "longitude")
    expected_times = np.datetime64("2026-01-01") + np.arange(0, 48, 6).astype("timedelta64[h]")
    np.testing.assert_array_equal(flat["valid_time"].values, expected_times)
    np.testing.assert_array_equal(flat["ch4"].values[:, 0, 0, 0], np.arange(0, 48, 6))
    assert flat["ch4"].attrs["units"] == "kg kg**-1"


def test_eac4_is_requested_over_the_padded_domain(tmp_path, domain_file, ads_delivers, ads_eac4):
    ads_delivers(ads_eac4)
    client = FakeClient()

    download_pressure_levels(
        "eac4",
        datetime.date(2024, 12, 7),
        datetime.date(2024, 12, 7),
        tmp_path / "eac4.nc",
        domain_file,
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
            "date": "2024-12-07/2024-12-07",
            "time": [f"{hour:02d}:00" for hour in range(0, 24, 3)],
            "area": [-17.0, 137.0, -33.0, 153.0],
            "data_format": "netcdf_zip",
        },
    )]
    # fmt: on


def test_a_request_is_made_for_each_month(tmp_path, domain_file, ads_delivers, ads_eac4):
    ads_delivers(ads_eac4)
    client = FakeClient()

    download_pressure_levels(
        "eac4",
        datetime.date(2024, 11, 30),
        datetime.date(2024, 12, 2),
        tmp_path / "eac4.nc",
        domain_file,
        client=client,
    )

    assert [request["date"] for _, request in client.requests] == [
        "2024-11-30/2024-11-30",
        "2024-12-01/2024-12-02",
    ]


def test_forecasts_are_requested_at_leads_of_the_00z_forecast(
    tmp_path, domain_file, ads_delivers, ads_forecasts
):
    ads_delivers(ads_forecasts)
    client = FakeClient()

    download_pressure_levels(
        "forecasts",
        datetime.date(2026, 1, 1),
        datetime.date(2026, 1, 2),
        tmp_path / "forecasts.nc",
        domain_file,
        client=client,
    )

    [(dataset, request)] = client.requests
    assert dataset == "cams-global-greenhouse-gas-forecasts"
    assert request["date"] == "2026-01-01/2026-01-02"
    assert request["leadtime_hour"] == ["0", "6", "12", "18"]
    assert request["pressure_level"][0] == "50"


def test_forecasts_are_saved_on_one_valid_time_axis(
    tmp_path, domain_file, ads_delivers, ads_forecasts
):
    ads_delivers(ads_forecasts)
    destination = tmp_path / "forecasts.nc"

    download_pressure_levels(
        "forecasts",
        datetime.date(2026, 1, 1),
        datetime.date(2026, 1, 2),
        destination,
        domain_file,
        client=FakeClient(),
    )

    with xr.open_dataset(destination) as saved:
        assert saved["ch4"].dims == ("valid_time", "pressure_level", "latitude", "longitude")
        assert len(saved["valid_time"]) == 8
        assert saved.attrs["cams_product"] == "forecasts"
