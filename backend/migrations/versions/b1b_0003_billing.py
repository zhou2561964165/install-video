"""Explicit frozen B1b DDL; no runtime models, data repair or business activation."""
from alembic import context, op
import sqlalchemy as sa

revision = 'b1b_0003'
down_revision = 'b1b_0002'
branch_labels = None
depends_on = None

UPGRADE_SQL = (
    """CREATE TABLE app.billinginbox (
	id VARCHAR NOT NULL, 
	provider_account_scope VARCHAR NOT NULL, 
	livemode BOOLEAN NOT NULL, 
	event_id VARCHAR NOT NULL, 
	event_type VARCHAR NOT NULL, 
	api_version VARCHAR, 
	received_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	payload_sha256 VARCHAR(64) NOT NULL, 
	canonical_sha256 VARCHAR(64) NOT NULL, 
	canonical_version INTEGER NOT NULL, 
	canonical_payload TEXT NOT NULL, 
	business_payload TEXT, 
	status VARCHAR NOT NULL, 
	attempt_count BIGINT NOT NULL, 
	attempt_limit BIGINT NOT NULL, 
	budget_deadline TIMESTAMP WITH TIME ZONE NOT NULL, 
	next_run_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	lease_owner VARCHAR, 
	lease_epoch BIGINT NOT NULL, 
	lease_deadline TIMESTAMP WITH TIME ZONE, 
	error_code VARCHAR, 
	outcome_reason VARCHAR, 
	completed_at TIMESTAMP WITH TIME ZONE, 
	payload_purged_at TIMESTAMP WITH TIME ZONE, 
	CONSTRAINT pk_billinginbox PRIMARY KEY (id), 
	CONSTRAINT ck_billinginbox_status CHECK (status IN ('received','processing','retry_wait','waiting_binding','applied','ignored','needs_review')), 
	CONSTRAINT ck_billinginbox_lease_pair CHECK ((lease_owner IS NULL) = (lease_deadline IS NULL)), 
	CONSTRAINT uq_billinginbox_scope_event UNIQUE (provider_account_scope, livemode, event_id), 
	CONSTRAINT ck_billinginbox_processing_lease CHECK (status <> 'processing' OR lease_owner IS NOT NULL), 
	CONSTRAINT ck_billinginbox_budget CHECK (attempt_count >= 0 AND attempt_limit > 0 AND attempt_count <= attempt_limit AND lease_epoch >= 0), 
	CONSTRAINT ck_billinginbox_canonical_version CHECK (canonical_version > 0), 
	CONSTRAINT ck_billinginbox_budget_deadline CHECK (budget_deadline >= received_at)
)
""",
    """CREATE INDEX ix_billinginbox_status_lease ON app.billinginbox (status, lease_deadline)
""",
    """CREATE INDEX ix_billinginbox_status_next_run ON app.billinginbox (status, next_run_at)
""",
    """CREATE TABLE app.billingfact (
	id VARCHAR NOT NULL, 
	inbox_id VARCHAR, 
	user_id VARCHAR, 
	checkout_id VARCHAR, 
	provider_account_scope VARCHAR NOT NULL, 
	livemode BOOLEAN, 
	event_id VARCHAR, 
	payment_intent VARCHAR, 
	session_id VARCHAR, 
	invoice_id VARCHAR, 
	charge_id VARCHAR, 
	subscription_id VARCHAR, 
	provider_status VARCHAR, 
	amount_total BIGINT, 
	amount_refunded BIGINT, 
	currency VARCHAR(3), 
	reconciliation VARCHAR NOT NULL, 
	observed_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_billingfact PRIMARY KEY (id), 
	CONSTRAINT uq_billingfact_inbox_id UNIQUE (inbox_id), 
	CONSTRAINT fk_billingfact_checkout_id_billingcheckout FOREIGN KEY(checkout_id) REFERENCES app.billingcheckout (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_billingfact_user_id_user FOREIGN KEY(user_id) REFERENCES app."user" (id) ON DELETE RESTRICT, 
	CONSTRAINT ck_billingfact_amount_total CHECK (amount_total IS NULL OR amount_total >= 0), 
	CONSTRAINT ck_billingfact_amount_refunded CHECK (amount_refunded IS NULL OR amount_refunded >= 0), 
	CONSTRAINT ck_billingfact_reconciliation CHECK (reconciliation IN ('unknown','verified','needs_review')), 
	CONSTRAINT fk_billingfact_inbox_id_billinginbox FOREIGN KEY(inbox_id) REFERENCES app.billinginbox (id) ON DELETE RESTRICT, 
	CONSTRAINT ck_billingfact_scope_mode CHECK ((provider_account_scope = 'legacy_unknown' AND livemode IS NULL) OR (provider_account_scope <> 'legacy_unknown' AND livemode IS NOT NULL))
)
""",
    """CREATE INDEX ix_billingfact_checkout_id ON app.billingfact (checkout_id)
""",
    """CREATE INDEX ix_billingfact_scope_pi ON app.billingfact (provider_account_scope, livemode, payment_intent)
""",
    """ALTER TABLE app.billingcheckout ADD COLUMN provider_account_scope VARCHAR NULL
""",
    """ALTER TABLE app.billingcheckout ADD COLUMN livemode BOOLEAN NULL
""",
    """ALTER TABLE app.billingcheckout ADD COLUMN create_payload TEXT NULL
""",
    """ALTER TABLE app.billingcheckout ADD COLUMN create_payload_sha256 VARCHAR(64) NULL
""",
    """ALTER TABLE app.billingcheckout ADD COLUMN create_payload_version INTEGER NULL
""",
    """ALTER TABLE app.billingcheckout ADD COLUMN create_started_at TIMESTAMP WITH TIME ZONE NULL
""",
    """ALTER TABLE app.billingcheckout ADD COLUMN create_completed_at TIMESTAMP WITH TIME ZONE NULL
""",
    """ALTER TABLE app.billingcheckout ADD COLUMN create_result_code VARCHAR NULL
""",
    """ALTER TABLE app.billingcheckout ADD COLUMN reconciliation VARCHAR NULL
""",
    """ALTER TABLE app.billingcheckout ADD COLUMN reconcile_attempts INTEGER DEFAULT 0 NOT NULL
""",
    """ALTER TABLE app.billingcheckout ALTER COLUMN reconcile_attempts DROP DEFAULT
""",
    """ALTER TABLE app.billingcheckout ADD COLUMN reconciliation_started_at TIMESTAMP WITH TIME ZONE NULL
""",
    """ALTER TABLE app.billingcheckout ADD COLUMN reconciliation_evidence VARCHAR NULL
""",
    """ALTER TABLE app.billingcheckout ADD COLUMN reconciliation_actor VARCHAR NULL
""",
    """ALTER TABLE app.billingcheckout ADD COLUMN reconciliation_reason VARCHAR NULL
""",
    """ALTER TABLE app.billingcheckout ADD COLUMN revision BIGINT DEFAULT 0 NOT NULL
""",
    """ALTER TABLE app.billingcheckout ALTER COLUMN revision DROP DEFAULT
""",
    """ALTER TABLE app.billingcheckout ADD CONSTRAINT ck_billingcheckout_reconcile_attempts CHECK (reconcile_attempts >= 0 AND reconcile_attempts <= 3)
""",
    """ALTER TABLE app.billingcheckout ADD CONSTRAINT ck_billingcheckout_reconciliation CHECK (reconciliation IS NULL OR reconciliation IN ('not_started','unknown','verified','needs_review','closed'))
""",
    """ALTER TABLE app.billingevent ADD COLUMN provider_account_scope VARCHAR NOT NULL DEFAULT 'legacy_unknown'
""",
    """ALTER TABLE app.billingevent ALTER COLUMN provider_account_scope DROP DEFAULT
""",
    """ALTER TABLE app.billingevent ADD COLUMN livemode BOOLEAN NULL
""",
    """ALTER TABLE app.billingevent ADD COLUMN outcome VARCHAR NULL
""",
    """ALTER TABLE app.billingevent ADD CONSTRAINT ck_billingevent_scope_mode CHECK ((provider_account_scope = 'legacy_unknown' AND livemode IS NULL) OR (provider_account_scope <> 'legacy_unknown' AND livemode IS NOT NULL))
""",
)

def upgrade():
    for statement in UPGRADE_SQL:
        op.execute(sa.text(statement))

def _assert_empty_business_database():
    if context.is_offline_mode():
        raise RuntimeError('Offline destructive downgrade cannot verify an empty database')
    connection = op.get_bind()
    tables = ['user', 'job', 'quota', 'downloadidempotency', 'membership', 'billingcheckout', 'billingevent', 'billingpayment', 'downloadaccess', 'downloadoperation', 'quotacharge', 'resourcecounter', 'resourcereservation', 'billinginbox', 'billingfact']
    connection.execute(sa.text('LOCK TABLE ' + ', '.join('app."' + name + '"' for name in sorted(tables)) + ' IN ACCESS EXCLUSIVE MODE'))
    for name in tables:
        if name == 'resourcecounter':
            # Only the exact untouched bootstrap rows are disposable schema seeds.
            predicate = "used <> 0 OR scope <> 'global' OR resource NOT IN ('admission_slots','receipt_entries')"
            query = 'SELECT EXISTS (SELECT 1 FROM app.resourcecounter WHERE ' + predicate + ')'
        else:
            query = 'SELECT EXISTS (SELECT 1 FROM app."' + name + '" LIMIT 1)'
        if connection.scalar(sa.text(query)):
            raise RuntimeError('Refusing destructive downgrade of nonempty business tables')


def downgrade():
    _assert_empty_business_database()
    op.execute(sa.text('ALTER TABLE app.billingevent DROP CONSTRAINT ck_billingevent_scope_mode'))
    op.execute(sa.text('ALTER TABLE app.billingevent DROP COLUMN outcome'))
    op.execute(sa.text('ALTER TABLE app.billingevent DROP COLUMN livemode'))
    op.execute(sa.text('ALTER TABLE app.billingevent DROP COLUMN provider_account_scope'))
    op.execute(sa.text('ALTER TABLE app.billingcheckout DROP CONSTRAINT ck_billingcheckout_reconciliation'))
    op.execute(sa.text('ALTER TABLE app.billingcheckout DROP CONSTRAINT ck_billingcheckout_reconcile_attempts'))
    op.execute(sa.text('ALTER TABLE app.billingcheckout DROP COLUMN revision'))
    op.execute(sa.text('ALTER TABLE app.billingcheckout DROP COLUMN reconciliation_reason'))
    op.execute(sa.text('ALTER TABLE app.billingcheckout DROP COLUMN reconciliation_actor'))
    op.execute(sa.text('ALTER TABLE app.billingcheckout DROP COLUMN reconciliation_evidence'))
    op.execute(sa.text('ALTER TABLE app.billingcheckout DROP COLUMN reconciliation_started_at'))
    op.execute(sa.text('ALTER TABLE app.billingcheckout DROP COLUMN reconcile_attempts'))
    op.execute(sa.text('ALTER TABLE app.billingcheckout DROP COLUMN reconciliation'))
    op.execute(sa.text('ALTER TABLE app.billingcheckout DROP COLUMN create_result_code'))
    op.execute(sa.text('ALTER TABLE app.billingcheckout DROP COLUMN create_completed_at'))
    op.execute(sa.text('ALTER TABLE app.billingcheckout DROP COLUMN create_started_at'))
    op.execute(sa.text('ALTER TABLE app.billingcheckout DROP COLUMN create_payload_version'))
    op.execute(sa.text('ALTER TABLE app.billingcheckout DROP COLUMN create_payload_sha256'))
    op.execute(sa.text('ALTER TABLE app.billingcheckout DROP COLUMN create_payload'))
    op.execute(sa.text('ALTER TABLE app.billingcheckout DROP COLUMN livemode'))
    op.execute(sa.text('ALTER TABLE app.billingcheckout DROP COLUMN provider_account_scope'))
    op.execute(sa.text('DROP TABLE app.billingfact'))
    op.execute(sa.text('DROP TABLE app.billinginbox'))
