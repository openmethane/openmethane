from datetime import UTC, datetime

import pytest

from openmethane.fourdvar.params import archive_defn
from openmethane.fourdvar.util import archive_handle


@pytest.fixture(autouse=True)
def archive_root(tmp_path, monkeypatch):
    monkeypatch.setattr(archive_defn, "archive_path", str(tmp_path))
    monkeypatch.setattr(archive_defn, "experiment", "openmethane")
    monkeypatch.setattr(archive_defn, "desc_name", "")
    monkeypatch.setattr(archive_handle, "finished_setup", False)
    monkeypatch.setattr(archive_handle, "archive_path", "")
    return tmp_path


def _freeze_time(monkeypatch, hour, second=0):
    moment = datetime(2026, 10, 6, hour, 15, second, tzinfo=UTC)
    monkeypatch.setattr(archive_handle, "_utcnow", lambda: moment)


def test_creates_timestamped_directory_and_latest_link(archive_root, monkeypatch):
    _freeze_time(monkeypatch, 3, 42)

    archive_handle.setup()

    assert archive_handle.get_archive_path() == str(archive_root / "openmethane-20261006-031542")
    assert (archive_root / "openmethane-20261006-031542").is_dir()
    link = archive_root / "openmethane-latest"
    assert link.is_symlink()
    # relative, so the archive can be moved or bind mounted
    assert link.readlink().as_posix() == "openmethane-20261006-031542"


def test_latest_link_follows_newest_run_and_keeps_old_runs(archive_root, monkeypatch):
    _freeze_time(monkeypatch, 3)
    archive_handle.setup()
    (archive_root / "openmethane-20261006-031500" / "result.nc").write_text("first")

    _freeze_time(monkeypatch, 5)
    monkeypatch.setattr(archive_handle, "finished_setup", False)
    archive_handle.setup()

    assert archive_handle.get_archive_path() == str(archive_root / "openmethane-20261006-051500")
    assert (archive_root / "openmethane-latest").resolve() == (
        archive_root / "openmethane-20261006-051500"
    )
    assert (archive_root / "openmethane-20261006-031500" / "result.nc").read_text() == "first"


def test_same_second_start_fails_rather_than_reusing_directory(monkeypatch):
    _freeze_time(monkeypatch, 3)
    archive_handle.setup()

    monkeypatch.setattr(archive_handle, "finished_setup", False)
    with pytest.raises(FileExistsError):
        archive_handle.setup()


def test_existing_directories_are_left_alone(archive_root, monkeypatch):
    (archive_root / "openmethane").mkdir()
    (archive_root / "openmethane" / "old.nc").write_text("old")
    _freeze_time(monkeypatch, 3)

    archive_handle.setup()

    assert (archive_root / "openmethane" / "old.nc").read_text() == "old"


def test_setup_is_idempotent(monkeypatch):
    _freeze_time(monkeypatch, 3)
    archive_handle.setup()
    path = archive_handle.get_archive_path()

    _freeze_time(monkeypatch, 5)
    archive_handle.setup()

    assert archive_handle.get_archive_path() == path
