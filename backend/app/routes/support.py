"""User customer-support API: /api/support/meta, POST/GET /api/support/tickets (Bearer login required)."""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session

from ..db import get_session
from ..models import User
from ..services import support_catalog as catalog
from ..services import support_tickets
from ..services.auth import get_current_user

router = APIRouter()


class TicketRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    category: str = Field(min_length=1, max_length=64)
    note: Optional[str] = Field(default=None, max_length=4000)  # trimmed length is enforced by the service
    checkout_id: Optional[str] = Field(default=None, max_length=256)


@router.get('/api/support/meta')
def support_meta(user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict:
    return {'categories': [{'id': key, 'label': label} for key, label in catalog.CATEGORIES.items()],
            'note_max': catalog.NOTE_MAX,
            'checkouts': support_tickets.eligible_checkouts(session, user.id, datetime.now(timezone.utc))}


@router.post('/api/support/tickets')
def submit_ticket(req: TicketRequest, user: User = Depends(get_current_user),
                  session: Session = Depends(get_session)) -> dict:
    ticket = support_tickets.create_ticket(session, user.id, req.category, req.note, req.checkout_id,
                                           datetime.now(timezone.utc))
    return {'id': ticket.id, 'state': ticket.state}


@router.get('/api/support/tickets')
def my_tickets(user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict:
    return {'items': support_tickets.list_tickets(session, user.id)}
