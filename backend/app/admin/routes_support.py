"""Admin customer-support endpoints (contract .3): list, detail, reply, reject; verify and re-issue (Task 7).

Write order follows the admin rule: live session (401) → Origin → CSRF (403) → permission (403).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..services import admin_queries, admin_support
from .deps import AdminContext, current_admin, engine_of, require_csrf, require_origin, require_permission, settings_of
from .errors import AdminError
from .schemas import (PaymentCheck, ReissueResult, SupportReply, SupportTicketDetail, SupportTicketPage, SupportTicketState,
                      utc)

router = APIRouter()


def _times(item: dict, *names: str) -> dict:
    return {**item, **{name: utc(item[name]) for name in names}}


def writer(permission: str):
    def check(request: Request) -> AdminContext:
        context = current_admin(request)
        require_origin(request)
        require_csrf(request, context)
        if permission not in context.permissions:
            raise AdminError(403, 'forbidden')
        return context
    return check


@router.get('/support/tickets', response_model=SupportTicketPage)
def admin_list_support_tickets(request: Request,
                               _: AdminContext = Depends(require_permission('support:read'))) -> SupportTicketPage:
    query = admin_queries.parse_list_query(admin_queries.RESOURCES['adminListSupportTickets'], request.query_params,
                                           settings_of(request))
    with admin_queries.read_snapshot(engine_of(request)) as (connection, as_of):
        items, total = admin_support.list_tickets(connection, as_of, query)
    return SupportTicketPage(items=[_times(item, 'created_at', 'resolved_at') for item in items], total=total,
                             page=query.page, page_size=query.page_size, as_of=utc(as_of))


@router.get('/support/tickets/{ticket_id}', response_model=SupportTicketDetail)
def admin_get_support_ticket(ticket_id: str, request: Request,
                             _: AdminContext = Depends(require_permission('support:read'))) -> SupportTicketDetail:
    with admin_queries.read_snapshot(engine_of(request)) as (connection, as_of):
        item = admin_support.ticket_detail(connection, as_of, ticket_id, settings_of(request))
    if item is None:
        raise AdminError(404, 'not_found')
    item = _times(item, 'created_at', 'resolved_at', 'as_of')
    if item['checkout']:
        item['checkout'] = _times(item['checkout'], 'created_at', 'expires_at')
    item['membership'] = _times(item['membership'], 'expires_at')
    if item['latest_check']:
        item['latest_check'] = _times(item['latest_check'], 'checked_at')
    return SupportTicketDetail(**item)


@router.post('/support/tickets/{ticket_id}/reply', response_model=SupportTicketState)
def admin_reply_support_ticket(ticket_id: str, body: SupportReply, request: Request,
                               context: AdminContext = Depends(writer('support:write'))) -> SupportTicketState:
    return SupportTicketState(**admin_support.close_ticket(
        engine_of(request), ticket_id, actor_user_id=context.user_id, request_id=request.state.request_id,
        template_id=body.template_id, note=body.note, rejected=False))


@router.post('/support/tickets/{ticket_id}/reject', response_model=SupportTicketState)
def admin_reject_support_ticket(ticket_id: str, body: SupportReply, request: Request,
                                context: AdminContext = Depends(writer('support:write'))) -> SupportTicketState:
    return SupportTicketState(**admin_support.close_ticket(
        engine_of(request), ticket_id, actor_user_id=context.user_id, request_id=request.state.request_id,
        template_id=body.template_id, note=body.note, rejected=True))


@router.post('/support/tickets/{ticket_id}/verify-payment', response_model=PaymentCheck)
def admin_verify_support_payment(ticket_id: str, request: Request,
                                 context: AdminContext = Depends(writer('support:write'))) -> PaymentCheck:
    item = admin_support.verify_payment(engine_of(request), ticket_id, actor_user_id=context.user_id,
                                        request_id=request.state.request_id, settings=settings_of(request),
                                        reader=request.app.state.session_reader)
    return PaymentCheck(**_times(item, 'checked_at'))


@router.post('/support/tickets/{ticket_id}/reissue', response_model=ReissueResult)
def admin_reissue_membership(ticket_id: str, request: Request,
                             context: AdminContext = Depends(writer('support:reissue'))) -> ReissueResult:
    item = admin_support.reissue(engine_of(request), ticket_id, actor_user_id=context.user_id,
                                 request_id=request.state.request_id, settings=settings_of(request),
                                 idempotency_key=request.headers.get('idempotency-key'))
    return ReissueResult(**_times(item, 'expires_at'))
