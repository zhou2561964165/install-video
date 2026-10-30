"""Pure entitlement rules: no configuration, database or network is involved."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

NOW = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)


@pytest.mark.parametrize('mode,deadline,paid,status,effective,reason,permanent', [
    ('auto', None, 30, 'active', True, 'payment_active', False),
    ('auto', None, 0, 'active', False, 'payment_expired', False),
    ('auto', None, 30, 'free', False, 'payment_inactive', False),
    ('enabled', None, -30, 'free', True, 'admin_enabled', True),
    ('enabled', 30, -30, 'free', True, 'admin_enabled', False),
    ('enabled', 0, 30, 'active', False, 'admin_expired', False),
    ('enabled', -30, 30, 'active', False, 'admin_expired', False),
    ('disabled', None, 30, 'active', False, 'admin_disabled', False),
])
def test_admin_control_precedence_and_exact_expiry(mode, deadline, paid, status, effective, reason, permanent):
    from app.services.membership_policy import resolve
    payment = SimpleNamespace(status=status, expires_at=NOW.timestamp() + paid)
    control = SimpleNamespace(mode=mode, expires_at=None if deadline is None else NOW + timedelta(seconds=deadline))
    result = resolve(payment, control, NOW)
    assert (result.effective, result.reason, result.permanent) == (effective, reason, permanent)
    expected = control.expires_at if mode == 'enabled' else (
        datetime.fromtimestamp(payment.expires_at, timezone.utc) if mode == 'auto' else None)
    assert result.expires_at == expected


def test_no_payment_or_control_is_free_and_explicit_enable_can_grant():
    from app.services.membership_policy import resolve
    assert resolve(None, None, NOW).effective is False
    assert resolve(None, None, NOW).reason == 'payment_inactive'
    assert resolve(None, SimpleNamespace(mode='enabled', expires_at=None), NOW).permanent is True


def test_sql_and_python_agree_for_missing_payment_and_control():
    from sqlalchemy import Column, DateTime, Float, MetaData, String, Table, create_engine, select
    from app.services.membership_policy import effective_sql, resolve
    metadata = MetaData()
    payment = Table('payment', metadata, Column('user_id', String, primary_key=True),
                    Column('status', String), Column('expires_at', Float))
    control = Table('control', metadata, Column('user_id', String, primary_key=True),
                    Column('mode', String), Column('expires_at', DateTime(timezone=True)))
    users = Table('users', metadata, Column('id', String, primary_key=True))
    engine = create_engine('sqlite://')
    metadata.create_all(engine)
    cases = [('missing', None, None), ('paid', ('active', 30), None),
             ('disabled', ('active', 30), ('disabled', None)),
             ('permanent', None, ('enabled', None)),
             ('boundary', ('active', 30), ('enabled', NOW)),
             ('future', ('free', -30), ('enabled', NOW + timedelta(seconds=30)))]
    with engine.begin() as connection:
        for uid, p, c in cases:
            connection.execute(users.insert().values(id=uid))
            if p:
                connection.execute(payment.insert().values(user_id=uid, status=p[0], expires_at=NOW.timestamp()+p[1]))
            if c:
                connection.execute(control.insert().values(user_id=uid, mode=c[0], expires_at=c[1]))
        statement = select(users.c.id, effective_sql(NOW, payment, control)).select_from(
            users.outerjoin(payment, payment.c.user_id == users.c.id).outerjoin(control, control.c.user_id == users.c.id))
        actual = dict(connection.execute(statement).all())
    expected = {uid: resolve(SimpleNamespace(status=p[0], expires_at=NOW.timestamp()+p[1]) if p else None,
                            SimpleNamespace(mode=c[0], expires_at=c[1]) if c else None, NOW).effective
                for uid, p, c in cases}
    assert actual == expected
