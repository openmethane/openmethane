from datetime import UTC, datetime

import pytest

from openmethane.fourdvar.params import archive_defn
from openmethane.fourdvar.util import archive_handle


@pytest.fixture
def archive(tmp_path, monkeypatch):
    monkeypatch.setattr(archive_defn, "archive_path", str(tmp_path))
    monkeypatch.setattr(archive_defn, "experiment", "openmethane")
    monkeypatch.setattr(archive_defn, "desc_name", "")
    monkeypatch.setattr(archive_handle, "finished_setup", False)
    monkeypatch.setattr(archive_handle, "archive_path", "")

    def start_run(hour: int, second: int = 0):
        moment = datetime(2026, 10, 6, hour, 15, second, tzinfo=UTC)
        monkeypatch.setattr(archive_handle, "_utcnow", lambda: moment)
        monkeypatch.setattr(archive_handle, "finished_setup", False)
        archive_handle.setup()
        return archive_handle.get_archive_path()

    return tmp_path, start_run


def test_creates_timestamped_directory_and_latest_link(archive):
    root, start_run = archive

    path = start_run(3, 42)

    assert path == str(root / "openmethane-20261006-031542")
    assert (root / "openmethane-20261006-031542").is_dir()
    link = root / "openmethane-latest"
    assert link.is_symlink()
    # relative, so the archive can be moved or bind mounted
    assert link.readlink().as_posix() == "openmethane-20261006-031542"


def test_latest_link_follows_newest_run_and_keeps_old_runs(archive):
    root, start_run = archive

    first = start_run(3)
    (root / "openmethane-20261006-031500" / "result.nc").write_text("first")
    second = start_run(5)

    assert first != second
    assert (root / "openmethane-latest").resolve() == (root / "openmethane-20261006-051500")
    assert (root / "openmethane-20261006-031500" / "result.nc").read_text() == "first"


def test_same_second_start_fails_rather_than_reusing_directory(archive):
    _, start_run = archive

    start_run(3)
    with pytest.raises(FileExistsError):
        start_run(3)


def test_existing_directories_are_left_alone(archive):
    root, start_run = archive
    (root / "openmethane").mkdir()
    (root / "openmethane" / "old.nc").write_text("old")

    start_run(3)

    assert (root / "openmethane" / "old.nc").read_text() == "old"


def test_setup_is_idempotent(archive):
    _, start_run = archive

    path = start_run(3)
    archive_handle.setup()

    assert archive_handle.get_archive_path() == path
