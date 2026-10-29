"""Admin response/request models (contract 1.0.0-proposal.20261028.3); fields mirror the YAML schemas."""
from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, model_serializer


def utc(value: datetime | None) -> str | None:
    """Contract time: UTC ISO 8601 ending in Z (naive values are taken as UTC)."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=1024)


class SessionCreated(BaseModel):
    session_expires_at: str


class Capability(BaseModel):
    ready: bool
    reason: str | None


class Capabilities(BaseModel):
    account_access_write: Capability
    billing_amounts: Capability
    support_reissue: Capability


def capabilities(settings) -> Capabilities:
    return Capabilities(
        account_access_write=Capability(ready=False, reason='m2_not_enabled'),
        billing_amounts=Capability(ready=False, reason='amount_source_unconfirmed'),
        support_reissue=Capability(ready=True, reason=None) if settings.stripe_read_key
        else Capability(ready=False, reason='stripe_read_key_missing'))


class AdminMe(BaseModel):
    user_id: str
    email: str
    role: str
    permissions: list[str]
    session_expires_at: str
    csrf_token: str
    capabilities: Capabilities


class StateCount(BaseModel):
    state: str
    count: int


class Overview(BaseModel):
    as_of: str
    users_total: int
    effective_vip_total: int
    retained_server_jobs_total: int
    jobs_by_public_status: list[StateCount]
    jobs_by_internal_state: list[StateCount]
    scope: dict[str, str]


class ComponentStatus(BaseModel):
    component: str
    status: str
    reason_code: str | None
    checked_at: str | None


class SystemStatus(BaseModel):
    as_of: str
    components: list[ComponentStatus]
    capabilities: Capabilities
    download_submission_ready: Capability


class PaginationPolicy(BaseModel):
    default_page: int
    default_page_size: int
    max_page_size: int


class PolicyLimits(BaseModel):
    session_ttl_seconds: int
    reason_min_length: int
    reason_max_length: int
    idempotency_replay_retention_seconds: int
    refresh_interval_seconds: int


class FilterDescriptor(BaseModel):
    name: str
    kind: str
    allowed_values: list[str] | None = None  # contract: present only for kind=enum, absent otherwise

    @model_serializer(mode='wrap')
    def _drop_absent_allowed_values(self, handler):
        data = handler(self)
        if data.get('allowed_values') is None:
            data.pop('allowed_values', None)
        return data


class ResourceQuery(BaseModel):
    resource: str
    sort_values: list[str]
    filters: list[FilterDescriptor]


class StateDisplay(BaseModel):
    value: str
    label: str
    tone: str


class StateDictionary(BaseModel):
    domain: str
    values: list[StateDisplay]


class AdminMeta(BaseModel):
    api_version: str
    contract_version: str
    as_of: str
    features: Capabilities
    pagination: PaginationPolicy
    display_timezone: str
    quota_day_timezone: str
    quota_day_semantics: str
    limits: PolicyLimits
    queries: list[ResourceQuery]
    state_dictionaries: list[StateDictionary]


class AccessControl(BaseModel):
    enabled: bool
    revision: str
    protected_account: bool


class Quota(BaseModel):
    quota_day: str
    used: int
    limit: int | None
    remaining: int | None
    unlimited: bool


class MembershipOut(BaseModel):
    user_id: str
    status: str
    effective: bool
    expires_at: str | None
    revision: str | None
    entitlement_source: str | None
    cancel_at_period_end: bool


class UserSummary(BaseModel):
    id: str
    email: str
    created_at: str
    access: AccessControl
    membership: MembershipOut


class UserDetail(UserSummary):
    quota: Quota
    as_of: str


class UserPage(BaseModel):
    items: list[UserSummary]
    total: int
    page: int
    page_size: int
    as_of: str


class MembershipPage(BaseModel):
    items: list[MembershipOut]
    total: int
    page: int
    page_size: int
    as_of: str


class JobSummary(BaseModel):
    id: str
    user_id: str | None
    title: str | None
    source_host: str | None
    execution_version: int
    public_status: str
    internal_state: str | None
    progress: float
    attempts_used: int
    attempts_limit: int
    created_at: str
    updated_at: str


class ArtifactSummary(BaseModel):
    media_state: str | None
    byte_size: str | None
    media_format: str | None
    media_check: str | None
    completed_at: str | None


class AttemptSummary(BaseModel):
    id: str
    attempt_index: int
    state: str
    started_at: str
    ended_at: str | None
    error_code: str | None


class JobDetail(JobSummary):
    expires_at: str | None
    run_deadline_at: str | None
    next_run_at: str | None
    error_type: str | None
    error_message: str | None
    artifact: ArtifactSummary
    attempts: list[AttemptSummary]
    as_of: str


class JobPage(BaseModel):
    items: list[JobSummary]
    total: int
    page: int
    page_size: int
    as_of: str


class Money(BaseModel):
    amount_minor: str | None
    currency: str | None
    currency_exponent: int | None


class BillingFactSnapshot(BaseModel):
    id: str
    provider_account_scope: str
    livemode: bool | None
    reconciliation: str
    provider_status: str | None
    money: Money | None
    amount_refunded_minor: str | None
    observed_at: str


class CheckoutSummary(BaseModel):
    id: str
    user_id: str
    state: str
    reconciliation: str | None
    fulfilled: bool
    provider_account_scope: str | None
    livemode: bool | None
    created_at: str
    expires_at: str | None
    revision: str


class CheckoutDetail(CheckoutSummary):
    price_id: str
    mode: str
    duration_days: int
    reconcile_attempts: int
    verified_facts: list[BillingFactSnapshot]
    facts_state: str
    as_of: str


class PaymentSummary(BaseModel):
    id: str
    user_id: str | None
    source_id: str | None
    revoked: bool
    money: Money | None
    amount_state: str
    amount_source: str | None


class PaymentDetail(PaymentSummary):
    verified_facts: list[BillingFactSnapshot]
    facts_state: str
    facts_reason: str | None
    as_of: str


class CheckoutPage(BaseModel):
    items: list[CheckoutSummary]
    total: int
    page: int
    page_size: int
    as_of: str


class PaymentPage(BaseModel):
    items: list[PaymentSummary]
    total: int
    page: int
    page_size: int
    as_of: str


class AuditChange(BaseModel):
    enabled_before: bool
    enabled_after: bool
    revision_before: str
    revision_after: str


class AuditEntry(BaseModel):
    id: str
    actor_user_id: str | None
    target_user_id: str | None
    action: str
    outcome: str
    reason: str | None
    request_id: str
    recorded_at: str
    change: AuditChange | None
    operation: str | None


class AuditPage(BaseModel):
    items: list[AuditEntry]
    total: int
    page: int
    page_size: int
    as_of: str


class AccessPatch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: bool
    reason: str = Field(min_length=10, max_length=2000)
    expected_revision: str = Field(pattern=r'^(0|[1-9][0-9]*)$')


class SupportAction(BaseModel):
    allowed: bool
    reason: str | None


class SupportActions(BaseModel):
    verify: SupportAction
    reissue: SupportAction
    reply: SupportAction
    reject: SupportAction


class PaymentCheck(BaseModel):
    result: str
    checked_at: str
    fresh: bool


class SupportTicketSummary(BaseModel):
    id: str
    user_id: str
    user_email: str
    category: str
    category_label: str
    priority: str
    state: str
    resolution: str | None
    checkout_id: str | None
    created_at: str
    resolved_at: str | None


class SupportTicketDetail(SupportTicketSummary):
    user_note: str | None
    reply_template: str | None
    reply_text: str | None
    reply_note: str | None
    resolved_by: str | None
    checkout: CheckoutSummary | None
    membership: MembershipOut
    latest_check: PaymentCheck | None
    actions: SupportActions
    as_of: str


class SupportTicketPage(BaseModel):
    items: list[SupportTicketSummary]
    total: int
    page: int
    page_size: int
    as_of: str


class SupportReply(BaseModel):
    model_config = ConfigDict(extra='forbid')
    template_id: str = Field(min_length=1, max_length=64)
    note: str | None = Field(default=None, max_length=4000)


class SupportTicketState(BaseModel):
    id: str
    state: str
    resolution: str | None


class ReissueResult(BaseModel):
    ticket_id: str
    granted_days: int
    expires_at: str
    reply_text: str
