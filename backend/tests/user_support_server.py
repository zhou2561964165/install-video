"""Local integration server for the user side: the business app (/api, SQLite from DB_URL) plus the built user
frontend (FRONTEND_DIST) on one origin. Seeds one synthetic user with an appealable order. Test use only."""
import os
import time

from fastapi.staticfiles import StaticFiles
from sqlmodel import Session

from app.db import engine
from app.main import app
from app.models import BillingCheckout, User
from app.services.auth import hash_password
from user_support_constants import EMAIL, PASSWORD

with Session(engine) as session:
    if session.get(User, 'syn-support-user') is None:
        session.add(User(id='syn-support-user', email=EMAIL, password_hash=hash_password(PASSWORD)))
        session.add(BillingCheckout(id='co-syn-appeal01', user_id='syn-support-user', price_id='price_synthetic',
                                    mode='payment', duration_days=30, origin='http://127.0.0.1',
                                    created_at=time.time() - 3600, state='open', fulfilled=False))
        session.commit()

app.mount('/', StaticFiles(directory=os.environ['FRONTEND_DIST'], html=True), name='user-frontend')
