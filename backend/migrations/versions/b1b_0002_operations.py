"""Explicit frozen B1b DDL; no runtime models, data repair or business activation."""
from alembic import context, op
import sqlalchemy as sa

revision = 'b1b_0002'
down_revision = 'b1_0001'
branch_labels = None
depends_on = None

UPGRADE_SQL = (
    """CREATE TABLE app.downloadoperation (
	id VARCHAR NOT NULL, 
	user_id VARCHAR NOT NULL, 
	canonical_payload TEXT NOT NULL, 
	fingerprint VARCHAR(64) NOT NULL, 
	canonical_format_id VARCHAR NOT NULL, 
	max_height INTEGER, 
	membership_revision BIGINT NOT NULL, 
	quota_day DATE NOT NULL, 
	state VARCHAR NOT NULL, 
	job_id VARCHAR, 
	job_id_tombstone VARCHAR, 
	accepted_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	deadline_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	resolve_deadline_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	completed_at TIMESTAMP WITH TIME ZONE, 
	capacity_reserved BOOLEAN NOT NULL, 
	resolve_owner VARCHAR, 
	resolve_epoch BIGINT NOT NULL, 
	resolve_lease_deadline TIMESTAMP WITH TIME ZONE, 
	resolve_attempts_used BIGINT NOT NULL, 
	resolve_attempts_limit BIGINT NOT NULL, 
	resolve_attempt_deadline TIMESTAMP WITH TIME ZONE, 
	budget_version INTEGER NOT NULL, 
	budget_checkpoint_json TEXT NOT NULL, 
	budget_checkpoint_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	error_code VARCHAR, 
	CONSTRAINT pk_downloadoperation PRIMARY KEY (id), 
	CONSTRAINT ck_downloadoperation_state CHECK (state IN ('resolving','accepted_server','direct_ready','succeeded','failed','needs_review')), 
	CONSTRAINT ck_downloadoperation_budget_checkpoint CHECK (budget_version > 0 AND length(budget_checkpoint_json) > 0), 
	CONSTRAINT ck_downloadoperation_checkpoint_time CHECK (budget_checkpoint_at >= accepted_at), 
	CONSTRAINT ck_downloadoperation_access_snapshot CHECK (membership_revision >= 0 AND (max_height IS NULL OR max_height > 0)), 
	CONSTRAINT ck_downloadoperation_resolve_lease_pair CHECK ((resolve_owner IS NULL) = (resolve_lease_deadline IS NULL)), 
	CONSTRAINT uq_downloadoperation_job_id UNIQUE (job_id), 
	CONSTRAINT fk_downloadoperation_user_id_user FOREIGN KEY(user_id) REFERENCES app."user" (id) ON DELETE RESTRICT, 
	CONSTRAINT ck_downloadoperation_deadline CHECK (deadline_at >= accepted_at), 
	CONSTRAINT ck_downloadoperation_resolve_budget CHECK (resolve_epoch >= 0 AND resolve_attempts_used >= 0 AND resolve_attempts_used <= resolve_attempts_limit AND resolve_attempts_limit > 0), 
	CONSTRAINT fk_downloadoperation_job_id_job FOREIGN KEY(job_id) REFERENCES app.job (id) ON DELETE RESTRICT, 
	CONSTRAINT ck_downloadoperation_resolve_deadline CHECK (resolve_deadline_at >= accepted_at AND resolve_deadline_at <= deadline_at)
)
""",
    """CREATE INDEX ix_downloadoperation_state_lease ON app.downloadoperation (state, resolve_lease_deadline)
""",
    """CREATE INDEX ix_downloadoperation_user_id_accepted_at ON app.downloadoperation (user_id, accepted_at)
""",
    """CREATE TABLE app.quotacharge (
	operation_id VARCHAR NOT NULL, 
	user_id VARCHAR NOT NULL, 
	quota_day DATE NOT NULL, 
	delta BIGINT NOT NULL, 
	charged_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_quotacharge PRIMARY KEY (operation_id), 
	CONSTRAINT fk_quotacharge_operation_id_downloadoperation FOREIGN KEY(operation_id) REFERENCES app.downloadoperation (id) ON DELETE RESTRICT, 
	CONSTRAINT ck_quotacharge_delta_one CHECK (delta = 1), 
	CONSTRAINT fk_quotacharge_user_id_user FOREIGN KEY(user_id) REFERENCES app."user" (id) ON DELETE RESTRICT
)
""",
    """CREATE INDEX ix_quotacharge_user_id_quota_day ON app.quotacharge (user_id, quota_day)
""",
    """CREATE TABLE app.resourcecounter (
	resource VARCHAR NOT NULL, 
	scope VARCHAR NOT NULL, 
	used BIGINT NOT NULL, 
	CONSTRAINT pk_resourcecounter PRIMARY KEY (resource, scope), 
	CONSTRAINT ck_resourcecounter_used_nonnegative CHECK (used >= 0)
)
""",
    """CREATE TABLE app.resourcereservation (
	operation_id VARCHAR NOT NULL, 
	resource VARCHAR NOT NULL, 
	scope VARCHAR NOT NULL, 
	units BIGINT NOT NULL, 
	released BOOLEAN NOT NULL, 
	reserved_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	released_at TIMESTAMP WITH TIME ZONE, 
	CONSTRAINT pk_resourcereservation PRIMARY KEY (operation_id, resource, scope), 
	CONSTRAINT fk_resourcereservation_counter FOREIGN KEY(resource, scope) REFERENCES app.resourcecounter (resource, scope) ON DELETE RESTRICT, 
	CONSTRAINT ck_resourcereservation_release_state CHECK ((released = false AND released_at IS NULL) OR (released = true AND released_at IS NOT NULL)), 
	CONSTRAINT ck_resourcereservation_units_positive CHECK (units > 0), 
	CONSTRAINT fk_resourcereservation_operation_id_downloadoperation FOREIGN KEY(operation_id) REFERENCES app.downloadoperation (id) ON DELETE RESTRICT
)
""",
    """CREATE INDEX ix_resourcereservation_counter_released ON app.resourcereservation (resource, scope, released)
""",
    """ALTER TABLE app.downloadidempotency ADD COLUMN operation_id VARCHAR NULL
""",
    """ALTER TABLE app.downloadidempotency ADD CONSTRAINT uq_downloadidempotency_operation_id UNIQUE (operation_id)
""",
    """ALTER TABLE app.downloadidempotency ADD CONSTRAINT fk_downloadidempotency_operation_id_downloadoperation FOREIGN KEY (operation_id) REFERENCES app.downloadoperation(id) ON DELETE RESTRICT
""",
    """LOCK TABLE app.downloadidempotency IN SHARE ROW EXCLUSIVE MODE
""",
    """INSERT INTO app.resourcecounter(resource,scope,used) SELECT 'receipt_entries','global',COUNT(*) FROM app.downloadidempotency
""",
    """INSERT INTO app.resourcecounter(resource,scope,used) VALUES ('admission_slots','global',0)
""",
)

def upgrade():
    for statement in UPGRADE_SQL:
        op.execute(sa.text(statement))

def _assert_empty_business_database():
    if context.is_offline_mode():
        raise RuntimeError('Offline destructive downgrade cannot verify an empty database')
    connection = op.get_bind()
    tables = ['user', 'job', 'quota', 'downloadidempotency', 'membership', 'billingcheckout', 'billingevent', 'billingpayment', 'downloadaccess', 'downloadoperation', 'quotacharge', 'resourcecounter', 'resourcereservation']
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
    op.execute(sa.text('ALTER TABLE app.downloadidempotency DROP COLUMN operation_id'))
    op.execute(sa.text('DROP TABLE app.resourcereservation'))
    op.execute(sa.text('DROP TABLE app.resourcecounter'))
    op.execute(sa.text('DROP TABLE app.quotacharge'))
    op.execute(sa.text('DROP TABLE app.downloadoperation'))
