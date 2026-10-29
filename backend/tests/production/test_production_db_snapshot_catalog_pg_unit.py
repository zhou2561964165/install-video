"""Pure PostgreSQL catalog boundaries; no database/config/application imports."""
import importlib.util
import pytest
from tools import production_db_snapshot_catalog as facade


def pg_module():
    assert importlib.util.find_spec('tools._production_db_snapshot_catalog_pg') is not None, 'PG collector missing'
    from tools import _production_db_snapshot_catalog_pg as pg
    return pg


def test_pg_dispatch_enters_e0_once():
    # PG dispatch must be a branch in the existing E0 owner, never another context.
    import inspect
    source = inspect.getsource(facade._CatalogContext.__enter__)
    assert '_collect_pg' in source
    assert source.count('readonly_snapshot(') == 1


def test_pg18_notnull_catalog_rows():
    pg = pg_module()
    assert pg._notnull([(1, [1], True, False)], {1}) == {1}
    for rows in ([], [(1, [1], False, False)], [(1, [1], True, True)],
                 [(1, [1, 2], True, False)], [(1, [1], True, False)] * 2):
        with pytest.raises(Exception) as caught:
            pg._notnull(rows, {1})
        assert caught.value.code == 'source_profile_unsupported'


def test_pg_bounds_before_text_fetch():
    pg = pg_module()
    class Connection:
        def __init__(self): self.calls = []
        def execute(self, statement, params):
            self.calls.append(str(statement))
            class Result:
                def __init__(self): self.row = (2049, 1, 1)
                def fetchone(self):
                    row, self.row = self.row, None
                    return row
                def close(self): pass
            return Result()
    connection = Connection()
    with pytest.raises(Exception) as caught:
        pg._bounded(connection, 'SELECT 1 AS value', {}, [0, 0])
    assert caught.value.code == 'catalog_limit_exceeded'
    assert len(connection.calls) == 1


@pytest.mark.parametrize('index',range(43))
def test_complete_frozen_check_and_mutation(index):
    pg=pg_module()
    table,identifier,expr=_CHECK_TEXT[index]
    assert pg._check_id(table,expr)==identifier
    assert pg._check_id(table,'(('+expr+'))')==identifier
    # Every frozen definition must reject a changed operand, unknown operator,
    # additional conjunct, trailing SQL, and wrong table independently.
    import re
    mutations=[expr+' AND false',expr+'; SELECT 1',expr.replace('=', '!=',1) if '=' in expr else expr+' OR true']
    match=re.search(r"'[^']*'|\b\d+\b",expr)
    if match:
        mutations.append(expr[:match.start()]+("'different'" if match[0].startswith("'") else '99999')+expr[match.end():])
    match=re.search(r'\b[a-z_]+\b',expr)
    mutations.append(expr[:match.start()]+'wrong_column'+expr[match.end():])
    for changed in mutations:
        with pytest.raises(Exception) as caught: pg._check_id(table,changed)
        assert caught.value.code=='source_profile_unsupported'
        assert caught.value.__context__ is caught.value.__cause__ is None
    with pytest.raises(Exception): pg._check_id('unknown_table',expr)


@pytest.mark.parametrize('index',range(43))
def test_check_logical_order_and_enum_order(index):
    pg=pg_module()
    table,identifier,expr=_CHECK_TEXT[index]
    ast=pg._expression(expr)
    if ast[0] in ('and','or') and len(ast[1])>1:
        changed=(ast[0],tuple(reversed(ast[1])))
        assert changed!=ast
        assert (table,changed) not in pg._checks()
    import re
    changed=re.sub(r"IN \('([^']*)','([^']*)'",lambda m:"IN ('"+m[2]+"','"+m[1]+"'",expr)
    if changed!=expr:
        with pytest.raises(Exception):pg._check_id(table,changed)


@pytest.mark.parametrize('expr',[
 "status = ANY (ARRAY['queued'::text,'downloading'::text,'merging'::text,'done'::text,'error'::text])",
 "(status)::text = ANY ((ARRAY['queued'::character varying,'downloading'::character varying,'merging'::character varying,'done'::character varying,'error'::character varying])::text[])",
 "(status)::pg_catalog.text OPERATOR(pg_catalog.=) ANY (ARRAY['queued'::pg_catalog.text,'downloading'::pg_catalog.text,'merging'::pg_catalog.text,'done'::pg_catalog.text,'error'::pg_catalog.text])",
],ids=['any','varchar-relabel','qualified'])
def test_finite_pg_deparse_variants(expr):
    assert pg_module()._check_id('job',expr)=='job.status.v1'


@pytest.mark.parametrize('expr',[
 'pg_catalog.evil(status)',"evil.length(status)>0",'status COLLATE "C" = status',
 "status = ANY(ARRAY['queued','error'])",'1=1 -- comment',
 'B6_PG_PRIVATE_CANARY()',"status::jsonb = '{}'::jsonb",'((('+('x '*5)+')))',
],ids=['unknown-call','shadow','collation','wrong-enum','comment','canary','cast','junk'])
def test_unknown_expression_rejected(expr):
    with pytest.raises(Exception) as caught: pg_module()._check_id('job',expr)
    assert caught.value.code=='source_profile_unsupported'


@pytest.mark.parametrize('index',range(2))
def test_full_function_body_tokens(index):
    pg=pg_module()
    identifier,body=_FUNCTION_TEXT[index]
    record=dict(oid=12345,proname='renamed',prolang=13500,language='plpgsql',prokind='f',pronargs=0,
        proargtypes='',proallargtypes=None,proargmodes=None,proargnames=None,pronargdefaults=0,
        proargdefaults=None,provariadic=0,prorettype=2279,proretset=False,prosecdef=False,
        proconfig=['search_path=pg_catalog'],prosrc=body,probin=None,prosqlbody=None,
        provolatile='v',proisstrict=False,proleakproof=False,proparallel='u',prosupport=0,protrftypes=None)
    assert pg._function_id(tuple(record.items()))==identifier
    for key,value in [('prosrc',body+' NULL;'),('prosecdef',True),('proconfig',['search_path=app']),
                      ('pronargs',1),('prorettype',25),('prokind','p'),('proparallel','s'),('proisstrict',True)]:
        changed=dict(record);changed[key]=value
        with pytest.raises(Exception): pg._function_id(tuple(changed.items()))


def test_pg_array_text_ast_limits():
    pg=pg_module()
    for expr in ('('*33+'true'+')'*33,'x'*65537,"x=ANY(ARRAY["+','.join('1' for _ in range(33000))+'])'):
        with pytest.raises(Exception) as caught:pg._check_id('job',expr)
        assert caught.value.code=='catalog_limit_exceeded'


def test_fetch_preserves_baseexception_when_close_fails():
    pg=pg_module()
    failure=KeyboardInterrupt('private')
    class Result:
        def fetchone(self):raise failure
        def close(self):raise RuntimeError('private')
    with pytest.raises(KeyboardInterrupt) as caught:pg._fetch(Result(),2)
    assert caught.value is failure


def synthetic_catalog():
    """Independent two-table catalog for private builder validation, no profiles."""
    data=dict(namespace=9000,relations=[dict(oid=9001,relname='user',relkind='r',relpersistence='p',
      relispartition=False,relam=2,reloftype=0,reltype=9002,relnatts=1,relchecks=0,relhasrules=False,
      relhastriggers=False,relrowsecurity=False,relforcerowsecurity=False,reloptions=None,
      relreplident='d',reltoastrelid=0,relnamespace=9000)],
      columns=[dict(attrelid=9001,attnum=1,attname='id',atttypid=1043,atttypmod=-1,
      attnotnull=True,attcollation=100,attidentity='',attgenerated='',atthasdef=False,
      attisdropped=False,attislocal=True,attinhcount=0)],
      constraints=[dict(oid=9010,contype='n',conrelid=9001,contypid=0,conkey=[1],confrelid=0,
      confkey=None,conindid=0,condeferrable=False,condeferred=False,convalidated=True,
      conenforced=True,conislocal=True,coninhcount=0,conparentid=0,connoinherit=False,
      conperiod=False,confmatchtype=' ',confupdtype=' ',confdeltype=' ',confdelsetcols=None,
      conpfeqop=None,conppeqop=None,conffeqop=None,conexclop=None,conbin=None,expression=None,
      connamespace=9000)],indexes=[],functions=[],triggers=[],defaults=[],forbidden=[],
      types=[dict(oid=1043,typname='varchar',typnamespace=11,typtype='b',typbasetype=0,
        typelem=0,typrelid=0,typarray=1015,typcollation=100),
        dict(oid=9002,typname='user',typnamespace=9000,typtype='c',typbasetype=0,
        typelem=0,typrelid=9001,typarray=9003,typcollation=0),
        dict(oid=9003,typname='_user',typnamespace=9000,typtype='b',typbasetype=0,
        typelem=9002,typrelid=0,typarray=0,typcollation=0)],
      dependencies=[(1259,9001,0,2615,9000,0,'n'),(1247,9002,0,1259,9001,0,'i'),
        (1247,9003,0,1247,9002,0,'i'),(2606,9010,0,1259,9001,1,'a')],
      opclasses=[],operators=[],builtin_functions=[],collations=[(100,'default',11,'d',-1,True)],
      languages=[],head='b1_0001')
    data['relations'].append(dict(data['relations'][0],oid=9011,relname='user_pkey',relkind='i',relam=403,reltype=0,relreplident='n'))
    data['constraints'].append(dict(data['constraints'][0],oid=9012,contype='p',conindid=9011,connoinherit=True))
    data['indexes'].append(dict(indexrelid=9011,indrelid=9001,indnatts=1,indnkeyatts=1,
      indkey=[1],indclass=[3126],indcollation=[100],indoption=[0],indexprs=None,indpred=None,
      indisunique=True,indnullsnotdistinct=False,indisprimary=True,indisexclusion=False,
      indimmediate=True,indisvalid=True,indisready=True,indislive=True,indcheckxmin=False,predicate=None))
    data['opclasses'].append((3126,'text_ops',11,403,25,True,0,'text_ops',11))
    data['dependencies'] += [(1259,9011,0,2606,9012,0,'i'),(2606,9012,0,1259,9001,1,'a')]
    return data


def test_actual_catalog_builder_does_not_fill_missing_profile():
    pg=pg_module();data=synthetic_catalog()
    descriptor=pg._describe(data)
    assert len(descriptor.tables)==1 and descriptor.tables[0].name=='user'
    assert descriptor.tables[0].columns[0].physical_type.kind=='pg_varchar'
    assert not descriptor.metadata_tables


@pytest.mark.parametrize('group,field,value',[
 ('relations','relkind','v'),('relations','relpersistence','u'),('relations','relispartition',True),
 ('relations','relhasrules',True),('relations','relhastriggers',True),('relations','relrowsecurity',True),
 ('relations','relforcerowsecurity',True),('relations','reloptions',['x']),('relations','relreplident','f'),
 ('relations','relam',999),('columns','atttypid',999),('columns','atttypmod',0),
 ('columns','attidentity','a'),('columns','attgenerated','s'),('columns','atthasdef',True),
 ('columns','attisdropped',True),('columns','attislocal',False),('columns','attinhcount',1),
 ('columns','attnotnull',False),('columns','attnum',2),('columns','attcollation',999),
 ('constraints','convalidated',False),('constraints','conenforced',False),
 ('constraints','condeferrable',True),('constraints','condeferred',True),('constraints','conislocal',False),
 ('constraints','coninhcount',1),('constraints','conparentid',1),('constraints','conperiod',True),
 ('constraints','connoinherit',True),('constraints','conkey',[1,2]),('constraints','connamespace',999),
],ids=lambda v: str(v) if type(v) in (str,int,bool) else 'array')
def test_fake_catalog_mutations(group,field,value):
    pg=pg_module();data=synthetic_catalog();data[group][0][field]=value
    with pytest.raises(Exception) as caught:pg._describe(data)
    assert caught.value.code=='source_profile_unsupported'


@pytest.mark.parametrize('group', ['relations','columns','constraints','types','dependencies'])
def test_extra_or_missing_object(group):
    pg=pg_module()
    for operation in ('missing','extra'):
        data=synthetic_catalog()
        if operation=='missing': data[group].pop()
        else:data[group].append(data[group][0])
        with pytest.raises(Exception):pg._describe(data)


def test_unknown_external_dependency_not_guessed_by_oid_or_name():
    pg=pg_module();data=synthetic_catalog()
    data['dependencies'].append((2606,9010,0,1255,1,0,'n'))
    with pytest.raises(Exception):pg._describe(data)


@pytest.mark.parametrize('status',[0,1,3,4])
def test_physical_pg_state_inactive(status):
    from types import SimpleNamespace
    from tools.production_db_snapshot import SnapshotConnectionError
    with pytest.raises(SnapshotConnectionError) as caught:
        pg_module()._assert_pg_active(None,SimpleNamespace(info=SimpleNamespace(transaction_status=status)))
    assert caught.value.code=='snapshot_inactive'

# Independently frozen from the reviewed PG DDL, not product templates.
_CHECK_TEXT = (('job', 'job.status.v1', "status IN ('queued','downloading','merging','done','error')"), ('downloadoperation', 'downloadoperation.state.v1', "state IN ('resolving','accepted_server','direct_ready','succeeded','failed','needs_review')"), ('downloadoperation', 'downloadoperation.budget_checkpoint.v1', 'budget_version > 0 AND length(budget_checkpoint_json) > 0'), ('downloadoperation', 'downloadoperation.checkpoint_time.v1', 'budget_checkpoint_at >= accepted_at'), ('downloadoperation', 'downloadoperation.access_snapshot.v1', 'membership_revision >= 0 AND (max_height IS NULL OR max_height > 0)'), ('downloadoperation', 'downloadoperation.resolve_lease_pair.v1', '(resolve_owner IS NULL) = (resolve_lease_deadline IS NULL)'), ('downloadoperation', 'downloadoperation.deadline.v1', 'deadline_at >= accepted_at'), ('downloadoperation', 'downloadoperation.resolve_budget.v1', 'resolve_epoch >= 0 AND resolve_attempts_used >= 0 AND resolve_attempts_used <= resolve_attempts_limit AND resolve_attempts_limit > 0'), ('downloadoperation', 'downloadoperation.resolve_deadline.v1', 'resolve_deadline_at >= accepted_at AND resolve_deadline_at <= deadline_at'), ('quotacharge', 'quotacharge.delta_one.v1', 'delta = 1'), ('resourcecounter', 'resourcecounter.used_nonnegative.v1', 'used >= 0'), ('resourcereservation', 'resourcereservation.release_state.v1', '(released = false AND released_at IS NULL) OR (released = true AND released_at IS NOT NULL)'), ('resourcereservation', 'resourcereservation.units_positive.v1', 'units > 0'), ('billinginbox', 'billinginbox.status.v1', "status IN ('received','processing','retry_wait','waiting_binding','applied','ignored','needs_review')"), ('billinginbox', 'billinginbox.lease_pair.v1', '(lease_owner IS NULL) = (lease_deadline IS NULL)'), ('billinginbox', 'billinginbox.processing_lease.v1', "status <> 'processing' OR lease_owner IS NOT NULL"), ('billinginbox', 'billinginbox.budget.v1', 'attempt_count >= 0 AND attempt_limit > 0 AND attempt_count <= attempt_limit AND lease_epoch >= 0'), ('billinginbox', 'billinginbox.canonical_version.v1', 'canonical_version > 0'), ('billinginbox', 'billinginbox.budget_deadline.v1', 'budget_deadline >= received_at'), ('billingfact', 'billingfact.amount_total.v1', 'amount_total IS NULL OR amount_total >= 0'), ('billingfact', 'billingfact.amount_refunded.v1', 'amount_refunded IS NULL OR amount_refunded >= 0'), ('billingfact', 'billingfact.reconciliation.v1', "reconciliation IN ('unknown','verified','needs_review')"), ('billingfact', 'billingfact.scope_mode.v1', "(provider_account_scope = 'legacy_unknown' AND livemode IS NULL) OR (provider_account_scope <> 'legacy_unknown' AND livemode IS NOT NULL)"), ('billingcheckout', 'billingcheckout.reconcile_attempts.v1', 'reconcile_attempts >= 0 AND reconcile_attempts <= 3'), ('billingcheckout', 'billingcheckout.reconciliation.v1', "reconciliation IS NULL OR reconciliation IN ('not_started','unknown','verified','needs_review','closed')"), ('billingevent', 'billingevent.scope_mode.v1', "(provider_account_scope = 'legacy_unknown' AND livemode IS NULL) OR (provider_account_scope <> 'legacy_unknown' AND livemode IS NOT NULL)"), ('billingreconciliationtask', 'billingreconciliationtask.policy_json.v1', "octet_length(policy_json) BETWEEN 1 AND 65536 AND jsonb_typeof(policy_json::jsonb)='object'"), ('billingreconciliationtask', 'billingreconciliationtask.revisions.v1', 'initial_checkout_revision>=0 AND expected_checkout_revision>=initial_checkout_revision AND membership_revision>=0 AND revision>=0 AND next_audit_seq>=1'), ('billingreconciliationtask', 'billingreconciliationtask.input_sha256.v1', "input_sha256 ~ '^[0-9a-f]{64}$'"), ('billingreconciliationtask', 'billingreconciliationtask.scope.v1', "provider_account_scope <> 'legacy_unknown' AND length(provider_account_scope)>0"), ('billingreconciliationtask', 'billingreconciliationtask.query_json.v1', "octet_length(query_json) BETWEEN 1 AND 65536 AND jsonb_typeof(query_json::jsonb)='object'"), ('billingreconciliationtask', 'billingreconciliationtask.get_budget.v1', 'get_attempts>=0 AND get_attempts<=get_limit'), ('billingreconciliationtask', 'billingreconciliationtask.audit_context.v1', "actor_ref ~ '^op:[A-Za-z0-9_.:-]{1,60}$' AND evidence_ref ~ '^ev:[A-Za-z0-9_.:-]{1,120}$'"), ('billingreconciliationtask', 'billingreconciliationtask.versions_limits.v1', 'input_version=1 AND budget_version=1 AND get_limit=3'), ('billingreconciliationtask', 'billingreconciliationtask.deadline.v1', 'budget_deadline>=started_at'), ('billingreconciliationtask', 'billingreconciliationtask.reason.v1', "reason_code IN ('unknown_create','missing_reference','legacy_verification')"), ('billingreconciliationtask', 'billingreconciliationtask.terminal.v1', "(status='running' AND completed_at IS NULL) OR (status IN ('verified','needs_review') AND completed_at IS NOT NULL)"), ('billingreconciliationaudit', 'billingreconciliationaudit.projection_json.v1', "octet_length(projection_json) BETWEEN 1 AND 65536 AND jsonb_typeof(projection_json::jsonb)='object'"), ('billingreconciliationaudit', 'billingreconciliationaudit.reason.v1', "reason_code IN ('unknown_create','missing_reference','legacy_verification')"), ('billingreconciliationaudit', 'billingreconciliationaudit.sequence_version.v1', 'seq>0 AND projection_version=1'), ('billingreconciliationaudit', 'billingreconciliationaudit.projection_sha256.v1', "projection_sha256 ~ '^[0-9a-f]{64}$'"), ('billingreconciliationaudit', 'billingreconciliationaudit.audit_context.v1', "actor_ref ~ '^op:[A-Za-z0-9_.:-]{1,60}$' AND evidence_ref ~ '^ev:[A-Za-z0-9_.:-]{1,120}$'"), ('billingreconciliationaudit', 'billingreconciliationaudit.event_ordinal.v1', "(event_kind IN ('task_started','task_finished') AND get_ordinal IS NULL) OR (event_kind IN ('get_reserved','get_observed') AND get_ordinal IS NOT NULL AND get_ordinal BETWEEN 1 AND 3)"))
_FUNCTION_TEXT = (('b3b_reject_mutation.v1', "\nBEGIN\n  RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='B3b immutable reconciliation evidence';\nEND;\n"), ('b3b_task_update_guard.v1', "\nBEGIN\n  IF ROW(NEW.id,NEW.checkout_id,NEW.user_id,NEW.provider_account_scope,NEW.livemode,NEW.actor_ref,NEW.reason_code,NEW.evidence_ref,NEW.input_version,NEW.input_sha256,NEW.query_json,NEW.policy_json,NEW.initial_checkout_revision,NEW.membership_revision,NEW.owner_ref,NEW.started_at,NEW.budget_deadline,NEW.get_limit,NEW.budget_version) IS DISTINCT FROM ROW(OLD.id,OLD.checkout_id,OLD.user_id,OLD.provider_account_scope,OLD.livemode,OLD.actor_ref,OLD.reason_code,OLD.evidence_ref,OLD.input_version,OLD.input_sha256,OLD.query_json,OLD.policy_json,OLD.initial_checkout_revision,OLD.membership_revision,OLD.owner_ref,OLD.started_at,OLD.budget_deadline,OLD.get_limit,OLD.budget_version ) THEN\n    RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='B3b task identity and policy are frozen';\n  END IF;\n  IF OLD.status <> 'running' AND NEW IS DISTINCT FROM OLD THEN\n    RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='B3b terminal task is immutable';\n  END IF;\n  IF NEW.get_attempts < OLD.get_attempts OR NEW.get_attempts > OLD.get_attempts + 1\n     OR NEW.get_attempts > 3 OR NEW.next_audit_seq < OLD.next_audit_seq\n     OR NEW.revision < OLD.revision OR NEW.expected_checkout_revision < OLD.expected_checkout_revision THEN\n    RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='B3b task counters must advance monotonically';\n  END IF;\n  RETURN NEW;\nEND;\n"))
