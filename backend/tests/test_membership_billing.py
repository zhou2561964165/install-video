import hashlib
import hmac
import json
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
from uuid import uuid4

import pytest
import stripe
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.config import Settings, settings
from app.db import engine
from app.main import app
from app.models import BillingCheckout, BillingEvent, BillingPayment, DownloadAccess, Job, JobStatus, Membership, Quota, User
from app.services import billing, membership, ytdlp_service
from app.services.auth import create_token
from app.services.quota import check_and_reserve, get_quota_info


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setattr("app.main._window", defaultdict(list))
    for name, value in {"stripe_secret_key": "sk_test_mock", "stripe_webhook_secret": "whsec_mock",
                        "stripe_price_id": "price_test", "stripe_billing_mode": "payment",
                        "stripe_price_label": "$10 / 30 days", "stripe_public_origin": "http://localhost:5173"}.items():
        monkeypatch.setattr(settings, name, value)
    monkeypatch.setattr("app.services.membership.is_unlimited_user", lambda _: False)
    user = User(email=f"{uuid4()}@example.com", password_hash="unused")
    with Session(engine) as s:
        s.add(user)
        s.commit()
        s.refresh(user)
        user_id = user.id
    headers = {"Authorization": "Bearer " + create_token(user_id)}
    calls = []
    sessions = {}
    def create(params, options):
        calls.append((params, options))
        key = options["idempotency_key"]
        return sessions.setdefault(key, {"id": "cs_" + uuid4().hex, "url": "https://checkout.stripe.com/pay/test",
                                        "expires_at": time.time() + 3600, "status": "open"})
    api = SimpleNamespace(v1=SimpleNamespace(checkout=SimpleNamespace(sessions=SimpleNamespace(
        create=create, retrieve=lambda sid: next(v for v in sessions.values() if v["id"] == sid))),
        subscriptions=SimpleNamespace(retrieve=lambda *a, **kw: {}),
        billing_portal=SimpleNamespace(sessions=SimpleNamespace(create=lambda params: {"url": "https://billing.stripe.com/test"}))))
    monkeypatch.setattr(billing, "client", lambda: api)
    return TestClient(app), headers, user_id, calls, api


def intent(setup):
    client, headers, uid, calls, api = setup
    assert client.post("/api/billing/checkout", headers=headers).status_code == 200
    with Session(engine) as s:
        row = s.exec(select(BillingCheckout).where(BillingCheckout.user_id == uid)).first()
        s.expunge(row)
        return row


def event(row, kind="checkout.session.completed", **changes):
    obj = {"id": row.stripe_id, "client_reference_id": row.user_id, "metadata": {"checkout_id": row.id},
           "mode": row.mode, "payment_status": "paid", "status": "complete", "customer": "cus_" + row.user_id,
           "payment_intent": "pi_" + row.id}
    obj.update(changes)
    return {"id": "evt_" + uuid4().hex, "type": kind, "data": {"object": obj}}


def post_event(client, body, timestamp=None, tamper=False):
    payload = json.dumps(body).encode()
    stamp = int(time.time()) if timestamp is None else timestamp
    sig = hmac.new(b"whsec_mock", str(stamp).encode() + b"." + payload, hashlib.sha256).hexdigest()
    return client.post("/api/billing/webhook", content=payload + (b" " if tamper else b""),
                       headers={"Stripe-Signature": f"t={stamp},v1={sig}"})


def test_unconfigured_checkout_is_closed_and_public_has_no_secrets(setup, monkeypatch):
    client, headers, *_ = setup
    monkeypatch.setattr(settings, "stripe_price_id", "")
    obj = client.get("/api/membership/plans").json()
    assert not obj["checkout_available"]
    assert "sk_test" not in json.dumps(obj)
    assert client.post("/api/billing/checkout", headers=headers).status_code == 503
    assert client.get("/api/membership").status_code == 401
    assert client.post("/api/billing/portal", headers=headers).status_code == 503


def test_checkout_reuses_durable_session_and_does_not_grant_on_redirect(setup):
    client, headers, uid, calls, _ = setup
    one = client.post("/api/billing/checkout", headers=headers)
    two = client.post("/api/billing/checkout", headers=headers)
    assert one.json() == two.json()
    assert len(calls) == 1
    assert calls[0][0]["mode"] == "payment"
    assert client.get("/api/membership?membership=success", headers=headers).json()["plan"] == "free"


def test_checkout_explicitly_uses_ordinary_payments(setup):
    client, headers, _, calls, _ = setup
    assert client.post("/api/billing/checkout", headers=headers).status_code == 200
    assert calls[0][0]["managed_payments"] == {"enabled": False}


def test_existing_pending_validation_failure_recovers_without_new_key(setup):
    client, headers, uid, calls, api = setup
    original = api.v1.checkout.sessions.create
    attempts = []

    def first_validation_then_ordinary(params, options):
        attempts.append((params.copy(), options.copy()))
        if len(attempts) == 1:
            # A provider parameter-validation failure creates no remote session.
            raise stripe.InvalidRequestError("Product tax code missing for Managed Payments", param=None)
        assert params["managed_payments"] == {"enabled": False}
        return original(params, options)

    api.v1.checkout.sessions.create = first_validation_then_ordinary
    assert client.post("/api/billing/checkout", headers=headers).status_code == 503
    assert len(attempts) == 1  # No hidden retry or fallback POST.
    assert client.post("/api/billing/checkout", headers=headers).status_code == 200
    assert attempts[0][1]["idempotency_key"] == attempts[1][1]["idempotency_key"]
    with Session(engine) as s:
        assert len(s.exec(select(BillingCheckout).where(BillingCheckout.user_id == uid)).all()) == 1
    assert client.get("/api/membership", headers=headers).json()["plan"] == "free"


def test_idempotency_conflict_preserves_pending_intent_and_redacts_logs(setup, caplog):
    client, headers, uid, _, api = setup
    attempts = []

    def conflict(params, options):
        attempts.append(options["idempotency_key"])
        raise stripe.IdempotencyError("private-provider-text sk_test_sensitive")

    api.v1.checkout.sessions.create = conflict
    for _ in range(2):
        response = client.post("/api/billing/checkout", headers=headers)
        assert response.status_code == 503
        assert "待核实" in response.json()["detail"]["error"]
        assert "sensitive" not in response.text
    assert len(set(attempts)) == 1
    with Session(engine) as s:
        rows = s.exec(select(BillingCheckout).where(BillingCheckout.user_id == uid)).all()
        assert len(rows) == 1 and rows[0].state == "pending" and not rows[0].fulfilled
    assert "IdempotencyError" in caplog.text
    assert "private-provider-text" not in caplog.text
    assert "sk_test_sensitive" not in caplog.text


def test_provider_configuration_failure_has_safe_classification(setup, caplog):
    client, headers, _, _, api = setup

    def invalid(params, options):
        raise stripe.InvalidRequestError("sensitive-vendor-response sk_test_hidden", param=None)

    api.v1.checkout.sessions.create = invalid
    response = client.post("/api/billing/checkout", headers=headers)
    assert response.status_code == 503
    assert "配置" in response.json()["detail"]["error"]
    assert "sensitive-vendor-response" not in response.text + caplog.text
    assert "sk_test_hidden" not in response.text + caplog.text
    assert "InvalidRequestError" in caplog.text


def test_timeout_replays_same_key_and_frozen_parameters(setup, monkeypatch):
    client, headers, uid, calls, api = setup
    original = api.v1.checkout.sessions.create
    keys = []
    def uncertain(params, options):
        keys.append((dict(params), dict(options)))
        if len(keys) == 1:
            original(params, options)
            raise TimeoutError()
        return original(params, options)
    api.v1.checkout.sessions.create = uncertain
    assert client.post("/api/billing/checkout", headers=headers).status_code == 503
    monkeypatch.setattr(settings, "stripe_price_id", "price_changed")
    monkeypatch.setattr(settings, "stripe_public_origin", "http://localhost:9999")
    assert client.post("/api/billing/checkout", headers=headers).status_code == 200
    assert keys[0] == keys[1]


@pytest.mark.parametrize("tamper,age", [(True, 0), (False, 600)])
def test_webhook_rejects_forged_and_expired_signatures(setup, tamper, age):
    client, *_ = setup
    row = intent(setup)
    result = post_event(client, event(row), int(time.time()) - age, tamper)
    assert result.status_code == 400


def test_paid_only_once_despite_duplicate_distinct_events_and_expiry(setup):
    client, headers, uid, *_ = setup
    row = intent(setup)
    unpaid = event(row, payment_status="unpaid")
    assert post_event(client, unpaid).status_code == 200
    assert client.get("/api/membership", headers=headers).json()["plan"] == "free"
    paid = event(row)
    assert post_event(client, paid).status_code == 200
    expires = client.get("/api/membership", headers=headers).json()["expires_at"]
    assert post_event(client, paid).status_code == 200
    assert post_event(client, event(row, "checkout.session.async_payment_succeeded")).status_code == 200
    assert post_event(client, event(row, "checkout.session.expired")).status_code == 200
    assert client.get("/api/membership", headers=headers).json()["expires_at"] == expires
    assert client.post("/api/billing/checkout", headers=headers).status_code == 409
    with Session(engine) as s:
        obj = s.get(Membership, uid)
        obj.expires_at = time.time() - 1
        s.add(obj)
        s.commit()
    assert client.get("/api/membership", headers=headers).json()["plan"] == "free"


def test_signed_cross_account_binding_fails_closed(setup):
    client, headers, uid, *_ = setup
    row = intent(setup)
    assert post_event(client, event(row, client_reference_id="another-user")).status_code == 503
    assert client.get("/api/membership", headers=headers).json()["plan"] == "free"


def test_free_features_denied_before_cached_source_and_llm(setup, monkeypatch):
    client, headers, *_ = setup
    def fail(*a, **kw):
        raise AssertionError("must reject before source/cache/LLM")
    monkeypatch.setattr("app.routes.subtitle.load_cached_subtitle", fail)
    monkeypatch.setattr("app.routes.summary.load_cached_subtitle", fail)
    for path in ("/api/subtitle", "/api/subtitle/export", "/api/subtitle/translate", "/api/summary"):
        r = client.post(path, json={"url": "https://example.com/v", "format": "srt"}, headers=headers)
        assert r.status_code == 403
        assert r.json()["detail"]["error_type"] == "membership_required"


def test_free_unlimited_counts_existing_finite_row(setup):
    _, _, uid, *_ = setup
    with Session(engine) as s:
        for _ in range(12):
            check_and_reserve(s, uid)
        used, limit, day = get_quota_info(s, uid)
        assert used == 12 and limit is None
        assert s.exec(select(Quota).where(Quota.user_id == uid)).first().limit == settings.default_quota_limit


@pytest.mark.parametrize("selector,height,allowed", [("18", 720, True), ("18", 1080, False),
    ("18/best", 720, False), ("best", None, False), ("bestvideo[height<=720]+bestaudio/best[height<=720]", 720, True)])
def test_free_selector_resolution_and_server_bound(monkeypatch, selector, height, allowed):
    monkeypatch.setattr(ytdlp_service, "extract_info", lambda _: {})
    monkeypatch.setattr(ytdlp_service, "build_format_options", lambda _: [{"format_id": selector, "height": height}])
    if allowed:
        assert "height<=720" in ytdlp_service.restrict_format("https://example.com", selector, 720)
    else:
        with pytest.raises(ValueError):
            ytdlp_service.restrict_format("https://example.com", selector, 720)


def test_expired_vip_cannot_replay_hd_or_retrieve_hd_file(setup, monkeypatch, tmp_path):
    client, headers, uid, *_ = setup
    path = tmp_path / "video.mp4"
    path.write_bytes(b"data")
    with Session(engine) as s:
        job = Job(url="https://example.com", format_id="hd", status=JobStatus.done, file_path=str(path), user_id=uid)
        s.add(job)
        s.commit()
        jid = job.id
        s.add(DownloadAccess(job_id=jid, max_height=None))
        s.commit()
    monkeypatch.setattr(ytdlp_service, "restrict_format", lambda *a: (_ for _ in ()).throw(ValueError()))
    assert client.get("/api/file/" + jid, headers=headers).status_code == 403
    assert client.post("/api/download", headers={**headers, "Idempotency-Key": "old-hd"},
                       json={"url": "https://example.com", "format_id": "hd"}).status_code == 403


def test_subscription_uses_current_paid_period_and_stale_events_cannot_restore(setup, monkeypatch):
    client, headers, uid, calls, api = setup
    monkeypatch.setattr(settings, "stripe_billing_mode", "subscription")
    row = intent(setup)
    paid_end = int(time.time()) + 1800
    sub = {"id": "sub_" + uid, "customer": "cus_" + uid, "status": "active", "cancel_at_period_end": True,
           "items": {"data": [{"price": {"id": "price_test"}, "current_period_end": paid_end + 5000}]},
           "latest_invoice": {"id": "in_" + uid, "status": "paid",
               "payments": {"data": [{"status": "paid", "payment": {"payment_intent": "pi_" + uid}}]},
               "lines": {"data": [{"pricing": {"price_details": {"price": "price_test"}}, "period": {"end": paid_end}}]}}}
    api.v1.subscriptions.retrieve = lambda *a, **kw: stripe.StripeObject.construct_from(sub, None)
    assert post_event(client, event(row, subscription="sub_" + uid)).status_code == 200
    with Session(engine) as s:
        assert s.get(Membership, uid).expires_at == paid_end
    assert client.get("/api/membership", headers=headers).json()["cancel_at_period_end"]
    assert client.post("/api/billing/portal", headers=headers).status_code == 200
    sub["status"] = "canceled"
    update = {"id": "evt_" + uuid4().hex, "type": "customer.subscription.deleted",
              "data": {"object": {"id": "sub_" + uid, "customer": "cus_" + uid}}}
    assert post_event(client, update).status_code == 200
    update["id"], update["type"] = "evt_" + uuid4().hex, "customer.subscription.updated"
    assert post_event(client, update).status_code == 200
    assert post_event(client, event(row, subscription="sub_" + uid)).status_code == 200
    assert client.get("/api/membership", headers=headers).json()["plan"] == "free"


def test_active_without_paid_matching_invoice_does_not_grant(setup, monkeypatch):
    client, headers, uid, calls, api = setup
    monkeypatch.setattr(settings, "stripe_billing_mode", "subscription")
    row = intent(setup)
    api.v1.subscriptions.retrieve = lambda *a, **kw: {"customer": "cus_" + uid, "status": "active",
        "latest_invoice": {"status": "open", "paid": False}}
    assert post_event(client, event(row, subscription="sub_" + uid)).status_code == 200
    assert client.get("/api/membership", headers=headers).json()["plan"] == "free"


def test_checkout_concurrent_clicks_share_same_provider_key(setup):
    client, headers, uid, calls, api = setup
    def click(_):
        with Session(engine) as s:
            return billing.checkout(s, s.get(User, uid))
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(click, range(3)))
    assert all(r == results[0] for r in results)
    assert len({c[1]["idempotency_key"] for c in calls}) == 1


@pytest.mark.parametrize("kwargs", [{"membership_free_max_height": 1080}, {"stripe_billing_mode": "auto"},
                                    {"stripe_timeout_seconds": 0}, {"stripe_vip_duration_days": False}])
def test_billing_config_bounds(kwargs):
    with pytest.raises(ValueError):
        Settings(**kwargs)


def test_uncertain_checkout_after_idempotency_retention_is_not_recreated(setup):
    client, headers, uid, calls, api = setup
    api.v1.checkout.sessions.create = lambda *a, **kw: (_ for _ in ()).throw(TimeoutError())
    assert client.post("/api/billing/checkout", headers=headers).status_code == 503
    with Session(engine) as s:
        row = s.exec(select(BillingCheckout).where(BillingCheckout.user_id == uid)).first()
        row.created_at = time.time() - 24 * 3600
        s.add(row)
        s.commit()
    api.v1.checkout.sessions.create = lambda *a, **kw: pytest.fail("must not create a new charge")
    assert client.post("/api/billing/checkout", headers=headers).status_code == 503


def test_portal_remains_available_when_new_sales_are_disabled(setup, monkeypatch):
    client, headers, uid, calls, api = setup
    with Session(engine) as s:
        s.add(Membership(user_id=uid, customer_id="cus_" + uid, subscription_id="sub_" + uid))
        s.commit()
    monkeypatch.setattr(settings, "stripe_price_id", "")
    monkeypatch.setattr(settings, "stripe_billing_mode", "")
    state = client.get("/api/membership", headers=headers).json()
    assert state["portal_available"] and not state["checkout_available"]
    assert client.post("/api/billing/portal", headers=headers).status_code == 200


def test_expired_local_subscription_must_be_canceled_before_new_checkout(setup):
    client, headers, uid, calls, api = setup
    with Session(engine) as s:
        s.add(Membership(user_id=uid, customer_id="cus_" + uid, subscription_id="sub_old_" + uid,
                         status="active", expires_at=time.time() - 1))
        s.commit()
    api.v1.subscriptions.retrieve = lambda *a, **kw: {"status": "past_due"}
    assert client.post("/api/billing/checkout", headers=headers).status_code == 409
    assert not calls
    api.v1.subscriptions.retrieve = lambda *a, **kw: {"status": "canceled"}
    assert client.post("/api/billing/checkout", headers=headers).status_code == 200


def test_canceled_subscription_repurchase_binds_new_id_and_ignores_old_events(setup, monkeypatch):
    client, headers, uid, calls, api = setup
    monkeypatch.setattr(settings, "stripe_billing_mode", "subscription")
    old_id, new_id = "sub_old_" + uid, "sub_new_" + uid
    with Session(engine) as s:
        s.add(Membership(user_id=uid, customer_id="cus_" + uid, subscription_id=old_id, status="expired"))
        s.commit()
    end = int(time.time()) + 1800
    def retrieve(sid, **kwargs):
        return {"status": "canceled"} if sid == old_id else {"customer": "cus_" + uid, "status": "active",
            "items": {"data": [{"price": {"id": "price_test"}, "current_period_end": end}]},
            "latest_invoice": {"id": "in_" + uid, "status": "paid", "paid": True,
                "payments": {"data": [{"status": "paid", "payment": {"payment_intent": "pi_" + uid}}]},
                "lines": {"data": [{"price": {"id": "price_test"}, "period": {"end": end}}]}}}
    api.v1.subscriptions.retrieve = retrieve
    row = intent(setup)
    assert post_event(client, event(row, subscription=new_id)).status_code == 200
    old_event = {"id": "evt_" + uuid4().hex, "type": "customer.subscription.deleted",
                 "data": {"object": {"id": old_id, "customer": "cus_" + uid}}}
    assert post_event(client, old_event).status_code == 200
    with Session(engine) as s:
        assert s.get(Membership, uid).subscription_id == new_id
        assert membership.is_vip(s, uid)


def test_free_direct_path_rechecks_current_height(monkeypatch):
    class Extractor:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def extract_info(self, *a, **kw): return {"formats": [{"format_id": "18", "height": height[0],
                                                               "url": "https://cdn.example/v"}]}
    height = [720]
    monkeypatch.setattr(ytdlp_service, "_youtube_dl", lambda _: Extractor())
    assert ytdlp_service.get_direct_url("https://example.com", "18[height<=720]")[0]
    height[0] = 1080
    assert ytdlp_service.get_direct_url("https://example.com", "18[height<=720]")[0] is None


def test_free_download_records_checked_height_and_remains_retrievable(setup, monkeypatch, tmp_path):
    client, headers, uid, *_ = setup
    from app.services.jobs import job_manager
    monkeypatch.setattr(ytdlp_service, "restrict_format", lambda *a: "18[height<=720]")
    monkeypatch.setattr(job_manager, "submit_download", lambda *a: None)
    monkeypatch.setattr(job_manager, "cleanup_expired", lambda: None)
    result = client.post("/api/download", json={"url": "https://example.com", "format_id": "18", "force_server": True},
                         headers=headers)
    assert result.status_code == 200
    path = tmp_path / "v.mp4"
    path.write_bytes(b"data")
    with Session(engine) as s:
        job = s.get(Job, result.json()["job_id"])
        job.status, job.file_path = JobStatus.done, str(path)
        s.add(job)
        assert s.get(DownloadAccess, job.id).max_height == 720
        s.commit()
    assert client.get("/api/file/" + result.json()["job_id"], headers=headers).status_code == 200


def test_sdk_client_has_bounded_timeout_and_zero_retries(monkeypatch):
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_mock")
    # This builds the real official SDK client without making any network request.
    sdk = billing.client()
    assert sdk._requestor._options.max_network_retries == 0
    assert sdk._requestor._get_http_client()._timeout == settings.stripe_timeout_seconds


def test_known_old_checkout_can_recover_missing_expiration_webhook(setup):
    client, headers, uid, calls, api = setup
    row = intent(setup)
    with Session(engine) as s:
        stored = s.get(BillingCheckout, row.id)
        stored.created_at = time.time() - 25 * 3600
        stored.expires_at = time.time() - 3600
        s.add(stored)
        s.commit()
    api.v1.checkout.sessions.retrieve = lambda sid: {"id": sid, "status": "expired", "expires_at": time.time() - 1}
    # First reconcile the known session. A later explicit click starts a new intent.
    assert client.post("/api/billing/checkout", headers=headers).status_code == 503
    assert client.post("/api/billing/checkout", headers=headers).status_code == 200
    assert len({row[1]["idempotency_key"] for row in calls}) == 2


def test_one_time_purchase_replaces_ended_subscription_entitlement_source(setup):
    client, headers, uid, calls, api = setup
    old_id = "sub_old_" + uid
    with Session(engine) as s:
        s.add(Membership(user_id=uid, customer_id="cus_" + uid, subscription_id=old_id, status="expired"))
        s.commit()
    api.v1.subscriptions.retrieve = lambda *a, **kw: {"status": "canceled"}
    row = intent(setup)
    assert post_event(client, event(row)).status_code == 200
    late = {"id": "evt_" + uuid4().hex, "type": "customer.subscription.deleted",
            "data": {"object": {"id": old_id, "customer": "cus_" + uid}}}
    assert post_event(client, late).status_code == 200
    with Session(engine) as s:
        assert s.get(Membership, uid).subscription_id is None
        assert membership.is_vip(s, uid)


def test_source_8k_options_are_available_to_vip_and_denied_to_free(setup, monkeypatch):
    client, headers, uid, *_ = setup
    source = {"formats": [{"format_id": "eightk", "height": 4320, "vcodec": "av01", "acodec": "none", "ext": "mp4"},
                          {"format_id": "hd", "height": 720, "vcodec": "avc1", "acodec": "none", "ext": "mp4"}]}
    monkeypatch.setattr(ytdlp_service, "extract_info", lambda _: source)
    options = ytdlp_service.build_format_options(source)
    choice = next(item for item in options if item["height"] == 4320)
    payload = {"url": "https://example.com", "format_id": choice["format_id"], "force_server": True}
    assert client.post("/api/download", headers=headers, json=payload).status_code == 403
    with Session(engine) as s:
        s.add(Membership(user_id=uid, status="active", expires_at=time.time() + 300))
        s.commit()
    from app.services.jobs import job_manager
    submitted = []
    monkeypatch.setattr(job_manager, "submit_download", lambda job, url, fmt: submitted.append(fmt))
    monkeypatch.setattr(job_manager, "cleanup_expired", lambda: None)
    assert client.post("/api/download", headers=headers, json=payload).status_code == 200
    assert submitted == [choice["format_id"]]


@pytest.mark.parametrize("origin", ["https://[", "https://example.com:invalid", "https://:pass@", "https://u:p@example.com"])
def test_bad_public_origin_closes_checkout(setup, monkeypatch, origin):
    monkeypatch.setattr(settings, "stripe_public_origin", origin)
    assert not billing.checkout_available()


def reversal(row, kind="charge.refunded", **changes):
    obj = {"id": "ch_" + uuid4().hex, "payment_intent": "pi_" + row.id,
           "customer": "cus_" + row.user_id, "amount": 1000, "amount_refunded": 1000, "refunded": True}
    obj.update(changes)
    return {"id": "evt_" + uuid4().hex, "type": kind, "data": {"object": obj}}


@pytest.mark.parametrize("kind", ["charge.refunded", "charge.dispute.created", "charge.dispute.funds_withdrawn",
                                 "charge.dispute.closed"])
def test_reversed_current_payment_revokes_and_late_checkout_does_not_restore(setup, kind):
    client, headers, uid, *_ = setup
    row = intent(setup)
    assert post_event(client, event(row)).status_code == 200
    notice = reversal(row, kind, status="lost")
    assert post_event(client, notice).status_code == 200
    assert post_event(client, notice).status_code == 200
    assert post_event(client, event(row)).status_code == 200
    assert client.get("/api/membership", headers=headers).json()["plan"] == "free"


def test_partial_refund_does_not_revoke_full_membership(setup):
    client, headers, uid, *_ = setup
    row = intent(setup)
    assert post_event(client, event(row)).status_code == 200
    assert post_event(client, reversal(row, amount_refunded=100, refunded=False)).status_code == 200
    assert client.get("/api/membership", headers=headers).json()["plan"] == "vip"


def test_refund_before_checkout_persists_tombstone_and_retries_binding(setup):
    client, headers, uid, *_ = setup
    row = intent(setup)
    notice = reversal(row)
    assert post_event(client, notice).status_code == 503
    with Session(engine) as s:
        assert s.get(BillingPayment, "pi_" + row.id).revoked
        assert s.get(BillingEvent, notice["id"]) is None
    assert post_event(client, event(row)).status_code == 200
    assert post_event(client, notice).status_code == 200
    assert client.get("/api/membership", headers=headers).json()["plan"] == "free"


def test_refund_of_old_payment_cannot_revoke_new_purchase(setup):
    client, headers, uid, *_ = setup
    old = intent(setup)
    assert post_event(client, event(old)).status_code == 200
    with Session(engine) as s:
        account = s.get(Membership, uid)
        account.expires_at = time.time() - 1
        s.add(account)
        s.commit()
    new = intent(setup)
    # intent() selects the first row for older tests; use active attempt for this repurchase.
    with Session(engine) as s:
        account = s.get(Membership, uid)
        new = s.get(BillingCheckout, account.active_checkout_id)
        s.expunge(new)
    assert post_event(client, event(new)).status_code == 200
    assert post_event(client, reversal(old)).status_code == 200
    assert client.get("/api/membership", headers=headers).json()["plan"] == "vip"


def paid_sub(uid, end):
    return {"customer": "cus_" + uid, "status": "active", "items": {"data": [
        {"price": {"id": "price_test"}, "current_period_end": end}]},
        "latest_invoice": {"id": "in_" + uid, "status": "paid", "payments": {"data": [
            {"status": "paid", "payment": {"type": "payment_intent", "payment_intent": "pi_" + uid}}]},
            "lines": {"data": [{"price": {"id": "price_test"}, "period": {"end": end}}]}}}


def test_subscription_refund_cannot_be_restored_by_late_invoice_but_new_renewal_can(setup, monkeypatch):
    client, headers, uid, calls, api = setup
    monkeypatch.setattr(settings, "stripe_billing_mode", "subscription")
    row = intent(setup)
    sub = paid_sub(uid, int(time.time()) + 300)
    api.v1.subscriptions.retrieve = lambda *a, **kw: sub
    assert post_event(client, event(row, subscription="sub_" + uid)).status_code == 200
    assert post_event(client, reversal(row, payment_intent="pi_" + uid)).status_code == 200
    invoice_notice = {"id": "evt_" + uuid4().hex, "type": "invoice.paid", "data": {"object": {
        "id": "in_" + uid, "customer": "cus_" + uid,
        "parent": {"subscription_details": {"subscription": "sub_" + uid}}}}}
    assert post_event(client, invoice_notice).status_code == 200
    assert client.get("/api/membership", headers=headers).json()["plan"] == "free"
    sub["latest_invoice"]["id"] += "new"
    sub["latest_invoice"]["payments"]["data"][0]["payment"]["payment_intent"] += "new"
    invoice_notice["id"] = "evt_" + uuid4().hex
    assert post_event(client, invoice_notice).status_code == 200
    assert client.get("/api/membership", headers=headers).json()["plan"] == "vip"


def test_subscription_network_wait_does_not_hold_sqlite_write_lock(setup, monkeypatch):
    client, headers, uid, calls, api = setup
    monkeypatch.setattr(settings, "stripe_billing_mode", "subscription")
    row = intent(setup)
    entered, release = Event(), Event()
    def slow(*a, **kw):
        entered.set()
        assert release.wait(5)
        return paid_sub(uid, int(time.time()) + 300)
    api.v1.subscriptions.retrieve = slow
    with ThreadPoolExecutor(max_workers=2) as pool:
        future = pool.submit(post_event, client, event(row, subscription="sub_" + uid))
        assert entered.wait(2)
        def usage():
            with Session(engine) as s:
                check_and_reserve(s, uid)
        try:
            pool.submit(usage).result(timeout=1)
        finally:
            release.set()
        assert future.result().status_code == 200


def test_stale_subscription_snapshot_cannot_overwrite_concurrent_revocation(setup, monkeypatch):
    client, headers, uid, calls, api = setup
    monkeypatch.setattr(settings, "stripe_billing_mode", "subscription")
    row = intent(setup)
    def changed_during_request(*a, **kw):
        with Session(engine) as s:
            account = s.get(Membership, uid)
            account.status, account.expires_at = "expired", 0
            account.revision += 1
            s.add(account)
            s.commit()
        return paid_sub(uid, int(time.time()) + 300)
    api.v1.subscriptions.retrieve = changed_during_request
    notice = event(row, subscription="sub_" + uid)
    assert post_event(client, notice).status_code == 503
    assert client.get("/api/membership", headers=headers).json()["plan"] == "free"
    with Session(engine) as s:
        assert s.get(BillingEvent, notice["id"]) is None


def test_dispute_resolves_charge_payment_binding_outside_transaction(setup):
    client, headers, uid, calls, api = setup
    row = intent(setup)
    assert post_event(client, event(row)).status_code == 200
    api.v1.charges = SimpleNamespace(retrieve=lambda cid: {"payment_intent": "pi_" + row.id})
    notice = reversal(row, "charge.dispute.created", payment_intent=None, charge="ch_test")
    assert post_event(client, notice).status_code == 200
    assert client.get("/api/membership", headers=headers).json()["plan"] == "free"


def test_async_failure_releases_checkout_slot_and_late_failure_cannot_revoke_paid(setup):
    client, headers, uid, calls, api = setup
    old = intent(setup)
    assert post_event(client, event(old, payment_status="unpaid")).status_code == 200
    assert post_event(client, event(old, "checkout.session.async_payment_failed", payment_status="unpaid")).status_code == 200
    assert client.post("/api/billing/checkout", headers=headers).status_code == 200
    assert len(calls) == 2
    with Session(engine) as s:
        active = s.get(Membership, uid).active_checkout_id
        new = s.get(BillingCheckout, active)
        s.expunge(new)
    assert post_event(client, event(new)).status_code == 200
    assert post_event(client, event(new, "checkout.session.async_payment_failed", payment_status="unpaid")).status_code == 200
    assert post_event(client, event(old, "checkout.session.async_payment_failed", payment_status="unpaid")).status_code == 200
    assert client.get("/api/membership", headers=headers).json()["plan"] == "vip"


def test_checkout_old_subscription_network_wait_releases_sqlite_lock(setup):
    client, headers, uid, calls, api = setup
    with Session(engine) as s:
        s.add(Membership(user_id=uid, customer_id="cus_" + uid, subscription_id="sub_" + uid))
        s.commit()
    entered, release = Event(), Event()
    def slow(*a, **kw):
        entered.set()
        assert release.wait(5)
        return {"status": "canceled"}
    api.v1.subscriptions.retrieve = slow
    with ThreadPoolExecutor(max_workers=2) as pool:
        future = pool.submit(client.post, "/api/billing/checkout", headers=headers)
        assert entered.wait(2)
        def usage():
            with Session(engine) as s:
                check_and_reserve(s, uid)
        try:
            pool.submit(usage).result(timeout=1)
        finally:
            release.set()
        assert future.result().status_code == 200


@pytest.mark.parametrize("mode,restricted", [("subscription", True), ("payment", False)])
def test_only_subscriptions_restrict_to_immediate_card_payments(setup, monkeypatch, mode, restricted):
    client, headers, uid, calls, api = setup
    monkeypatch.setattr(settings, "stripe_billing_mode", mode)
    intent(setup)
    params = calls[0][0]
    if restricted:
        assert params["payment_method_types"] == ["card"]
    else:
        assert "payment_method_types" not in params
