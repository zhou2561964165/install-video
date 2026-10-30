"""mc_0016 migration/ACL checks. Live checks require nonce-owned disposable PG."""
import io
import os

from alembic import command
from alembic.script import ScriptDirectory
import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app import db
from test_pg_job_repository import case  # noqa: F401

OWNED = pytest.mark.skipif(not os.environ.get('B3B_PG_OWNERSHIP'), reason='explicit owned PG window required')


def test_new_head_has_exact_parent_and_import_target():
    script = ScriptDirectory.from_config(db.migration_config())
    assert script.get_heads() == ['mc_0016']
    assert script.get_revision('mc_0016').down_revision == 't1_0015'
    from tools.production_db_import import TARGET_HEAD
    assert TARGET_HEAD == 'mc_0016'


def test_offline_preview_requires_explicit_admin_subset_and_never_grants_runtime_writes():
    config = db.migration_config()
    config.output_buffer = io.StringIO()
    config.attributes['b3b_runtime_roles'] = ('pv_api', 'pv_admin', 'pv_billing')
    with pytest.raises(RuntimeError, match='explicit'):
        command.upgrade(config, 't1_0015:mc_0016', sql=True)
    config.attributes['mc_admin_roles'] = ('not_runtime',)
    with pytest.raises(RuntimeError, match='subset'):
        command.upgrade(config, 't1_0015:mc_0016', sql=True)
    config.attributes['mc_admin_roles'] = ('pv_admin',)
    config.output_buffer = io.StringIO()
    command.upgrade(config, 't1_0015:mc_0016', sql=True)
    sql = config.output_buffer.getvalue()
    assert 'GRANT INSERT,UPDATE ON TABLE app.membershipcontrol TO "pv_admin"' in sql
    assert 'GRANT SELECT,INSERT ON TABLE app.membershipcontroloperation TO "pv_admin"' in sql
    assert 'GRANT SELECT ON TABLE app.membershipcontrol TO "pv_api"' in sql
    assert 'GRANT INSERT,UPDATE ON TABLE app.membershipcontrol TO "pv_api"' not in sql
    assert 'GRANT SELECT,INSERT ON TABLE app.membershipcontroloperation TO "pv_billing"' not in sql


@OWNED
def test_columns_and_admin_table_acl(case):
    expected = {'membershipcontrol': {'user_id', 'mode', 'expires_at', 'revision', 'updated_at', 'actor_user_id'},
                'membershipcontroloperation': {'idempotency_key', 'request_sha256', 'user_id', 'actor_user_id',
                                                'result_json', 'audit_id', 'created_at'}}
    with case.migration.connect() as connection:
        inspector = inspect(connection)
        for table, columns in expected.items():
            assert {c['name'] for c in inspector.get_columns(table, schema='app')} == columns
            actual = {p for p in ('SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER')
                      if connection.scalar(text("SELECT has_table_privilege('pv_app',:t,:p)"), {'t': 'app.' + table, 'p': p})}
            assert actual == ({'SELECT','INSERT','UPDATE'} if table == 'membershipcontrol' else {'SELECT','INSERT'})
        assert not connection.scalar(text("SELECT EXISTS(SELECT 1 FROM information_schema.table_privileges "
                                          "WHERE table_schema='app' AND table_name='membershipcontrol' AND grantee='PUBLIC')"))


@OWNED
def test_extra_runtime_role_has_no_control_or_operation_write(case):
    from b3b_pg_helpers import owned_probe_roles
    # Own the temporary role with the existing nonce/ownership ledger; no persistent role changes.
    with owned_probe_roles() as roles:
        reader = roles[0]
        case.migrate('downgrade', 't1_0015')
        try:
            case.migrate(runtime_roles=('pv_app', reader))
            with case.migration.connect() as connection:
                assert connection.scalar(text('SELECT has_table_privilege(:r,\'app.membershipcontrol\',\'SELECT\')'), {'r': reader})
                for table in ('membershipcontrol', 'membershipcontroloperation'):
                    for privilege in ('INSERT', 'UPDATE', 'DELETE', 'TRUNCATE'):
                        assert not connection.scalar(text('SELECT has_table_privilege(:r,:t,:p)'), {'r': reader, 't': 'app.'+table, 'p': privilege})
                assert not connection.scalar(text('SELECT has_table_privilege(:r,\'app.membershipcontroloperation\',\'SELECT\')'), {'r': reader})
        finally:
            # Drop the only objects granted to this temporary role before its owned-role cleanup.
            case.migrate('downgrade', 't1_0015')
            case.migrate()


@OWNED
def test_constraints_reject_invalid_modes_and_downgrade_keeps_data(case):
    from admin_pg_helpers import make_user, run
    target = make_user(case, grant=False)
    for mode, expiry in [('other', None), ('auto', '2030-01-01T00:00:00Z'), ('disabled', '2030-01-01T00:00:00Z')]:
        with pytest.raises(IntegrityError):
            run(case, 'INSERT INTO app.membershipcontrol (user_id,mode,expires_at,revision,updated_at,actor_user_id) '
                      'VALUES (:u,:m,:e,1,now(),:u)', u=target, m=mode, e=expiry)
    run(case, "INSERT INTO app.membershipcontrol (user_id,mode,expires_at,revision,updated_at,actor_user_id) "
              "VALUES (:u,'enabled',NULL,1,now(),:u)", u=target)
    with pytest.raises(RuntimeError, match='controls exist'):
        case.migrate('downgrade', 't1_0015')
    with case.application.connect() as connection:
        assert connection.scalar(text('SELECT version_num FROM app.alembic_version')) == 'mc_0016'
