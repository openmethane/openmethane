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
    cut_inversion_to_domain,
    download_in_ranges,
    download_inversion,
    download_pressure_levels,
    forecasts_by_valid_time,
    months_in_range,
    padded_domain_bounds,
)


class FakeResult:
    location = "https://ads.example/result.zip"
    content_length = 1


class FakeClient:
    """Records each request in place of the ADS, and fails the ones numbered in `fail`"""

    def __init__(self, fail=()):
        self.requests = []
        self.fail = fail

    def retrieve(self, dataset, request):
        self.requests.append((dataset, request))
        if len(self.requests) - 1 in self.fail:
            raise RuntimeError("the ADS has no data for this request")
        return FakeResult()


@pytest.fixture
def domain_file(tmp_path):
    path = tmp_path / "domain.nc"
    xr.Dataset(coords={"lat": [-30.0, -20.0], "lon": [140.0, 150.0]}).to_netcdf(path)
    return path


@pytest.fixture
def ads_delivers(monkeypatch, tmp_path):
    """Make each range download deliver a zip of the next of the given datasets

    The last dataset is delivered again for any further downloads.
    """

    def deliver(*datasets: xr.Dataset):
        netcdfs = []
        for i, dataset in enumerate(datasets):
            netcdfs.append(tmp_path / f"delivered-{i}.nc")
            dataset.to_netcdf(netcdfs[-1])

        def fake_download_in_ranges(url, destination, size):
            netcdf = netcdfs.pop(0) if len(netcdfs) > 1 else netcdfs[0]
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
def ads_eac4_next_midnight(ads_eac4):
    """EAC4 at 00:00 on the day after `ads_eac4`, with a value of 2 to tell it apart"""
    return (
        ads_eac4.isel(valid_time=[0])
        .assign_coords(valid_time=[np.datetime64("2024-12-08", "ns")])
        .assign(ch4_c=lambda dataset: dataset["ch4_c"] * 2)
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
    assert client.requests[0] == (
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
    )
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

    assert [request["date"] for _, request in client.requests[:-1]] == [
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

    dataset, request = client.requests[0]
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


@pytest.fixture
def ads_forecast_lead_24(ads_forecasts):
    """The 24 h lead of the second forecast in `ads_forecasts`, valid at 2026-01-03 00:00"""
    lead = np.array([24], dtype="timedelta64[h]").astype("timedelta64[ns]")
    forecast = ads_forecasts.isel(forecast_reference_time=[1], forecast_period=[0])
    return forecast.assign_coords(
        forecast_period=lead,
        valid_time=(
            ("forecast_reference_time", "forecast_period"),
            forecast["forecast_reference_time"].values[:, None] + lead[None, :],
        ),
    ).assign(ch4=lambda dataset: dataset["ch4"] + 24)


def test_eac4_requests_00z_of_the_day_after_the_end(tmp_path, domain_file, ads_delivers, ads_eac4):
    ads_delivers(ads_eac4)
    client = FakeClient()

    download_pressure_levels(
        "eac4",
        datetime.date(2024, 11, 30),
        datetime.date(2024, 12, 7),
        tmp_path / "eac4.nc",
        domain_file,
        client=client,
    )

    _, request = client.requests[-1]
    assert request["date"] == "2024-12-08/2024-12-08"
    assert request["time"] == ["00:00"]


def test_forecasts_request_the_24_hour_lead_of_the_last_day(
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

    _, request = client.requests[-1]
    assert request["date"] == "2026-01-02/2026-01-02"
    assert request["leadtime_hour"] == ["24"]


def test_eac4_is_saved_through_00z_of_the_day_after_the_end(
    tmp_path, domain_file, ads_delivers, ads_eac4, ads_eac4_next_midnight
):
    ads_delivers(ads_eac4, ads_eac4_next_midnight)
    destination = tmp_path / "eac4.nc"

    download_pressure_levels(
        "eac4",
        datetime.date(2024, 12, 7),
        datetime.date(2024, 12, 7),
        destination,
        domain_file,
        client=FakeClient(),
    )

    with xr.open_dataset(destination) as saved:
        assert len(saved["valid_time"]) == 9
        assert saved["valid_time"].values[-1] == np.datetime64("2024-12-08", "ns")
        assert (saved["ch4_c"].values[-1] == 2).all()


def test_forecasts_are_saved_through_the_24_hour_lead_of_the_last_day(
    tmp_path, domain_file, ads_delivers, ads_forecasts, ads_forecast_lead_24
):
    ads_delivers(ads_forecasts, ads_forecast_lead_24)
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
        expected = np.datetime64("2026-01-01") + np.arange(0, 54, 6).astype("timedelta64[h]")
        np.testing.assert_array_equal(saved["valid_time"].values, expected)
        np.testing.assert_array_equal(saved["ch4"].values[:, 0, 0, 0], np.arange(0, 54, 6))


def test_the_download_goes_ahead_when_the_next_midnight_is_not_available(
    tmp_path, domain_file, ads_delivers, ads_eac4, caplog
):
    ads_delivers(ads_eac4)
    destination = tmp_path / "eac4.nc"

    download_pressure_levels(
        "eac4",
        datetime.date(2024, 12, 7),
        datetime.date(2024, 12, 7),
        destination,
        domain_file,
        client=FakeClient(fail=[1]),
    )

    with xr.open_dataset(destination) as saved:
        assert saved["valid_time"].values[-1] == np.datetime64("2024-12-07T21:00", "ns")
    assert "2024-12-08 00:00 could not be downloaded" in caplog.text
    assert "24:00 BCON record of 2024-12-07 will repeat" in caplog.text


@pytest.fixture
def ads_inversion_months(monkeypatch):
    """Record each month the inversion is asked for, and fail the ones in `missing`"""
    requested = []
    missing = set()

    def fake_retrieve_inversion_month(year, month, version, destination, client=None):
        requested.append((year, month))
        if (year, month) in missing:
            raise RuntimeError(f"The CAMS inversion {version} has no methane for {year}-{month}")
        return destination

    monkeypatch.setattr(cams_download, "retrieve_inversion_month", fake_retrieve_inversion_month)
    return requested, missing


def test_inversion_downloads_only_the_months_of_the_range_when_it_ends_mid_month(
    tmp_path, ads_inversion_months
):
    requested, _ = ads_inversion_months

    download_inversion(datetime.date(2024, 9, 20), datetime.date(2024, 10, 30), "v25r1", tmp_path)

    assert requested == [(2024, 9), (2024, 10)]


def test_inversion_downloads_the_next_month_when_the_range_ends_on_a_month_end(
    tmp_path, ads_inversion_months
):
    requested, _ = ads_inversion_months

    files = download_inversion(
        datetime.date(2024, 10, 1), datetime.date(2024, 10, 31), "v25r1", tmp_path
    )

    assert requested == [(2024, 10), (2024, 11)]
    assert files == [tmp_path / "2024-10.nc", tmp_path / "2024-11.nc"]


def test_inversion_goes_ahead_without_a_next_month_past_the_end_of_the_release(
    tmp_path, ads_inversion_months, caplog
):
    requested, missing = ads_inversion_months
    missing.add((2026, 1))

    files = download_inversion(
        datetime.date(2025, 12, 1), datetime.date(2025, 12, 31), "v25r1", tmp_path
    )

    assert requested == [(2025, 12), (2026, 1)]
    assert files == [tmp_path / "2025-12.nc"]
    assert "v25r1 for 2026-01 could not be downloaded" in caplog.text
    assert "24:00 BCON record of 2025-12-31 will repeat its 18:00 field" in caplog.text


def test_inversion_still_fails_when_a_month_of_the_range_is_missing(tmp_path, ads_inversion_months):
    _, missing = ads_inversion_months
    missing.add((2026, 1))

    with pytest.raises(RuntimeError, match="has no methane for 2026-1"):
        download_inversion(datetime.date(2025, 12, 1), datetime.date(2026, 1, 5), "v25r1", tmp_path)


def inversion_month(path, first_day, days):
    """A small monthly inversion file, 6-hourly over `days` days from `first_day`"""
    times = np.datetime64(first_day, "ns") + np.arange(0, 24 * days, 6).astype("timedelta64[h]")
    shape = (len(times), 2, 3, 2)
    xr.Dataset(
        {
            "CH4": (("time", "level", "latitude", "longitude"), np.ones(shape)),
            "ps": (("time", "latitude", "longitude"), np.ones(shape[:1] + shape[2:])),
            "hyam": (("level",), [0.0, 100.0]),
            "hybm": (("level",), [1.0, 0.5]),
        },
        coords={
            "time": times,
            "latitude": [-30.0, -25.0, -20.0],
            "longitude": [140.0, 150.0],
        },
        attrs={"release": "v25r1"},
    ).to_netcdf(path)
    return path


def test_the_inversion_cut_keeps_only_the_first_step_of_the_next_month(tmp_path, domain_file):
    months = [
        inversion_month(tmp_path / "2024-10.nc", "2024-10-30", 2),
        inversion_month(tmp_path / "2024-11.nc", "2024-11-01", 2),
    ]
    destination = tmp_path / "cut.nc"

    cut_inversion_to_domain(
        months, domain_file, datetime.date(2024, 10, 31), datetime.date(2024, 10, 31), destination
    )

    with xr.open_dataset(destination) as cut:
        expected = np.datetime64("2024-10-31") + np.arange(0, 30, 6).astype("timedelta64[h]")
        np.testing.assert_array_equal(cut["time"].values, expected)
