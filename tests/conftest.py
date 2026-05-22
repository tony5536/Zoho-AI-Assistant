import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts._helpers import build_test_service  # noqa: E402


@pytest.fixture
async def service(tmp_path):
    db = tmp_path / "test.db"
    svc = await build_test_service(db)
    yield svc
