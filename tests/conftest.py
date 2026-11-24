from pathlib import Path

import pytest

from pipeline.session import get_spark

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def spark():
    session = get_spark("onboarding-tests", "UTC")
    yield session
    session.stop()
