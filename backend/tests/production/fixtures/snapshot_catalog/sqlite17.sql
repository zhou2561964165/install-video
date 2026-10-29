CREATE TABLE "billingcheckout" (
    "id" VARCHAR NOT NULL,
    "user_id" VARCHAR NOT NULL,
    "price_id" VARCHAR NOT NULL,
    "mode" VARCHAR NOT NULL,
    "duration_days" INTEGER NOT NULL,
    "origin" VARCHAR NOT NULL,
    "customer_id" VARCHAR,
    "created_at" FLOAT NOT NULL,
    "stripe_id" VARCHAR,
    "url" VARCHAR,
    "expires_at" FLOAT NOT NULL,
    "state" VARCHAR NOT NULL,
    "fulfilled" BOOLEAN NOT NULL,
    "provider_account_scope" VARCHAR,
    "livemode" BOOLEAN,
    "create_payload" TEXT,
    "create_payload_sha256" VARCHAR(64),
    "create_payload_version" INTEGER,
    "create_started_at" DATETIME,
    "create_completed_at" DATETIME,
    "create_result_code" VARCHAR,
    "reconciliation" VARCHAR,
    "reconcile_attempts" INTEGER NOT NULL,
    "reconciliation_started_at" DATETIME,
    "reconciliation_evidence" VARCHAR,
    "reconciliation_actor" VARCHAR,
    "reconciliation_reason" VARCHAR,
    "revision" BIGINT NOT NULL,
    PRIMARY KEY ("id"),
    FOREIGN KEY ("user_id") REFERENCES "user" ("id") ON DELETE NO ACTION,
    UNIQUE ("stripe_id"),
    CHECK (reconciliation IS NULL OR reconciliation IN ('not_started','unknown','verified','needs_review','closed')),
    CHECK (reconcile_attempts >= 0 AND reconcile_attempts <= 3)
);

CREATE TABLE "billingevent" (
    "id" VARCHAR NOT NULL,
    "processed_at" FLOAT NOT NULL,
    "provider_account_scope" VARCHAR NOT NULL,
    "livemode" BOOLEAN,
    "outcome" VARCHAR,
    PRIMARY KEY ("id"),
    CHECK ((provider_account_scope = 'legacy_unknown' AND livemode IS NULL) OR (provider_account_scope <> 'legacy_unknown' AND livemode IS NOT NULL))
);

CREATE TABLE "billingfact" (
    "id" VARCHAR NOT NULL,
    "inbox_id" VARCHAR,
    "user_id" VARCHAR,
    "checkout_id" VARCHAR,
    "provider_account_scope" VARCHAR NOT NULL,
    "livemode" BOOLEAN,
    "event_id" VARCHAR,
    "payment_intent" VARCHAR,
    "session_id" VARCHAR,
    "invoice_id" VARCHAR,
    "charge_id" VARCHAR,
    "subscription_id" VARCHAR,
    "provider_status" VARCHAR,
    "amount_total" BIGINT,
    "amount_refunded" BIGINT,
    "currency" VARCHAR(3),
    "reconciliation" VARCHAR NOT NULL,
    "observed_at" DATETIME NOT NULL,
    PRIMARY KEY ("id"),
    FOREIGN KEY ("inbox_id") REFERENCES "billinginbox" ("id") ON DELETE RESTRICT,
    FOREIGN KEY ("user_id") REFERENCES "user" ("id") ON DELETE RESTRICT,
    FOREIGN KEY ("checkout_id") REFERENCES "billingcheckout" ("id") ON DELETE RESTRICT,
    UNIQUE ("inbox_id"),
    CHECK (amount_total IS NULL OR amount_total >= 0),
    CHECK (amount_refunded IS NULL OR amount_refunded >= 0),
    CHECK (reconciliation IN ('unknown','verified','needs_review')),
    CHECK ((provider_account_scope = 'legacy_unknown' AND livemode IS NULL) OR (provider_account_scope <> 'legacy_unknown' AND livemode IS NOT NULL))
);

CREATE TABLE "billinginbox" (
    "id" VARCHAR NOT NULL,
    "provider_account_scope" VARCHAR NOT NULL,
    "livemode" BOOLEAN NOT NULL,
    "event_id" VARCHAR NOT NULL,
    "event_type" VARCHAR NOT NULL,
    "api_version" VARCHAR,
    "received_at" DATETIME NOT NULL,
    "payload_sha256" VARCHAR(64) NOT NULL,
    "canonical_sha256" VARCHAR(64) NOT NULL,
    "canonical_version" INTEGER NOT NULL,
    "canonical_payload" TEXT NOT NULL,
    "business_payload" TEXT,
    "status" VARCHAR NOT NULL,
    "attempt_count" BIGINT NOT NULL,
    "attempt_limit" BIGINT NOT NULL,
    "budget_deadline" DATETIME NOT NULL,
    "next_run_at" DATETIME NOT NULL,
    "lease_owner" VARCHAR,
    "lease_epoch" BIGINT NOT NULL,
    "lease_deadline" DATETIME,
    "error_code" VARCHAR,
    "outcome_reason" VARCHAR,
    "completed_at" DATETIME,
    "payload_purged_at" DATETIME,
    PRIMARY KEY ("id"),
    UNIQUE ("provider_account_scope", "livemode", "event_id"),
    CHECK (status IN ('received','processing','retry_wait','waiting_binding','applied','ignored','needs_review')),
    CHECK (attempt_count >= 0 AND attempt_limit > 0 AND attempt_count <= attempt_limit AND lease_epoch >= 0),
    CHECK (canonical_version > 0),
    CHECK ((lease_owner IS NULL) = (lease_deadline IS NULL)),
    CHECK (status <> 'processing' OR lease_owner IS NOT NULL),
    CHECK (budget_deadline >= received_at)
);

CREATE TABLE "billingpayment" (
    "payment_intent" VARCHAR NOT NULL,
    "user_id" VARCHAR,
    "source_id" VARCHAR,
    "revoked" BOOLEAN NOT NULL,
    PRIMARY KEY ("payment_intent"),
    FOREIGN KEY ("user_id") REFERENCES "user" ("id") ON DELETE NO ACTION
);

CREATE TABLE "billingreconciliationaudit" (
    "id" VARCHAR(36) NOT NULL,
    "task_id" VARCHAR NOT NULL,
    "seq" BIGINT NOT NULL,
    "event_kind" VARCHAR(16) NOT NULL,
    "get_ordinal" INTEGER,
    "recorded_at" DATETIME NOT NULL,
    "actor_ref" VARCHAR(63) NOT NULL,
    "reason_code" VARCHAR(32) NOT NULL,
    "evidence_ref" VARCHAR(123) NOT NULL,
    "projection_version" INTEGER NOT NULL,
    "projection_json" TEXT NOT NULL,
    "projection_sha256" VARCHAR(64) NOT NULL,
    PRIMARY KEY ("id"),
    FOREIGN KEY ("task_id") REFERENCES "billingreconciliationtask" ("id") ON DELETE RESTRICT,
    UNIQUE ("task_id", "seq"),
    UNIQUE ("task_id", "event_kind", "get_ordinal"),
    CHECK (seq>0 AND projection_version=1),
    CHECK ((event_kind IN ('task_started','task_finished') AND get_ordinal IS NULL) OR (event_kind IN ('get_reserved','get_observed') AND get_ordinal IS NOT NULL AND get_ordinal BETWEEN 1 AND 3)),
    CHECK (reason_code IN ('unknown_create','missing_reference','legacy_verification'))
);

CREATE TABLE "billingreconciliationtask" (
    "id" VARCHAR(36) NOT NULL,
    "checkout_id" VARCHAR NOT NULL,
    "user_id" VARCHAR NOT NULL,
    "provider_account_scope" VARCHAR(128) NOT NULL,
    "livemode" BOOLEAN NOT NULL,
    "actor_ref" VARCHAR(63) NOT NULL,
    "reason_code" VARCHAR(32) NOT NULL,
    "evidence_ref" VARCHAR(123) NOT NULL,
    "input_version" INTEGER NOT NULL,
    "input_sha256" VARCHAR(64) NOT NULL,
    "query_json" TEXT NOT NULL,
    "policy_json" TEXT NOT NULL,
    "initial_checkout_revision" BIGINT NOT NULL,
    "expected_checkout_revision" BIGINT NOT NULL,
    "membership_revision" BIGINT NOT NULL,
    "owner_ref" VARCHAR(128) NOT NULL,
    "started_at" DATETIME NOT NULL,
    "budget_deadline" DATETIME NOT NULL,
    "get_attempts" BIGINT NOT NULL,
    "get_limit" INTEGER NOT NULL,
    "budget_version" INTEGER NOT NULL,
    "status" VARCHAR(16) NOT NULL,
    "outcome_reason" VARCHAR(64),
    "completed_at" DATETIME,
    "next_audit_seq" BIGINT NOT NULL,
    "revision" BIGINT NOT NULL,
    PRIMARY KEY ("id"),
    FOREIGN KEY ("checkout_id") REFERENCES "billingcheckout" ("id") ON DELETE RESTRICT,
    FOREIGN KEY ("user_id") REFERENCES "user" ("id") ON DELETE RESTRICT,
    UNIQUE ("checkout_id"),
    CHECK (provider_account_scope <> 'legacy_unknown' AND length(provider_account_scope)>0),
    CHECK (reason_code IN ('unknown_create','missing_reference','legacy_verification')),
    CHECK (input_version=1 AND budget_version=1 AND get_limit=3),
    CHECK (initial_checkout_revision>=0 AND expected_checkout_revision>=initial_checkout_revision AND membership_revision>=0 AND revision>=0 AND next_audit_seq>=1),
    CHECK (get_attempts>=0 AND get_attempts<=get_limit),
    CHECK (budget_deadline>=started_at),
    CHECK ((status='running' AND completed_at IS NULL) OR (status IN ('verified','needs_review') AND completed_at IS NOT NULL))
);

CREATE TABLE "downloadaccess" (
    "job_id" VARCHAR NOT NULL,
    "max_height" INTEGER,
    PRIMARY KEY ("job_id"),
    FOREIGN KEY ("job_id") REFERENCES "job" ("id") ON DELETE NO ACTION
);

CREATE TABLE "downloadidempotency" (
    "id" VARCHAR NOT NULL,
    "user_id" VARCHAR NOT NULL,
    "key" VARCHAR(128) NOT NULL,
    "fingerprint" VARCHAR NOT NULL,
    "state" VARCHAR NOT NULL,
    "created_at" FLOAT NOT NULL,
    "expires_at" FLOAT,
    "direct_expires_at" FLOAT,
    "status_code" INTEGER,
    "response_json" VARCHAR,
    "operation_id" VARCHAR,
    PRIMARY KEY ("id"),
    FOREIGN KEY ("user_id") REFERENCES "user" ("id") ON DELETE NO ACTION,
    FOREIGN KEY ("operation_id") REFERENCES "downloadoperation" ("id") ON DELETE RESTRICT,
    UNIQUE ("user_id", "key"),
    UNIQUE ("operation_id")
);

CREATE TABLE "downloadoperation" (
    "id" VARCHAR NOT NULL,
    "user_id" VARCHAR NOT NULL,
    "canonical_payload" TEXT NOT NULL,
    "fingerprint" VARCHAR(64) NOT NULL,
    "canonical_format_id" VARCHAR NOT NULL,
    "max_height" INTEGER,
    "membership_revision" BIGINT NOT NULL,
    "quota_day" DATE NOT NULL,
    "state" VARCHAR NOT NULL,
    "job_id" VARCHAR,
    "job_id_tombstone" VARCHAR,
    "accepted_at" DATETIME NOT NULL,
    "deadline_at" DATETIME NOT NULL,
    "resolve_deadline_at" DATETIME NOT NULL,
    "completed_at" DATETIME,
    "capacity_reserved" BOOLEAN NOT NULL,
    "resolve_owner" VARCHAR,
    "resolve_epoch" BIGINT NOT NULL,
    "resolve_lease_deadline" DATETIME,
    "resolve_attempts_used" BIGINT NOT NULL,
    "resolve_attempts_limit" BIGINT NOT NULL,
    "resolve_attempt_deadline" DATETIME,
    "budget_version" INTEGER NOT NULL,
    "budget_checkpoint_json" TEXT NOT NULL,
    "budget_checkpoint_at" DATETIME NOT NULL,
    "error_code" VARCHAR,
    PRIMARY KEY ("id"),
    FOREIGN KEY ("user_id") REFERENCES "user" ("id") ON DELETE RESTRICT,
    FOREIGN KEY ("job_id") REFERENCES "job" ("id") ON DELETE RESTRICT,
    CHECK (state IN ('resolving','accepted_server','direct_ready','succeeded','failed','needs_review')),
    CHECK (membership_revision >= 0 AND (max_height IS NULL OR max_height > 0)),
    CHECK (resolve_epoch >= 0 AND resolve_attempts_used >= 0 AND resolve_attempts_used <= resolve_attempts_limit AND resolve_attempts_limit > 0),
    CHECK (budget_version > 0 AND length(budget_checkpoint_json) > 0),
    CHECK ((resolve_owner IS NULL) = (resolve_lease_deadline IS NULL)),
    CHECK (deadline_at >= accepted_at),
    CHECK (resolve_deadline_at >= accepted_at AND resolve_deadline_at <= deadline_at),
    CHECK (budget_checkpoint_at >= accepted_at),
    UNIQUE ("job_id")
);

CREATE TABLE "job" (
    "id" VARCHAR NOT NULL,
    "url" VARCHAR NOT NULL,
    "title" VARCHAR,
    "format_id" VARCHAR,
    "status" VARCHAR(11) NOT NULL,
    "progress" FLOAT NOT NULL,
    "file_path" VARCHAR,
    "file_size" BIGINT,
    "error_type" VARCHAR,
    "error" VARCHAR,
    "created_at" DATETIME NOT NULL,
    "updated_at" DATETIME NOT NULL,
    "expires_at" DATETIME,
    "user_id" VARCHAR,
    PRIMARY KEY ("id"),
    FOREIGN KEY ("user_id") REFERENCES "user" ("id") ON DELETE NO ACTION,
    CHECK (status IN ('queued','downloading','merging','done','error'))
);

CREATE TABLE "membership" (
    "user_id" VARCHAR NOT NULL,
    "customer_id" VARCHAR,
    "subscription_id" VARCHAR,
    "status" VARCHAR NOT NULL,
    "expires_at" FLOAT NOT NULL,
    "cancel_at_period_end" BOOLEAN NOT NULL,
    "active_checkout_id" VARCHAR,
    "revision" INTEGER NOT NULL,
    "entitlement_source" VARCHAR,
    PRIMARY KEY ("user_id"),
    FOREIGN KEY ("user_id") REFERENCES "user" ("id") ON DELETE NO ACTION,
    UNIQUE ("customer_id"),
    UNIQUE ("subscription_id")
);

CREATE TABLE "quota" (
    "id" VARCHAR NOT NULL,
    "user_id" VARCHAR NOT NULL,
    "date" VARCHAR NOT NULL,
    "downloads_used" INTEGER NOT NULL,
    "limit" INTEGER NOT NULL,
    PRIMARY KEY ("id"),
    FOREIGN KEY ("user_id") REFERENCES "user" ("id") ON DELETE NO ACTION,
    UNIQUE ("user_id", "date")
);

CREATE TABLE "quotacharge" (
    "operation_id" VARCHAR NOT NULL,
    "user_id" VARCHAR NOT NULL,
    "quota_day" DATE NOT NULL,
    "delta" BIGINT NOT NULL,
    "charged_at" DATETIME NOT NULL,
    PRIMARY KEY ("operation_id"),
    FOREIGN KEY ("operation_id") REFERENCES "downloadoperation" ("id") ON DELETE RESTRICT,
    FOREIGN KEY ("user_id") REFERENCES "user" ("id") ON DELETE RESTRICT,
    CHECK (delta = 1)
);

CREATE TABLE "resourcecounter" (
    "resource" VARCHAR NOT NULL,
    "scope" VARCHAR NOT NULL,
    "used" BIGINT NOT NULL,
    PRIMARY KEY ("resource", "scope"),
    CHECK (used >= 0)
);

CREATE TABLE "resourcereservation" (
    "operation_id" VARCHAR NOT NULL,
    "resource" VARCHAR NOT NULL,
    "scope" VARCHAR NOT NULL,
    "units" BIGINT NOT NULL,
    "released" BOOLEAN NOT NULL,
    "reserved_at" DATETIME NOT NULL,
    "released_at" DATETIME,
    PRIMARY KEY ("operation_id", "resource", "scope"),
    FOREIGN KEY ("operation_id") REFERENCES "downloadoperation" ("id") ON DELETE RESTRICT,
    FOREIGN KEY ("resource", "scope") REFERENCES "resourcecounter" ("resource", "scope") ON DELETE RESTRICT,
    CHECK (units > 0),
    CHECK ((released = false AND released_at IS NULL) OR (released = true AND released_at IS NOT NULL))
);

CREATE TABLE "user" (
    "id" VARCHAR NOT NULL,
    "email" VARCHAR NOT NULL,
    "password_hash" VARCHAR NOT NULL,
    "created_at" DATETIME NOT NULL,
    PRIMARY KEY ("id")
);

CREATE INDEX "ix_billingcheckout_user_id" ON "billingcheckout" ("user_id");

CREATE INDEX "ix_billingfact_scope_pi" ON "billingfact" ("provider_account_scope", "livemode", "payment_intent");

CREATE INDEX "ix_billingfact_checkout_id" ON "billingfact" ("checkout_id");

CREATE INDEX "ix_billinginbox_status_next_run" ON "billinginbox" ("status", "next_run_at");

CREATE INDEX "ix_billinginbox_status_lease" ON "billinginbox" ("status", "lease_deadline");

CREATE INDEX "ix_billingpayment_user_id" ON "billingpayment" ("user_id");

CREATE UNIQUE INDEX "uq_billingreconciliationaudit_lifecycle" ON "billingreconciliationaudit" ("task_id", "event_kind") WHERE get_ordinal IS NULL;

CREATE INDEX "ix_billingreconciliationtask_status_deadline" ON "billingreconciliationtask" ("status", "budget_deadline");

CREATE INDEX "ix_billingreconciliationtask_user_id" ON "billingreconciliationtask" ("user_id");

CREATE INDEX "ix_downloadidempotency_user_id" ON "downloadidempotency" ("user_id");

CREATE INDEX "ix_downloadidempotency_expires_at" ON "downloadidempotency" ("expires_at");

CREATE INDEX "ix_downloadoperation_user_id_accepted_at" ON "downloadoperation" ("user_id", "accepted_at");

CREATE INDEX "ix_downloadoperation_state_lease" ON "downloadoperation" ("state", "resolve_lease_deadline");

CREATE INDEX "ix_quota_user_id" ON "quota" ("user_id");

CREATE INDEX "ix_quotacharge_user_id_quota_day" ON "quotacharge" ("user_id", "quota_day");

CREATE INDEX "ix_resourcereservation_counter_released" ON "resourcereservation" ("resource", "scope", "released");

CREATE UNIQUE INDEX "ix_user_email" ON "user" ("email");
