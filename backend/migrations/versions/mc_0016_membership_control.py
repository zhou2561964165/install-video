"""Independent admin member controls. No payment-row backfill or payment fact changes."""
import re

from alembic import context, op
import sqlalchemy as sa

revision = 'mc_0016'
down_revision = 't1_0015'
branch_labels = None
depends_on = None

TABLES = ('membershipcontroloperation', 'membershipcontrol')
CONTROL_COLUMNS = ('user_id', 'mode', 'expires_at', 'revision', 'updated_at', 'actor_user_id')
OPERATION_COLUMNS = ('idempotency_key', 'request_sha256', 'user_id', 'actor_user_id', 'result_json', 'audit_id', 'created_at')


def _roles():
    runtime = context.config.attributes.get('b3b_runtime_roles')
    admins = context.config.attributes.get('mc_admin_roles')
    for roles in (runtime, admins):
        if not isinstance(roles, (list, tuple)) or not 1 <= len(roles) <= 16:
            raise RuntimeError('MC migration requires explicit runtime and admin roles')
        if any(type(role) is not str or not re.fullmatch(r'[a-z_][a-z0-9_]{0,62}', role) or role == 'public' for role in roles):
            raise RuntimeError('MC migration role identifier rejected')
        if len(set(roles)) != len(roles):
            raise RuntimeError('MC migration roles must be unique')
    if not set(admins) <= set(runtime):
        raise RuntimeError('MC admin roles must be an explicit subset of runtime roles')
    if not context.is_offline_mode():
        connection = op.get_bind()
        for role in runtime:
            row = connection.execute(sa.text('SELECT rolname,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls '
                                             'FROM pg_roles WHERE rolname=:role'), {'role': role}).one_or_none()
            if row is None or any(row[1:]):
                raise RuntimeError('MC runtime role has unsafe attributes')
    return tuple(runtime), tuple(admins)


UPGRADE_SQL = (
"""CREATE TABLE app.membershipcontrol (
    user_id VARCHAR NOT NULL,
    mode VARCHAR NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE,
    revision BIGINT NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    actor_user_id VARCHAR NOT NULL,
    CONSTRAINT pk_membershipcontrol PRIMARY KEY (user_id),
    CONSTRAINT fk_membershipcontrol_user_id_user FOREIGN KEY (user_id) REFERENCES app."user" (id) ON DELETE RESTRICT,
    CONSTRAINT fk_membershipcontrol_actor_user_id_user FOREIGN KEY (actor_user_id) REFERENCES app."user" (id) ON DELETE RESTRICT,
    CONSTRAINT ck_membershipcontrol_mode CHECK (mode IN ('auto','enabled','disabled')),
    CONSTRAINT ck_membershipcontrol_expires_mode CHECK (mode='enabled' OR expires_at IS NULL),
    CONSTRAINT ck_membershipcontrol_revision CHECK (revision >= 1)
)""",
"""CREATE TABLE app.membershipcontroloperation (
    idempotency_key VARCHAR(128) NOT NULL,
    request_sha256 VARCHAR(64) NOT NULL,
    user_id VARCHAR NOT NULL,
    actor_user_id VARCHAR NOT NULL,
    result_json TEXT NOT NULL,
    audit_id VARCHAR(64) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT pk_membershipcontroloperation PRIMARY KEY (idempotency_key),
    CONSTRAINT fk_membershipcontroloperation_user_id_user FOREIGN KEY (user_id) REFERENCES app."user" (id) ON DELETE RESTRICT,
    CONSTRAINT fk_membershipcontroloperation_actor_user_id_user FOREIGN KEY (actor_user_id) REFERENCES app."user" (id) ON DELETE RESTRICT,
    CONSTRAINT fk_membershipcontroloperation_audit_id_adminaudit FOREIGN KEY (audit_id) REFERENCES app.adminaudit (event_id) ON DELETE RESTRICT,
    CONSTRAINT ck_membershipcontroloperation_request_sha256 CHECK (length(request_sha256) = 64)
)""",
"""CREATE FUNCTION app.membershipcontroloperation_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'membershipcontroloperation is append-only';
END
$$""",
"""CREATE TRIGGER tr_membershipcontroloperation_immutable BEFORE UPDATE OR DELETE ON app.membershipcontroloperation
FOR EACH ROW EXECUTE FUNCTION app.membershipcontroloperation_immutable()""",
"""CREATE TRIGGER tr_membershipcontroloperation_no_truncate BEFORE TRUNCATE ON app.membershipcontroloperation
FOR EACH STATEMENT EXECUTE FUNCTION app.membershipcontroloperation_immutable()""",
)


def upgrade():
    runtime, admins = _roles()  # validate every identifier before DDL
    for statement in UPGRADE_SQL:
        op.execute(sa.text(statement))
    for table in TABLES:
        op.execute(sa.text(f'REVOKE ALL ON TABLE app.{table} FROM PUBLIC'))
        for role in runtime:
            op.execute(sa.text(f'REVOKE ALL ON TABLE app.{table} FROM "{role}"'))
    for role in runtime:
        op.execute(sa.text(f'GRANT SELECT ON TABLE app.membershipcontrol TO "{role}"'))
    for role in admins:
        op.execute(sa.text(f'GRANT INSERT,UPDATE ON TABLE app.membershipcontrol TO "{role}"'))
        op.execute(sa.text(f'GRANT SELECT,INSERT ON TABLE app.membershipcontroloperation TO "{role}"'))


def downgrade():
    if context.is_offline_mode():
        raise RuntimeError('Offline downgrade cannot verify that no membership controls exist')
    connection = op.get_bind()
    connection.execute(sa.text('LOCK TABLE ' + ', '.join('app.' + table for table in TABLES) + ' IN ACCESS EXCLUSIVE MODE'))
    for table in TABLES:
        if connection.scalar(sa.text(f'SELECT EXISTS(SELECT 1 FROM app.{table})')):
            raise RuntimeError('Refusing downgrade while membership controls exist')
    for table in TABLES:
        op.execute(sa.text(f'DROP TABLE app.{table}'))
    op.execute(sa.text('DROP FUNCTION app.membershipcontroloperation_immutable()'))
