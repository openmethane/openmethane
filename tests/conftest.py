from pathlib import Path

import pytest


@pytest.fixture
def root_dir() -> Path:
    return Path(__file__).parent.parent


@pytest.fixture
def test_data_dir(root_dir) -> Path:
    return root_dir / "tests" / "test-data"
