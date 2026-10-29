CREATE TABLE billingcheckout (
	id VARCHAR NOT NULL, 
	user_id VARCHAR NOT NULL, 
	price_id VARCHAR NOT NULL, 
	mode VARCHAR NOT NULL, 
	duration_days INTEGER NOT NULL, 
	origin VARCHAR NOT NULL, 
	customer_id VARCHAR, 
	created_at FLOAT NOT NULL, 
	stripe_id VARCHAR, 
	url VARCHAR, 
	expires_at FLOAT NOT NULL, 
	state VARCHAR NOT NULL, 
	fulfilled BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES user (id), 
	UNIQUE (stripe_id)
);

CREATE TABLE billingevent (
	id VARCHAR NOT NULL, 
	processed_at FLOAT NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE billingpayment (
	payment_intent VARCHAR NOT NULL, 
	user_id VARCHAR, 
	source_id VARCHAR, 
	revoked BOOLEAN NOT NULL, 
	PRIMARY KEY (payment_intent), 
	FOREIGN KEY(user_id) REFERENCES user (id)
);

CREATE TABLE downloadaccess (
	job_id VARCHAR NOT NULL, 
	max_height INTEGER, 
	PRIMARY KEY (job_id), 
	FOREIGN KEY(job_id) REFERENCES job (id)
);

CREATE TABLE downloadidempotency (
	id VARCHAR NOT NULL, 
	user_id VARCHAR NOT NULL, 
	"key" VARCHAR(128) NOT NULL, 
	fingerprint VARCHAR NOT NULL, 
	state VARCHAR NOT NULL, 
	created_at FLOAT NOT NULL, 
	expires_at FLOAT, 
	direct_expires_at FLOAT, 
	status_code INTEGER, 
	response_json VARCHAR, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_download_idempotency_user_key UNIQUE (user_id, "key"), 
	FOREIGN KEY(user_id) REFERENCES user (id)
);

CREATE TABLE job (
	id VARCHAR NOT NULL, 
	url VARCHAR NOT NULL, 
	title VARCHAR, 
	format_id VARCHAR, 
	status VARCHAR(11) NOT NULL, 
	progress FLOAT NOT NULL, 
	file_path VARCHAR, 
	file_size INTEGER, 
	error_type VARCHAR, 
	error VARCHAR, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	expires_at DATETIME, 
	user_id VARCHAR, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES user (id)
);

CREATE TABLE membership (
	user_id VARCHAR NOT NULL, 
	customer_id VARCHAR, 
	subscription_id VARCHAR, 
	status VARCHAR NOT NULL, 
	expires_at FLOAT NOT NULL, 
	cancel_at_period_end BOOLEAN NOT NULL, 
	active_checkout_id VARCHAR, 
	revision INTEGER NOT NULL, 
	entitlement_source VARCHAR, 
	PRIMARY KEY (user_id), 
	FOREIGN KEY(user_id) REFERENCES user (id), 
	UNIQUE (customer_id), 
	UNIQUE (subscription_id)
);

CREATE TABLE quota (
	id VARCHAR NOT NULL, 
	user_id VARCHAR NOT NULL, 
	date VARCHAR NOT NULL, 
	downloads_used INTEGER NOT NULL, 
	"limit" INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_quota_user_date UNIQUE (user_id, date), 
	FOREIGN KEY(user_id) REFERENCES user (id)
);

CREATE TABLE user (
	id VARCHAR NOT NULL, 
	email VARCHAR NOT NULL, 
	password_hash VARCHAR NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_billingcheckout_user_id ON billingcheckout (user_id);

CREATE INDEX ix_billingpayment_user_id ON billingpayment (user_id);

CREATE INDEX ix_downloadidempotency_expires_at ON downloadidempotency (expires_at);

CREATE INDEX ix_downloadidempotency_user_id ON downloadidempotency (user_id);

CREATE INDEX ix_quota_user_id ON quota (user_id);

CREATE UNIQUE INDEX ix_user_email ON user (email);
