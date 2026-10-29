"""Admin read endpoints (M1): meta, overview, system status, and the business lists/details."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from ..config import settings as runtime_settings

from ..services import admin_queries
from ..services import admin_audit
from .deps import (AdminContext, current_admin, engine_of, require_csrf, require_origin,
                   require_permission, settings_of)
from .errors import AdminError
from .schemas import (AccessPatch, AdminMeta, AuditPage, Capability, CheckoutDetail, CheckoutPage,
                      JobDetail, JobPage, MembershipPage, Overview, PaymentDetail, PaymentPage, SystemStatus, UserDetail,
                      UserPage, capabilities, utc)

router = APIRouter()
CONTRACT_VERSION = '1.0.0-proposal.20261028.3'


def _download_readiness():
    if not runtime_settings.pg_business_enabled:
        return Capability(ready=False, reason='pg_business_startup_blocked')
    if runtime_settings.pg_cutover_read_only:
        return Capability(ready=False, reason='maintenance')
    from ..services.source_broker import ping
    if not ping(runtime_settings.source_broker_socket):
        return Capability(ready=False, reason='outbound_unavailable')
    return Capability(ready=True, reason=None)


def _filters(spec: admin_queries.ResourceSpec) -> list[dict]:
    return [{'name': item.name, 'kind': item.kind, **({'allowed_values': list(item.allowed)} if item.kind == 'enum' else {})}
            for item in spec.filters]


@router.get('/meta', response_model=AdminMeta, response_model_exclude_none=False)
def admin_meta(request: Request, _: AdminContext = Depends(current_admin)) -> AdminMeta:
    settings = settings_of(request)
    with admin_queries.read_snapshot(engine_of(request)) as (_connection, as_of):
        pass
    return AdminMeta(
        api_version='v1', contract_version=CONTRACT_VERSION, as_of=utc(as_of), features=capabilities(settings),
        pagination={'default_page': 1, 'default_page_size': settings.default_page_size,
                    'max_page_size': settings.max_page_size},
        display_timezone=settings.display_timezone, quota_day_timezone='UTC',
        quota_day_semantics='accepted_at_utc_date',
        limits={'session_ttl_seconds': settings.session_ttl_seconds, 'reason_min_length': settings.reason_min_length,
                'reason_max_length': settings.reason_max_length,
                'idempotency_replay_retention_seconds': settings.idempotency_replay_retention_seconds,
                'refresh_interval_seconds': settings.refresh_interval_seconds},
        queries=[{'resource': name, 'sort_values': list(spec.sorts), 'filters': _filters(spec)}
                 for name, spec in admin_queries.RESOURCES.items()],
        state_dictionaries=[{'domain': domain, 'values': [{'value': v, 'label': label, 'tone': tone}
                                                          for v, label, tone in values]}
                            for domain, values in admin_queries.STATE_DICTIONARIES])


@router.get('/overview', response_model=Overview)
def admin_overview(request: Request, _: AdminContext = Depends(require_permission('overview:read'))) -> Overview:
    with admin_queries.read_snapshot(engine_of(request)) as (connection, as_of):
        data = admin_queries.overview(connection, as_of)
    return Overview(**{**data, 'as_of': utc(data['as_of'])})


@router.get('/system/status', response_model=SystemStatus)
def admin_system_status(request: Request, _: AdminContext = Depends(require_permission('system:read'))) -> SystemStatus:
    with admin_queries.read_snapshot(engine_of(request)) as (_connection, as_of):
        components = admin_queries.system_components(as_of)
    return SystemStatus(
        as_of=utc(as_of), capabilities=capabilities(settings_of(request)),
        components=[{**item, 'checked_at': utc(item['checked_at'])} for item in components],
        download_submission_ready=_download_readiness())


# --- Users and memberships (Task 7) -------------------------------------------------------------

def _membership(item: dict) -> dict:
    return {**item, 'expires_at': utc(item['expires_at'])}


def _user(item: dict) -> dict:
    return {**item, 'created_at': utc(item['created_at']), 'membership': _membership(item['membership'])}


def _page(items, total, query, as_of) -> dict:
    return {'items': items, 'total': total, 'page': query.page, 'page_size': query.page_size, 'as_of': utc(as_of)}


@router.get('/users', response_model=UserPage)
def admin_list_users(request: Request, context: AdminContext = Depends(require_permission('users:read'))) -> UserPage:
    query = admin_queries.parse_list_query(admin_queries.RESOURCES['adminListUsers'], request.query_params,
                                           settings_of(request))
    with admin_queries.read_snapshot(engine_of(request)) as (connection, as_of):
        items, total = admin_queries.list_users(connection, as_of, query, context.user_id)
    return UserPage(**_page([_user(item) for item in items], total, query, as_of))


@router.get('/users/{user_id}', response_model=UserDetail)
def admin_get_user(user_id: str, request: Request,
                   context: AdminContext = Depends(require_permission('users:read'))) -> UserDetail:
    with admin_queries.read_snapshot(engine_of(request)) as (connection, as_of):
        item = admin_queries.user_detail(connection, as_of, user_id, context.user_id)
    if item is None:
        raise AdminError(404, 'not_found')
    return UserDetail(**{**_user(item), 'as_of': utc(item['as_of'])})


@router.get('/memberships', response_model=MembershipPage)
def admin_list_memberships(request: Request,
                           _: AdminContext = Depends(require_permission('memberships:read'))) -> MembershipPage:
    query = admin_queries.parse_list_query(admin_queries.RESOURCES['adminListMemberships'], request.query_params,
                                           settings_of(request))
    with admin_queries.read_snapshot(engine_of(request)) as (connection, as_of):
        items, total = admin_queries.list_memberships(connection, as_of, query)
    return MembershipPage(**_page([_membership(item) for item in items], total, query, as_of))


# --- Jobs (Task 8) -------------------------------------------------------------------------------

def _times(item: dict, *names: str) -> dict:
    return {**item, **{name: utc(item[name]) for name in names}}


@router.get('/jobs', response_model=JobPage)
def admin_list_jobs(request: Request, _: AdminContext = Depends(require_permission('jobs:read'))) -> JobPage:
    query = admin_queries.parse_list_query(admin_queries.RESOURCES['adminListJobs'], request.query_params,
                                           settings_of(request))
    with admin_queries.read_snapshot(engine_of(request)) as (connection, as_of):
        items, total = admin_queries.list_jobs(connection, as_of, query)
    return JobPage(**_page([_times(item, 'created_at', 'updated_at') for item in items], total, query, as_of))


@router.get('/jobs/{job_id}', response_model=JobDetail)
def admin_get_job(job_id: str, request: Request, _: AdminContext = Depends(require_permission('jobs:read'))) -> JobDetail:
    with admin_queries.read_snapshot(engine_of(request)) as (connection, as_of):
        item = admin_queries.job_detail(connection, as_of, job_id)
    if item is None:
        raise AdminError(404, 'not_found')
    item = _times(item, 'created_at', 'updated_at', 'expires_at', 'run_deadline_at', 'next_run_at', 'as_of')
    item['artifact'] = _times(item['artifact'], 'completed_at')
    item['attempts'] = [_times(attempt, 'started_at', 'ended_at') for attempt in item['attempts']]
    return JobDetail(**item)


# --- Billing (Task 9) ----------------------------------------------------------------------------

def _facts_out(facts: list) -> list:
    return [_times(fact, 'observed_at') for fact in facts]


@router.get('/billing/checkouts', response_model=CheckoutPage)
def admin_list_checkouts(request: Request, _: AdminContext = Depends(require_permission('billing:read'))) -> CheckoutPage:
    query = admin_queries.parse_list_query(admin_queries.RESOURCES['adminListCheckouts'], request.query_params,
                                           settings_of(request))
    with admin_queries.read_snapshot(engine_of(request)) as (connection, as_of):
        items, total = admin_queries.list_checkouts(connection, as_of, query)
    return CheckoutPage(**_page([_times(item, 'created_at', 'expires_at') for item in items], total, query, as_of))


@router.get('/billing/checkouts/{checkout_id}', response_model=CheckoutDetail)
def admin_get_checkout(checkout_id: str, request: Request,
                       _: AdminContext = Depends(require_permission('billing:read'))) -> CheckoutDetail:
    with admin_queries.read_snapshot(engine_of(request)) as (connection, as_of):
        item = admin_queries.checkout_detail(connection, as_of, checkout_id)
    if item is None:
        raise AdminError(404, 'not_found')
    item = _times(item, 'created_at', 'expires_at', 'as_of')
    return CheckoutDetail(**{**item, 'verified_facts': _facts_out(item['verified_facts'])})


@router.get('/billing/payments', response_model=PaymentPage)
def admin_list_payments(request: Request, _: AdminContext = Depends(require_permission('billing:read'))) -> PaymentPage:
    query = admin_queries.parse_list_query(admin_queries.RESOURCES['adminListPayments'], request.query_params,
                                           settings_of(request))
    with admin_queries.read_snapshot(engine_of(request)) as (connection, as_of):
        items, total = admin_queries.list_payments(connection, as_of, query)
    return PaymentPage(**_page(items, total, query, as_of))


@router.get('/billing/payments/{payment_id}', response_model=PaymentDetail)
def admin_get_payment(payment_id: str, request: Request,
                      _: AdminContext = Depends(require_permission('billing:read'))) -> PaymentDetail:
    with admin_queries.read_snapshot(engine_of(request)) as (connection, as_of):
        item = admin_queries.payment_detail(connection, as_of, payment_id)
    if item is None:
        raise AdminError(404, 'not_found')
    item = _times(item, 'as_of')
    return PaymentDetail(**{**item, 'verified_facts': _facts_out(item['verified_facts'])})


# --- Audit and the closed M2 access endpoint (Task 10) ----------------------------------------------

@router.get('/audit/logs', response_model=AuditPage)
def admin_list_audit_logs(request: Request, _: AdminContext = Depends(require_permission('audit:read'))) -> AuditPage:
    query = admin_queries.parse_list_query(admin_queries.RESOURCES['adminListAuditLogs'], request.query_params,
                                           settings_of(request))
    with admin_queries.read_snapshot(engine_of(request)) as (connection, as_of):
        items, total = admin_queries.list_audit(connection, as_of, query)
    return AuditPage(**_page([_times(item, 'recorded_at') for item in items], total, query, as_of))


@router.patch('/users/{user_id}/access')
def admin_set_user_access(user_id: str, body: AccessPatch, request: Request) -> None:
    """M2 operation; while account_access_write is not ready it changes nothing and answers 503 (contract)."""
    context = current_admin(request)
    require_origin(request)
    require_csrf(request, context)
    # M1: account_access_write is never ready (deps.ready_capabilities); M2 replaces this body with the real write.
    with engine_of(request).begin() as connection:
        admin_audit.record(connection, actor_user_id=context.user_id, actor_kind='admin',
                           action='users.access_denied', outcome='denied', request_id=request.state.request_id,
                           target_user_id=user_id)
    raise AdminError(503, 'capability_unavailable')
