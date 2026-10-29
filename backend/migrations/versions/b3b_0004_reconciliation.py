"""B3b one-shot reconciliation identities and immutable audit; explicit runtime roles."""
import re
from alembic import context,op
import sqlalchemy as sa

revision='b3b_0004'
down_revision='b1b_0003'
branch_labels=None
depends_on=None


def _runtime_roles():
    roles=context.config.attributes.get('b3b_runtime_roles')
    if not isinstance(roles,(list,tuple)) or not 1<=len(roles)<=16:
        raise RuntimeError('B3b migration requires explicit runtime roles')
    if any(type(role) is not str or not re.fullmatch(r'[a-z_][a-z0-9_]{0,62}',role) or role=='public' for role in roles):
        raise RuntimeError('B3b migration runtime role identifier rejected')
    if len(set(roles))!=len(roles):
        raise RuntimeError('B3b migration runtime role identifiers must be unique')
    if not context.is_offline_mode():
        connection=op.get_bind()
        for role in roles:
            row=connection.execute(sa.text("SELECT rolname,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=:role"),{'role':role}).one_or_none()
            if row is None or any(row[1:]):
                raise RuntimeError('B3b runtime role has unsafe attributes')
            unsafe=connection.scalar(sa.text("""
SELECT pg_has_role(:role,current_user,'MEMBER')
 OR EXISTS(SELECT 1 FROM pg_roles p WHERE (p.rolsuper OR p.rolcreatedb OR p.rolcreaterole OR p.rolreplication OR p.rolbypassrls) AND pg_has_role(:role,p.oid,'MEMBER'))
 OR EXISTS(SELECT 1 FROM pg_roles p WHERE left(p.rolname,3)='pg_' AND pg_has_role(:role,p.oid,'MEMBER'))
 OR EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='app' AND pg_has_role(:role,c.relowner,'MEMBER'))
 OR has_database_privilege(:role,current_database(),'CREATE')
 OR has_database_privilege(:role,current_database(),'TEMP')
 OR has_schema_privilege(:role,'app','CREATE')
 OR has_schema_privilege(:role,'public','CREATE')
"""),{'role':role})
            if unsafe:
                raise RuntimeError('B3b runtime role has unsafe inherited or DDL privileges')
    return roles

UPGRADE_SQL=(
    """CREATE TABLE app.billingreconciliationtask (
	id VARCHAR(36) NOT NULL, 
	checkout_id VARCHAR NOT NULL, 
	user_id VARCHAR NOT NULL, 
	provider_account_scope VARCHAR(128) NOT NULL, 
	livemode BOOLEAN NOT NULL, 
	actor_ref VARCHAR(63) NOT NULL, 
	reason_code VARCHAR(32) NOT NULL, 
	evidence_ref VARCHAR(123) NOT NULL, 
	input_version INTEGER NOT NULL, 
	input_sha256 VARCHAR(64) NOT NULL, 
	query_json TEXT NOT NULL, 
	policy_json TEXT NOT NULL, 
	initial_checkout_revision BIGINT NOT NULL, 
	expected_checkout_revision BIGINT NOT NULL, 
	membership_revision BIGINT NOT NULL, 
	owner_ref VARCHAR(128) NOT NULL, 
	started_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	budget_deadline TIMESTAMP WITH TIME ZONE NOT NULL, 
	get_attempts BIGINT NOT NULL, 
	get_limit INTEGER NOT NULL, 
	budget_version INTEGER NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	outcome_reason VARCHAR(64), 
	completed_at TIMESTAMP WITH TIME ZONE, 
	next_audit_seq BIGINT NOT NULL, 
	revision BIGINT NOT NULL, 
	CONSTRAINT pk_billingreconciliationtask PRIMARY KEY (id), 
	CONSTRAINT ck_billingreconciliationtask_policy_json CHECK (octet_length(policy_json) BETWEEN 1 AND 65536 AND jsonb_typeof(policy_json::jsonb)='object'), 
	CONSTRAINT ck_billingreconciliationtask_revisions CHECK (initial_checkout_revision>=0 AND expected_checkout_revision>=initial_checkout_revision AND membership_revision>=0 AND revision>=0 AND next_audit_seq>=1), 
	CONSTRAINT fk_billingreconciliationtask_user_id_user FOREIGN KEY(user_id) REFERENCES app."user" (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_billingreconciliationtask_checkout_id_billingcheckout FOREIGN KEY(checkout_id) REFERENCES app.billingcheckout (id) ON DELETE RESTRICT, 
	CONSTRAINT uq_billingreconciliationtask_checkout_id UNIQUE (checkout_id), 
	CONSTRAINT ck_billingreconciliationtask_input_sha256 CHECK (input_sha256 ~ '^[0-9a-f]{64}$'), 
	CONSTRAINT ck_billingreconciliationtask_scope CHECK (provider_account_scope <> 'legacy_unknown' AND length(provider_account_scope)>0), 
	CONSTRAINT ck_billingreconciliationtask_query_json CHECK (octet_length(query_json) BETWEEN 1 AND 65536 AND jsonb_typeof(query_json::jsonb)='object'), 
	CONSTRAINT ck_billingreconciliationtask_get_budget CHECK (get_attempts>=0 AND get_attempts<=get_limit), 
	CONSTRAINT ck_billingreconciliationtask_audit_context CHECK (actor_ref ~ '^op:[A-Za-z0-9_.:-]{1,60}$' AND evidence_ref ~ '^ev:[A-Za-z0-9_.:-]{1,120}$'), 
	CONSTRAINT ck_billingreconciliationtask_versions_limits CHECK (input_version=1 AND budget_version=1 AND get_limit=3), 
	CONSTRAINT ck_billingreconciliationtask_deadline CHECK (budget_deadline>=started_at), 
	CONSTRAINT ck_billingreconciliationtask_reason CHECK (reason_code IN ('unknown_create','missing_reference','legacy_verification')), 
	CONSTRAINT ck_billingreconciliationtask_terminal CHECK ((status='running' AND completed_at IS NULL) OR (status IN ('verified','needs_review') AND completed_at IS NOT NULL))
)
""",
    """CREATE INDEX ix_billingreconciliationtask_status_deadline ON app.billingreconciliationtask (status, budget_deadline)
""",
    """CREATE INDEX ix_billingreconciliationtask_user_id ON app.billingreconciliationtask (user_id)
""",
    """CREATE TABLE app.billingreconciliationaudit (
	id VARCHAR(36) NOT NULL, 
	task_id VARCHAR NOT NULL, 
	seq BIGINT NOT NULL, 
	event_kind VARCHAR(16) NOT NULL, 
	get_ordinal INTEGER, 
	recorded_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	actor_ref VARCHAR(63) NOT NULL, 
	reason_code VARCHAR(32) NOT NULL, 
	evidence_ref VARCHAR(123) NOT NULL, 
	projection_version INTEGER NOT NULL, 
	projection_json TEXT NOT NULL, 
	projection_sha256 VARCHAR(64) NOT NULL, 
	CONSTRAINT pk_billingreconciliationaudit PRIMARY KEY (id), 
	CONSTRAINT uq_billingreconciliationaudit_get_event UNIQUE (task_id, event_kind, get_ordinal), 
	CONSTRAINT ck_billingreconciliationaudit_projection_json CHECK (octet_length(projection_json) BETWEEN 1 AND 65536 AND jsonb_typeof(projection_json::jsonb)='object'), 
	CONSTRAINT fk_billingreconciliationaudit_task_id_billingreconciliationtask FOREIGN KEY(task_id) REFERENCES app.billingreconciliationtask (id) ON DELETE RESTRICT, 
	CONSTRAINT ck_billingreconciliationaudit_reason CHECK (reason_code IN ('unknown_create','missing_reference','legacy_verification')), 
	CONSTRAINT ck_billingreconciliationaudit_sequence_version CHECK (seq>0 AND projection_version=1), 
	CONSTRAINT uq_billingreconciliationaudit_task_seq UNIQUE (task_id, seq), 
	CONSTRAINT ck_billingreconciliationaudit_projection_sha256 CHECK (projection_sha256 ~ '^[0-9a-f]{64}$'), 
	CONSTRAINT ck_billingreconciliationaudit_audit_context CHECK (actor_ref ~ '^op:[A-Za-z0-9_.:-]{1,60}$' AND evidence_ref ~ '^ev:[A-Za-z0-9_.:-]{1,120}$'), 
	CONSTRAINT ck_billingreconciliationaudit_event_ordinal CHECK ((event_kind IN ('task_started','task_finished') AND get_ordinal IS NULL) OR (event_kind IN ('get_reserved','get_observed') AND get_ordinal IS NOT NULL AND get_ordinal BETWEEN 1 AND 3))
)
""",
    """CREATE UNIQUE INDEX uq_billingreconciliationaudit_lifecycle ON app.billingreconciliationaudit (task_id, event_kind) WHERE get_ordinal IS NULL
""",
    """CREATE FUNCTION app.b3b_reject_mutation() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
BEGIN
  RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='B3b immutable reconciliation evidence';
END;
$$
""",
    """CREATE FUNCTION app.b3b_task_update_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
BEGIN
  IF ROW(NEW.id,NEW.checkout_id,NEW.user_id,NEW.provider_account_scope,NEW.livemode,NEW.actor_ref,NEW.reason_code,NEW.evidence_ref,NEW.input_version,NEW.input_sha256,NEW.query_json,NEW.policy_json,NEW.initial_checkout_revision,NEW.membership_revision,NEW.owner_ref,NEW.started_at,NEW.budget_deadline,NEW.get_limit,NEW.budget_version) IS DISTINCT FROM ROW(OLD.id,OLD.checkout_id,OLD.user_id,OLD.provider_account_scope,OLD.livemode,OLD.actor_ref,OLD.reason_code,OLD.evidence_ref,OLD.input_version,OLD.input_sha256,OLD.query_json,OLD.policy_json,OLD.initial_checkout_revision,OLD.membership_revision,OLD.owner_ref,OLD.started_at,OLD.budget_deadline,OLD.get_limit,OLD.budget_version ) THEN
    RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='B3b task identity and policy are frozen';
  END IF;
  IF OLD.status <> 'running' AND NEW IS DISTINCT FROM OLD THEN
    RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='B3b terminal task is immutable';
  END IF;
  IF NEW.get_attempts < OLD.get_attempts OR NEW.get_attempts > OLD.get_attempts + 1
     OR NEW.get_attempts > 3 OR NEW.next_audit_seq < OLD.next_audit_seq
     OR NEW.revision < OLD.revision OR NEW.expected_checkout_revision < OLD.expected_checkout_revision THEN
    RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='B3b task counters must advance monotonically';
  END IF;
  RETURN NEW;
END;
$$
""",
    """CREATE TRIGGER trg_b3b_audit_row BEFORE UPDATE OR DELETE ON app.billingreconciliationaudit FOR EACH ROW EXECUTE FUNCTION app.b3b_reject_mutation()
""",
    """CREATE TRIGGER trg_b3b_audit_truncate BEFORE TRUNCATE ON app.billingreconciliationaudit FOR EACH STATEMENT EXECUTE FUNCTION app.b3b_reject_mutation()
""",
    """CREATE TRIGGER trg_b3b_task_delete BEFORE DELETE ON app.billingreconciliationtask FOR EACH ROW EXECUTE FUNCTION app.b3b_reject_mutation()
""",
    """CREATE TRIGGER trg_b3b_task_truncate BEFORE TRUNCATE ON app.billingreconciliationtask FOR EACH STATEMENT EXECUTE FUNCTION app.b3b_reject_mutation()
""",
    """CREATE TRIGGER trg_b3b_task_update BEFORE UPDATE ON app.billingreconciliationtask FOR EACH ROW EXECUTE FUNCTION app.b3b_task_update_guard()
""",
    """REVOKE ALL ON FUNCTION app.b3b_reject_mutation() FROM PUBLIC
""",
    """REVOKE ALL ON FUNCTION app.b3b_task_update_guard() FROM PUBLIC
""",
    """REVOKE ALL ON TABLE app.billingreconciliationtask,app.billingreconciliationaudit FROM PUBLIC
""",
)

def upgrade():
    roles=_runtime_roles()  # validate before any DDL
    for statement in UPGRADE_SQL:
        op.execute(sa.text(statement))
    for role in roles:
        quoted='"'+role+'"'  # ASCII identifier validated above; never a guessed role.
        op.execute(sa.text('REVOKE ALL ON TABLE app.billingreconciliationaudit,app.billingreconciliationtask FROM '+quoted))
        op.execute(sa.text('GRANT SELECT,INSERT ON TABLE app.billingreconciliationaudit TO '+quoted))
        op.execute(sa.text('GRANT SELECT,INSERT,UPDATE ON TABLE app.billingreconciliationtask TO '+quoted))
        if not context.is_offline_mode():
            for table,allowed in [('billingreconciliationaudit',{'SELECT','INSERT'}),('billingreconciliationtask',{'SELECT','INSERT','UPDATE'})]:
                for privilege in ('SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER'):
                    actual=op.get_bind().scalar(sa.text('SELECT has_table_privilege(:role,:table,:privilege)'),{'role':role,'table':'app.'+table,'privilege':privilege})
                    if actual != (privilege in allowed):
                        raise RuntimeError('B3b runtime effective privileges remain unsafe')


def downgrade():
    if context.is_offline_mode():
        raise RuntimeError('Offline destructive downgrade cannot verify an empty database')
    tables=['billingcheckout', 'billingevent', 'billingfact', 'billinginbox', 'billingpayment', 'billingreconciliationaudit', 'billingreconciliationtask', 'downloadaccess', 'downloadidempotency', 'downloadoperation', 'job', 'membership', 'quota', 'quotacharge', 'resourcecounter', 'resourcereservation', 'user']
    connection=op.get_bind()
    connection.execute(sa.text('LOCK TABLE '+', '.join('app."'+name+'"' for name in tables)+' IN ACCESS EXCLUSIVE MODE'))
    for name in tables:
        if name=='resourcecounter':
            query="SELECT EXISTS(SELECT 1 FROM app.resourcecounter WHERE used<>0 OR scope<>'global' OR resource NOT IN ('admission_slots','receipt_entries'))"
        else:
            query='SELECT EXISTS(SELECT 1 FROM app."'+name+'" LIMIT 1)'
        if connection.scalar(sa.text(query)):
            raise RuntimeError('Refusing destructive downgrade of nonempty business tables')
    op.drop_table('billingreconciliationaudit',schema='app')
    op.drop_table('billingreconciliationtask',schema='app')
    op.execute(sa.text('DROP FUNCTION app.b3b_task_update_guard()'))
    op.execute(sa.text('DROP FUNCTION app.b3b_reject_mutation()'))
