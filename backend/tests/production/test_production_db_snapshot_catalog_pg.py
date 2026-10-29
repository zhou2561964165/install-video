"""Opt-in nonce-owned PG catalog metadata tests; never target pv_verify."""
from pathlib import Path
import copy
import json
import os
import traceback
import pytest
from sqlalchemy import text
from tools.production_db_snapshot_catalog import catalog_snapshot, CatalogError
from tools.production_db_snapshot_schema import schema_document
from tools.production_db_snapshot_profiles import SOURCE_PROFILES
from tools import _production_db_snapshot_catalog_pg as pg

pytestmark=pytest.mark.skipif(not os.environ.get('B3B_PG_OWNERSHIP'),reason='explicit owned PG window required')
TASK=Path(r'E:\install_video\.planning\2026-10-24-production-execution')


def write_evidence(name,value):
    label=os.environ['B6_CATALOG_PG_LABEL']
    def safe(item):
        if type(item) is bytes:return {'bytes_hex':item.hex()}
        raise TypeError('unsupported_metadata')
    with (TASK/f'b6-catalog-pg-{label}-{name}.json').open('x',encoding='utf8') as stream:
        json.dump(value,stream,indent=2,default=safe)


def test_four_real_migration_heads(monkeypatch):
    from b3b_pg_helpers import isolated_database
    original=pg._describe;captures=[];errors=[];matched=[]
    def capture(data):
        captures.append(copy.deepcopy(data))
        return original(data)
    monkeypatch.setattr(pg,'_describe',capture)
    heads=('b1_0001','b1b_0002','b1b_0003','b3b_0004')
    with isolated_database(target=heads[0]) as case:
        for index,head in enumerate(heads):
            if index:case.migrate(target=head)
            with case.application.connect() as connection:
                before=connection.scalar(text('SHOW search_path'));connection.rollback()
                try:
                    with catalog_snapshot(connection) as source:
                        profile='pg_'+head+'_v1'
                        expected=json.loads((TASK/f'b6-source-profiles-golden-{profile}.json').read_text('utf8'))
                        assert schema_document(source.descriptor)==expected
                        assert source.descriptor is not SOURCE_PROFILES[profile].descriptor
                        assert source.profile.profile_id==profile
                        assert source.descriptor.heads==(head,)
                        assert len(source.descriptor.tables)==(9,13,15,17)[index]
                        assert sum(len(t.columns) for t in source.descriptor.tables)==(63,105,165,203)[index]
                        assert len(source.descriptor.metadata_tables)==1
                        assert connection.scalar(text('SHOW search_path'))=='pg_catalog'
                        assert connection.scalar(text('SHOW transaction_isolation'))=='repeatable read'
                        assert connection.scalar(text('SHOW transaction_read_only'))=='on'
                        source.assert_active()
                    assert connection.scalar(text('SHOW search_path'))==before
                    connection.rollback()
                    matched.append(head)
                except Exception as error:
                    errors.append(dict(head=head,code=getattr(error,'code',type(error).__name__),
                        frames=[dict(file=Path(f.filename).name,line=f.lineno) for f in traceback.extract_tb(error.__traceback__)]))
                    connection.rollback()
                    assert connection.scalar(text('SHOW search_path'))==before
                    connection.rollback()
    write_evidence('actual-catalog',captures)
    write_evidence('head-results',dict(matched=matched,errors=errors))
    assert not errors, 'four_head_catalog_rejected_see_metadata_evidence'
