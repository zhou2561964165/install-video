"""B5 U5b Task 3: media_check 'signature' (container-signature check; 'verified' stays for decode-level)."""
import os

import pytest
from sqlalchemy import text

from test_pg_download_worker import media, run, worker  # noqa: F401  (fixtures/helpers)
from test_pg_job_repository import case, db, submit  # noqa: F401  (fixtures/helpers)

pytestmark = pytest.mark.skipif(not os.environ.get('B3B_PG_OWNERSHIP'), reason='explicit owned PG window required')


def test_chain_follows_orphans():
    from alembic.script import ScriptDirectory
    from app import db as app_db
    script = ScriptDirectory.from_config(app_db.migration_config())
    assert script.get_revision('b5_0012').down_revision == 'c5b_0011'
    assert 'b5_0012' not in script.get_heads()


def test_signature_check_publishes_end_to_end(case, worker, media, submit):
    job = submit('k1').job_id
    assert run(case, worker, media, 'fake:oksig:1000') == 'published'
    with case.migration.connect() as connection:
        assert connection.scalar(text('SELECT media_check FROM app.artifactmanifest WHERE job_id=:j'), {'j': job}) == 'signature'


def test_unknown_check_value_is_still_rejected(case, worker, media, submit):
    from sqlalchemy.exc import IntegrityError
    job = submit('k1').job_id
    assert run(case, worker, media, 'fake:ok:1000') == 'published'
    with pytest.raises(IntegrityError):
        db(case, "UPDATE app.artifactmanifest SET media_check='decoded' WHERE job_id=:j", j=job)


def test_downgrade_refuses_signature_rows_then_allows(case, worker, media, submit):
    job = submit('k1').job_id
    assert run(case, worker, media, 'fake:oksig:1000') == 'published'
    with pytest.raises(Exception):
        case.migrate(action='downgrade', target='c5b_0011')
    db(case, "UPDATE app.artifactmanifest SET media_check='verified' WHERE job_id=:j", j=job)
    case.migrate(action='downgrade', target='c5b_0011')
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        db(case, "UPDATE app.artifactmanifest SET media_check='signature' WHERE job_id=:j", j=job)
