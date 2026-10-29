"""Local integration server: the admin API (/api/admin/v1) and the built admin frontend (/admin/) on one
origin, like production. Configuration only from the environment (DB_URL, ADMIN_*, ADMIN_DIST;
ADMIN_FAKE_STRIPE=1 swaps in the synthetic payment reader)."""
import os

from fastapi.staticfiles import StaticFiles

from app.admin.app import build_asgi
from app.admin.config import AdminSettings
from app.db import build_engine


class SyntheticSessionReader:
    """ADMIN_FAKE_STRIPE=1 only (this test module): answers the seeded Checkout Session, never calls Stripe."""

    def read(self, session_id):
        from app.admin.seed_synthetic import REISSUE_SESSION, fake_paid_session
        from app.services.support_payment_check import ReaderUnavailable
        if session_id != REISSUE_SESSION:
            raise ReaderUnavailable()
        return fake_paid_session(session_id)


reader = SyntheticSessionReader() if os.environ.get('ADMIN_FAKE_STRIPE') == '1' else None
app = build_asgi(AdminSettings.from_env(), build_engine(os.environ['DB_URL'], role='api'), session_reader=reader)
app.mount('/admin', StaticFiles(directory=os.environ['ADMIN_DIST'], html=True), name='admin-static')
