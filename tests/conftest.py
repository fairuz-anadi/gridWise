import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PUBLIC_CASES = json.loads((ROOT / "tests/fixtures/public_cases.json").read_text(encoding="utf-8"))["cases"]


@pytest.fixture(params=PUBLIC_CASES, ids=[c["id"] for c in PUBLIC_CASES])
def public_case(request) -> dict:
    return request.param
