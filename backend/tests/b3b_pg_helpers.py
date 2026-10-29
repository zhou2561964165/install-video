"""B3b-only disposable PG databases. Explicit identity/ownership; no env/old DB fallback."""
from contextlib import contextmanager
from dataclasses import dataclass
import json
import time
import os
from pathlib import Path
import re
import socket
from threading import local
import uuid

import pytest
from alembic import command
from sqlalchemy import URL, create_engine, text
from sqlalchemy.pool import NullPool

from app import db

TASK=Path(r'E:\install_video\.planning\2026-10-24-production-execution').resolve()
CONTROL=TASK/'postgres-runtime/control.json'
ROLES={'bootstrap':'pv_bootstrap','migration':'pv_migrator','application':'pv_app'}
NAME=re.compile(r'pv_b3b_[0-9a-f]{12}_[0-9a-f]{8}\Z')
NONCE=re.compile(r'[0-9a-f]{32}\Z')


class IsolationError(RuntimeError):
    pass


def validated_control(marker=None, ownership=None):
    marker=marker if marker is not None else os.environ.get('B3B_PG_CONTROL')
    ownership=ownership if ownership is not None else os.environ.get('B3B_PG_OWNERSHIP')
    if not marker or not ownership:
        raise IsolationError('Explicit B3b control and ownership are required')
    path=Path(marker).resolve()
    owner_path=Path(ownership).resolve()
    if path!=CONTROL or owner_path.parent!=TASK or not owner_path.name.startswith('b3b-db-ownership-'):
        raise IsolationError('B3b control/ownership target mismatch')
    control=json.loads(path.read_text('utf8'))
    if (control['host']!='127.0.0.1' or control['port']!=62328 or control['database']!='pv_verify'
            or control['schema']!='app' or control['roles']!=ROLES
            or Path(control['data_directory']).resolve()!=(TASK/'postgres-runtime/cluster').resolve()):
        raise IsolationError('B3b isolated cluster identity mismatch')
    record=json.loads(owner_path.read_text('utf8'))
    if (not NONCE.fullmatch(record.get('run_nonce','')) or record.get('control_path')!=str(CONTROL)
            or record.get('port')!=62328 or record.get('server_pid')!=control.get('server_pid')
            or not record.get('ready')):
        raise IsolationError('B3b ownership is not ready')
    return control,owner_path,record


def save_record(path,record):
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(record,indent=2),encoding='utf8')
    # Windows: a scanner/indexer can briefly hold the target (WinError 5). Retry the same atomic
    # replace a bounded number of times; a persistent failure still raises.
    for attempt in range(20):
        try:
            temp.replace(path)
            return
        except PermissionError:
            if attempt==19:
                raise
            time.sleep(0.05*(attempt+1))


def connection_engine(control,role,database,*,bootstrap=False):
    if role not in ROLES or (database!='postgres' and database!='pv_verify' and not NAME.fullmatch(database)):
        raise IsolationError('B3b connection target rejected')
    if database=='pv_verify' and role!='migration':
        raise IsolationError('B3b pv_verify access is restricted to the protected read snapshot')
    if bootstrap and database!='postgres':
        _,_,ownership=validated_control()
        if not any(item['database']==database and item['oid'] is not None and not item['dropped'] for item in ownership['databases']):
            raise IsolationError('B3b bootstrap database is not owned by this run')
    values=json.loads((CONTROL.parent/'private/credentials.json').read_text('utf8'))
    url=URL.create('postgresql+psycopg',username=ROLES[role],password=values[role],
                   host='127.0.0.1',port=62328,database=database)
    try:
        if bootstrap:
            if role!='bootstrap' or (database!='postgres' and not NAME.fullmatch(database)):
                raise IsolationError('B3b bootstrap target rejected')
            return create_engine(url,echo=False,hide_parameters=True,poolclass=NullPool,
                                 isolation_level='AUTOCOMMIT',connect_args={'connect_timeout':3,
                                 'options':'-c timezone=UTC -c search_path=pg_catalog -c statement_timeout=10000'})
        return db.build_engine(url,role='migration' if role=='migration' else 'api')
    finally:
        del values,url


def verify_cluster(connection,control,record):
    info=connection.execute(text("SELECT current_database(),current_user,current_setting('server_version'),host(inet_server_addr()),inet_server_port(),current_setting('data_directory'),(SELECT system_identifier::text FROM pg_control_system())")).one()
    if (tuple(info[:5])!=('postgres','pv_bootstrap','18.6','127.0.0.1',62328)
            or Path(info[5]).resolve()!=Path(control['data_directory']).resolve()
            or info[6]!=record['cluster_identifier']):
        raise IsolationError('B3b live cluster identity mismatch')
    lines=(Path(control['data_directory'])/'postmaster.pid').read_text('utf8').splitlines()
    if (int(lines[0])!=control['server_pid'] or int(lines[0])!=record['server_pid']
            or Path(lines[1]).resolve()!=Path(control['data_directory']).resolve() or int(lines[3])!=62328):
        raise IsolationError('B3b server PID/port mismatch')


@dataclass
class DisposableDatabase:
    application: object
    migration: object
    database: str
    oid: int
    nonce: str

    def migrate(self,action='upgrade',target='head',*,runtime_roles=('pv_app',)):
        config=db.migration_config()
        if runtime_roles is not None:
            config.attributes['b3b_runtime_roles']=runtime_roles
        with self.migration.begin() as connection:
            config.attributes['connection']=connection
            getattr(command,action)(config,target)


def drop_owned_database(admin,control,path,record,item):
    """Shared normal/runner-failure cleanup. Never infer ownership from a prefix."""
    current=json.loads(path.read_text('utf8'))
    if current['run_nonce']!=record['run_nonce']:
        raise IsolationError('B3b ownership record changed; database retained')
    stored=next((entry for entry in current['databases'] if entry['database']==item['database']),None)
    if stored is None or any(stored[key]!=item[key] for key in ('oid','nonce','owner','before_absent')):
        raise IsolationError('B3b database ownership record changed')
    record.clear()
    record.update(current)
    item=stored
    name=item['database']
    if (not NAME.fullmatch(name) or not NONCE.fullmatch(item['nonce']) or
            name!='pv_b3b_'+record['run_nonce'][:12]+'_'+item['nonce'][:8] or
            not item['before_absent'] or item['oid'] is None or item['owner']!='pv_migrator'):
        raise IsolationError('B3b cleanup record mismatch; database retained')
    with admin.connect() as connection:
        verify_cluster(connection,control,record)
        row=connection.execute(text("SELECT d.oid,pg_get_userbyid(d.datdba),shobj_description(d.oid,'pg_database') FROM pg_database d WHERE datname=:name"),{'name':name}).one_or_none()
        if row is None or tuple(row)!=(item['oid'],'pv_migrator','b3b:'+record['run_nonce']+':'+item['nonce']):
            raise IsolationError('B3b cleanup ownership mismatch; database retained')
        connection.execute(text('SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datid=:oid AND pid<>pg_backend_pid()'),{'oid':item['oid']})
        connection.execute(text('DROP DATABASE "'+name+'"'))
        assert not connection.scalar(text('SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname=:name)'),{'name':name})
    item.update(dropped=True,phase='dropped',identity_verified_before_drop=True)
    save_record(path,record)


@contextmanager
def isolated_database(*,target='head'):
    control,path,record=validated_control()
    if any(not item['dropped'] for item in record['databases']):
        raise IsolationError('B3b database provisioning must be serialized')
    admin=connection_engine(control,'bootstrap','postgres',bootstrap=True)
    case_nonce=uuid.uuid4().hex
    name='pv_b3b_'+record['run_nonce'][:12]+'_'+case_nonce[:8]
    item={'database':name,'nonce':case_nonce,'oid':None,'owner':'pv_migrator',
          'before_absent':False,'phase':'planned','dropped':False}
    record['databases'].append(item)
    save_record(path,record)
    application=migration=None
    created=False
    try:
        with admin.connect() as connection:
            verify_cluster(connection,control,record)
            if connection.scalar(text('SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname=:name)'),{'name':name}):
                raise IsolationError('B3b database existed before this run')
            item['before_absent']=True
            save_record(path,record)
            connection.execute(text('CREATE DATABASE "'+name+'" OWNER pv_migrator TEMPLATE template0'))
            created=True
            item['oid']=connection.scalar(text('SELECT oid FROM pg_database WHERE datname=:name'),{'name':name})
            connection.execute(text('COMMENT ON DATABASE "'+name+'" IS \'b3b:'+record['run_nonce']+':'+case_nonce+'\''))
            item['phase']='created'
            save_record(path,record)
            connection.execute(text('REVOKE ALL ON DATABASE "'+name+'" FROM PUBLIC'))
            connection.execute(text('GRANT CONNECT ON DATABASE "'+name+'" TO pv_app'))
        migration=connection_engine(control,'migration',name)
        application=connection_engine(control,'application',name)
        with migration.begin() as connection:
            assert connection.scalar(text('SELECT current_database()'))==name
            connection.execute(text('REVOKE ALL ON SCHEMA public FROM PUBLIC'))
            connection.execute(text('CREATE SCHEMA app AUTHORIZATION pv_migrator'))
            connection.execute(text('GRANT USAGE ON SCHEMA app TO pv_app'))
            # Reproduce the existing broad DML inheritance; b3b migration must narrow it.
            connection.execute(text('ALTER DEFAULT PRIVILEGES FOR ROLE pv_migrator IN SCHEMA app GRANT SELECT,INSERT,UPDATE,DELETE ON TABLES TO pv_app'))
        case=DisposableDatabase(application,migration,name,item['oid'],case_nonce)
        case.migrate(target=target)
        item['phase']='migrated'
        save_record(path,record)
        yield case
    finally:
        for engine in (application,migration):
            if engine is not None:
                engine.dispose()
        if created:
            try:
                drop_owned_database(admin,control,path,record,item)
            except Exception:
                next(entry for entry in record['databases'] if entry['database']==name)['phase']='retained_cleanup_failed'
                save_record(path,record)
                raise
            finally:
                admin.dispose()
        else:
            admin.dispose()


@contextmanager
def owned_probe_roles(count=1):
    """Root-authorized NOLOGIN negative probes only; no original role membership edits."""
    if not 1<=count<=2:
        raise IsolationError('B3b probe role count rejected')
    control,path,record=validated_control()
    admin=connection_engine(control,'bootstrap','postgres',bootstrap=True)
    names=[]
    try:
        for _ in range(count):
            nonce=uuid.uuid4().hex
            name='pv_b3b_role_'+record['run_nonce'][:12]+'_'+nonce[:8]
            item={'role':name,'nonce':nonce,'oid':None,'before_absent':False,'dropped':False,'memberships':[]}
            record.setdefault('probe_roles',[]).append(item)
            save_record(path,record)
            with admin.connect() as connection:
                verify_cluster(connection,control,record)
                assert not connection.scalar(text('SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=:name)'),{'name':name})
                item['before_absent']=True
                save_record(path,record)
                connection.execute(text('CREATE ROLE "'+name+'" NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS INHERIT'))
                item['oid']=connection.scalar(text('SELECT oid FROM pg_roles WHERE rolname=:name'),{'name':name})
                connection.execute(text('COMMENT ON ROLE "'+name+'" IS \'b3b:'+record['run_nonce']+':'+nonce+'\''))
                save_record(path,record)
            names.append(name)
        yield names
    finally:
        try:
            current=json.loads(path.read_text('utf8'))
            assert current['run_nonce']==record['run_nonce']
            for name in reversed(names):
                item=next(entry for entry in current['probe_roles'] if entry['role']==name)
                drop_owned_probe_role(admin,control,path,current,item)
        finally:
            admin.dispose()


def grant_probe_membership(parent,member):
    control,path,record=validated_control()
    own={entry['role'] for entry in record.get('probe_roles',[]) if not entry['dropped']}
    if member not in own or (parent not in own and parent not in {'pg_read_server_files','pg_signal_backend'}):
        raise IsolationError('B3b probe membership target rejected')
    admin=connection_engine(control,'bootstrap','postgres',bootstrap=True)
    try:
        with admin.connect() as connection:
            verify_cluster(connection,control,record)
            connection.execute(text('GRANT "'+parent+'" TO "'+member+'"'))
        next(entry for entry in record['probe_roles'] if entry['role']==member)['memberships'].append(parent)
        save_record(path,record)
    finally:
        admin.dispose()


def drop_owned_probe_role(admin,control,path,record,item):
    name=item['role']
    if (not re.fullmatch(r'pv_b3b_role_[0-9a-f]{12}_[0-9a-f]{8}',name) or
            not item['before_absent'] or item['oid'] is None or
            name!='pv_b3b_role_'+record['run_nonce'][:12]+'_'+item['nonce'][:8]):
        raise IsolationError('B3b probe role ownership mismatch; retained')
    with admin.connect() as connection:
        verify_cluster(connection,control,record)
        row=connection.execute(text("SELECT oid,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls,rolcanlogin,rolconfig,shobj_description(oid,'pg_authid') FROM pg_roles WHERE rolname=:name"),{'name':name}).one_or_none()
        if (row is None or row[0]!=item['oid'] or any(row[1:7]) or row[7] is not None or
                row[8]!='b3b:'+record['run_nonce']+':'+item['nonce']):
            raise IsolationError('B3b probe role identity changed; retained')
        memberships=connection.scalars(text('SELECT p.rolname FROM pg_auth_members m JOIN pg_roles p ON p.oid=m.roleid WHERE m.member=:oid ORDER BY p.rolname'),{'oid':item['oid']}).all()
        if memberships!=sorted(item['memberships']):
            raise IsolationError('B3b probe role memberships changed; retained')
        connection.execute(text('DROP ROLE "'+name+'"'))
        assert not connection.scalar(text('SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=:name)'),{'name':name})
    item.update(dropped=True,identity_verified_before_drop=True)
    save_record(path,record)


@pytest.fixture
def guarded_sockets(monkeypatch):
    original_connect=socket.socket.connect
    original_connect_ex=socket.socket.connect_ex
    original_pair=socket.socketpair
    original_resolve=socket.getaddrinfo
    state=local()
    def pair(*args,**kwargs):
        state.pair=True
        try:
            return original_pair(*args,**kwargs)
        finally:
            state.pair=False
    def allowed(address):
        return (isinstance(address,tuple) and address[0] in {'127.0.0.1','::1'} and
                (address[1]==62328 or getattr(state,'pair',False)))
    def connect(sock,address):
        if not allowed(address):
            raise IsolationError('B3b external socket denied')
        return original_connect(sock,address)
    def connect_ex(sock,address):
        if not allowed(address):
            raise IsolationError('B3b external socket denied')
        return original_connect_ex(sock,address)
    def resolve(host,*args,**kwargs):
        if host not in {'127.0.0.1','::1'}:
            raise IsolationError('B3b external DNS denied')
        return original_resolve(host,*args,**kwargs)
    def sendto(*args,**kwargs):
        raise IsolationError('B3b UDP socket denied')
    monkeypatch.setattr(socket,'socketpair',pair)
    monkeypatch.setattr(socket.socket,'connect',connect)
    monkeypatch.setattr(socket.socket,'connect_ex',connect_ex)
    monkeypatch.setattr(socket.socket,'sendto',sendto)
    monkeypatch.setattr(socket,'getaddrinfo',resolve)


@pytest.fixture
def schema_pg(guarded_sockets):
    if not os.environ.get('B3B_PG_CONTROL'):
        pytest.skip('Explicit B3B_PG_CONTROL opt-in required')
    with isolated_database() as case:
        yield case


@pytest.fixture
def pg(schema_pg):
    """Runtime owner consumes only this explicitly disposable application Engine."""
    yield schema_pg.application
