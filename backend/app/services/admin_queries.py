"""Admin read model: one REPEATABLE READ read-only snapshot per request, a data-driven list-query
registry (filters/sorts per contract list operation), pagination and safe projections.

Never writes, never calls a provider, never imports the download core. Every list query is
validated against RESOURCES; unknown names, values or sorts are 422 (no SQL is built from input).
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace
import re

from sqlalchemy import and_, case, func, select, text

from ..admin.errors import AdminError
from ..models import Job, Membership, MembershipControl, User
from .membership_policy import effective_sql, resolve

_ID = re.compile(r'[A-Za-z0-9_.:-]{1,256}\Z')
_PAGE = re.compile(r'[0-9]{1,9}\Z')       # ASCII only; str.isdigit accepts e.g. '\u00b2'
_PAGE_SIZE = re.compile(r'[0-9]{1,4}\Z')
_UTC = re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z\Z')


@dataclass(frozen=True)
class FilterSpec:
    name: str
    kind: str                      # enum | boolean | text | id | datetime
    allowed: tuple = ()            # enum values (as served in meta: strings)
    max_length: int | None = None  # text
    integer: bool = False          # enum of integers (execution_version)


@dataclass(frozen=True)
class ResourceSpec:
    sorts: tuple[str, ...]
    default_sort: str
    filters: tuple[FilterSpec, ...]


@dataclass(frozen=True)
class ListQuery:
    page: int
    page_size: int
    sort_field: str
    descending: bool
    filters: dict


def _enum(name, values, integer=False):
    return FilterSpec(name, 'enum', tuple(str(v) for v in values), integer=integer)


# Mirrors the list operations of contract 1.0.0-proposal.20261028.3 (checked by tests against the YAML).
RESOURCES: dict[str, ResourceSpec] = {
    'adminListUsers': ResourceSpec(('created_at:asc', 'created_at:desc', 'email:asc', 'email:desc'), 'created_at:desc', (
        FilterSpec('email', 'text', max_length=254), FilterSpec('enabled', 'boolean'),
        FilterSpec('effective_vip', 'boolean'))),
    'adminListJobs': ResourceSpec(('created_at:asc', 'created_at:desc', 'updated_at:asc', 'updated_at:desc'), 'created_at:desc', (
        FilterSpec('user_id', 'id'), _enum('public_status', ('queued', 'downloading', 'merging', 'done', 'error')),
        _enum('internal_state', ('queued', 'running', 'retry_wait', 'succeeded', 'failed', 'needs_review',
                                 'legacy_hold', 'legacy_unset')),
        _enum('execution_version', (1, 2), integer=True))),
    'adminListMemberships': ResourceSpec(('expires_at:asc', 'expires_at:desc', 'user_id:asc'), 'user_id:asc', (
        FilterSpec('user_id', 'id'), FilterSpec('effective', 'boolean'), _enum('status', ('free', 'active', 'expired')))),
    'adminListCheckouts': ResourceSpec(('created_at:asc', 'created_at:desc'), 'created_at:desc', (
        FilterSpec('user_id', 'id'), _enum('state', ('pending', 'open', 'paid', 'expired', 'failed')),
        _enum('reconciliation', ('not_started', 'unknown', 'verified', 'needs_review', 'closed')),
        FilterSpec('fulfilled', 'boolean'), FilterSpec('provider_account_scope', 'text', max_length=128),
        FilterSpec('livemode', 'boolean'))),
    'adminListPayments': ResourceSpec(('id:asc', 'id:desc'), 'id:asc', (
        FilterSpec('user_id', 'id'), FilterSpec('revoked', 'boolean'), FilterSpec('payment_id', 'id'))),
    'adminListSupportTickets': ResourceSpec(('priority:desc', 'created_at:asc', 'created_at:desc'), 'priority:desc', (
        _enum('state', ('open', 'resolved', 'rejected')),
        _enum('category', ('membership_not_credited', 'download_failing', 'login_problem', 'other')),
        _enum('priority', ('priority', 'normal')), FilterSpec('user_id', 'id'))),
    'adminListAuditLogs': ResourceSpec(('recorded_at:asc', 'recorded_at:desc'), 'recorded_at:desc', (
        FilterSpec('actor_user_id', 'id'), FilterSpec('target_user_id', 'id'), FilterSpec('action', 'text', max_length=64),
        _enum('outcome', ('succeeded', 'denied', 'failed')), FilterSpec('recorded_from', 'datetime'),
        FilterSpec('recorded_before', 'datetime'))),
}

STATE_DICTIONARIES = (
    ('job.public_status', (('queued', '排队中', 'info'), ('downloading', '下载中', 'info'), ('merging', '合并中', 'info'),
                           ('done', '已完成', 'success'), ('error', '失败', 'error'))),
    ('job.internal_state', (('queued', '等待执行', 'info'), ('running', '执行中', 'info'), ('retry_wait', '等待重试', 'warning'),
                            ('succeeded', '成功', 'success'), ('failed', '失败', 'error'),
                            ('needs_review', '需人工复核', 'warning'), ('legacy_hold', '旧版保留', 'neutral'),
                            ('legacy_unset', '旧版未设置', 'neutral'))),
    ('membership.status', (('free', '暂无付款会员', 'neutral'), ('active', '原会员记录已启用', 'success'), ('expired', '原会员记录已到期', 'warning'))),
    ('checkout.state', (('pending', '待创建', 'neutral'), ('open', '待支付', 'info'), ('paid', '订单标记已付款', 'success'),
                        ('expired', '已过期', 'neutral'), ('failed', '失败', 'error'))),
    ('reconciliation', (('not_started', '未开始', 'neutral'), ('unknown', '待确认', 'warning'),
                        ('verified', '已核实', 'success'), ('needs_review', '需人工复核', 'warning'),
                        ('closed', '已关闭', 'neutral'))),
    ('job.attempt', (('running', '执行中', 'info'), ('lost', '已中断', 'warning'), ('failed', '失败', 'error'),
                     ('succeeded', '成功', 'success'))),
    ('audit.outcome', (('succeeded', '成功', 'success'), ('denied', '已拒绝', 'warning'), ('failed', '失败', 'error'))),
    ('system.status', (('ok', '正常', 'success'), ('degraded', '降级', 'warning'), ('unavailable', '不可用', 'error'),
                       ('unknown', '未知', 'neutral'))),
)  # domain names are exactly the ones the admin frontend renders (AdminStateTag)


@contextmanager
def read_snapshot(engine):
    """One consistent read-only snapshot; as_of is that transaction's DB clock (UTC)."""
    with engine.connect().execution_options(isolation_level='REPEATABLE READ', postgresql_readonly=True) as connection:
        with connection.begin():
            yield connection, connection.scalar(text('SELECT now()'))


def _field_error(errors: list, name: str) -> None:
    errors.append({'field': name, 'message': '字段值不合法'})


def _value(spec: FilterSpec, raw: str):
    if spec.kind == 'boolean':
        if raw not in ('true', 'false'):
            raise ValueError
        return raw == 'true'
    if spec.kind == 'enum':
        if raw not in spec.allowed:
            raise ValueError
        return int(raw) if spec.integer else raw
    if spec.kind == 'id':
        if not _ID.match(raw):
            raise ValueError
        return raw
    if spec.kind == 'text':
        if not raw or len(raw) > spec.max_length:
            raise ValueError
        return raw
    if spec.kind == 'datetime':
        if not _UTC.match(raw):
            raise ValueError
        return datetime.fromisoformat(raw.replace('Z', '+00:00'))
    raise ValueError


def parse_list_query(spec: ResourceSpec, params, settings) -> ListQuery:
    errors: list = []
    known = {item.name: item for item in spec.filters}
    filters = {}
    page, page_size, sort = 1, settings.default_page_size, spec.default_sort
    for name in params:
        raw = params[name]
        if name == 'page':
            if not _PAGE.match(raw) or int(raw) < 1:
                _field_error(errors, name)
            else:
                page = int(raw)
        elif name == 'page_size':
            if not _PAGE_SIZE.match(raw) or not 1 <= int(raw) <= settings.max_page_size:
                _field_error(errors, name)
            else:
                page_size = int(raw)
        elif name == 'sort':
            if raw not in spec.sorts:
                _field_error(errors, name)
            else:
                sort = raw
        elif name in known:
            try:
                filters[name] = _value(known[name], raw)
            except ValueError:
                _field_error(errors, name)
        else:
            _field_error(errors, name)
    if errors:
        raise AdminError(422, 'validation_failed', field_errors=errors)
    field, direction = sort.split(':')
    return ListQuery(page, page_size, field, direction == 'desc', filters)


def paginate(connection, statement, query: ListQuery, sort_columns: dict, tiebreak, secondary: dict | None = None):
    """(rows, total) from one snapshot: total counts the filtered set; beyond the last page rows are [].
    `secondary` adds per-sort-field ORDER BY clauses before the id tiebreak."""
    total = connection.scalar(select(func.count()).select_from(statement.subquery()))
    column = sort_columns[query.sort_field]
    order = (column.desc() if query.descending else column.asc()).nulls_last()
    extra = list((secondary or {}).get(query.sort_field, ()))
    rows = connection.execute(statement.order_by(order, *extra, tiebreak.asc())
                              .offset((query.page - 1) * query.page_size).limit(query.page_size)).all()
    return rows, total


def effective_vip(as_of: datetime):
    return effective_sql(as_of, Membership.__table__, MembershipControl.__table__)


def overview(connection, as_of: datetime) -> dict:
    user, job, membership = User.__table__, Job.__table__, Membership.__table__
    by_status = connection.execute(select(job.c.status, func.count()).group_by(job.c.status)).all()
    internal = func.coalesce(job.c.internal_state, 'legacy_unset')
    by_internal = connection.execute(select(internal, func.count()).group_by(internal)).all()
    return {
        'as_of': as_of,
        'users_total': connection.scalar(select(func.count()).select_from(user)),
        'effective_vip_total': connection.scalar(select(func.count()).select_from(
            user.outerjoin(membership, membership.c.user_id == user.c.id)
                .outerjoin(MembershipControl.__table__, MembershipControl.user_id == user.c.id)).where(effective_vip(as_of))),
        'retained_server_jobs_total': connection.scalar(select(func.count()).select_from(job)),
        'jobs_by_public_status': [{'state': getattr(state, 'value', state), 'count': count}
                                  for state, count in sorted(by_status, key=lambda item: str(item[0]))],
        'jobs_by_internal_state': [{'state': state, 'count': count} for state, count in sorted(by_internal)],
        'scope': {'users': '全部注册用户', 'effective_vip': '管理员设置优先；自动管理按原会员记录已启用且在本次查询时间仍有效计算',
                  'jobs': '当前仍保留的服务端任务记录（不是全部下载次数，也不是营收）'},
    }


def system_components(as_of: datetime) -> list[dict]:
    """database is ok because this read-only query just succeeded; nothing else has a reliable sample in M1."""
    unknown = {'status': 'unknown', 'reason_code': 'no_reliable_sample', 'checked_at': None}
    return [{'component': 'database', 'status': 'ok', 'reason_code': None, 'checked_at': as_of},
            {'component': 'download_worker', **unknown}, {'component': 'billing_worker', **unknown},
            {'component': 'artifact_store', **unknown}]


# --- Users and memberships (Task 7) -------------------------------------------------------------

def _epoch_utc(value) -> datetime | None:
    if value is None or value <= 0:
        return None
    return datetime.fromtimestamp(value, tz=timezone.utc)


def membership_projection(row, user_id: str, as_of: datetime) -> dict:
    """Payment fields remain facts; effective fields follow the shared override policy."""
    get = lambda key, default=None: getattr(row, key, default) if row is not None else default
    payment = SimpleNamespace(status=get('m_status'), expires_at=get('m_expires_at', 0)) if get('m_status') else None
    control = SimpleNamespace(mode=get('mc_mode', 'auto'), expires_at=get('mc_expires_at'))
    actual = resolve(payment, control, as_of)
    return {'user_id': user_id, 'status': get('m_status') or 'free', 'effective': actual.effective,
            'expires_at': _epoch_utc(get('m_expires_at')), 'revision': str(get('m_revision')) if payment else None,
            'entitlement_source': get('m_source'), 'cancel_at_period_end': bool(get('m_cancel')),
            'control_mode': get('mc_mode') or 'auto', 'control_revision': str(get('mc_revision') or 0),
            'control_expires_at': get('mc_expires_at'), 'effective_reason': actual.reason,
            'effective_expires_at': actual.expires_at, 'effective_permanent': actual.permanent}


def membership_columns():
    membership, control = Membership.__table__, MembershipControl.__table__
    return (membership.c.status.label('m_status'), membership.c.expires_at.label('m_expires_at'),
            membership.c.revision.label('m_revision'), membership.c.entitlement_source.label('m_source'),
            membership.c.cancel_at_period_end.label('m_cancel'), membership.c.subscription_id.label('m_subscription'),
            control.c.mode.label('mc_mode'), control.c.revision.label('mc_revision'),
            control.c.expires_at.label('mc_expires_at'))


def _user_statement(operator_id: str):
    from ..models_admin import accountcontrol, admingrant
    user, membership = User.__table__, Membership.__table__
    protected = func.coalesce(accountcontrol.c.protected_account, False) | func.coalesce(admingrant.c.active, False) \
        | (user.c.id == operator_id)
    return select(
        user.c.id, user.c.email, user.c.created_at,
        func.coalesce(accountcontrol.c.enabled, True).label('enabled'),
        func.coalesce(accountcontrol.c.revision, 0).label('control_revision'), protected.label('protected'),
        *membership_columns(),
    ).select_from(user.outerjoin(accountcontrol, accountcontrol.c.user_id == user.c.id)
                  .outerjoin(admingrant, admingrant.c.user_id == user.c.id)
                  .outerjoin(membership, membership.c.user_id == user.c.id)
                  .outerjoin(MembershipControl.__table__, MembershipControl.user_id == user.c.id))


def _user_summary(row, as_of: datetime) -> dict:
    return {'id': row.id, 'email': row.email, 'created_at': row.created_at,
            'access': {'enabled': bool(row.enabled), 'revision': str(row.control_revision),
                       'protected_account': bool(row.protected)},
            'membership': membership_projection(row, row.id, as_of)}


def _like(value: str) -> str:
    return '%' + value.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'


def list_users(connection, as_of: datetime, query: ListQuery, operator_id: str):
    from ..models_admin import accountcontrol
    user, membership = User.__table__, Membership.__table__
    statement = _user_statement(operator_id)
    filters = query.filters
    if 'email' in filters:
        statement = statement.where(user.c.email.ilike(_like(filters['email']), escape='\\'))
    if 'enabled' in filters:
        statement = statement.where(func.coalesce(accountcontrol.c.enabled, True).is_(filters['enabled']))
    if 'effective_vip' in filters:
        condition = effective_vip(as_of)
        statement = statement.where(condition if filters['effective_vip'] else ~func.coalesce(condition, False))
    rows, total = paginate(connection, statement, query,
                           {'created_at': user.c.created_at, 'email': user.c.email}, user.c.id)
    return [_user_summary(row, as_of) for row in rows], total


def quota_projection(connection, user_id: str, as_of: datetime) -> dict:
    """Existing quota domain read at the snapshot's UTC day; unlimited keeps the real used count."""
    from ..config import settings
    from ..models import Quota
    from .quota_policy import is_unlimited_user
    quota = Quota.__table__
    day = as_of.astimezone(timezone.utc).date()
    row = connection.execute(select(quota.c.downloads_used, quota.c.limit)
                             .where(quota.c.user_id == user_id, quota.c.date == day.isoformat())).first()
    used = row.downloads_used if row else 0
    limit = row.limit if row else settings.default_quota_limit
    unlimited = bool(settings.membership_unlimited_downloads or is_unlimited_user(user_id))
    return {'quota_day': day.isoformat(), 'used': used, 'limit': None if unlimited else limit,
            'remaining': None if unlimited else limit - used, 'unlimited': unlimited}


def user_detail(connection, as_of: datetime, user_id: str, operator_id: str) -> dict | None:
    row = connection.execute(_user_statement(operator_id).where(User.__table__.c.id == user_id)).first()
    if row is None:
        return None
    return {**_user_summary(row, as_of), 'quota': quota_projection(connection, user_id, as_of), 'as_of': as_of}


def list_memberships(connection, as_of: datetime, query: ListQuery):
    membership = Membership.__table__
    statement = select(membership.c.user_id, *membership_columns()).select_from(
        membership.outerjoin(MembershipControl.__table__, MembershipControl.user_id == membership.c.user_id))
    filters = query.filters
    if 'user_id' in filters:
        statement = statement.where(membership.c.user_id == filters['user_id'])
    if 'status' in filters:
        statement = statement.where(membership.c.status == filters['status'])
    if 'effective' in filters:
        statement = statement.where(effective_vip(as_of) if filters['effective'] else ~effective_vip(as_of))
    expires = case((membership.c.expires_at <= 0, None), else_=membership.c.expires_at)  # same as the projection
    rows, total = paginate(connection, statement, query,
                           {'expires_at': expires, 'user_id': membership.c.user_id}, membership.c.user_id)
    return [membership_projection(row, row.user_id, as_of) for row in rows], total


# --- Jobs (Task 8) -------------------------------------------------------------------------------

GENERIC_ERROR = '任务失败，原因未归类'
# Fixed safe texts by error_type; Job.error (raw text) is never returned. Unknown types use GENERIC_ERROR.
ERROR_MESSAGES = {
    'network': '网络连接异常，可稍后重试', 'http_408': '来源响应超时', 'http_429': '来源限制了请求频率',
    'http_5xx': '来源服务器异常', 'http_401': '来源要求登录或授权', 'http_403': '来源拒绝访问',
    'http_404': '来源内容不存在', 'http_410': '来源内容已删除', 'http_412': '来源校验未通过',
    'http_4xx': '来源拒绝了请求', 'session_expired': '来源登录状态已失效，需人工处理',
    'permission_changed': '来源访问权限已变化，需人工处理', 'source_unavailable': '来源暂不可用或不受支持',
    'source_blocked': '来源地址被安全策略拒绝', 'source_budget_exhausted': '来源请求超出预算',
    'file_too_large': '文件超过大小限制', 'disk_error': '服务器存储异常', 'media_invalid': '下载内容不是有效的媒体文件',
    'format_unsupported': '所选格式不受支持', 'execution_crashed': '下载进程异常退出',
    'execution_protocol_error': '下载进程通信异常', 'execution_terminated': '下载进程被终止',
    'execution_request_invalid': '下载请求参数无效', 'execution_scenario_unknown': '下载执行方式未知',
    'executor_unknown': '下载执行器未知', 'run_deadline_exceeded': '任务超过最长执行时间',
}


def source_host(url) -> str | None:
    from urllib.parse import urlsplit
    try:
        host = urlsplit(url).hostname if isinstance(url, str) else None
    except ValueError:
        return None
    return host.lower() if host and re.fullmatch(r'[A-Za-z0-9.:-]+', host) else None


def error_message(error_type: str | None) -> str | None:
    if not error_type:
        return None
    return ERROR_MESSAGES.get(error_type, GENERIC_ERROR)


def _job_columns(job):
    return (job.c.id, job.c.user_id, job.c.title, job.c.url, job.c.execution_version, job.c.status,
            job.c.internal_state, job.c.progress, job.c.attempts_used, job.c.attempts_limit, job.c.created_at,
            job.c.updated_at)


def _job_summary(row) -> dict:
    return {'id': row.id, 'user_id': row.user_id, 'title': row.title, 'source_host': source_host(row.url),
            'execution_version': row.execution_version, 'public_status': getattr(row.status, 'value', row.status),
            'internal_state': row.internal_state, 'progress': max(0.0, min(100.0, float(row.progress or 0))),
            'attempts_used': row.attempts_used, 'attempts_limit': row.attempts_limit,
            'created_at': row.created_at, 'updated_at': row.updated_at}


def list_jobs(connection, as_of: datetime, query: ListQuery):
    job = Job.__table__
    statement = select(*_job_columns(job))
    filters = query.filters
    if 'user_id' in filters:
        statement = statement.where(job.c.user_id == filters['user_id'])
    if 'public_status' in filters:
        statement = statement.where(job.c.status == filters['public_status'])
    if 'internal_state' in filters:
        state = filters['internal_state']
        statement = statement.where(job.c.internal_state.is_(None) if state == 'legacy_unset'
                                    else job.c.internal_state == state)
    if 'execution_version' in filters:
        statement = statement.where(job.c.execution_version == filters['execution_version'])
    rows, total = paginate(connection, statement, query,
                           {'created_at': job.c.created_at, 'updated_at': job.c.updated_at}, job.c.id)
    return [_job_summary(row) for row in rows], total


def job_detail(connection, as_of: datetime, job_id: str) -> dict | None:
    from ..models_execution import ArtifactManifest, JobAttempt
    job, manifest, attempt = Job.__table__, ArtifactManifest.__table__, JobAttempt.__table__
    row = connection.execute(
        select(*_job_columns(job), job.c.expires_at, job.c.run_deadline_at, job.c.next_run_at, job.c.error_type,
               job.c.media_state, job.c.completed_at, manifest.c.byte_size, manifest.c.media_format,
               manifest.c.media_check)
        .select_from(job.outerjoin(manifest, manifest.c.attempt_id == job.c.visible_attempt_id))
        .where(job.c.id == job_id)).first()
    if row is None:
        return None
    attempts = connection.execute(
        select(attempt.c.id, attempt.c.attempt_index, attempt.c.state, attempt.c.started_at, attempt.c.ended_at,
               attempt.c.error_code).where(attempt.c.job_id == job_id).order_by(attempt.c.attempt_index)).all()
    return {**_job_summary(row), 'expires_at': row.expires_at, 'run_deadline_at': row.run_deadline_at,
            'next_run_at': row.next_run_at, 'error_type': row.error_type, 'error_message': error_message(row.error_type),
            'artifact': {'media_state': row.media_state,
                         'byte_size': None if row.byte_size is None else str(row.byte_size),
                         'media_format': row.media_format, 'media_check': row.media_check,
                         'completed_at': row.completed_at},
            'attempts': [dict(item._mapping) for item in attempts], 'as_of': as_of}


# --- Billing (Task 9) ----------------------------------------------------------------------------
# M1: billing_amounts is not ready, so every money / refund amount is null and amount_state 'unknown';
# Checkout state, reconciliation and fulfilled stay independent; Payment.revoked is separate.

def _fact_snapshot(row) -> dict:
    return {'id': row.id, 'provider_account_scope': row.provider_account_scope, 'livemode': row.livemode,
            'reconciliation': 'verified', 'provider_status': row.provider_status, 'money': None,
            'amount_refunded_minor': None, 'observed_at': row.observed_at}


def _facts(connection, condition):
    from ..models_billing import BillingFact
    fact = BillingFact.__table__
    return connection.execute(select(fact.c.id, fact.c.user_id, fact.c.provider_account_scope, fact.c.livemode,
                                     fact.c.provider_status, fact.c.reconciliation, fact.c.observed_at)
                              .where(condition).order_by(fact.c.observed_at, fact.c.id)).all()


def payment_facts(connection, payment_intent: str, payment_user_id: str | None) -> tuple[str, list, str | None]:
    """(facts_state, verified snapshots, reason). Every same-PI candidate is checked first (integration plan §7):
    ambiguous (unbound/mismatched user, several or unknown scope groups) wins over none."""
    from ..models_billing import BillingFact
    candidates = _facts(connection, BillingFact.__table__.c.payment_intent == payment_intent)
    if not candidates:
        return 'none', [], 'no_candidates'
    if payment_user_id is None:
        return 'ambiguous', [], 'payment_user_unbound'
    if any(row.user_id != payment_user_id for row in candidates):
        return 'ambiguous', [], 'user_mismatch'
    groups = {(row.provider_account_scope, row.livemode) for row in candidates}
    if len(groups) != 1:
        return 'ambiguous', [], 'scope_conflict'
    scope, livemode = next(iter(groups))
    if scope == 'legacy_unknown' or livemode is None:
        return 'ambiguous', [], 'scope_unknown'
    verified = [_fact_snapshot(row) for row in candidates if row.reconciliation == 'verified']
    return ('available', verified, None) if verified else ('none', [], 'no_verified_facts')


def checkout_facts(connection, checkout_id: str, scope: str | None, livemode: bool | None) -> tuple[str, list]:
    """Only verified facts of this checkout in the checkout's own scope/livemode; unknown scope or any
    cross-scope candidate is ambiguous (never joined)."""
    from ..models_billing import BillingFact
    candidates = _facts(connection, BillingFact.__table__.c.checkout_id == checkout_id)
    if not candidates:
        return 'none', []
    if scope in (None, 'legacy_unknown') or livemode is None:
        return 'ambiguous', []
    if any((row.provider_account_scope, row.livemode) != (scope, livemode) for row in candidates):
        return 'ambiguous', []
    verified = [_fact_snapshot(row) for row in candidates if row.reconciliation == 'verified']
    return ('available', verified) if verified else ('none', [])


def _checkout_columns(checkout):
    return (checkout.c.id, checkout.c.user_id, checkout.c.state, checkout.c.reconciliation, checkout.c.fulfilled,
            checkout.c.provider_account_scope, checkout.c.livemode, checkout.c.created_at, checkout.c.expires_at,
            checkout.c.revision)


def _checkout_summary(row) -> dict:
    return {'id': row.id, 'user_id': row.user_id, 'state': row.state, 'reconciliation': row.reconciliation,
            'fulfilled': bool(row.fulfilled), 'provider_account_scope': row.provider_account_scope,
            'livemode': row.livemode, 'created_at': _epoch_utc(row.created_at), 'expires_at': _epoch_utc(row.expires_at),
            'revision': str(row.revision)}


def list_checkouts(connection, as_of: datetime, query: ListQuery):
    from ..models import BillingCheckout
    checkout = BillingCheckout.__table__
    statement = select(*_checkout_columns(checkout))
    for name in ('user_id', 'state', 'reconciliation', 'fulfilled', 'provider_account_scope', 'livemode'):
        if name in query.filters:
            statement = statement.where(checkout.c[name] == query.filters[name])
    rows, total = paginate(connection, statement, query, {'created_at': checkout.c.created_at}, checkout.c.id)
    return [_checkout_summary(row) for row in rows], total


def checkout_detail(connection, as_of: datetime, checkout_id: str) -> dict | None:
    from ..models import BillingCheckout
    checkout = BillingCheckout.__table__
    row = connection.execute(select(*_checkout_columns(checkout), checkout.c.price_id, checkout.c.mode,
                                    checkout.c.duration_days, checkout.c.reconcile_attempts)
                             .where(checkout.c.id == checkout_id)).first()
    if row is None:
        return None
    state, facts = checkout_facts(connection, checkout_id, row.provider_account_scope, row.livemode)
    return {**_checkout_summary(row), 'price_id': row.price_id, 'mode': row.mode, 'duration_days': row.duration_days,
            'reconcile_attempts': row.reconcile_attempts, 'verified_facts': facts, 'facts_state': state, 'as_of': as_of}


def _payment_summary(row) -> dict:
    return {'id': row.payment_intent, 'user_id': row.user_id, 'source_id': row.source_id, 'revoked': bool(row.revoked),
            'money': None, 'amount_state': 'unknown', 'amount_source': None}


def list_payments(connection, as_of: datetime, query: ListQuery):
    from ..models import BillingPayment
    payment = BillingPayment.__table__
    statement = select(payment.c.payment_intent, payment.c.user_id, payment.c.source_id, payment.c.revoked)
    if 'user_id' in query.filters:
        statement = statement.where(payment.c.user_id == query.filters['user_id'])
    if 'revoked' in query.filters:
        statement = statement.where(payment.c.revoked.is_(query.filters['revoked']))
    if 'payment_id' in query.filters:
        statement = statement.where(payment.c.payment_intent == query.filters['payment_id'])
    rows, total = paginate(connection, statement, query, {'id': payment.c.payment_intent}, payment.c.payment_intent)
    return [_payment_summary(row) for row in rows], total


def payment_detail(connection, as_of: datetime, payment_id: str) -> dict | None:
    from ..models import BillingPayment
    payment = BillingPayment.__table__
    row = connection.execute(select(payment.c.payment_intent, payment.c.user_id, payment.c.source_id, payment.c.revoked)
                             .where(payment.c.payment_intent == payment_id)).first()
    if row is None:
        return None
    state, facts, reason = payment_facts(connection, payment_id, row.user_id)
    return {**_payment_summary(row), 'verified_facts': facts, 'facts_state': state, 'facts_reason': reason, 'as_of': as_of}


# --- Audit (Task 10) -----------------------------------------------------------------------------

_CHANGE_KEYS = ('enabled_before', 'enabled_after', 'revision_before', 'revision_after')
_MEMBERSHIP_CHANGE_KEYS = ('control_mode_before', 'control_mode_after', 'control_expires_at_before',
                           'control_expires_at_after', 'control_revision_before', 'control_revision_after')


def _audit_change(action: str, changes) -> dict | None:
    """Only users.access results carry a contract AuditChange; anything else (e.g. CLI notes) is never exposed."""
    keys = _MEMBERSHIP_CHANGE_KEYS if action == 'users.membership' else _CHANGE_KEYS
    if (not action.startswith('users.access') and action != 'users.membership') or not isinstance(changes, dict) or set(changes) != set(keys):
        return None
    return {key: changes[key] for key in keys}


def list_audit(connection, as_of: datetime, query: ListQuery):
    from ..models_admin import adminaudit
    statement = select(adminaudit.c.event_id, adminaudit.c.actor_user_id, adminaudit.c.target_user_id,
                       adminaudit.c.action, adminaudit.c.outcome, adminaudit.c.reason, adminaudit.c.request_id,
                       adminaudit.c.recorded_at, adminaudit.c.changes)
    filters = query.filters
    for name in ('actor_user_id', 'target_user_id', 'action', 'outcome'):
        if name in filters:
            statement = statement.where(adminaudit.c[name] == filters[name])
    if 'recorded_from' in filters:
        statement = statement.where(adminaudit.c.recorded_at >= filters['recorded_from'])
    if 'recorded_before' in filters:
        statement = statement.where(adminaudit.c.recorded_at < filters['recorded_before'])
    rows, total = paginate(connection, statement, query, {'recorded_at': adminaudit.c.recorded_at}, adminaudit.c.event_id)
    return [{'id': row.event_id, 'actor_user_id': row.actor_user_id, 'target_user_id': row.target_user_id,
             'action': row.action, 'outcome': row.outcome, 'reason': row.reason, 'request_id': row.request_id,
             'recorded_at': row.recorded_at, 'change': _audit_change(row.action, row.changes),
             'operation': 'users.access' if row.action.startswith('users.access') else (
                 'users.membership' if row.action == 'users.membership' else None)} for row in rows], total
