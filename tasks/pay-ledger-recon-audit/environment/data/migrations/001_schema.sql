-- Schema migration for the payments ledger.
-- Foreign keys are intentionally OFF: the auditor must detect orphan rows.
PRAGMA foreign_keys = OFF;
PRAGMA journal_mode = WAL;

CREATE TABLE tenants (
    tenant_id            TEXT PRIMARY KEY,
    jurisdiction         TEXT NOT NULL,
    base_currency        TEXT NOT NULL,
    audit_day_offset_min INTEGER NOT NULL DEFAULT 0,
    minimum_balance_minor INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE accounts (
    account_id  TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    currency    TEXT NOT NULL,
    opened_day  INTEGER NOT NULL,
    closed_day  INTEGER,
    status      TEXT
);

CREATE TABLE merchants (
    merchant_id TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    mcc         TEXT NOT NULL,
    kyc_status  TEXT NOT NULL CHECK (kyc_status IN ('verified', 'unverified'))
);

CREATE TABLE merchant_category_rules (
    rule_id   TEXT PRIMARY KEY,
    priority  INTEGER NOT NULL,
    pattern   TEXT NOT NULL,
    mcc       TEXT NOT NULL,
    fee_bps   INTEGER NOT NULL
);

CREATE TABLE transactions (
    tx_id        TEXT PRIMARY KEY,
    account_id   TEXT NOT NULL,
    kind         TEXT,
    amount_minor INTEGER NOT NULL DEFAULT 0,
    currency     TEXT NOT NULL,
    ts_utc       INTEGER NOT NULL,
    sequence_id  INTEGER NOT NULL DEFAULT 0,
    parent_tx_id TEXT,
    status       TEXT,
    merchant_id  TEXT,
    fx_micro     INTEGER
);
CREATE INDEX idx_tx_account ON transactions(account_id);
CREATE INDEX idx_tx_parent  ON transactions(parent_tx_id);
CREATE INDEX idx_tx_kind    ON transactions(kind);

CREATE TABLE holds (
    hold_id      TEXT PRIMARY KEY,
    account_id   TEXT NOT NULL,
    amount_minor INTEGER NOT NULL,
    placed_ts    INTEGER NOT NULL,
    expires_ts   INTEGER NOT NULL,
    released_ts  INTEGER,
    reason       TEXT
);

CREATE TABLE fx_rates (
    day        INTEGER NOT NULL,
    base       TEXT NOT NULL,
    quote      TEXT NOT NULL,
    rate_micro INTEGER NOT NULL,
    PRIMARY KEY (day, base, quote)
);

CREATE TABLE mv_daily_balances (
    account_id   TEXT NOT NULL,
    day          INTEGER NOT NULL,
    balance_minor INTEGER NOT NULL,
    committed_ts INTEGER NOT NULL,
    PRIMARY KEY (account_id, day)
);
