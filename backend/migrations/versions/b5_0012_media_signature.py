"""B5 U5b: artifactmanifest.media_check accepts 'signature' (container-signature check).

'verified' keeps its meaning (reserved for a decode-level check by the C/supervisor stage).
Only the CHECK changes; grants are untouched. Downgrade refuses while 'signature' rows exist.
"""
from alembic import context,op
import sqlalchemy as sa

revision='b5_0012'
down_revision='c5b_0011'
branch_labels=None
depends_on=None


def upgrade():
    op.execute(sa.text('ALTER TABLE app.artifactmanifest DROP CONSTRAINT ck_artifactmanifest_media_check'))
    op.execute(sa.text("ALTER TABLE app.artifactmanifest ADD CONSTRAINT ck_artifactmanifest_media_check "
                       "CHECK (media_check IN ('verified','signature'))"))


def downgrade():
    if context.is_offline_mode():
        raise RuntimeError('Offline downgrade cannot verify that no signature-checked manifest exists')
    connection=op.get_bind()
    connection.execute(sa.text('LOCK TABLE app.artifactmanifest IN ACCESS EXCLUSIVE MODE'))
    if connection.scalar(sa.text("SELECT EXISTS(SELECT 1 FROM app.artifactmanifest WHERE media_check='signature')")):
        raise RuntimeError('Refusing downgrade while signature-checked manifests exist')
    op.execute(sa.text('ALTER TABLE app.artifactmanifest DROP CONSTRAINT ck_artifactmanifest_media_check'))
    op.execute(sa.text("ALTER TABLE app.artifactmanifest ADD CONSTRAINT ck_artifactmanifest_media_check "
                       "CHECK (media_check IN ('verified'))"))
