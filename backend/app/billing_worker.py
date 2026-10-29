"""Explicit durable worker CLI: python -m app.billing_worker [--once].

No manual replay/reset command. The full PG web application remains gated by B1.
"""
import argparse
import logging
import time
import uuid

from .config import settings
from .db import build_engine, assert_schema_current
from .services import billing
from .services.billing_pg import BillingConfiguration
from .services.billing_inbox import run_once


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    engine = build_engine(settings.db_url, role='worker')
    owner = 'billing-' + str(uuid.uuid4())
    try:
        cfg = BillingConfiguration.configured(settings, engine.dialect.name)
        assert_schema_current(engine)
        while True:
            try:
                outcome = run_once(engine, cfg, billing.client, owner)
            except Exception:
                # A failed/unknown commit never starts an unowned retry; the
                # persisted lease and attempt budget govern later recovery.
                logging.getLogger(__name__).error('Billing worker attempt did not complete')
                if args.once:
                    raise SystemExit(1) from None
                outcome = None
            if args.once:
                return
            if outcome is None:
                time.sleep(1)
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
