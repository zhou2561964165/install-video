"""Caller supplies the migration connection; never load application .env."""
from alembic import context

config = context.config


def run_migrations():
    if context.is_offline_mode():
        context.configure(dialect_name='postgresql', literal_binds=True,
                          version_table_schema='app')
        with context.begin_transaction():
            context.run_migrations()
        return
    connection = config.attributes.get('connection')
    if connection is None or connection.dialect.name != 'postgresql':
        raise RuntimeError('Migrations require an explicit PostgreSQL connection')
    context.configure(connection=connection, version_table_schema='app',
                      transactional_ddl=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


run_migrations()
