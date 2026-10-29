"""Private finite PostgreSQL catalog reader; metadata only, within caller E0.

No engine, DDL execution, source I/O, expected descriptor, ACL certification,
driver callback gate, hard timeout, or export/import behavior is provided here.
"""
from __future__ import annotations

import re
from sqlalchemy import text
from tools.production_db_snapshot_format import SnapshotError, _raise_safe
from tools.production_db_snapshot import SnapshotConnectionError
from tools.production_db_snapshot_schema import (PhysicalType, ColumnDescriptor,
    UniqueDescriptor, ForeignKeyDescriptor, IndexDescriptor, TriggerDescriptor,
    TableDescriptor, SchemaDescriptor)

_MAX_RECORDS = 2048
_MAX_TEXT = 65536
_MAX_TOTAL = 2 << 20
_NAME = re.compile(r'[a-z_][a-z0-9_]{0,127}\Z')


class _PgCatalogError(RuntimeError):
    def __init__(self, code):
        self.code = code if type(code) is str and code in ('catalog_failed','catalog_limit_exceeded') else 'catalog_failed'
        super().__init__(self.code)


def _need(condition, code='source_profile_unsupported'):
    if condition: return
    if code == 'source_profile_unsupported': _raise_safe(code)
    error = _PgCatalogError(code)
    try: raise error
    except _PgCatalogError:
        error.__context__ = error.__cause__ = None
        raise


def _fetch(result, maximum):
    failure = None
    rows = []
    try:
        while True:
            row = result.fetchone()
            if row is None: break
            _need(len(rows) < maximum, 'catalog_limit_exceeded')
            rows.append(tuple(row))
    except BaseException as error: failure = error
    finally:
        try: result.close()
        except Exception:
            if failure is None: raise
    if failure is not None: raise failure
    return rows


def _bounded(connection, sql, params, budget):
    # The subquery is assembled only from module-owned constant SQL. Catalog
    # values never become SQL. Aggregate before fetching any variable content.
    aggregate = ('SELECT pg_catalog.count(1), pg_catalog.max(pg_catalog.octet_length('
        'pg_catalog.row_to_json(q)::pg_catalog.text)), pg_catalog.sum(pg_catalog.octet_length('
        'pg_catalog.row_to_json(q)::pg_catalog.text)) FROM ('+sql+') AS q')
    rows = _fetch(connection.execute(text(aggregate),params),1)
    _need(len(rows)==1 and len(rows[0])==3)
    count, largest, total = rows[0]
    _need(type(count) is int and count >= 0)
    if count == 0:
        _need(largest is None and total is None)
        return []
    _need(type(largest) is int and type(total) is int and largest >= 0 and total >= 0)
    _need(budget[0]+count <= _MAX_RECORDS and largest <= _MAX_TEXT and budget[1]+total <= _MAX_TOTAL,
          'catalog_limit_exceeded')
    budget[0] += count; budget[1] += total
    result = _fetch(connection.execute(text(sql+' LIMIT 2049'),params),count)
    _need(len(result)==count)
    return result


def _notnull(rows, expected):
    actual = set()
    for oid, keys, enforced, noinherit in rows:
        _need(type(oid) is int and type(keys) is list and len(keys)==1 and type(keys[0]) is int)
        _need(type(enforced) is bool and enforced and type(noinherit) is bool and not noinherit)
        _need(keys[0] not in actual)
        actual.add(keys[0])
    _need(actual==expected)
    return actual


def _assert_pg_active(connection, raw):
    state = getattr(raw,'info',None)
    status = getattr(state,'transaction_status',None) if state is not None else raw.get_transaction_status()
    if not ((type(status) is int or type(status).__module__=='psycopg.pq') and status==2):
        raise SnapshotConnectionError('snapshot_inactive')


_REL_FIELDS=('oid','relname','relkind','relpersistence','relispartition','relam','reloftype','reltype',
    'relnatts','relchecks','relhasrules','relhastriggers','relrowsecurity','relforcerowsecurity',
    'reloptions','relreplident','reltoastrelid','relnamespace')
_ATTR_FIELDS=('attrelid','attnum','attname','atttypid','atttypmod','attnotnull','attcollation',
    'attidentity','attgenerated','atthasdef','attisdropped','attislocal','attinhcount')
_CON_FIELDS=('oid','contype','conrelid','contypid','conkey','confrelid','confkey','conindid',
    'condeferrable','condeferred','convalidated','conenforced','conislocal','coninhcount',
    'conparentid','connoinherit','conperiod','confmatchtype','confupdtype','confdeltype',
    'confdelsetcols','conpfeqop','conppeqop','conffeqop','conexclop','conbin','expression','connamespace')
_IDX_FIELDS=('indexrelid','indrelid','indnatts','indnkeyatts','indkey','indclass','indcollation',
    'indoption','indexprs','indpred','indisunique','indnullsnotdistinct','indisprimary','indisexclusion',
    'indimmediate','indisvalid','indisready','indislive','indcheckxmin','predicate')
_TYPE_FIELDS=('oid','typname','typnamespace','typtype','typbasetype','typelem','typrelid','typarray','typcollation')
_PROC_FIELDS=('oid','proname','prolang','prokind','pronargs','proargtypes','proallargtypes','proargmodes',
    'proargnames','pronargdefaults','proargdefaults','provariadic','prorettype','proretset','prosecdef',
    'proconfig','prosrc','probin','prosqlbody','provolatile','proisstrict','proleakproof','proparallel',
    'prosupport','protrftypes','language')
_TRG_FIELDS=('oid','tgrelid','tgname','tgtype','tgenabled','tgisinternal','tgfoid','tgconstraint',
    'tgconstrrelid','tgconstrindid','tgparentid','tgdeferrable','tginitdeferred','tgattr','tgnargs',
    'tgargs','tgqual','tgoldtable','tgnewtable')
_BUILTINS={1043:('varchar','pg_varchar'),25:('text','pg_text'),23:('int4','pg_int4'),20:('int8','pg_int8'),
    701:('float8','pg_float8'),16:('bool','pg_bool'),1082:('date','pg_date'),1184:('timestamptz','pg_timestamptz')}
_HEADS=('b1_0001','b1b_0002','b1b_0003','b3b_0004')


def _records(connection,fields,sql,params,budget):
    result=[]
    for row in _bounded(connection,sql,params,budget):
        _need(len(row)==len(fields))
        result.append(dict(zip(fields,row)))
    return result


def _raw_valid(value,depth=0):
    _need(depth<=8,'catalog_limit_exceeded')
    kind=type(value)
    if kind is str:
        _need(len(value)<=_MAX_TEXT and len(value.encode('utf8'))<=_MAX_TEXT,'catalog_limit_exceeded')
    elif kind is list or kind is tuple:
        _need(len(value)<=2048,'catalog_limit_exceeded')
        for item in value:_raw_valid(item,depth+1)
    elif kind is dict:
        _need(len(value)<=40,'catalog_limit_exceeded')
        for key,item in value.items():_need(type(key) is str);_raw_valid(item,depth+1)
    else:_need(kind in (int,bool,bytes,type(None)))


def _name(value):_need(type(value) is str and _NAME.fullmatch(value) is not None)


def _oid_map(rows):
    result={}
    for row in rows:
        oid=row['oid'];_need(type(oid) is int and oid>0 and oid not in result);result[oid]=row
    return result


def _keys(value,columns):
    _need(type(value) is list and 1<=len(value)<=96 and all(type(v) is int and v in columns for v in value))
    _need(len(set(value))==len(value))
    return tuple(columns[v]['attname'] for v in value)


def _edge(deps,source,target,kind):
    value=(*source,*target,kind);_need(value in deps)
    return value


def _describe(data):
    # Validate container/scalar exact types before comparison, hashing or sorting.
    _need(type(data) is dict and len(data)<=24)
    for key,value in data.items():
        _need(type(key) is str)
        if key not in ('relations','columns','constraints','indexes','types','functions','triggers',
            'dependencies','defaults','forbidden','opclasses','operators','builtin_functions','collations','languages'):
            _raw_valid(value);continue
        _need(type(value) is list and len(value)<=2048,'catalog_limit_exceeded')
        for row in value:_raw_valid(row)
    app=data['namespace'];_need(type(app) is int and app>0)
    rels=_oid_map(data['relations']);types=_oid_map(data['types']);constraints=_oid_map(data['constraints'])
    procs=_oid_map(data['functions']);triggers=_oid_map(data['triggers'])
    _need(not data['defaults'] and not data['forbidden'])
    deps=set(data['dependencies']);_need(len(deps)==len(data['dependencies']))
    _need(all(type(dep) is tuple and len(dep)==7 and all(type(x) is int for x in dep[:6]) and type(dep[6]) is str for dep in deps))
    heaps={oid:r for oid,r in rels.items() if r['relnamespace']==app and r['relkind']=='r'}
    _need(1<=len(heaps)<=18)
    indexes={}
    for index in data['indexes']:
        oid=index['indexrelid'];_need(oid not in indexes);indexes[oid]=index
    _need(set(rels)==set(heaps)|set(indexes)|{r['reltoastrelid'] for r in heaps.values() if r['reltoastrelid']})
    columns={oid:{} for oid in heaps}
    toast_heaps={r['reltoastrelid']:oid for oid,r in heaps.items() if r['reltoastrelid']}
    toast_columns={oid:{} for oid in toast_heaps}
    for column in data['columns']:
        relid=column['attrelid'];number=column['attnum']
        target=columns if relid in columns else toast_columns
        _need(relid in target and type(number) is int and 1<=number<=96 and number not in target[relid])
        target[relid][number]=column
    allowed_deps=set();owned={(2615,app,0)}
    tables=[];function_ids={}
    for oid,proc in procs.items():
        _name(proc['proname']);function_ids[oid]=_function_id(tuple(proc.items()))
        owned.add((1255,oid,0))
        allowed_deps.add(_edge(deps,(1255,oid,0),(2615,app,0),'n'))
        allowed_deps.add(_edge(deps,(1255,oid,0),(2612,proc['prolang'],0),'n'))
        _need((proc['prolang'],'plpgsql',True) in data['languages'])
    _need(len(set(function_ids.values()))==len(function_ids))
    for oid,relation in heaps.items():
        _name(relation['relname']);_ordinary(relation,heap=True)
        owned.add((1259,oid,0));allowed_deps.add(_edge(deps,(1259,oid,0),(2615,app,0),'n'))
        attrs=columns[oid];_need(len(attrs)==relation['relnatts'] and set(attrs)==set(range(1,len(attrs)+1)))
        rowtype=types.get(relation['reltype']);_need(rowtype is not None)
        _need(rowtype['typtype']=='c' and rowtype['typrelid']==oid and rowtype['typnamespace']==app and rowtype['typbasetype']==0 and rowtype['typelem']==0)
        array=types.get(rowtype['typarray']);_need(array is not None)
        _need(array['typtype']=='b' and array['typelem']==rowtype['oid'] and array['typrelid']==0 and array['typnamespace']==app and array['typbasetype']==0)
        for typeoid,target in ((rowtype['oid'],(1259,oid,0)),(array['oid'],(1247,rowtype['oid'],0))):
            owned.add((1247,typeoid,0));allowed_deps.add(_edge(deps,(1247,typeoid,0),target,'i'))
        coldescs=[]
        for number,column in attrs.items():
            _name(column['attname'])
            _need(column['attidentity']=='' and column['attgenerated']=='' and not column['atthasdef'] and not column['attisdropped'] and column['attislocal'] and column['attinhcount']==0)
            typ=types.get(column['atttypid']);_need(typ is not None and typ['oid'] in _BUILTINS)
            _need(typ['typnamespace']==11 and typ['typname']==_BUILTINS[typ['oid']][0] and typ['typtype']=='b' and typ['typbasetype']==0 and typ['typelem']==0)
            mod=column['atttypmod'];_need(type(mod) is int)
            if typ['oid']==1043:_need(mod==-1 or 5<=mod<=1048580);args=() if mod==-1 else (mod-4,)
            else:_need(mod==-1);args=()
            _need(column['attcollation']==(100 if typ['oid'] in (1043,25) else 0))
            if column['attcollation']:_need((100,'default',11,'d',-1,True) in data['collations'])
            coldescs.append(ColumnDescriptor(column['attname'],PhysicalType(_BUILTINS[typ['oid']][1],args),not column['attnotnull'],'absent','absent','absent','dialect_default'))
        cons=[c for c in constraints.values() if c['conrelid']==oid]
        _need(len(cons)<=96,'catalog_limit_exceeded')
        checks=[];uniques=[];fks=[];pk=();backing={};notnull=[]
        for con in cons:
            _constraint_base(con,app);cid=con['oid'];kind=con['contype'];owned.add((2606,cid,0))
            keys=_keys(con['conkey'],attrs)
            for number in con['conkey']:
                allowed_deps.add(_edge(deps,(2606,cid,0),(1259,oid,number),'a'))
            if kind=='n':notnull.append((cid,con['conkey'],con['conenforced'],con['connoinherit']))
            elif kind=='c':
                _need(not con['connoinherit'] and type(con['conbin']) is str and type(con['expression']) is str)
                checks.append(_check_id(relation['relname'],con['expression']))
            elif kind in ('p','u'):
                _need(con['conindid'] in indexes and con['conindid'] not in backing)
                backing[con['conindid']]=con
                allowed_deps.add(_edge(deps,(1259,con['conindid'],0),(2606,cid,0),'i'))
                if kind=='p':_need(not pk);pk=keys
                else:uniques.append(UniqueDescriptor(keys,True,False,False,True))
            elif kind=='f':
                target=con['confrelid'];_need(target in heaps and target in columns)
                targetcols=columns[target];targetkeys=_keys(con['confkey'],targetcols)
                _need(len(keys)==len(targetkeys) and con['conindid'] in indexes and indexes[con['conindid']]['indrelid']==target)
                _need(con['confmatchtype']=='s' and con['confupdtype'] in 'arcnd' and con['confdeltype'] in 'arcnd' and con['confdelsetcols'] is None)
                _foreign_operators(con,attrs,targetcols,data)
                actions={'a':'NO_ACTION','r':'RESTRICT','c':'CASCADE','n':'SET_NULL','d':'SET_DEFAULT'}
                fks.append(ForeignKeyDescriptor(keys,'app',heaps[target]['relname'],targetkeys,actions[con['confupdtype']],actions[con['confdeltype']],'SIMPLE',False,False,True))
            else:_need(False)
            for dep in deps:
                if dep[:3]!=(2606,cid,0):continue
                refclass,refid,refsub,deptype=dep[3:]
                if refclass==1259 and refid==oid and refsub in con['conkey'] and deptype in ('a','n'):allowed_deps.add(dep)
                elif kind=='f' and refclass==1259 and deptype=='n' and ((refid==con['confrelid'] and refsub in con['confkey']) or (refid==con['conindid'] and refsub==0)):allowed_deps.add(dep)
                elif kind=='c' and deptype=='n' and (refclass,refid) in _builtin_dependency_ids(data):allowed_deps.add(dep)
        _notnull(notnull,{n for n,c in attrs.items() if c['attnotnull']})
        _need(relation['relchecks']==len(checks))
        explicit=[]
        for ixid,index in indexes.items():
            if index['indrelid']!=oid:continue
            indexrel=rels[ixid];_ordinary(indexrel,heap=False);_need(indexrel['relnamespace']==app)
            owned.add((1259,ixid,0));_index(index,attrs,data)
            keys=_keys(index['indkey'],attrs)
            if ixid in backing:
                con=backing[ixid]
                _need(keys==_keys(con['conkey'],attrs) and index['indisunique'] and index['indisprimary']==(con['contype']=='p') and index['indpred'] is None)
            else:
                _need(not index['indisprimary'])
                for number in index['indkey']:allowed_deps.add(_edge(deps,(1259,ixid,0),(1259,oid,number),'a'))
                predicate='absent'
                if index['indpred'] is not None:
                    _need(relation['relname']=='billingreconciliationaudit' and keys==('task_id','event_kind') and index['indisunique'] and _expression(index['predicate'])==('null',('column','get_ordinal')))
                    predicate='get_ordinal_is_null_v1'
                    # A partial predicate adds dependencies on its referenced column.
                    number=next(n for n,c in attrs.items() if c['attname']=='get_ordinal')
                    for kind in ('a','n'):
                        edge=(1259,ixid,0,1259,oid,number,kind)
                        if edge in deps:allowed_deps.add(edge)
                explicit.append(IndexDescriptor(keys,index['indisunique'],'btree',('asc',)*len(keys),('dialect_default',)*len(keys),predicate,(),True))
        rules=[];actual_triggers=[t for t in triggers.values() if t['tgrelid']==oid]
        _need(relation['relhastriggers']==bool(actual_triggers))
        for trigger in actual_triggers:
            tid=trigger['oid'];owned.add((2620,tid,0))
            if trigger['tgisinternal']:
                _internal_trigger(trigger,constraints,heaps,indexes,data)
                allowed_deps.add(_edge(deps,(2620,tid,0),(2606,trigger['tgconstraint'],0),'i'))
            else:
                rules.append(_trigger(trigger,relation['relname'],function_ids))
                allowed_deps.add(_edge(deps,(2620,tid,0),(1259,oid,0),'a'))
                allowed_deps.add(_edge(deps,(2620,tid,0),(1255,trigger['tgfoid'],0),'n'))
        tables.append(TableDescriptor(relation['relname'],tuple(coldescs),pk,tuple(uniques),tuple(fks),tuple(explicit),tuple(checks),tuple(rules),'pg_ordinary_heap_v1','nondeferrable_validated_v1'))
    _need(set(constraints)=={c['oid'] for c in constraints.values() if c['conrelid'] in heaps})
    _need(set(triggers)=={t['oid'] for t in triggers.values() if t['tgrelid'] in heaps})
    _toast(toast_heaps,toast_columns,rels,indexes,deps,owned,allowed_deps,data)
    _need({oid for oid,t in types.items() if t['typnamespace']==app}=={oid for cls,oid,sub in owned if cls==1247})
    # Every captured dependency has a reviewed meaning; no unknown endpoints,
    # extension memberships, references into/out of the app closure, or leftovers.
    _need(deps==allowed_deps)
    _need(type(data['head']) is str and data['head'] in _HEADS)
    return SchemaDescriptor(1,'pg','app',(data['head'],),tuple(t for t in tables if t.name!='alembic_version'),
        tuple(t for t in tables if t.name=='alembic_version'),tuple(sorted(function_ids.values())),())


def _ordinary(row,*,heap):
    _need(row['relkind']==('r' if heap else 'i') and row['relpersistence']=='p' and not row['relispartition'] and row['relam']==(2 if heap else 403) and row['reloftype']==0)
    _need(not row['relhasrules'] and not row['relrowsecurity'] and not row['relforcerowsecurity'] and row['reloptions'] is None and row['relreplident']==('d' if heap else 'n'))
    if not heap:_need(not row['relhastriggers'] and row['relchecks']==0 and row['reltype']==0 and row['reltoastrelid']==0)


def _constraint_base(con,app):
    _need(con['connamespace']==app and con['contypid']==0 and con['contype'] in ('n','c','p','u','f'))
    _need(not con['condeferrable'] and not con['condeferred'] and con['convalidated'] and con['conenforced'] and con['conislocal'] and con['coninhcount']==0 and con['conparentid']==0 and not con['conperiod'] and con['conexclop'] is None)
    if con['contype']!='c':_need(con['conbin'] is None and con['expression'] is None)
    if con['contype'] not in ('p','u','f'):_need(con['conindid']==0)
    if con['contype']!='f':
        _need(con['confrelid']==0 and con['confkey'] is None and con['confdelsetcols'] is None and con['conpfeqop'] is None and con['conppeqop'] is None and con['conffeqop'] is None)


def _index(index,columns,data):
    _need(index['indnatts']==index['indnkeyatts']==len(index['indkey']) and 1<=len(index['indkey'])<=96)
    _need(index['indisvalid'] and index['indisready'] and index['indislive'] and index['indimmediate'] and not index['indisexclusion'] and not index['indcheckxmin'] and not index['indnullsnotdistinct'] and index['indexprs'] is None)
    _keys(index['indkey'],columns)
    _need(all(type(index[x]) is list and len(index[x])==len(index['indkey']) for x in ('indclass','indcollation','indoption')))
    classes={row[0]:row for row in data['opclasses']}
    names={25:('text_ops','text_ops'),23:('int4_ops','integer_ops'),20:('int8_ops','integer_ops'),
        701:('float8_ops','float_ops'),16:('bool_ops','bool_ops'),1082:('date_ops','datetime_ops'),1184:('timestamptz_ops','datetime_ops')}
    for number,opclass,collation,option in zip(index['indkey'],index['indclass'],index['indcollation'],index['indoption']):
        typ=columns[number]['atttypid'];typ=25 if typ==1043 else typ
        _need(typ in names and opclass in classes)
        row=classes[opclass];name,family=names[typ]
        _need(row[1:]==(name,11,403,typ,True,0,family,11))
        _need(collation==columns[number]['attcollation'] and option==0)


def _foreign_operators(con,attrs,targetcols,data):
    operators={row[0]:row for row in data['operators']}
    sources={25:'texteq',23:'int4eq',20:'int8eq',701:'float8eq',16:'booleq',1082:'date_eq',1184:'timestamp_eq'}
    for array in ('conpfeqop','conppeqop','conffeqop'):
        values=con[array];_need(type(values) is list and len(values)==len(con['conkey']))
        for opid,left,right in zip(values,con['conkey'],con['confkey']):
            a=attrs[left]['atttypid'];b=targetcols[right]['atttypid'];a=25 if a==1043 else a;b=25 if b==1043 else b
            _need(a==b and opid in operators and a in sources)
            row=operators[opid]
            _need(row[1:]==('=',11,a,a,16,11,12,sources[a],sources[a],None,'f',False,False,False))


def _builtin_dependency_ids(data):
    # Pinned builtins normally have no pg_depend rows. Non-pinned dependencies
    # are accepted only with the same fully validated signatures, never OID size.
    return set()


_RULES={('billingreconciliationaudit','b3b_reject_mutation.v1',27):('trg_b3b_audit_row.v1',('UPDATE','DELETE'),'ROW'),
 ('billingreconciliationaudit','b3b_reject_mutation.v1',34):('trg_b3b_audit_truncate.v1',('TRUNCATE',),'STATEMENT'),
 ('billingreconciliationtask','b3b_reject_mutation.v1',11):('trg_b3b_task_delete.v1',('DELETE',),'ROW'),
 ('billingreconciliationtask','b3b_reject_mutation.v1',34):('trg_b3b_task_truncate.v1',('TRUNCATE',),'STATEMENT'),
 ('billingreconciliationtask','b3b_task_update_guard.v1',19):('trg_b3b_task_update.v1',('UPDATE',),'ROW')}


def _trigger_base(trigger):
    _need(trigger['tgenabled']=='O' and trigger['tgparentid']==0 and not trigger['tgdeferrable'] and not trigger['tginitdeferred'] and trigger['tgattr']==[] and trigger['tgnargs']==0 and trigger['tgargs']==b'' and trigger['tgqual'] is None and trigger['tgoldtable'] is None and trigger['tgnewtable'] is None)


def _trigger(trigger,table,functions):
    _trigger_base(trigger);_need(not trigger['tgisinternal'] and trigger['tgconstraint']==0 and trigger['tgconstrrelid']==0 and trigger['tgconstrindid']==0 and trigger['tgfoid'] in functions)
    fn=functions[trigger['tgfoid']];key=(table,fn,trigger['tgtype']);_need(key in _RULES)
    rule,events,level=_RULES[key]
    return TriggerDescriptor(rule,fn,'BEFORE',events,level,'origin_enabled_v1')


def _internal_trigger(trigger,constraints,heaps,indexes,data):
    _trigger_base(trigger);con=constraints.get(trigger['tgconstraint'])
    _need(con is not None and con['contype']=='f' and trigger['tgconstrindid']==con['conindid'])
    procs={row[0]:row for row in data['builtin_functions']}
    row=procs.get(trigger['tgfoid']);_need(row is not None)
    _need(row[1]==11 and row[3]==12 and row[4]=='f' and row[5]==0 and row[6]=='' and row[7]==2279 and row[8] is False and row[9] is None and row[10] is None)
    function=row[2];_need(row[11]==function)
    if function=='RI_FKey_check_ins':expected=(con['conrelid'],con['confrelid'],5)
    elif function=='RI_FKey_check_upd':expected=(con['conrelid'],con['confrelid'],17)
    else:
        action={'a':'noaction','r':'restrict','c':'cascade','n':'setnull','d':'setdefault'}
        possibilities={('RI_FKey_'+action[con['confdeltype']]+'_del'):9,
          ('RI_FKey_'+action[con['confupdtype']]+'_upd'):17}
        _need(function in possibilities);expected=(con['confrelid'],con['conrelid'],possibilities[function])
    _need((trigger['tgrelid'],trigger['tgconstrrelid'],trigger['tgtype'])==expected)


def _toast(toast_heaps,columns,rels,indexes,deps,owned,allowed,data):
    for oid,parent in toast_heaps.items():
        relation=rels[oid]
        _need(relation['relkind']=='t' and relation['relpersistence']=='p' and relation['relam']==2 and relation['reloftype']==0 and relation['reltype']==0 and relation['relnatts']==3 and not relation['relhasrules'] and not relation['relhastriggers'] and not relation['relrowsecurity'] and not relation['relforcerowsecurity'] and not relation['relispartition'] and relation['reloptions'] is None and relation['reltoastrelid']==0)
        owned.add((1259,oid,0));allowed.add(_edge(deps,(1259,oid,0),(1259,parent,0),'i'))
        attrs=columns[oid];_need(set(attrs)=={1,2,3})
        _need(tuple((attrs[n]['attname'],attrs[n]['atttypid']) for n in (1,2,3))==(('chunk_id',26),('chunk_seq',23),('chunk_data',17)))
        matches=[i for i in indexes.values() if i['indrelid']==oid];_need(len(matches)==1)
        index=matches[0];ixid=index['indexrelid'];indexrel=rels[ixid];_ordinary(indexrel,heap=False)
        _need(indexrel['relnamespace']==relation['relnamespace'] and index['indkey']==[1,2] and index['indnatts']==index['indnkeyatts']==2 and index['indisunique'] and index['indisprimary'] and index['indpred'] is None and index['indexprs'] is None and index['indoption']==[0,0] and index['indcollation']==[0,0] and index['indisvalid'] and index['indisready'] and index['indislive'] and index['indimmediate'] and not index['indnullsnotdistinct'] and not index['indisexclusion'] and not index['indcheckxmin'])
        classes={r[0]:r for r in data['opclasses']}
        _need(len(index['indclass'])==2 and all(x in classes for x in index['indclass']))
        _need(tuple(classes[x][1:] for x in index['indclass'])==(('oid_ops',11,403,26,True,0,'oid_ops',11),('int4_ops',11,403,23,True,0,'integer_ops',11)))
        # TOAST index has no pg_depend rows: it is an implementation member of
        # the dependent toast relation. Its class/type/key is checked explicitly.
        owned.add((1259,ixid,0))
        for n in (1,2):
            edge=(1259,ixid,0,1259,oid,n,'a')
            if edge in deps:allowed.add(edge)


def _collect_pg(connection):
    budget=[0,0]
    # Fixed SQL only; SET LOCAL and every SELECT run on the one E0 connection.
    connection.execute(text('SET LOCAL search_path=pg_catalog')).close()
    namespaces=_bounded(connection,"SELECT n.oid,n.nspname FROM pg_catalog.pg_namespace n WHERE n.nspname OPERATOR(pg_catalog.=) 'app'",{},budget)
    _need(len(namespaces)==1 and len(namespaces[0])==2 and type(namespaces[0][0]) is int and namespaces[0][1]=='app')
    app=namespaces[0][0];params={'app':app}
    temp=_bounded(connection,"""SELECT c.oid FROM pg_catalog.pg_class c WHERE c.relnamespace OPERATOR(pg_catalog.=) pg_catalog.pg_my_temp_schema()
      UNION ALL SELECT p.oid FROM pg_catalog.pg_proc p WHERE p.pronamespace OPERATOR(pg_catalog.=) pg_catalog.pg_my_temp_schema()
      UNION ALL SELECT t.oid FROM pg_catalog.pg_type t WHERE t.typnamespace OPERATOR(pg_catalog.=) pg_catalog.pg_my_temp_schema()""",{},budget)
    _need(not temp)
    apprels='SELECT a.oid FROM pg_catalog.pg_class a WHERE a.relnamespace OPERATOR(pg_catalog.=) :app'
    toastrels='SELECT a.reltoastrelid FROM pg_catalog.pg_class a WHERE a.relnamespace OPERATOR(pg_catalog.=) :app'
    scope='c.relnamespace OPERATOR(pg_catalog.=) :app OR c.oid IN ('+toastrels+') OR c.oid IN (SELECT i.indexrelid FROM pg_catalog.pg_index i WHERE i.indrelid IN ('+toastrels+'))'
    relations=_records(connection,_REL_FIELDS,'SELECT '+','.join('c.'+x for x in _REL_FIELDS)+' FROM pg_catalog.pg_class c WHERE '+scope,params,budget)
    relationids=[r['oid'] for r in relations];params['relations']=relationids
    columns=_records(connection,_ATTR_FIELDS,'SELECT '+','.join('a.'+x for x in _ATTR_FIELDS)+
      ' FROM pg_catalog.pg_attribute a WHERE a.attrelid OPERATOR(pg_catalog.=) ANY(:relations) AND a.attnum OPERATOR(pg_catalog.>) 0 AND a.attrelid IN (SELECT c.oid FROM pg_catalog.pg_class c WHERE c.relkind IN (\'r\',\'t\')) ORDER BY a.attrelid,a.attnum',params,budget)
    conselect=','.join('c.'+x if x not in ('conbin','expression') else ('c.conbin::pg_catalog.text' if x=='conbin' else 'pg_catalog.pg_get_expr(c.conbin,c.conrelid,false)') for x in _CON_FIELDS)
    constraints=_records(connection,_CON_FIELDS,'SELECT '+conselect+' FROM pg_catalog.pg_constraint c WHERE c.connamespace OPERATOR(pg_catalog.=) :app OR c.conrelid OPERATOR(pg_catalog.=) ANY(:relations) OR c.confrelid OPERATOR(pg_catalog.=) ANY(:relations)',params,budget)
    idxselect=','.join(('i.'+x+'::pg_catalog.int2[]' if x in ('indkey','indoption') else 'i.'+x+'::pg_catalog.oid[]' if x in ('indclass','indcollation') else 'i.'+x+'::pg_catalog.text' if x in ('indexprs','indpred') else 'pg_catalog.pg_get_expr(i.indpred,i.indrelid,false)' if x=='predicate' else 'i.'+x) for x in _IDX_FIELDS)
    indexes=_records(connection,_IDX_FIELDS,'SELECT '+idxselect+' FROM pg_catalog.pg_index i WHERE i.indexrelid OPERATOR(pg_catalog.=) ANY(:relations) OR i.indrelid OPERATOR(pg_catalog.=) ANY(:relations)',params,budget)
    procselect=','.join('l.lanname' if x=='language' else 'p.'+x+'::pg_catalog.text' if x in ('proargtypes','proargdefaults','prosqlbody') else 'p.prosupport::pg_catalog.oid' if x=='prosupport' else 'p.'+x for x in _PROC_FIELDS)
    functions=_records(connection,_PROC_FIELDS,'SELECT '+procselect+' FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_language l ON l.oid OPERATOR(pg_catalog.=) p.prolang WHERE p.pronamespace OPERATOR(pg_catalog.=) :app',params,budget)
    params['functions']=[p['oid'] for p in functions]
    trgselect=','.join('t.'+x+'::pg_catalog.int2[]' if x=='tgattr' else 't.'+x+'::pg_catalog.text' if x=='tgqual' else 't.'+x for x in _TRG_FIELDS)
    triggers=_records(connection,_TRG_FIELDS,'SELECT '+trgselect+' FROM pg_catalog.pg_trigger t WHERE t.tgrelid OPERATOR(pg_catalog.=) ANY(:relations) OR t.tgfoid OPERATOR(pg_catalog.=) ANY(:functions)',params,budget)
    types=_records(connection,_TYPE_FIELDS,'SELECT '+','.join('t.'+x for x in _TYPE_FIELDS)+
      ' FROM pg_catalog.pg_type t WHERE t.typnamespace OPERATOR(pg_catalog.=) :app OR t.oid IN (1043,25,23,20,701,16,1082,1184)',params,budget)
    defaults=_bounded(connection,'SELECT a.oid FROM pg_catalog.pg_attrdef a WHERE a.adrelid OPERATOR(pg_catalog.=) ANY(:relations)',params,budget)
    # All forbidden categories are enumerated for the namespace/relation union.
    forbidden_sql="""SELECT o.oid FROM pg_catalog.pg_operator o WHERE o.oprnamespace OPERATOR(pg_catalog.=) :app
      UNION ALL SELECT o.oid FROM pg_catalog.pg_opclass o WHERE o.opcnamespace OPERATOR(pg_catalog.=) :app
      UNION ALL SELECT o.oid FROM pg_catalog.pg_opfamily o WHERE o.opfnamespace OPERATOR(pg_catalog.=) :app
      UNION ALL SELECT o.oid FROM pg_catalog.pg_collation o WHERE o.collnamespace OPERATOR(pg_catalog.=) :app
      UNION ALL SELECT o.oid FROM pg_catalog.pg_conversion o WHERE o.connamespace OPERATOR(pg_catalog.=) :app
      UNION ALL SELECT o.oid FROM pg_catalog.pg_ts_config o WHERE o.cfgnamespace OPERATOR(pg_catalog.=) :app
      UNION ALL SELECT o.oid FROM pg_catalog.pg_ts_dict o WHERE o.dictnamespace OPERATOR(pg_catalog.=) :app
      UNION ALL SELECT o.oid FROM pg_catalog.pg_ts_parser o WHERE o.prsnamespace OPERATOR(pg_catalog.=) :app
      UNION ALL SELECT o.oid FROM pg_catalog.pg_ts_template o WHERE o.tmplnamespace OPERATOR(pg_catalog.=) :app
      UNION ALL SELECT o.oid FROM pg_catalog.pg_rewrite o WHERE o.ev_class OPERATOR(pg_catalog.=) ANY(:relations)
      UNION ALL SELECT o.oid FROM pg_catalog.pg_policy o WHERE o.polrelid OPERATOR(pg_catalog.=) ANY(:relations)
      UNION ALL SELECT o.inhrelid FROM pg_catalog.pg_inherits o WHERE o.inhrelid OPERATOR(pg_catalog.=) ANY(:relations) OR o.inhparent OPERATOR(pg_catalog.=) ANY(:relations)
      UNION ALL SELECT o.partrelid FROM pg_catalog.pg_partitioned_table o WHERE o.partrelid OPERATOR(pg_catalog.=) ANY(:relations)
      UNION ALL SELECT o.ftrelid FROM pg_catalog.pg_foreign_table o WHERE o.ftrelid OPERATOR(pg_catalog.=) ANY(:relations)
      UNION ALL SELECT o.seqrelid FROM pg_catalog.pg_sequence o WHERE o.seqrelid OPERATOR(pg_catalog.=) ANY(:relations)
      UNION ALL SELECT o.oid FROM pg_catalog.pg_statistic_ext o WHERE o.stxrelid OPERATOR(pg_catalog.=) ANY(:relations) OR o.stxnamespace OPERATOR(pg_catalog.=) :app"""
    forbidden=_bounded(connection,forbidden_sql,params,budget)
    params.update(types=[t['oid'] for t in types if t['typnamespace']==app],constraints=[c['oid'] for c in constraints],triggers=[t['oid'] for t in triggers])
    # Full bidirectional dependency union. Class OIDs are fixed PG catalog IDs,
    # never a heuristic about the numerical size of user object OIDs.
    source=' OR '.join('(d.classid OPERATOR(pg_catalog.=) '+str(cls)+' AND d.objid OPERATOR(pg_catalog.=) ANY(:'+key+'))' for cls,key in ((1259,'relations'),(1247,'types'),(1255,'functions'),(2606,'constraints'),(2620,'triggers')))
    target=source.replace('d.classid','d.refclassid').replace('d.objid','d.refobjid')
    dependencies=_bounded(connection,'SELECT d.classid,d.objid,d.objsubid,d.refclassid,d.refobjid,d.refobjsubid,d.deptype FROM pg_catalog.pg_depend d WHERE '+source+' OR '+target,params,budget)
    params['opclasses']=list({v for i in indexes for v in i['indclass']})
    opclasses=_bounded(connection,'SELECT o.oid,o.opcname,o.opcnamespace,o.opcmethod,o.opcintype,o.opcdefault,o.opckeytype,f.opfname,f.opfnamespace FROM pg_catalog.pg_opclass o JOIN pg_catalog.pg_opfamily f ON f.oid OPERATOR(pg_catalog.=) o.opcfamily WHERE o.oid OPERATOR(pg_catalog.=) ANY(:opclasses)',params,budget)
    params['operators']=list({v for c in constraints for key in ('conpfeqop','conppeqop','conffeqop') for v in (c[key] or [])})
    operators=_bounded(connection,'SELECT o.oid,o.oprname,o.oprnamespace,o.oprleft,o.oprright,o.oprresult,p.pronamespace,p.prolang,p.proname,p.prosrc,p.probin,p.prokind,p.prosecdef,p.proretset,p.proisstrict IS FALSE FROM pg_catalog.pg_operator o JOIN pg_catalog.pg_proc p ON p.oid OPERATOR(pg_catalog.=) o.oprcode WHERE o.oid OPERATOR(pg_catalog.=) ANY(:operators)',params,budget)
    params['builtinfunctions']=[t['tgfoid'] for t in triggers if t['tgisinternal']]
    builtin_functions=_bounded(connection,'SELECT p.oid,p.pronamespace,p.proname,p.prolang,p.prokind,p.pronargs,p.proargtypes::pg_catalog.text,p.prorettype,p.prosecdef,p.proconfig,p.probin,p.prosrc FROM pg_catalog.pg_proc p WHERE p.oid OPERATOR(pg_catalog.=) ANY(:builtinfunctions)',params,budget)
    collations=_bounded(connection,'SELECT c.oid,c.collname,c.collnamespace,c.collprovider,c.collencoding,c.collisdeterministic FROM pg_catalog.pg_collation c WHERE c.oid OPERATOR(pg_catalog.=) 100',{},budget)
    params['languages']=[p['prolang'] for p in functions]
    languages=_bounded(connection,'SELECT l.oid,l.lanname,l.lanpltrusted FROM pg_catalog.pg_language l WHERE l.oid OPERATOR(pg_catalog.=) ANY(:languages)',params,budget)
    data=dict(namespace=app,relations=relations,columns=columns,constraints=constraints,indexes=indexes,functions=functions,
      triggers=triggers,types=types,defaults=defaults,forbidden=forbidden,dependencies=dependencies,opclasses=opclasses,
      operators=operators,builtin_functions=builtin_functions,collations=collations,languages=languages,head='b1_0001')
    # Validate every object, including the metadata relation, before reading its
    # single metadata value. No business rows are read by this collector.
    preliminary=_describe(data)
    _need(len(preliminary.metadata_tables)==1)
    metadata=preliminary.metadata_tables[0]
    _need(metadata==TableDescriptor('alembic_version',(ColumnDescriptor('version_num',PhysicalType('pg_varchar',(32,)),False,'absent','absent','absent','dialect_default'),),('version_num',),(),(),(),(),(),'pg_ordinary_heap_v1','nondeferrable_validated_v1'))
    heads=_fetch(connection.execute(text('SELECT version_num FROM app.alembic_version LIMIT 2')),2)
    _need(len(heads)==1 and len(heads[0])==1 and type(heads[0][0]) is str and heads[0][0] in _HEADS)
    data['head']=heads[0][0]
    return _describe(data)


def _lex(source):
    _need(type(source) is str)
    _need(len(source)<=_MAX_TEXT and len(source.encode('utf8'))<=_MAX_TEXT,'catalog_limit_exceeded')
    tokens=[];offset=depth=0
    while offset<len(source):
        char=source[offset]
        if char.isspace():offset+=1;continue
        if char in "'\"":
            quote=char;offset+=1;value=''
            while offset<len(source):
                if source[offset]==quote:
                    if offset+1<len(source) and source[offset+1]==quote:
                        value+=quote;offset+=2;continue
                    offset+=1;break
                value+=source[offset];offset+=1
            else:_need(False)
            if quote=='"':_need(_NAME.fullmatch(value) is not None)
            tokens.append(('s' if quote=="'" else 'w',value))
        elif char.isascii() and char.isdigit():
            word=re.match('[0-9]+',source[offset:])[0]
            _need(len(word)<=10,'catalog_limit_exceeded')
            tokens.append(('n',int(word)));offset+=len(word)
        elif char.isascii() and (char.isalpha() or char=='_'):
            word=re.match('[A-Za-z_][A-Za-z0-9_]*',source[offset:])[0]
            _need(len(word)<=128,'catalog_limit_exceeded')
            tokens.append(('w',word.lower()));offset+=len(word)
        else:
            pair=source[offset:offset+2]
            if pair in ('::','>=','<=','<>'):tokens.append(('p',pair));offset+=2
            else:
                _need(char in '(),.[]=<>~+;')
                if char in '([':
                    depth+=1;_need(depth<=32,'catalog_limit_exceeded')
                if char in ')]':depth-=1;_need(depth>=0)
                tokens.append(('p',char));offset+=1
        _need(len(tokens)<=32768,'catalog_limit_exceeded')
    _need(depth==0)
    return tuple(tokens)


class _Expression:
    def __init__(self,source):self.tokens=_lex(source);self.pos=0
    def take(self,value):
        if self.pos<len(self.tokens) and self.tokens[self.pos][1]==value:
            self.pos+=1;return True
        return False
    def expect(self,value):_need(self.take(value))
    def word(self):
        _need(self.pos<len(self.tokens) and self.tokens[self.pos][0]=='w')
        value=self.tokens[self.pos][1];self.pos+=1;return value
    def logical(self,operator,child):
        values=[child()]
        while self.take(operator):values.append(child())
        if len(values)==1:return values[0]
        # PG flattens associative boolean parentheses; order is preserved.
        flat=[]
        for value in values:flat.extend(value[1] if value[0]==operator else (value,))
        return (operator,tuple(flat))
    def expression(self):return self.logical('or',lambda:self.logical('and',self.compare))
    def compare(self):
        node=self.atom()
        if self.take('is'):
            negate=self.take('not');self.expect('null');return ('notnull' if negate else 'null',node)
        if self.take('between'):
            low=self.atom();self.expect('and');high=self.atom()
            return ('and',(('>=',node,low),('<=',node,high)))
        if self.take('in'):
            self.expect('(');values=[self.atom()]
            while self.take(','):values.append(self.atom())
            self.expect(')');return ('in',node,tuple(values))
        operator=None
        if self.take('operator'):
            self.expect('(');_need(self.word()=='pg_catalog');self.expect('.')
            _need(self.pos<len(self.tokens));operator=self.tokens[self.pos][1];self.pos+=1;self.expect(')')
            _need(operator in ('=','<>','>','>=','<','<=','~'))
        else:
            for candidate in ('=','<>','>','>=','<','<=','~'):
                if self.take(candidate):operator=candidate;break
        if operator:
            if self.take('any'):
                _need(operator=='=');self.expect('(');array=self.atom();self.expect(')')
                # Only the known PG enum expansion, retaining item order.
                if array[0]=='cast' and array[2]=='text[]':array=array[1]
                _need(array[0]=='array');return ('in',node,array[1])
            return (operator,node,self.atom())
        return node
    def atom(self):
        if self.take('('):node=self.expression();self.expect(')')
        elif self.take('array'):
            self.expect('[');values=[self.atom()]
            while self.take(','):values.append(self.atom());_need(len(values)<=96,'catalog_limit_exceeded')
            self.expect(']');node=('array',tuple(values))
        else:
            _need(self.pos<len(self.tokens));kind,value=self.tokens[self.pos];self.pos+=1
            if kind in ('n','s'):node=(kind,value)
            else:
                _need(kind=='w')
                if self.take('.'):
                    _need(value=='pg_catalog');value=self.word()
                if value in ('true','false'):node=('bool',value)
                elif self.take('('):
                    _need(value in ('length','octet_length','jsonb_typeof'))
                    node=('call',value,self.atom());self.expect(')')
                else:node=('column',value)
        while self.take('::'):
            target=self.word()
            if self.take('.'):_need(target=='pg_catalog');target=self.word()
            if target=='character':self.expect('varying');target='varchar'
            _need(target in ('text','varchar','jsonb'))
            if self.take('['):self.expect(']');target+='[]'
            node=('cast',node,target)
        return node


# Only declared varchar operands can use PG's implicit varchar -> text relabel.
_TEXT_COLUMNS=frozenset(('status','state','provider_account_scope','reconciliation','reason_code',
    'event_kind','budget_checkpoint_json','actor_ref','evidence_ref','input_sha256','projection_sha256'))


def _normalize(node):
    if node[0]=='cast' and node[2] in ('text','varchar'):
        child=_normalize(node[1])
        _need(child[0]=='s' or (node[2]=='text' and child[0]=='column' and child[1] in _TEXT_COLUMNS))
        return child
    parts=[]
    for value in node[1:]:
        if type(value) is tuple:
            value=tuple(_normalize(x) for x in value) if value and type(value[0]) is tuple else _normalize(value)
        parts.append(value)
    return (node[0],*parts)


def _expression(source):
    parser=_Expression(source);node=parser.expression();_need(parser.pos==len(parser.tokens))
    node=_normalize(node)
    pending=[(node,1)]
    while pending:
        value,depth=pending.pop();_need(depth<=32,'catalog_limit_exceeded')
        pending.extend((x,depth+1) for x in value if type(x) is tuple)
    return node


def _checks():return {(table,_expression(expr)):identifier for table,identifier,expr in _CHECK_TEXT}


def _check_id(table,expression):
    _need(type(table) is str and _NAME.fullmatch(table) is not None)
    node=_expression(expression);mapping=_checks();_need((table,node) in mapping)
    return mapping[table,node]


def _function_id(record):
    _need(type(record) is tuple and len(record)<=40)
    _need(all(type(x) is tuple and len(x)==2 and type(x[0]) is str for x in record))
    data=dict(record);_need(len(data)==len(record))
    expected=dict(prokind='f',pronargs=0,proargtypes='',proallargtypes=None,proargmodes=None,
        proargnames=None,pronargdefaults=0,proargdefaults=None,provariadic=0,prorettype=2279,
        proretset=False,prosecdef=False,proconfig=['search_path=pg_catalog'],probin=None,
        prosqlbody=None,provolatile='v',proisstrict=False,proleakproof=False,proparallel='u',
        prosupport=0,protrftypes=None,language='plpgsql')
    _need(set(data)==set(expected)|{'oid','proname','prosrc','prolang'})
    for key,value in expected.items():_need(type(data[key]) is type(value) and data[key]==value)
    _need(type(data['oid']) is int and type(data['prolang']) is int and type(data['proname']) is str)
    body=_lex(data['prosrc'])
    matches=[identifier for identifier,source in _FUNCTION_TEXT if _lex(source)==body]
    _need(len(matches)==1)
    return matches[0]
_CHECK_TEXT = (('job', 'job.status.v1', "status IN ('queued','downloading','merging','done','error')"), ('downloadoperation', 'downloadoperation.state.v1', "state IN ('resolving','accepted_server','direct_ready','succeeded','failed','needs_review')"), ('downloadoperation', 'downloadoperation.budget_checkpoint.v1', 'budget_version > 0 AND length(budget_checkpoint_json) > 0'), ('downloadoperation', 'downloadoperation.checkpoint_time.v1', 'budget_checkpoint_at >= accepted_at'), ('downloadoperation', 'downloadoperation.access_snapshot.v1', 'membership_revision >= 0 AND (max_height IS NULL OR max_height > 0)'), ('downloadoperation', 'downloadoperation.resolve_lease_pair.v1', '(resolve_owner IS NULL) = (resolve_lease_deadline IS NULL)'), ('downloadoperation', 'downloadoperation.deadline.v1', 'deadline_at >= accepted_at'), ('downloadoperation', 'downloadoperation.resolve_budget.v1', 'resolve_epoch >= 0 AND resolve_attempts_used >= 0 AND resolve_attempts_used <= resolve_attempts_limit AND resolve_attempts_limit > 0'), ('downloadoperation', 'downloadoperation.resolve_deadline.v1', 'resolve_deadline_at >= accepted_at AND resolve_deadline_at <= deadline_at'), ('quotacharge', 'quotacharge.delta_one.v1', 'delta = 1'), ('resourcecounter', 'resourcecounter.used_nonnegative.v1', 'used >= 0'), ('resourcereservation', 'resourcereservation.release_state.v1', '(released = false AND released_at IS NULL) OR (released = true AND released_at IS NOT NULL)'), ('resourcereservation', 'resourcereservation.units_positive.v1', 'units > 0'), ('billinginbox', 'billinginbox.status.v1', "status IN ('received','processing','retry_wait','waiting_binding','applied','ignored','needs_review')"), ('billinginbox', 'billinginbox.lease_pair.v1', '(lease_owner IS NULL) = (lease_deadline IS NULL)'), ('billinginbox', 'billinginbox.processing_lease.v1', "status <> 'processing' OR lease_owner IS NOT NULL"), ('billinginbox', 'billinginbox.budget.v1', 'attempt_count >= 0 AND attempt_limit > 0 AND attempt_count <= attempt_limit AND lease_epoch >= 0'), ('billinginbox', 'billinginbox.canonical_version.v1', 'canonical_version > 0'), ('billinginbox', 'billinginbox.budget_deadline.v1', 'budget_deadline >= received_at'), ('billingfact', 'billingfact.amount_total.v1', 'amount_total IS NULL OR amount_total >= 0'), ('billingfact', 'billingfact.amount_refunded.v1', 'amount_refunded IS NULL OR amount_refunded >= 0'), ('billingfact', 'billingfact.reconciliation.v1', "reconciliation IN ('unknown','verified','needs_review')"), ('billingfact', 'billingfact.scope_mode.v1', "(provider_account_scope = 'legacy_unknown' AND livemode IS NULL) OR (provider_account_scope <> 'legacy_unknown' AND livemode IS NOT NULL)"), ('billingcheckout', 'billingcheckout.reconcile_attempts.v1', 'reconcile_attempts >= 0 AND reconcile_attempts <= 3'), ('billingcheckout', 'billingcheckout.reconciliation.v1', "reconciliation IS NULL OR reconciliation IN ('not_started','unknown','verified','needs_review','closed')"), ('billingevent', 'billingevent.scope_mode.v1', "(provider_account_scope = 'legacy_unknown' AND livemode IS NULL) OR (provider_account_scope <> 'legacy_unknown' AND livemode IS NOT NULL)"), ('billingreconciliationtask', 'billingreconciliationtask.policy_json.v1', "octet_length(policy_json) BETWEEN 1 AND 65536 AND jsonb_typeof(policy_json::jsonb)='object'"), ('billingreconciliationtask', 'billingreconciliationtask.revisions.v1', 'initial_checkout_revision>=0 AND expected_checkout_revision>=initial_checkout_revision AND membership_revision>=0 AND revision>=0 AND next_audit_seq>=1'), ('billingreconciliationtask', 'billingreconciliationtask.input_sha256.v1', "input_sha256 ~ '^[0-9a-f]{64}$'"), ('billingreconciliationtask', 'billingreconciliationtask.scope.v1', "provider_account_scope <> 'legacy_unknown' AND length(provider_account_scope)>0"), ('billingreconciliationtask', 'billingreconciliationtask.query_json.v1', "octet_length(query_json) BETWEEN 1 AND 65536 AND jsonb_typeof(query_json::jsonb)='object'"), ('billingreconciliationtask', 'billingreconciliationtask.get_budget.v1', 'get_attempts>=0 AND get_attempts<=get_limit'), ('billingreconciliationtask', 'billingreconciliationtask.audit_context.v1', "actor_ref ~ '^op:[A-Za-z0-9_.:-]{1,60}$' AND evidence_ref ~ '^ev:[A-Za-z0-9_.:-]{1,120}$'"), ('billingreconciliationtask', 'billingreconciliationtask.versions_limits.v1', 'input_version=1 AND budget_version=1 AND get_limit=3'), ('billingreconciliationtask', 'billingreconciliationtask.deadline.v1', 'budget_deadline>=started_at'), ('billingreconciliationtask', 'billingreconciliationtask.reason.v1', "reason_code IN ('unknown_create','missing_reference','legacy_verification')"), ('billingreconciliationtask', 'billingreconciliationtask.terminal.v1', "(status='running' AND completed_at IS NULL) OR (status IN ('verified','needs_review') AND completed_at IS NOT NULL)"), ('billingreconciliationaudit', 'billingreconciliationaudit.projection_json.v1', "octet_length(projection_json) BETWEEN 1 AND 65536 AND jsonb_typeof(projection_json::jsonb)='object'"), ('billingreconciliationaudit', 'billingreconciliationaudit.reason.v1', "reason_code IN ('unknown_create','missing_reference','legacy_verification')"), ('billingreconciliationaudit', 'billingreconciliationaudit.sequence_version.v1', 'seq>0 AND projection_version=1'), ('billingreconciliationaudit', 'billingreconciliationaudit.projection_sha256.v1', "projection_sha256 ~ '^[0-9a-f]{64}$'"), ('billingreconciliationaudit', 'billingreconciliationaudit.audit_context.v1', "actor_ref ~ '^op:[A-Za-z0-9_.:-]{1,60}$' AND evidence_ref ~ '^ev:[A-Za-z0-9_.:-]{1,120}$'"), ('billingreconciliationaudit', 'billingreconciliationaudit.event_ordinal.v1', "(event_kind IN ('task_started','task_finished') AND get_ordinal IS NULL) OR (event_kind IN ('get_reserved','get_observed') AND get_ordinal IS NOT NULL AND get_ordinal BETWEEN 1 AND 3)"))
_FUNCTION_TEXT = (('b3b_reject_mutation.v1', "\nBEGIN\n  RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='B3b immutable reconciliation evidence';\nEND;\n"), ('b3b_task_update_guard.v1', "\nBEGIN\n  IF ROW(NEW.id,NEW.checkout_id,NEW.user_id,NEW.provider_account_scope,NEW.livemode,NEW.actor_ref,NEW.reason_code,NEW.evidence_ref,NEW.input_version,NEW.input_sha256,NEW.query_json,NEW.policy_json,NEW.initial_checkout_revision,NEW.membership_revision,NEW.owner_ref,NEW.started_at,NEW.budget_deadline,NEW.get_limit,NEW.budget_version) IS DISTINCT FROM ROW(OLD.id,OLD.checkout_id,OLD.user_id,OLD.provider_account_scope,OLD.livemode,OLD.actor_ref,OLD.reason_code,OLD.evidence_ref,OLD.input_version,OLD.input_sha256,OLD.query_json,OLD.policy_json,OLD.initial_checkout_revision,OLD.membership_revision,OLD.owner_ref,OLD.started_at,OLD.budget_deadline,OLD.get_limit,OLD.budget_version ) THEN\n    RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='B3b task identity and policy are frozen';\n  END IF;\n  IF OLD.status <> 'running' AND NEW IS DISTINCT FROM OLD THEN\n    RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='B3b terminal task is immutable';\n  END IF;\n  IF NEW.get_attempts < OLD.get_attempts OR NEW.get_attempts > OLD.get_attempts + 1\n     OR NEW.get_attempts > 3 OR NEW.next_audit_seq < OLD.next_audit_seq\n     OR NEW.revision < OLD.revision OR NEW.expected_checkout_revision < OLD.expected_checkout_revision THEN\n    RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='B3b task counters must advance monotonically';\n  END IF;\n  RETURN NEW;\nEND;\n"))

