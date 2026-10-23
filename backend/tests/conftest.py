import os
import tempfile
from pathlib import Path

# Hermetic test DB: the default DB_URL "sqlite:///./jobs.db" (relative to CWD)
# persists across test runs and leaks rows, making the count assertion in
# test_jobs.py::test_cleanup_expired_removes_file flaky. Redirect DB_URL to a
# fresh temp file BEFORE app.db is first imported — pytest imports conftest.py
# at collection time, before any test module imports app.*, so Settings.from_env()
# reads this value when the engine singleton is first created.
_tmpdir = Path(tempfile.mkdtemp(prefix="video-dl-tests-"))
_tmp_db = (_tmpdir / "test.db").as_posix()
os.environ["DB_URL"] = f"sqlite:///{_tmp_db}"


import pytest


@pytest.fixture
def vip_entitlements(monkeypatch):
    """Legacy route mechanics run as entitled users; H-005 tests exercise real DB gates."""
    monkeypatch.setattr("app.services.membership.is_vip", lambda session, uid: True)


@pytest.fixture
def legacy_daily_quota(monkeypatch, vip_entitlements):
    """Keep old finite-quota race and exemption regression coverage explicit."""
    from app.config import settings
    monkeypatch.setattr(settings, "membership_unlimited_downloads", False)
