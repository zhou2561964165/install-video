"""Atomic PG admission counters. All functions compose; none commits.

New acceptance: lock_capacity_counters -> User -> Membership -> receipt ->
operation INSERT -> reserve_capacity -> Quota/Charge -> Job/Access.
Only trusted deployment settings supply limits. No DTO accepts a limit.
"""
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import exists, func, update
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import Session, select

from ..config import settings
from ..models import DownloadOperation, ResourceCounter, ResourceReservation


@dataclass(frozen=True)
class CapacityDemand:
    resource: str
    scope: str
    units: int = 1


def _error(resource: str = 'admission_slots') -> HTTPException:
    receipt = resource == 'receipt_entries'
    return HTTPException(503, detail={
        'error_type': 'idempotency_unavailable' if receipt else 'download_capacity',
        'error': '请求记录容量暂不可用' if receipt else '下载任务容量暂不可用',
    })


def _demands(demands: tuple[CapacityDemand, ...]) -> tuple[CapacityDemand, ...]:
    if type(demands) is not tuple or not demands:
        raise ValueError('A nonempty tuple of capacity demands is required')
    keys = set()
    for demand in demands:
        if type(demand) is not CapacityDemand or type(demand.units) is not int or not 1 <= demand.units <= 100000:
            raise ValueError('Invalid capacity units')
        if type(demand.resource) is not str or demand.resource not in {'admission_slots', 'receipt_entries'}:
            raise ValueError('Unknown capacity resource')
        if type(demand.scope) is not str or not (demand.scope == 'global' or (demand.resource == 'admission_slots' and
                demand.scope.startswith('user:') and 5 < len(demand.scope) <= 133)):
            raise ValueError('Invalid capacity scope')
        key = (demand.resource, demand.scope)
        if key in keys:
            raise ValueError('Duplicate capacity demand')
        keys.add(key)
    return tuple(sorted(demands, key=lambda item: (item.resource, item.scope)))


def _limit(demand: CapacityDemand) -> int:
    if demand.resource == 'receipt_entries':
        limit = settings.download_idempotency_max_entries
    else:
        limit = (settings.download_admission_global_limit if demand.scope == 'global'
                 else settings.download_admission_user_limit)
    if type(limit) is not int or not 1 <= limit <= 100000:
        raise _error(demand.resource)
    return limit


def lock_capacity_counters(session: Session, demands: tuple[CapacityDemand, ...]) -> None:
    """Acquire all required resource rows first, in fixed dictionary order.

Session tracking rejects adding counters after domain locks or lower counters.
Raw SQL locks outside these interfaces remain the caller's responsibility.
"""
    ordered = _demands(demands)
    locked = session.info.setdefault('b2_capacity_locks', set())
    for demand in ordered:
        key = (demand.resource, demand.scope)
        if key in locked:
            continue
        if session.info.get('b2_domain_started') or (locked and key < max(locked)):
            raise RuntimeError('Capacity counters must be locked before domain rows, in order')
        with session.no_autoflush:
            if demand.scope != 'global':
                session.exec(insert(ResourceCounter).values(
                    resource=demand.resource, scope=demand.scope, used=0,
                ).on_conflict_do_nothing(index_elements=['resource', 'scope']))
            counter = session.exec(select(ResourceCounter).where(
                ResourceCounter.resource == demand.resource, ResourceCounter.scope == demand.scope,
            ).with_for_update()).first()
        if counter is None:
            raise _error(demand.resource)
        locked.add(key)


def _change_counter(session: Session, demand: CapacityDemand, *, release: bool = False) -> None:
    statement = update(ResourceCounter).where(
        ResourceCounter.resource == demand.resource, ResourceCounter.scope == demand.scope,
    )
    if release:
        statement = statement.where(ResourceCounter.used >= demand.units).values(
            used=ResourceCounter.used - demand.units)
    else:
        statement = statement.where(ResourceCounter.used + demand.units <= _limit(demand)).values(
            used=ResourceCounter.used + demand.units)
    if session.exec(statement.returning(ResourceCounter.used)).first() is None:
        raise _error(demand.resource)


def _operation(session: Session, operation_id: str) -> DownloadOperation:
    session.flush()
    operation = session.exec(select(DownloadOperation).where(
        DownloadOperation.id == operation_id).with_for_update().execution_options(populate_existing=True)).first()
    if operation is None:
        raise _error()
    session.info['b2_domain_started'] = True
    session.info.setdefault('b2_operations_locked', set()).add(operation_id)
    return operation


def reserve_capacity(session: Session, demands: tuple[CapacityDemand, ...], *, operation_id: str) -> None:
    """Reserve each op/resource/scope once. Released facts are never reopened."""
    ordered = _demands(demands)
    if any(item.resource != 'admission_slots' for item in ordered):
        raise ValueError('Receipt capacity has its own transaction interface')
    lock_capacity_counters(session, ordered)
    operation = _operation(session, operation_id)
    expected = {('admission_slots', 'global'), ('admission_slots', 'user:' + operation.user_id)}
    if ({(item.resource, item.scope) for item in ordered} != expected or
            len({item.units for item in ordered}) != 1 or
            operation.state not in {'resolving', 'accepted_server'}):
        raise _error()
    for demand in ordered:
        if demand.scope != 'global' and demand.scope != 'user:' + operation.user_id:
            raise _error()
        reservation = session.get(ResourceReservation, (operation_id, demand.resource, demand.scope),
                                  populate_existing=True)
        if reservation is not None:
            if reservation.units != demand.units or reservation.released:
                raise _error()
            continue
        _change_counter(session, demand)
        session.add(ResourceReservation(operation_id=operation_id, resource=demand.resource,
            scope=demand.scope, units=demand.units, reserved_at=session.exec(select(func.clock_timestamp())).one()))
    session.flush()
    operation.capacity_reserved = True
    session.add(operation)


def release_capacity(session: Session, operation_id: str, resources: tuple[str, ...]) -> None:
    """Release selected resource names across all scopes for this operation.

Discover IDs without locking; then counters -> operation -> reservation CAS.
CAS rowcount=0 is an idempotent no-op, never an additional decrement.
"""
    if resources != ('admission_slots',):
        raise ValueError('Only admission_slots is an operation resource')
    with session.no_autoflush:
        user_id = session.exec(select(DownloadOperation.user_id).where(
            DownloadOperation.id == operation_id)).first()
    if user_id is None:
        raise _error()
    # Lock the fixed supported scopes even if no reservation is visible yet. A
    # concurrent reserver commits before we re-read facts under these same locks.
    lock_capacity_counters(session, (CapacityDemand('admission_slots', 'global'),
                                    CapacityDemand('admission_slots', 'user:' + user_id)))
    operation = _operation(session, operation_id)
    if operation.user_id != user_id:
        raise _error()
    facts = session.exec(select(ResourceReservation).where(
        ResourceReservation.operation_id == operation_id,
        ResourceReservation.resource.in_(resources))).all()
    for fact in facts:
        if fact.scope != 'global' and fact.scope != 'user:' + operation.user_id:
            raise _error()
        changed = session.exec(update(ResourceReservation).where(
            ResourceReservation.operation_id == operation_id,
            ResourceReservation.resource == fact.resource, ResourceReservation.scope == fact.scope,
            ResourceReservation.released.is_(False),
        ).values(released=True, released_at=func.clock_timestamp()).returning(ResourceReservation.units)).first()
        if changed is not None:
            _change_counter(session, CapacityDemand(fact.resource, fact.scope, changed[0]), release=True)
    session.flush()
    remaining = session.exec(select(exists().where(
        ResourceReservation.operation_id == operation_id,
        ResourceReservation.released.is_(False)))).one()
    operation.capacity_reserved = remaining
    session.add(operation)


def reserve_receipt_entry(session: Session) -> None:
    """Increment once only when the caller inserts a NEW receipt in this transaction.

Prelock this counter with admission counters before any User/receipt row lock.
The caller must rollback on any later failure, and replay never calls this.
"""
    demand = CapacityDemand('receipt_entries', 'global')
    lock_capacity_counters(session, (demand,))
    _change_counter(session, demand)


def release_receipt_entry(session: Session) -> None:
    """Decrement only for a caller-confirmed receipt DELETE in this same txn.

The caller checks DELETE RETURNING/rowcount=1. No age/COUNT based repair.
"""
    demand = CapacityDemand('receipt_entries', 'global')
    lock_capacity_counters(session, (demand,))
    _change_counter(session, demand, release=True)
