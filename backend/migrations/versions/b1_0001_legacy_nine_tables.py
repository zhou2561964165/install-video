"""Explicit nine-table baseline. No business protocol or runtime queue cutover.

Revision ID: b1_0001
Revises: None
"""
from alembic import context, op
import sqlalchemy as sa

revision = 'b1_0001'
down_revision = None
branch_labels = None
depends_on = None

TABLES = ('user', 'job', 'quota', 'downloadidempotency', 'membership',
          'billingcheckout', 'billingevent', 'billingpayment', 'downloadaccess')


def upgrade():
    op.create_table('user',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('password_hash', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_user'), schema='app')
    op.create_index('ix_user_email', 'user', ['email'], unique=True, schema='app')
    op.create_table('job',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('url', sa.String(), nullable=False),
        sa.Column('title', sa.String(), nullable=True),
        sa.Column('format_id', sa.String(), nullable=True),
        sa.Column('status', sa.String(11), nullable=False),
        sa.Column('progress', sa.Float(), nullable=False),
        sa.Column('file_path', sa.String(), nullable=True),
        sa.Column('file_size', sa.BigInteger(), nullable=True),
        sa.Column('error_type', sa.String(), nullable=True),
        sa.Column('error', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('user_id', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id', name='pk_job'),
        sa.ForeignKeyConstraint(['user_id'], ['app.user.id'], name='fk_job_user_id_user'),
        sa.CheckConstraint("status IN ('queued','downloading','merging','done','error')", name='ck_job_status'),
        schema='app')
    op.create_table('quota',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('date', sa.String(), nullable=False),
        sa.Column('downloads_used', sa.Integer(), nullable=False),
        sa.Column('limit', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_quota'),
        sa.ForeignKeyConstraint(['user_id'], ['app.user.id'], name='fk_quota_user_id_user'),
        sa.UniqueConstraint('user_id', 'date', name='uq_quota_user_date'), schema='app')
    op.create_index('ix_quota_user_id', 'quota', ['user_id'], schema='app')
    op.create_table('downloadidempotency',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('key', sa.String(128), nullable=False),
        sa.Column('fingerprint', sa.String(), nullable=False),
        sa.Column('state', sa.String(), nullable=False),
        sa.Column('created_at', sa.Float(), nullable=False),
        sa.Column('expires_at', sa.Float(), nullable=True),
        sa.Column('direct_expires_at', sa.Float(), nullable=True),
        sa.Column('status_code', sa.Integer(), nullable=True),
        sa.Column('response_json', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id', name='pk_downloadidempotency'),
        sa.ForeignKeyConstraint(['user_id'], ['app.user.id'], name='fk_downloadidempotency_user_id_user'),
        sa.UniqueConstraint('user_id', 'key', name='uq_download_idempotency_user_key'), schema='app')
    op.create_index('ix_downloadidempotency_user_id', 'downloadidempotency', ['user_id'], schema='app')
    op.create_index('ix_downloadidempotency_expires_at', 'downloadidempotency', ['expires_at'], schema='app')
    op.create_table('membership',
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('customer_id', sa.String(), nullable=True),
        sa.Column('subscription_id', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('expires_at', sa.Float(), nullable=False),
        sa.Column('cancel_at_period_end', sa.Boolean(), nullable=False),
        sa.Column('active_checkout_id', sa.String(), nullable=True),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('entitlement_source', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('user_id', name='pk_membership'),
        sa.ForeignKeyConstraint(['user_id'], ['app.user.id'], name='fk_membership_user_id_user'),
        sa.UniqueConstraint('customer_id', name='uq_membership_customer_id'),
        sa.UniqueConstraint('subscription_id', name='uq_membership_subscription_id'), schema='app')
    op.create_table('billingcheckout',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('price_id', sa.String(), nullable=False),
        sa.Column('mode', sa.String(), nullable=False),
        sa.Column('duration_days', sa.Integer(), nullable=False),
        sa.Column('origin', sa.String(), nullable=False),
        sa.Column('customer_id', sa.String(), nullable=True),
        sa.Column('created_at', sa.Float(), nullable=False),
        sa.Column('stripe_id', sa.String(), nullable=True),
        sa.Column('url', sa.String(), nullable=True),
        sa.Column('expires_at', sa.Float(), nullable=False),
        sa.Column('state', sa.String(), nullable=False),
        sa.Column('fulfilled', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_billingcheckout'),
        sa.ForeignKeyConstraint(['user_id'], ['app.user.id'], name='fk_billingcheckout_user_id_user'),
        sa.UniqueConstraint('stripe_id', name='uq_billingcheckout_stripe_id'), schema='app')
    op.create_index('ix_billingcheckout_user_id', 'billingcheckout', ['user_id'], schema='app')
    op.create_table('billingevent',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('processed_at', sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_billingevent'), schema='app')
    op.create_table('billingpayment',
        sa.Column('payment_intent', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=True),
        sa.Column('source_id', sa.String(), nullable=True),
        sa.Column('revoked', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('payment_intent', name='pk_billingpayment'),
        sa.ForeignKeyConstraint(['user_id'], ['app.user.id'], name='fk_billingpayment_user_id_user'), schema='app')
    op.create_index('ix_billingpayment_user_id', 'billingpayment', ['user_id'], schema='app')
    op.create_table('downloadaccess',
        sa.Column('job_id', sa.String(), nullable=False),
        sa.Column('max_height', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('job_id', name='pk_downloadaccess'),
        sa.ForeignKeyConstraint(['job_id'], ['app.job.id'], name='fk_downloadaccess_job_id_job'), schema='app')


def downgrade():
    if context.is_offline_mode():
        raise RuntimeError('Offline destructive downgrade cannot verify an empty database')
    connection = op.get_bind()
    # Lock every table before checking any rows: no concurrent DML can race the guard.
    qualified = ', '.join('app."' + name + '"' for name in TABLES)
    connection.execute(sa.text('LOCK TABLE ' + qualified + ' IN ACCESS EXCLUSIVE MODE'))
    for name in TABLES:
        if connection.scalar(sa.text('SELECT EXISTS (SELECT 1 FROM app."' + name + '" LIMIT 1)')):
            raise RuntimeError('Refusing destructive downgrade of nonempty business tables')
    for name in reversed(TABLES):
        op.drop_table(name, schema='app')
