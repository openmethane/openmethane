"""Tests various archiving helpers."""
import datetime
import pathlib
from unittest.mock import call, patch

from util.archive import baseline, daily, fetch_domain, monthly

@patch('subprocess.run')
def test_monthly(mockRun, tmp_path):
    # initiate load archive for a 3 day monthly run
    monthly(
        "test-bucket-name",
        datetime.date(2022, 10, 29),
        datetime.date(2022, 10, 31),
        "test-domain",
        tmp_path,
    )

    # monthly run from 2022-10-29 to 2022-10-31 will fetch input, cmaq and mcip folders for each day
    for date in ['2022/10/29', '2022/10/30', '2022/10/31']:
        for path in ['input', 'cmaq', 'mcip']:
            # checks if s3 path exists with 'aws ls' before fetching with 'aws sync'
            mockRun.assert_has_calls([
                call([
                    "aws", "s3", "ls", f"s3://test-bucket-name/test-domain/daily/{date}/{path}",
                ], check=True, capture_output=False),
                call([
                    "aws", "s3", "sync", "--no-progress", f"s3://test-bucket-name/test-domain/daily/{date}/{path}",
                    str(tmp_path / f"test-domain/daily/{date}/{path}"),
                ], check=True, capture_output=True, text=True),
            ])

            mockRun.assert_has_calls([
                call([
                    "aws", "s3", "ls", f"s3://test-bucket-name/test-domain/daily/{date}/simulobs.pic.gz",
                ], check=True, capture_output=False),
                call([
                    "aws", "s3", "cp", "--no-progress", f"s3://test-bucket-name/test-domain/daily/{date}/simulobs.pic.gz",
                    str(tmp_path / f"test-domain/daily/{date}"),
                ], check=True, capture_output=True, text=True),
            ])


@patch('subprocess.run')
def test_daily(mockRun, tmp_path):
    # initiate load archive for a daily run
    daily(
        "test-bucket-name",
        datetime.date(2022, 10, 29),
        "test-domain",
        tmp_path,
        pathlib.Path("alerts-baseline.nc"),
    )

    # daily run will fetch wrf and mcip folders for each day
    for path in ['wrf', 'mcip']:
        # checks if s3 path exists with 'aws ls' before fetching with 'aws sync'
        mockRun.assert_has_calls([
            call([
                "aws", "s3", "ls", f"s3://test-bucket-name/test-domain/daily/2022/10/29/{path}",
            ], check=True, capture_output=False),
            call([
                "aws", "s3", "sync", "--no-progress", f"s3://test-bucket-name/test-domain/daily/2022/10/29/{path}",
                str(tmp_path / path),
            ], check=True, capture_output=True, text=True),
        ])

        mockRun.assert_called_with([
            "aws", "s3", "cp", "--no-progress",
            "s3://test-bucket-name/alerts-baseline.nc",
            str(tmp_path),
        ], check=True, capture_output=True, text=True)



@patch('subprocess.run')
def test_baseline(mockRun, tmp_path):
    # initiate load archive for a 3 day baseline run
    baseline(
        "test-bucket-name",
        "test-public-bucket",
        datetime.date(2022, 10, 29),
        datetime.date(2022, 10, 31),
        "test-domain",
        "v2",
        tmp_path,
    )

    # baseline must fetch the domain
    mockRun.assert_has_calls([
        call([
            "aws", "s3", "ls", "s3://test-public-bucket/domains/test-domain/v2/domain.test-domain.nc",
        ], check=True, capture_output=False),
        call([
            "aws", "s3", "cp", "--no-progress", "s3://test-public-bucket/domains/test-domain/v2/domain.test-domain.nc",
            str(tmp_path),
        ], check=True, capture_output=True, text=True),
    ])

    # baseline run from 2022-10-29 to 2022-10-31 will fetch input, cmaq and mcip folders for each day
    for date in ['2022/10/29', '2022/10/30', '2022/10/31']:
        # checks if s3 path exists with 'aws ls' before fetching with 'aws sync'
        mockRun.assert_has_calls([
            call([
                "aws", "s3", "ls", f"s3://test-bucket-name/test-domain/daily/{date}/input",
            ], check=True, capture_output=False),
            call([
                "aws", "s3", "sync", "--no-progress",
                "--exclude=*", "--include=test_obs.pic.gz",
                f"s3://test-bucket-name/test-domain/daily/{date}/input",
                str(tmp_path / f"test-domain/baseline/{date}/input"),
            ], check=True, capture_output=True, text=True),
        ])

        mockRun.assert_has_calls([
            call([
                "aws", "s3", "ls", f"s3://test-bucket-name/test-domain/daily/{date}/simulobs.pic.gz",
            ], check=True, capture_output=False),
            call([
                "aws", "s3", "cp", "--no-progress", f"s3://test-bucket-name/test-domain/daily/{date}/simulobs.pic.gz",
                str(tmp_path / f"test-domain/baseline/{date}"),
            ], check=True, capture_output=True, text=True),
        ])


@patch('subprocess.run')
def test_fetch_domain(mockRun, tmp_path):
    fetch_domain("test-bucket-name", "test-domain","v1", tmp_path)

    mockRun.assert_called_with([
        "aws", "s3", "cp", "--no-progress",
        "s3://test-bucket-name/domains/test-domain/v1/domain.test-domain.nc",
        str(tmp_path),
    ], check=True, capture_output=True, text=True)
