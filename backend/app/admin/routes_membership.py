"""Audited member controls; live session → Origin → CSRF → permission → capability."""
from fastapi import APIRouter, Depends, Request

from .deps import AdminContext, engine_of, settings_of
from .errors import AdminError
from .routes_support import writer
from .schemas import MembershipPatch, MembershipResult, capabilities
from ..services.admin_membership import set_membership

router = APIRouter()


@router.patch('/users/{user_id}/membership', response_model=MembershipResult)
def admin_set_membership(user_id: str, body: MembershipPatch, request: Request,
                         context: AdminContext = Depends(writer('memberships:write'))) -> MembershipResult:
    settings = settings_of(request)
    if not capabilities(settings).membership_control_write.ready:
        raise AdminError(503, 'capability_unavailable')
    return MembershipResult(**set_membership(engine_of(request), user_id, body, context=context,
        request_id=request.state.request_id, idempotency_key=request.headers.get('idempotency-key'), settings=settings))
