"""Admin M1 tables (migration m1_0014) on their own MetaData: never part of the business SQLModel
metadata, so SQLite create_all and the business app never see them. PostgreSQL only.
"""
from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, MetaData, String, Table
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData()

admingrant = Table(
    'admingrant', metadata,
    Column('user_id', String, primary_key=True),
    Column('role', String(32), nullable=False),
    Column('active', Boolean, nullable=False),
    Column('revision', BigInteger, nullable=False),
    Column('granted_at', DateTime(timezone=True), nullable=False),
    Column('granted_by', String(128), nullable=False),
    Column('reason', String(2000), nullable=False),
)

adminsession = Table(
    'adminsession', metadata,
    Column('id', String(64), primary_key=True),
    Column('token_hash', String(64), nullable=False, unique=True),
    Column('user_id', String, nullable=False),
    Column('created_at', DateTime(timezone=True), nullable=False),
    Column('expires_at', DateTime(timezone=True), nullable=False),
    Column('revoked_at', DateTime(timezone=True)),
)

accountcontrol = Table(
    'accountcontrol', metadata,
    Column('user_id', String, primary_key=True),
    Column('enabled', Boolean, nullable=False),
    Column('revision', BigInteger, nullable=False),
    Column('auth_revision', BigInteger, nullable=False),
    Column('protected_account', Boolean, nullable=False),
    Column('updated_at', DateTime(timezone=True), nullable=False),
)

adminaudit = Table(
    'adminaudit', metadata,
    Column('event_id', String(64), primary_key=True),
    Column('recorded_at', DateTime(timezone=True), nullable=False),
    Column('actor_user_id', String),
    Column('actor_kind', String(16), nullable=False),
    Column('action', String(64), nullable=False),
    Column('target_user_id', String),
    Column('outcome', String(16), nullable=False),
    Column('reason', String(2000)),
    Column('request_id', String(64), nullable=False),
    Column('changes', JSONB),
)

adminloginthrottle = Table(
    'adminloginthrottle', metadata,
    Column('key_hash', String(64), primary_key=True),
    Column('window_start', DateTime(timezone=True), nullable=False),
    Column('failures', Integer, nullable=False),
)
