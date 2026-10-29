"""Synthetic admin integration data — never real users, payments or jobs.

seed(engine) fills an EMPTY test database (name starting with 'pv_', i.e. a runner-owned nonce DB) with
fake users (@example.invalid), memberships, checkouts/payments/facts in every facts_state, jobs in every
state (including failures and an unknown error type), a quota overrun, a CLI audit row, support tickets
(priority/normal/closed, one paid-but-not-credited appeal) and an admin plus a viewer grant whose credentials
are the constants below (synthetic, local only). Use a privileged (migration)
engine: grants are not writable by the runtime role.
"""
from __future__ import annotations

from sqlalchemy import text

from ..services.auth import hash_password

ADMIN_EMAIL = 'synthetic-admin@example.invalid'
ADMIN_PASSWORD = 'synthetic-admin-only-26'  # synthetic local integration account, not a real credential
VIEWER_EMAIL = 'synthetic-viewer@example.invalid'
VIEWER_PASSWORD = 'synthetic-viewer-only-26'  # synthetic, local only
REISSUE_TICKET = 'tk-paid-unfulfilled'
REISSUE_SESSION = 'cs_syn_paid_unfulfilled'
REISSUE_PAYMENT = 'pi_syn_reissue'


class SeedRefused(RuntimeError):
    pass


def _database_name(connection) -> str:
    return connection.scalar(text('SELECT current_database()'))


def _user(connection, user_id, email, password='synthetic-user-pass'):
    connection.execute(text('INSERT INTO app."user" (id,email,password_hash,created_at) '
                            "VALUES (:i,:e,:p,now() - make_interval(days => :d))"),
                       {'i': user_id, 'e': email, 'p': hash_password(password), 'd': len(user_id)})


def _job(connection, job_id, user_id, *, version, status, internal_state=None, error_type=None, error=None,
         url='https://video.example.invalid/watch?v=demo'):
    deadline = "now() + interval '30 minutes'" if version == 2 else 'NULL'
    connection.execute(text(
        'INSERT INTO app.job (id,url,title,status,progress,user_id,execution_version,internal_state,error_type,error,'
        f"created_at,updated_at,run_deadline_at) VALUES (:i,:u,:t,:s,:p,:o,:v,:n,:et,:e,now(),now(),{deadline})"),
        {'i': job_id, 'u': url, 't': 'Synthetic ' + job_id, 's': status, 'p': 100.0 if status == 'done' else 0.0,
         'o': user_id, 'v': version, 'n': internal_state, 'et': error_type, 'e': error})


def seed(engine, *, seed_value: int = 20261028) -> dict[str, int]:
    with engine.begin() as connection:
        name = _database_name(connection)
        if not name.startswith('pv_'):
            raise SeedRefused('only a runner-owned synthetic database (pv_*) may be seeded')
        if connection.scalar(text('SELECT count(*) FROM app."user"')):
            raise SeedRefused('database is not empty')
        _user(connection, 'syn-admin', ADMIN_EMAIL, ADMIN_PASSWORD)
        connection.execute(text("INSERT INTO app.admingrant (user_id,role,active,revision,granted_at,granted_by,reason) "
                                "VALUES ('syn-admin','admin',true,1,now(),'cli:synthetic','synthetic integration admin')"))
        _user(connection, 'syn-viewer', VIEWER_EMAIL, VIEWER_PASSWORD)
        connection.execute(text("INSERT INTO app.admingrant (user_id,role,active,revision,granted_at,granted_by,reason) "
                                "VALUES ('syn-viewer','viewer',true,1,now(),'cli:synthetic','synthetic integration viewer')"))
        users = ['syn-vip', 'syn-expired', 'syn-paid-unfulfilled', 'syn-free', 'syn-ambiguous', 'syn-disabled']
        for user_id in users:
            _user(connection, user_id, user_id.replace('syn-', '') + '@example.invalid')
        connection.execute(text("INSERT INTO app.accountcontrol (user_id,enabled,revision,auth_revision,protected_account,"
                                "updated_at) VALUES ('syn-disabled',false,1,0,false,now())"))
        for user_id, status, offset, source in (('syn-vip', 'active', 20 * 86400, 'checkout'),
                                                ('syn-expired', 'active', -2 * 86400, 'checkout'),
                                                ('syn-ambiguous', 'canceled', 5 * 86400, None)):
            connection.execute(text('INSERT INTO app.membership (user_id,status,expires_at,cancel_at_period_end,revision,'
                                    'entitlement_source) VALUES (:u,:s,extract(epoch from now()) + :o,false,1,:src)'),
                               {'u': user_id, 's': status, 'o': offset, 'src': source})
        connection.execute(text("INSERT INTO app.quota (id,user_id,date,downloads_used,\"limit\") VALUES "
                                "('syn-q1','syn-free',to_char(now() AT TIME ZONE 'UTC','YYYY-MM-DD'),12,10)"))
        checkouts = (('co-paid-unfulfilled', 'syn-paid-unfulfilled', 'paid', False, 'needs_review', 'acct_synthetic', False),
                     ('co-paid-fulfilled', 'syn-vip', 'paid', True, 'verified', 'acct_synthetic', False),
                     ('co-open', 'syn-free', 'open', False, None, 'acct_synthetic', False),
                     ('co-expired', 'syn-expired', 'expired', False, 'closed', 'acct_synthetic', False),
                     ('co-legacy', 'syn-ambiguous', 'paid', False, None, None, None))
        for checkout_id, user_id, state, fulfilled, reconciliation, scope, livemode in checkouts:
            connection.execute(text(
                'INSERT INTO app.billingcheckout (id,user_id,price_id,mode,duration_days,origin,created_at,expires_at,state,'
                'fulfilled,provider_account_scope,livemode,reconciliation,reconcile_attempts,revision,stripe_id) VALUES '
                "(:i,:u,'price_synthetic','payment',30,'https://site.example.invalid',extract(epoch from now()) - 3600,"
                'extract(epoch from now()) + 3600,:s,:f,:scope,:live,:r,0,1,:sid)'),
                {'i': checkout_id, 'u': user_id, 's': state, 'f': fulfilled, 'scope': scope, 'live': livemode,
                 'r': reconciliation, 'sid': REISSUE_SESSION if checkout_id == 'co-paid-unfulfilled' else None})
        for pi, user_id in (('pi_syn_available', 'syn-vip'), ('pi_syn_ambiguous', 'syn-ambiguous'),
                            ('pi_syn_none', 'syn-paid-unfulfilled'), ('pi_syn_unbound', None)):
            connection.execute(text('INSERT INTO app.billingpayment (payment_intent,user_id,source_id,revoked) '
                                    "VALUES (:p,:u,:s,false)"), {'p': pi, 'u': user_id, 's': 'src_' + pi})
        facts = (('fact-1', 'syn-vip', 'pi_syn_available', 'co-paid-fulfilled', False),
                 ('fact-2', 'syn-ambiguous', 'pi_syn_ambiguous', None, False),
                 ('fact-3', 'syn-ambiguous', 'pi_syn_ambiguous', None, True),
                 ('fact-4', 'syn-free', 'pi_syn_unbound', None, False))
        for fact_id, user_id, pi, checkout_id, livemode in facts:
            connection.execute(text(
                'INSERT INTO app.billingfact (id,user_id,checkout_id,provider_account_scope,livemode,payment_intent,'
                "provider_status,amount_total,amount_refunded,currency,reconciliation,observed_at) VALUES "
                "(:i,:u,:c,'acct_synthetic',:live,:pi,'succeeded',990,0,'cny','verified',now())"),
                {'i': fact_id, 'u': user_id, 'c': checkout_id, 'live': livemode, 'pi': pi})
        _job(connection, 'job-v1-done', 'syn-vip', version=1, status='done')
        _job(connection, 'job-v1-error', 'syn-free', version=1, status='error', error_type='network',
             error='synthetic raw error text that must never be shown')
        _job(connection, 'job-v1-hold', 'syn-expired', version=1, status='queued', internal_state='legacy_hold')
        _job(connection, 'job-v2-queued', 'syn-vip', version=2, status='queued', internal_state='queued')
        _job(connection, 'job-v2-failed', 'syn-free', version=2, status='error', internal_state='failed',
             error_type='http_403')
        _job(connection, 'job-v2-unknown', 'syn-free', version=2, status='error', internal_state='failed',
             error_type='synthetic_new_code')
        _job(connection, 'job-v2-ok', 'syn-vip', version=2, status='queued', internal_state='queued')
        connection.execute(text("INSERT INTO app.jobattempt (id,job_id,epoch,owner,attempt_index,state,started_at,ended_at,"
                                "bytes_used) VALUES ('att-ok','job-v2-ok',1,'synthetic',1,'succeeded',now() - interval "
                                "'2 minutes',now(),4096)"))
        connection.execute(text("INSERT INTO app.artifactmanifest (attempt_id,job_id,epoch,relative_path,byte_size,sha256,"
                                "media_format,media_check,created_at) VALUES ('att-ok','job-v2-ok',1,"
                                "'job-v2-ok/1-att-ok/media.mp4',4096,repeat('a',64),'mp4','signature',now())"))
        connection.execute(text("UPDATE app.job SET internal_state='succeeded', status='done', visible_attempt_id='att-ok', "
                                "media_state='available', completed_at=now() WHERE id='job-v2-ok'"))
        connection.execute(text("INSERT INTO app.adminaudit (event_id,actor_kind,action,outcome,request_id,target_user_id,"
                                "reason,changes) VALUES ('syn-audit-grant','cli','admin.grant','succeeded',"
                                "'00000000-0000-4000-8000-000000000001','syn-admin','synthetic integration admin',"
                                "'{\"role\": \"admin\", \"by\": \"cli:synthetic\"}')"))
        # Created oldest first: the normal ticket is older than the priority ones, so the priority sort is visible.
        tickets = (('tk-normal-download', 'syn-free', 'download_failing', None, 'normal', 'open', None, 50),
                   (REISSUE_TICKET, 'syn-paid-unfulfilled', 'membership_not_credited', 'co-paid-unfulfilled', 'priority',
                    'open', None, 40),
                   ('tk-vip-other', 'syn-vip', 'other', None, 'priority', 'open', None, 30),
                   ('tk-closed-login', 'syn-expired', 'login_problem', None, 'normal', 'resolved', 'replied', 60))
        for ticket_id, user_id, category, checkout_id, priority, state, resolution, minutes in tickets:
            closed = state != 'open'
            connection.execute(text(
                'INSERT INTO app.supportticket (id,user_id,category,user_note,checkout_id,priority,state,resolution,'
                'reply_template,created_at,resolved_at,resolved_by,revision) VALUES (:i,:u,:c,:n,:co,:p,:s,:r,:t,'
                "now() - make_interval(mins => :m),CASE WHEN :closed THEN now() END,:by,0)"),
                {'i': ticket_id, 'u': user_id, 'c': category, 'n': '<b>synthetic note</b> shown as text', 'co': checkout_id,
                 'p': priority, 's': state, 'r': resolution, 't': 'login_help' if closed else None, 'm': minutes,
                 'closed': closed, 'by': 'syn-admin' if closed else None})
    return {'users': len(users) + 1, 'jobs': 7, 'checkouts': len(checkouts), 'payments': 4, 'facts': len(facts), 'tickets': len(tickets)}


def fake_paid_session(session_id: str) -> dict:
    """Stripe-shaped synthetic Checkout Session for the integration server's fake reader (never a real call)."""
    return {'id': session_id, 'status': 'complete', 'payment_status': 'paid', 'client_reference_id': 'syn-paid-unfulfilled',
            'mode': 'payment', 'livemode': False,
            'line_items': {'data': [{'price': {'id': 'price_synthetic'}, 'quantity': 1}]},
            'payment_intent': {'id': REISSUE_PAYMENT, 'status': 'succeeded',
                               'latest_charge': {'id': 'ch_syn', 'paid': True, 'status': 'succeeded', 'amount_refunded': 0,
                                                 'refunded': False, 'disputed': False}}}
