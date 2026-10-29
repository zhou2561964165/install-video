"""Synthetic catalog only; application imports and real DB connections are forbidden."""
from pathlib import Path
from contextlib import contextmanager
import os
import re
import sqlite3
import threading
import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import SAWarning

from tools.production_db_snapshot_catalog import catalog_snapshot, CatalogError
from tools.production_db_snapshot_profiles import SOURCE_PROFILES
from tools.production_db_snapshot_schema import schema_document
import tools.production_db_snapshot_catalog as catalog
from tools.production_db_snapshot import readonly_snapshot, SnapshotConnectionError
from tools.production_db_snapshot_format import encode_cell, decode_cell

FIXTURES = Path(__file__).parent / 'fixtures' / 'snapshot_catalog'


@pytest.mark.parametrize('version,profile', [(9, 'legacy_sqlite9_v1'), (17, 'sqlite_models17_v1')],ids=['s9','s17'])
def test_independent_sql_catalog(version, profile):
    engine = create_engine('sqlite:///:memory:')
    with engine.connect() as connection:
        connection.connection.driver_connection.executescript((FIXTURES / f'sqlite{version}.sql').read_text('utf8'))
        with catalog_snapshot(connection) as source:
            source.assert_active()
            assert schema_document(source.descriptor) == schema_document(SOURCE_PROFILES[profile].descriptor)
            assert source.descriptor is not SOURCE_PROFILES[profile].descriptor
            assert source.profile.profile_id == profile
        with pytest.raises(CatalogError, match='snapshot_inactive'):
            source.assert_active()
    engine.dispose()


@pytest.mark.parametrize('value', [None, 'legacy_sqlite9_v1', object()],ids=['none','id','object'])
def test_connection_required(value):
    with pytest.raises(CatalogError, match='connection_required'):
        with catalog_snapshot(value):
            pytest.fail('unexpected capability')


@contextmanager
def database(sql=None, version=17):
    engine=create_engine('sqlite:///:memory:')
    try:
        with engine.connect() as connection:
            connection.connection.driver_connection.executescript(sql if sql is not None else fixture(version))
            yield connection
    finally:engine.dispose()


def fixture(version=17):
    return (FIXTURES/f'sqlite{version}.sql').read_text('utf8')


def reject(connection,code='source_profile_unsupported'):
    with pytest.raises(CatalogError) as caught:
        with catalog_snapshot(connection):pytest.fail('unexpected capability')
    assert caught.value.code==code
    assert caught.value.__context__ is None and caught.value.__cause__ is None
    assert not catalog._ACTIVE


def mutate_table(sql,table,old,new):
    head='CREATE TABLE "'+table+'" ('
    start=sql.index(head);end=sql.index('\n);',start)+3
    original=sql[start:end]
    assert old in original
    return sql[:start]+original.replace(old,new,1)+sql[end:]


@pytest.mark.parametrize('sql',[
    'CREATE TABLE extra (id INTEGER)', 'CREATE VIEW extra AS SELECT 1',
    'CREATE TRIGGER extra AFTER INSERT ON user BEGIN SELECT 1; END',
    'CREATE INDEX extra ON user (password_hash)',
    'CREATE UNIQUE INDEX extra ON membership (customer_id)',
    'ALTER TABLE user ADD COLUMN extra TEXT', 'ANALYZE',
    'CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)',
    'CREATE VIRTUAL TABLE extra USING fts5(content)',
],ids=['table','view','trigger','index','unique','column','internal','metadata','virtual'])
def test_all_extra_catalog_objects_rejected(sql):
    with database(version=9) as connection:
        try:connection.connection.driver_connection.execute(sql)
        except sqlite3.OperationalError:
            if 'fts5' not in sql:raise
            pytest.skip('SQLite does not provide FTS5')
        reject(connection)


@pytest.mark.parametrize('old,new',[
    ('file_size INTEGER','file_size BIGINT'),('VARCHAR(11)','VARCHAR(12)'),
    ('VARCHAR(11)','VARCHAR'),('progress FLOAT','progress REAL'),
    ('url VARCHAR NOT NULL','url VARCHAR'),('title VARCHAR','title VARCHAR DEFAULT NULL'),
    ('title VARCHAR','title VARCHAR COLLATE BINARY'),
    ('PRIMARY KEY (id)','PRIMARY KEY (id) ON CONFLICT REPLACE'),
    ('FOREIGN KEY(user_id) REFERENCES user (id)','FOREIGN KEY(user_id) REFERENCES user (id) DEFERRABLE INITIALLY DEFERRED'),
    ('FOREIGN KEY(user_id) REFERENCES user (id)','FOREIGN KEY(user_id) REFERENCES user (id) MATCH SIMPLE'),
    ('FOREIGN KEY(user_id) REFERENCES user (id)','FOREIGN KEY(user_id) REFERENCES user (id) ON DELETE RESTRICT'),
],ids=['integer','length','bare','real','null','default','collate','conflict','deferred','match','restrict'])
def test_type_constraint_drift(old,new):
    sql=fixture(9).replace(old,new)
    assert sql!=fixture(9)
    with database(sql) as connection:reject(connection)


@pytest.mark.parametrize('mutation',[
    lambda s:s.replace('CREATE TABLE job (','CREATE TABLE job (extra TEXT GENERATED ALWAYS AS (title) VIRTUAL,'),
    lambda s:s.replace('CREATE TABLE job (','CREATE TABLE job (extra INTEGER,'),
    lambda s:s.replace('CREATE TABLE job (','CREATE TABLE job (extra INTEGER PRIMARY KEY AUTOINCREMENT,').replace('PRIMARY KEY (id),','UNIQUE (id),'),
    lambda s:s.replace('PRIMARY KEY (id),','PRIMARY KEY (id DESC),'),
    lambda s:s.replace('CREATE UNIQUE INDEX ix_user_email ON user (email)','CREATE UNIQUE INDEX ix_user_email ON user (email DESC)'),
    lambda s:s.replace('CREATE UNIQUE INDEX ix_user_email ON user (email)','CREATE UNIQUE INDEX ix_user_email ON user (email COLLATE BINARY)'),
    lambda s:s.replace('CREATE UNIQUE INDEX ix_user_email ON user (email)','CREATE UNIQUE INDEX ix_user_email ON user (lower(email))'),
    lambda s:s.replace('CREATE UNIQUE INDEX ix_user_email ON user (email)','CREATE UNIQUE INDEX ix_user_email ON user (email) WHERE email IS NULL'),
    lambda s:s.replace('UNIQUE (user_id, "key")','UNIQUE ("key", user_id)'),
    lambda s:s.replace('UNIQUE (customer_id),','UNIQUE (customer_id, subscription_id),'),
],ids=['generated','column','autoincrement','pkdesc','desc','collate','expression','partial','uqorder','uqcolumns'])
def test_index_and_table_drift(mutation):
    sql=mutation(fixture(9));assert sql!=fixture(9)
    with database(sql) as connection:reject(connection)


def test_without_rowid_rejected():
    sql=fixture(9).replace('FOREIGN KEY(user_id) REFERENCES user (id)\n);','FOREIGN KEY(user_id) REFERENCES user (id)\n) WITHOUT ROWID;')
    with database(sql) as connection:reject(connection)


def test_strict_rejected():
    # This new internal-compatible table is nevertheless an extra unknown object.
    with database(version=9) as connection:
        connection.connection.driver_connection.execute('CREATE TABLE extra (id INTEGER PRIMARY KEY) STRICT')
        reject(connection)


def test_missing_table_and_index():
    for statement in ('DROP TABLE quota','DROP INDEX ix_user_email'):
        with database(version=9) as connection:
            connection.connection.driver_connection.execute(statement);reject(connection)


@pytest.mark.parametrize('kind',['temp','attached'])
def test_attached_and_temp_objects_rejected(tmp_path,kind):
    statement,params=('CREATE TEMP TABLE extra(id)',()) if kind=='temp' else ("ATTACH DATABASE '"+str(tmp_path/'attached.db').replace("'","''")+"' AS extra",())
    if kind=='attached':
        import sitecustomize
        sitecustomize.approved(str(tmp_path/'attached.db'))
    with database(version=9) as connection:
        connection.connection.driver_connection.execute(statement,params);reject(connection)


def test_renamed_constraints_indexes_and_creation_order():
    sql=fixture(17)
    sql=sql.replace('"ix_', '"renamed_').replace('"uq_billingreconciliationaudit_lifecycle"','"renamed_partial"')
    statements=[s for s in sql.split(';') if s.strip()]
    tables=[s for s in statements if 'CREATE TABLE' in s]
    indexes=[s for s in statements if 'CREATE TABLE' not in s]
    with database(';'.join(list(reversed(tables))+list(reversed(indexes)))+';') as connection:
        with catalog_snapshot(connection) as source:assert source.profile.profile_id=='sqlite_models17_v1'


# The test matrix is independently recovered from the saved hand-reviewed SQL
# fixture's CHECK parentheses, not from the collector's expression registry.
def check_cases():
    cases=[]
    for block in fixture().split('CREATE TABLE ')[1:]:
        table=block.split('"')[1]
        for match in re.finditer(r'CHECK \(',block):
            start=match.end();depth=1;quote=False;i=start
            while depth:
                c=block[i]
                if c=="'":quote=not quote
                elif not quote:
                    if c=='(':depth+=1
                    if c==')':depth-=1
                i+=1
            cases.append((table,block[start:i-1]))
    assert len(cases)==36
    return cases


@pytest.mark.parametrize('table,expression',check_cases(),ids=['check'+str(i) for i in range(36)])
@pytest.mark.parametrize('change',['extra','constant','column','operator','function','group'])
def test_every_check_expression_mutation(table,expression,change):
    if change=='extra':altered='('+expression+') OR 1 = 1'
    elif change=='constant':
        altered=re.sub(r"'([^']*)'",lambda m:"'"+m[1]+'_drift' +"'",expression,count=1)
        if altered==expression:altered=re.sub(r'\b[0-9]+\b','99',expression,count=1)
        if altered==expression:altered=expression.replace('IS NULL','IS NOT NULL',1)
        if altered==expression:altered=expression+' AND 1 = 99'
    elif change=='column':altered=re.sub(r'\b[a-z_]+\b','wrong_column',expression,count=1)
    elif change=='operator':
        altered=re.sub(r'>=|<=|<>|>|=',lambda m:'<>' if m[0]!='<>' else '=',expression,count=1)
        if altered==expression:altered=expression.replace(' IN ',' NOT IN ',1).replace(' IS NULL',' IS NOT NULL',1)
    elif change=='function':altered='length('+expression+') > 0'
    else:altered='('+expression+') AND (1 = 1)'
    assert altered!=expression
    sql=mutate_table(fixture(),table,'CHECK ('+expression+')','CHECK ('+altered+')')
    # wrong_column is syntactically valid but SQLite refuses it before creation;
    # writable_schema supplies raw DDL data without executing that expression.
    if change=='column':
        with database() as connection:
            raw=connection.connection.driver_connection
            raw.execute('PRAGMA writable_schema=ON')
            raw.execute('UPDATE sqlite_master SET sql=replace(sql, ?, ?) WHERE name=?',('CHECK ('+expression+')','CHECK ('+altered+')',table))
            raw.commit();raw.execute('PRAGMA writable_schema=OFF')
            reject(connection)
    else:
        with database(sql) as connection:reject(connection)


@pytest.mark.parametrize('table,expression',check_cases(),ids=['check'+str(i) for i in range(36)])
def test_every_check_redundant_groups_and_keyword_case(table,expression):
    altered='(('+expression+'))'
    sql=mutate_table(fixture(),table,'CHECK ('+expression+')','CHECK ('+altered+')')
    with database(sql) as connection:
        with catalog_snapshot(connection) as source:
            assert source.profile.profile_id=='sqlite_models17_v1'


@pytest.mark.parametrize('table,expression',[c for c in check_cases() if ' IN ' in c[1]],ids=lambda value:'enum')
def test_all_enum_order_changes_rejected(table,expression):
    match=re.search(r"IN \('([^']*)','([^']*)'",expression)
    altered=expression[:match.start()]+expression[match.start():].replace(match[0],"IN ('"+match[2]+"','"+match[1]+"'",1)
    with database(mutate_table(fixture(),table,expression,altered)) as connection:reject(connection)


@pytest.mark.parametrize('old,new',[
    ('WHERE get_ordinal IS NULL','WHERE get_ordinal IS NOT NULL'),
    ('WHERE get_ordinal IS NULL','WHERE seq IS NULL'),
    ('WHERE get_ordinal IS NULL','WHERE get_ordinal IS NULL OR seq = 1'),
    ('("task_id", "event_kind") WHERE','("event_kind", "task_id") WHERE'),
],ids=['notnull','column','extra','order'])
def test_partial_predicate_mutations(old,new):
    sql=fixture().replace(old,new);assert sql!=fixture()
    with database(sql) as connection:reject(connection)


def test_capability_constructor_and_forgery():
    with pytest.raises(CatalogError):catalog.CatalogSnapshot(None,None)
    forged=object.__new__(catalog.CatalogSnapshot)
    with pytest.raises(CatalogError,match='snapshot_inactive'):forged.assert_active()
    with database(version=9) as connection:
        with catalog_snapshot(connection) as source:
            for value in (source,source.descriptor,source.profile):
                with pytest.raises(CatalogError,match='connection_required'):
                    with catalog_snapshot(value):pytest.fail('unexpected')
            assert catalog._resolve(source) is connection
            assert not hasattr(source,'connection') and not hasattr(source,'token')
            with pytest.raises(Exception):source.profile=None
    assert not catalog._ACTIVE


@pytest.mark.parametrize('owner',['pid','thread'])
def test_capability_owner_mismatch(monkeypatch,owner):
    with database(version=9) as connection:
        with catalog_snapshot(connection) as source:
            with monkeypatch.context() as patch:
                if owner=='pid':patch.setattr(catalog.os,'getpid',lambda:-1)
                else:patch.setattr(catalog.threading,'get_ident',lambda:-1)
                with pytest.raises(CatalogError,match='snapshot_owner_mismatch') as caught:source.assert_active()
                assert caught.value.__context__ is None
        assert not catalog._ACTIVE


def test_external_e0_token_and_active_transactions():
    with database(version=9) as connection:
        raw=connection.connection.driver_connection
        with readonly_snapshot(connection) as token:
            with pytest.raises(CatalogError,match='connection_required'):
                with catalog_snapshot(token):pytest.fail('unexpected')
        for sqlalchemy_transaction in (True,False):
            if sqlalchemy_transaction:transaction=connection.begin()
            else:raw.execute('BEGIN')
            reject(connection,'active_transaction_refused')
            assert connection.in_transaction() if sqlalchemy_transaction else raw.in_transaction
            if sqlalchemy_transaction:transaction.rollback()
            else:raw.rollback()


@pytest.mark.parametrize('initial',[0,1])
@pytest.mark.parametrize('failure',['none','collect','exception','base'])
def test_query_only_restore_and_original_body(initial,failure,monkeypatch):
    class Stop(BaseException):pass
    body=Stop() if failure=='base' else ValueError('synthetic body')
    with database(version=9) as connection:
        raw=connection.connection.driver_connection;raw.execute('PRAGMA query_only='+str(initial))
        if failure=='collect':
            monkeypatch.setattr(catalog,'_collect',lambda c:(_ for _ in ()).throw(RuntimeError('synthetic private failure')))
            reject(connection,'catalog_failed')
        elif failure in ('exception','base'):
            with pytest.raises(type(body)) as caught:
                with catalog_snapshot(connection) as source:raise body
            assert caught.value is body
            with pytest.raises(CatalogError):source.assert_active()
        else:
            with catalog_snapshot(connection):assert raw.execute('PRAGMA query_only').fetchone()==(1,)
        assert raw.execute('PRAGMA query_only').fetchone()==(initial,)
        assert not raw.in_transaction and not connection.in_transaction() and not catalog._ACTIVE


@pytest.mark.parametrize('operation',['commit','rollback','query_only'])
@pytest.mark.filterwarnings('ignore:transaction already deassociated from connection:sqlalchemy.exc.SAWarning')
def test_context_mutation_is_detected(operation):
    with database(version=9) as connection:
        with pytest.raises(CatalogError,match='snapshot_inactive'):
            with catalog_snapshot(connection) as source:
                if operation=='commit':connection.commit()
                elif operation=='rollback':connection.rollback()
                else:connection.connection.driver_connection.execute('PRAGMA query_only=OFF')
                source.assert_active()
        assert not catalog._ACTIVE


def test_fixed_error_context_in_caller_except():
    try:raise ValueError('private body')
    except ValueError:
        with pytest.raises(CatalogError) as caught:
            with catalog_snapshot(None):pytest.fail('unexpected')
        assert caught.value.__context__ is None and caught.value.__cause__ is None
    for code in catalog._CODES:
        assert CatalogError(code).code==code
    assert CatalogError('unknown').code=='catalog_failed'


def test_pg_dialect_without_psycopg_rejected_by_e0(monkeypatch):
    # PG catalog is approved (B6 PG catalog plan); a non-psycopg driver is
    # still refused by E0 before any transaction starts.
    with database(version=9) as connection:
        monkeypatch.setattr(connection.dialect,'name','postgresql')
        reject(connection,'postgres_driver_unsupported')
        assert not connection.in_transaction()


def test_physical_sqlite_raw_samples_are_not_normalized():
    values=['2026-10-25 01:02:03','2026-10-25T01:02:03.123456+08:00',0,1,2,'2',2.5,b'\x00\xff',None]
    with database(version=9) as connection:
        raw=connection.connection.driver_connection
        raw.execute('CREATE TABLE sample (v)')
        raw.executemany('INSERT INTO sample VALUES (?)',[(v,) for v in values]);raw.commit()
        rows=raw.execute('SELECT v,typeof(v) FROM sample').fetchall()
        assert [row[0] for row in rows]==values
        assert [row[1] for row in rows]==['text','text','integer','integer','integer','text','real','blob','null']
        for (actual,_),expected in zip(rows,values):
            assert type(actual) is type(expected)
            restored=decode_cell(encode_cell(actual))
            assert type(restored) is type(actual) and restored==actual


def test_schema_snapshot_wal_and_next_context(tmp_path,monkeypatch):
    path=tmp_path/'snapshot.db'
    writer=sqlite3.connect(str(path),check_same_thread=False)
    writer.executescript(fixture(9));writer.execute('PRAGMA journal_mode=WAL')
    engine=create_engine('sqlite:///file:'+path.as_posix()+'?mode=ro&uri=true')
    original=catalog._read;once=[];errors=[]
    def read(connection,sql,*args,**kwargs):
        result=original(connection,sql,*args,**kwargs)
        if 'coalesce(max' in sql and not once:
            once.append(True)
            def change():
                try:writer.execute('CREATE TABLE extra (id)');writer.commit()
                except BaseException as error:errors.append(error)
            thread=threading.Thread(target=change);thread.start();thread.join(3)
            assert not thread.is_alive() and not errors
        return result
    try:
        with engine.connect() as connection:
            monkeypatch.setattr(catalog,'_read',read)
            with catalog_snapshot(connection) as source:assert source.profile.profile_id=='legacy_sqlite9_v1'
            reject(connection)
    finally:engine.dispose();writer.close()


def test_rollback_journal_blocks_writer(tmp_path,monkeypatch):
    path=tmp_path/'snapshot.db';writer=sqlite3.connect(str(path),timeout=0.05)
    writer.executescript(fixture(9));writer.execute('PRAGMA journal_mode=DELETE')
    engine=create_engine('sqlite:///file:'+path.as_posix()+'?mode=ro&uri=true')
    original=catalog._read;once=[]
    def read(connection,sql,*args,**kwargs):
        result=original(connection,sql,*args,**kwargs)
        if 'coalesce(max' in sql and not once:
            once.append(True)
            with pytest.raises(sqlite3.OperationalError,match='locked'):
                writer.execute('CREATE TABLE extra (id)');writer.commit()
            writer.rollback()
        return result
    try:
        with engine.connect() as connection:
            monkeypatch.setattr(catalog,'_read',read)
            with catalog_snapshot(connection):pass
        assert once
    finally:engine.dispose();writer.close()


@pytest.mark.parametrize('syntax',["1 != 0","1 == 1","CAST(1 AS INTEGER) = 1","1 + 1 = 2","abs(1) = 1","1 IN (SELECT 1)","1 = 1 /* comment */","1 = 1; SELECT 1","'x' LIKE 'x'","length(main.x)>0"],ids=['ne','eq','cast','arithmetic','function','subquery','comment','multi','like','qualified'])
def test_unknown_expression_parser_complete_consumption(syntax):
    with pytest.raises(CatalogError):catalog._expression(syntax)


def test_ast_depth_limit():
    with pytest.raises(CatalogError,match='catalog_limit_exceeded'):
        catalog._expression(' AND '.join('x = 1' for _ in range(40)))


@pytest.mark.parametrize('field',['count','maximum','total'])
def test_catalog_preflight_limits_and_boundary(field,monkeypatch):
    with database(version=9) as connection:
        row=connection.connection.driver_connection.execute('SELECT count(*),max(length(CAST(sql AS BLOB))),sum(length(CAST(sql AS BLOB))) FROM sqlite_master').fetchone()
        index={'count':0,'maximum':1,'total':2}[field]
        constant={'count':'_MAX_RECORDS','maximum':'_MAX_DDL','total':'_MAX_TOTAL'}[field]
        monkeypatch.setattr(catalog,constant,row[index])
        with catalog_snapshot(connection):pass
        monkeypatch.setattr(catalog,constant,row[index]-1)
        reject(connection,'catalog_limit_exceeded')


@pytest.mark.parametrize('limit,text',[
    ('bytes',' '*65536),('tokens',','*32768),('depth','('*32+'x'+')'*32),
],ids=['bytes','tokens','depth'])
def test_lexer_limit_boundaries(limit,text):
    catalog._lex(text)
    bad=text+' ' if limit=='bytes' else text+',' if limit=='tokens' else '('+text+')'
    with pytest.raises(CatalogError,match='catalog_limit_exceeded'):catalog._lex(bad)


def test_multibyte_size_bound_before_parser():
    with pytest.raises(CatalogError,match='catalog_limit_exceeded'):catalog._lex("'"+'\u00e9'*32768+"'")


@pytest.mark.parametrize('kind',['columns','checks','tables'])
def test_object_count_limits(kind):
    if kind=='columns':sql='CREATE TABLE extra ('+','.join('x'+str(i)+' INTEGER' for i in range(97))+');'
    elif kind=='checks':sql='CREATE TABLE extra (x INTEGER,'+','.join('CHECK (x>0)' for _ in range(97))+');'
    else:sql=''.join('CREATE TABLE extra'+str(i)+' (x INTEGER);' for i in range(19))
    with database(sql) as connection:reject(connection,'catalog_limit_exceeded')


@pytest.mark.parametrize('pragma,change',[
    ('table_xinfo',lambda r:r[:-1]),
    ('table_xinfo',lambda r:[(*r[0][:6],1),*r[1:]]),
    ('table_xinfo',lambda r:[(r[0][0],r[0][1],'BIGINT',*r[0][3:]),*r[1:]]),
    ('foreign_key_list',lambda r:[]),
    ('foreign_key_list',lambda r:[(*r[0][:7],'SIMPLE'),*r[1:]] if r else r),
    ('index_list',lambda r:[]),
    ('index_list',lambda r:[(*r[0][:3],'c',r[0][4]),*r[1:]]),
    ('index_list',lambda r:[(*r[0][:4],1),*r[1:]]),
    ('index_xinfo',lambda r:r[:-1]),
    ('index_xinfo',lambda r:[(r[0][0],-2,None,*r[0][3:]),*r[1:]]),
    ('index_xinfo',lambda r:[(*r[0][:3],1,*r[0][4:]),*r[1:]]),
    ('index_xinfo',lambda r:[(*r[0][:4],'NOCASE',r[0][5]),*r[1:]]),
],ids=['missingcol','hidden','type','missingfk','match','missingidx','origin','partial','missingaux','cid','desc','collation'])
def test_pragma_contradictions_rejected(pragma,change,monkeypatch):
    original=catalog._pragma
    def altered(connection,name,identifier):
        rows=original(connection,name,identifier)
        return change(rows) if name==pragma and rows else rows
    with database(version=9) as connection:
        monkeypatch.setattr(catalog,'_pragma',altered);reject(connection)


@pytest.mark.parametrize('statement',[
    'CREATE TABLE extra(id INTEGER PRIMARY KEY AUTOINCREMENT)',
    'CREATE TABLE extra(id INTEGER, FOREIGN KEY(id) REFERENCES user(id))',
    'CREATE TABLE extra(id INTEGER CHECK(id>0))',
    'CREATE TABLE extra(id INTEGER UNIQUE)',
],ids=['autoincrement','fk','check','unique'])
def test_extra_internal_or_constraints_rejected(statement):
    with database(version=9) as connection:
        connection.connection.driver_connection.execute(statement);reject(connection)


@pytest.mark.parametrize('raw_sql',[
    'CREATE TABLE user (id VARCHAR NOT NULL PRIMARY KEY); SELECT 99',
    'CREATE TABLE user (id VARCHAR NOT NULL PRIMARY KEY) unknown',
    'CREATE TABLE user (id VARCHAR NOT NULL PRIMARY KEY, CHECK (private_canary()))',
    'CREATE TABLE user (id VARCHAR NOT NULL PRIMARY KEY, CHECK (id = \'B6_CATALOG_PRIVATE_CANARY\'))',
    None,
],ids=['multi','tail','function','literal','null'])
def test_raw_catalog_ddl_is_data_and_not_executed(raw_sql,capsys):
    with database(version=9) as connection:
        raw=connection.connection.driver_connection;calls=[];traced=[]
        raw.create_function('private_canary',0,lambda:calls.append(1))
        raw.execute('PRAGMA writable_schema=ON')
        raw.execute('UPDATE sqlite_master SET sql=? WHERE name=\'user\'',(raw_sql,));raw.commit()
        raw.execute('PRAGMA writable_schema=OFF');raw.set_trace_callback(traced.append)
        reject(connection)
        raw.set_trace_callback(None)
        assert calls==[]
        unknown=[sql.split()[0] for sql in traced if not sql.startswith(('PRAGMA ','BEGIN','ROLLBACK','SELECT ','-- PRAGMA '))]
        assert unknown==[]
        assert not any('private_canary' in sql or 'PRIVATE_CANARY' in sql or sql==raw_sql for sql in traced)
        assert capsys.readouterr()==('','')


def test_safe_driver_error_read_and_result_close(monkeypatch):
    class Result:
        def fetchone(self):raise RuntimeError('private driver')
        def close(self):raise RuntimeError('private close')
    with database(version=9) as connection:
        original=connection.exec_driver_sql
        def failure(sql,*args,**kwargs):
            return Result() if 'coalesce(max' in sql else original(sql,*args,**kwargs)
        monkeypatch.setattr(connection,'exec_driver_sql',failure)
        reject(connection,'catalog_failed')
        assert not connection.in_transaction()


@pytest.mark.parametrize('body_exception',[False,True])
def test_restore_failure_priority_and_safe_context(monkeypatch,body_exception):
    original=catalog.readonly_snapshot
    class Context:
        def __init__(self,connection):self.inner=original(connection)
        def __enter__(self):return self.inner.__enter__()
        def __exit__(self,*args):
            try:self.inner.__exit__(*args)
            finally:raise SnapshotConnectionError('connection_restore_failed')
    monkeypatch.setattr(catalog,'readonly_snapshot',Context)
    with database(version=9) as connection:
        with pytest.raises(CatalogError,match='connection_restore_failed') as caught:
            with catalog_snapshot(connection):
                if body_exception:raise KeyboardInterrupt('private original')
        assert caught.value.__context__ is None and caught.value.__cause__ is None
        assert not catalog._ACTIVE


def test_registered_capability_detects_other_connection_and_forgery():
    class Fake:
        descriptor=None
        profile=None
        def assert_active(self):return
    for value in (Fake(),None):
        with pytest.raises(CatalogError):catalog._resolve(value)
    with database(version=9) as a,database(version=9) as b:
        with catalog_snapshot(a) as source:
            forged=object.__new__(catalog.CatalogSnapshot)
            object.__setattr__(forged,'descriptor',source.descriptor)
            object.__setattr__(forged,'profile',source.profile)
            with pytest.raises(CatalogError):forged.assert_active()
            with catalog_snapshot(b) as second:
                assert catalog._resolve(source) is a and catalog._resolve(second) is b
        with pytest.raises(CatalogError):source.assert_active()


def test_runner_guard_uri_attach_and_application_imports(tmp_path):
    import sitecustomize
    for value in ['file:'+str(tmp_path/'x')+'?vfs=private', 'file:'+str(tmp_path/'x')+'?mode=ro&mode=rw',
                  'file://host/path',str(Path(os.environ['SYSTEMROOT'])/'private.db'),'relative.db']:
        with pytest.raises(RuntimeError):sitecustomize.approved(value)
    with database(version=9) as connection:
        raw=connection.connection.driver_connection
        with pytest.raises(sqlite3.DatabaseError):raw.execute('ATTACH DATABASE ? AS forbidden',(str(tmp_path/'bound.db'),))
        with pytest.raises(sqlite3.DatabaseError):raw.execute("SELECT load_extension('forbidden')")
    assert not any(name=='app' or name.startswith(('app.','alembic.','psycopg')) for name in __import__('sys').modules)


def test_read_baseexception_not_overwritten_by_cursor_close(monkeypatch):
    class Stop(BaseException):pass
    stop=Stop()
    class Result:
        def fetchone(self):raise stop
        def close(self):raise RuntimeError('private close')
    with database(version=9) as connection:
        original=connection.exec_driver_sql
        monkeypatch.setattr(connection,'exec_driver_sql',lambda sql,*a,**kw:Result() if 'coalesce(max' in sql else original(sql,*a,**kw))
        with pytest.raises(Stop) as caught:
            with catalog_snapshot(connection):pytest.fail('unexpected')
        assert caught.value is stop and not connection.in_transaction()


def test_identifier_size_preflight_before_full_records(monkeypatch):
    with database(version=9) as connection:
        raw=connection.connection.driver_connection
        raw.execute('PRAGMA writable_schema=ON')
        raw.execute('UPDATE sqlite_master SET name=? WHERE name=\'ix_user_email\'',('x'*129,));raw.commit()
        raw.execute('PRAGMA writable_schema=OFF')
        original=catalog._read
        def bounded(connection,sql,*args,**kwargs):
            if sql.startswith('SELECT type, name, tbl_name, sql'):pytest.fail('unbounded identifiers fetched')
            return original(connection,sql,*args,**kwargs)
        monkeypatch.setattr(catalog,'_read',bounded)
        reject(connection,'catalog_limit_exceeded')


def test_closed_connection_forces_restore_failure_and_invalidates():
    with database(version=9) as connection:
        with pytest.warns(SAWarning,match='^transaction already deassociated from connection$'):
            with pytest.raises(CatalogError,match='connection_restore_failed') as caught:
                with catalog_snapshot(connection) as source:connection.close()
        assert caught.value.__context__ is None and caught.value.__cause__ is None
        assert not catalog._ACTIVE
        with pytest.raises(CatalogError,match='snapshot_inactive'):source.assert_active()


def test_real_cross_thread_capability_refused_before_db_use():
    with database(version=9) as connection:
        with catalog_snapshot(connection) as source:
            errors=[]
            def consumer():
                try:source.assert_active()
                except BaseException as error:errors.append(error)
            thread=threading.Thread(target=consumer);thread.start();thread.join(2)
            assert not thread.is_alive() and len(errors)==1
            assert type(errors[0]) is CatalogError and errors[0].code=='snapshot_owner_mismatch'
            assert errors[0].__context__ is None and catalog._resolve(source) is connection


def test_catalog_subclass_never_gains_capability():
    class Subclass(catalog.CatalogSnapshot):pass
    forged=object.__new__(Subclass)
    with pytest.raises(CatalogError,match='snapshot_inactive'):forged.assert_active()
