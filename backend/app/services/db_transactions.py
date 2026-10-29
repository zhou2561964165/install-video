"""Short, local-only database transactions. Never put network/filesystem I/O in action.

The runner owns its Session and commit. A resolver must prove the complete domain
commit by stable operation ID; absence alone is UNKNOWN, not proof of rollback.
"""
from dataclasses import dataclass
from enum import Enum
import random
import time
from typing import Callable, Generic, TypeVar

from fastapi import HTTPException
from sqlalchemy import Engine, event
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlmodel import Session, select

from ..models import User

T = TypeVar('T')
RETRY_STATES = frozenset({'40P01', '40001', '55P03'})
CONFLICT_CONSTRAINTS = frozenset({
    'pk_quotacharge', 'pk_resourcereservation', 'pk_resourcecounter', 'pk_downloadoperation',
    'uq_quota_user_date', 'uq_download_idempotency_user_key',
    'uq_downloadidempotency_operation_id', 'uq_downloadoperation_job_id',
})
LOCK_INFO_KEYS = ('b2_locked_users', 'b2_capacity_locks', 'b2_domain_started', 'b2_operations_locked')


class ResolutionState(str, Enum):
    COMMITTED = 'committed'
    ROLLED_BACK = 'rolled_back'
    UNKNOWN = 'unknown'


@dataclass(frozen=True)
class CommitResolution(Generic[T]):
    state: ResolutionState
    value: T | None = None


class LocalSession(Session):
    """An action can flush, but cannot end the runner's transaction."""

    def commit(self):
        raise RuntimeError('Local database action must not commit')

    def rollback(self):
        raise RuntimeError('Local database action must not rollback')


def transaction_error(operation_id: str, *, uncertain: bool = False) -> HTTPException:
    return HTTPException(503, detail={
        'error_type': 'transaction_uncertain' if uncertain else 'database_unavailable',
        'error': '提交结果待核对，请保留原请求标识' if uncertain else '数据库暂不可用，请稍后重试',
        'operation_id': operation_id,
    })


def _sqlstate(error: Exception) -> str | None:
    return getattr(getattr(error, 'orig', error), 'sqlstate', None)


def _rollback(session: Session) -> bool:
    try:
        Session.rollback(session)
        return True
    except Exception:
        return False


def _database_error(operation_id: str, error: DBAPIError) -> HTTPException:
    if isinstance(error, IntegrityError):
        name = getattr(getattr(error.orig, 'diag', None), 'constraint_name', None)
        detail = {'error_type': 'database_conflict', 'error': '提交记录冲突', 'operation_id': operation_id}
        if name in CONFLICT_CONSTRAINTS:
            detail['constraint_code'] = name
        return HTTPException(409, detail=detail)
    return transaction_error(operation_id)


def run_local_transaction(
    engine: Engine, operation_id: str, action: Callable[[Session], T],
    resolve_unknown: Callable[[Session, str], CommitResolution[T]], *,
    sleeper: Callable[[float], None] = time.sleep,
    jitter: Callable[[], float] = random.random,
) -> T:
    """Run at most three pure DB attempts; never replay an ambiguous commit.

Resolvers get a fresh, read-only transaction and must return an explicit enum.
They must not interpret a temporarily absent operation as definite rollback.
IntegrityError/unique conflicts are caller-owned and are never ignored here.
"""
    if not isinstance(operation_id, str) or not operation_id or len(operation_id) > 128:
        raise ValueError('A bounded stable operation ID is required')
    for attempt in range(3):
        retry = False
        unknown_commit = False
        safe_error = None
        # A connection per attempt ensures an invalidated session is never reused.
        connection = None
        session = None
        try:
            connection = engine.connect()
            if engine.dialect.name == 'postgresql':
                connection = connection.execution_options(isolation_level='READ COMMITTED')
            session = LocalSession(bind=connection, expire_on_commit=False)
            try:
                value = action(session)
                session.flush()
            except Exception as error:
                rolled_back = _rollback(session)
                if _sqlstate(error) in RETRY_STATES and rolled_back:
                    retry = True
                elif isinstance(error, DBAPIError):
                    # Do not expose SQL, DSN or parameters through exception chains.
                    safe_error = _database_error(operation_id, error)
                else:
                    raise
            else:
                try:
                    Session.commit(session)
                    return value
                except Exception as error:
                    if _sqlstate(error) in RETRY_STATES and _rollback(session):
                        retry = True
                    elif isinstance(error, IntegrityError) and _rollback(session):
                        safe_error = _database_error(operation_id, error)
                    else:
                        # Rollback here can only clean up the client, not prove that
                        # the server did not commit. Resolve using another connection.
                        unknown_commit = True
                        try:
                            session.invalidate()
                        except Exception:
                            pass
        except DBAPIError as error:
            safe_error = _database_error(operation_id, error)
        finally:
            if session is not None:
                try:
                    session.close()
                except Exception:
                    pass
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass
        # Raise after leaving all exception handlers. `from None` alone suppresses
        # formatting but retains __context__, potentially retaining SQL credentials.
        if safe_error is not None:
            raise safe_error from None
        if unknown_commit:
            resolution = CommitResolution(ResolutionState.UNKNOWN)
            try:
                with engine.connect() as fresh:
                    if engine.dialect.name == 'postgresql':
                        fresh = fresh.execution_options(isolation_level='READ COMMITTED')
                    with LocalSession(bind=fresh, expire_on_commit=False) as resolver_session:
                        if engine.dialect.name == 'postgresql':
                            from sqlalchemy import text
                            resolver_session.exec(text('SET TRANSACTION READ ONLY'))
                        result = resolve_unknown(resolver_session, operation_id)
                        if type(result) is CommitResolution and type(result.state) is ResolutionState:
                            resolution = result
            except Exception:
                pass
            if resolution.state is ResolutionState.COMMITTED:
                return resolution.value
            if resolution.state is ResolutionState.ROLLED_BACK:
                retry = True
            else:
                raise transaction_error(operation_id, uncertain=True) from None
        if not retry or attempt == 2:
            raise transaction_error(operation_id) from None
        sleeper((0.020, 0.100)[attempt] * (1 + min(1.0, max(0.0, jitter()))))
    raise AssertionError('unreachable')


def lock_user(session: Session, user_id: str) -> User:
    """Lock an existing stable user; never create a development account."""
    locked_users = session.info.setdefault('b2_locked_users', set())
    if user_id not in locked_users and session.info.get('b2_operations_locked'):
        raise RuntimeError('User must be locked before operation')
    if locked_users and user_id not in locked_users and user_id < max(locked_users):
        raise RuntimeError('Users must be locked in ID order')
    with session.no_autoflush:
        user = session.exec(select(User).where(User.id == user_id).with_for_update()).first()
    if user is None:
        raise HTTPException(404, detail={'error_type': 'user_not_found', 'error': '用户不存在'})
    locked_users.add(user_id)
    session.info['b2_domain_started'] = True
    return user


@event.listens_for(Session, 'after_transaction_end')
def _clear_lock_tracking(session: Session, transaction) -> None:
    if transaction.parent is None:
        for key in LOCK_INFO_KEYS:
            session.info.pop(key, None)


@event.listens_for(Session, 'after_transaction_create')
def _snapshot_savepoint_locks(session: Session, transaction) -> None:
    if transaction.nested:
        transaction._b2_lock_snapshot = {
            key: set(value) if isinstance(value, set) else value
            for key, value in session.info.items() if key in LOCK_INFO_KEYS}


@event.listens_for(Session, 'after_soft_rollback')
def _restore_savepoint_locks(session: Session, transaction) -> None:
    # PostgreSQL releases locks acquired after a savepoint when rolling it back.
    # Retaining those keys would falsely claim the outer transaction still holds them.
    if transaction.nested:
        snapshot = getattr(transaction, '_b2_lock_snapshot', {})
        for key in LOCK_INFO_KEYS:
            session.info.pop(key, None)
        session.info.update(snapshot)
