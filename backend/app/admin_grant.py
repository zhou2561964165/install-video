"""Operator CLI for admin grants: python -m app.admin_grant {grant,revoke,list} ...

Grants exist only through this CLI (no web self-service, no "first user becomes admin"). It connects
with ADMIN_CLI_DB_URL — a privileged operator role; the runtime role can only read grants, so a
compromised web process cannot grant itself access. grant/revoke are dry runs unless --apply.
Revoking also ends the user's admin sessions. Every applied change is audited. Exit codes:
0 done, 2 refused input/configuration, 3 database refused the change.
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys
import uuid

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import DBAPIError

from .db import DatabaseConfigurationError, build_engine
from .models import User
from .models_admin import admingrant, adminsession
from .services import admin_audit

REASON_MIN, REASON_MAX = 10, 500


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='python -m app.admin_grant')
    commands = parser.add_subparsers(dest='command', required=True)
    grant = commands.add_parser('grant')
    grant.add_argument('--user-id', required=True)
    grant.add_argument('--role', required=True, choices=('admin', 'viewer'))
    grant.add_argument('--reason', required=True)
    grant.add_argument('--apply', action='store_true')
    revoke = commands.add_parser('revoke')
    revoke.add_argument('--user-id', required=True)
    revoke.add_argument('--reason', required=True)
    revoke.add_argument('--apply', action='store_true')
    commands.add_parser('list')
    return parser


def _os_user() -> str:
    try:
        return getpass.getuser()
    except Exception:  # no login name available (e.g. a stripped environment)
        return 'unknown'


def _out(message: str) -> None:
    print(message, flush=True)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    url = os.environ.get('ADMIN_CLI_DB_URL')
    if not url:
        _out('refused: ADMIN_CLI_DB_URL is not set (operator role connection)')
        return 2
    reason = getattr(args, 'reason', None)
    if reason is not None:
        reason = reason.strip()
        if not REASON_MIN <= len(reason) <= REASON_MAX:
            _out(f'refused: reason must be {REASON_MIN}..{REASON_MAX} characters')
            return 2
    try:
        engine = build_engine(url, role='migration')
    except DatabaseConfigurationError:
        _out('refused: invalid ADMIN_CLI_DB_URL')
        return 2
    actor = 'cli:' + _os_user()
    try:
        with engine.begin() as connection:
            if args.command == 'list':
                for row in connection.execute(select(admingrant.c.user_id, admingrant.c.role, admingrant.c.active,
                                                     admingrant.c.revision, admingrant.c.granted_at)
                                              .order_by(admingrant.c.user_id)):
                    _out(f'{row.user_id}\t{row.role}\tactive={row.active}\trevision={row.revision}\t'
                         f'granted_at={row.granted_at.isoformat()}')
                return 0
            user = User.__table__
            if connection.scalar(select(func.count()).select_from(user).where(user.c.id == args.user_id)) != 1:
                _out('refused: no such user')
                return 2
            if args.command == 'revoke':
                active = connection.scalar(select(admingrant.c.active).where(admingrant.c.user_id == args.user_id))
                if active is not True:
                    _out('refused: user has no active grant')
                    return 2
            if not args.apply:
                change = f'{args.command} user_id={args.user_id}' + (f' role={args.role}' if args.command == 'grant' else '')
                _out(f'dry-run: would {change}; re-run with --apply to write')
                return 0
            if args.command == 'grant':
                statement = pg_insert(admingrant).values(
                    user_id=args.user_id, role=args.role, active=True, revision=1, granted_at=func.now(),
                    granted_by=actor, reason=reason)
                connection.execute(statement.on_conflict_do_update(
                    index_elements=[admingrant.c.user_id],
                    set_={'role': args.role, 'active': True, 'revision': admingrant.c.revision + 1,
                          'granted_at': func.now(), 'granted_by': actor, 'reason': reason}))
                changes = {'role': args.role, 'by': actor}
            else:
                connection.execute(update(admingrant).where(admingrant.c.user_id == args.user_id)
                                   .values(active=False, revision=admingrant.c.revision + 1))
                connection.execute(update(adminsession).where(adminsession.c.user_id == args.user_id,
                                                              adminsession.c.revoked_at.is_(None))
                                   .values(revoked_at=func.now()))
                changes = {'by': actor}
            admin_audit.record(connection, actor_user_id=None, actor_kind='cli', action='admin.' + args.command,
                               outcome='succeeded', request_id=str(uuid.uuid4()), target_user_id=args.user_id,
                               reason=reason, changes=changes)
    except DBAPIError:
        _out('refused: the database rejected the change (is ADMIN_CLI_DB_URL the operator role?)')
        return 3
    finally:
        engine.dispose()
    _out(f'applied: {args.command} user_id={args.user_id}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
