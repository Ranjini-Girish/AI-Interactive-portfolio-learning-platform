-- Ledger seed: accounts, transactions, holds, mv_daily_balances.
-- Day numbers (opaque integer day identifiers, never calendar dates).
-- Reference: day D covers ts in [D*86400, (D+1)*86400). Spot-checks:
--   day 19960 = ts in [1724544000, 1724630400)
--   day 19970 = ts in [1725408000, 1725494400)
--   day 19975 = ts in [1725840000, 1725926400)
--   day 19998 = ts in [1727827200, 1727913600)
--   day 19999 = ts in [1727913600, 1728000000)
--   day 20000 = ts in [1728000000, 1728086400)  -- current_day
--   day 20001 = ts in [1728086400, 1728172800)  -- after current_day

INSERT INTO accounts (account_id, tenant_id, currency, opened_day, closed_day, status) VALUES
  ('ACC_001', 'T_USD',     'USD', 19000, NULL,  'active'),
  ('ACC_002', 'T_USD',     'USD', 19000, NULL,  'active'),
  ('ACC_003', 'T_USD',     'USD', 19000, 19970, 'closed'),
  ('ACC_004', 'T_EUR',     'EUR', 19000, NULL,  'active'),
  ('ACC_005', 'T_USD',     'USD', 19000, NULL,  'active'),
  ('ACC_006', 'T_GBP',     'GBP', 19000, NULL,  'active'),
  ('ACC_007', 'T_USD',     'USD', 19000, NULL,  'active'),
  ('ACC_008', 'T_USD',     'USD', 19000, NULL,  'active'),
  ('ACC_009', 'T_PHANTOM', 'USD', 19000, NULL,  'active'),
  ('ACC_010', 'T_USD',     'USD', 19000, NULL,  'active'),
  ('ACC_011', 'T_USD',     'USD', 19000, NULL,  'active'),
  ('ACC_012', 'T_USD',     'USD', 19000, NULL,  'active'),
  ('ACC_013', 'T_USD',     'USD', 19000, NULL,  'active');

-- ACC_001 (clean baseline; M_AMZ -> rule R001 200 bps; funded by parentless refund)
INSERT INTO transactions (tx_id, account_id, kind, amount_minor, currency, ts_utc, sequence_id, parent_tx_id, status, merchant_id, fx_micro) VALUES
  ('TX_001_fund',  'ACC_001', 'refund',  20000, 'USD', 1727900000, 1, NULL,         'committed', NULL,       NULL),
  ('TX_001_a',     'ACC_001', 'capture',  5000, 'USD', 1727950000, 1, NULL,         'committed', 'M_AMZ',    NULL),
  ('TX_001_a_fee', 'ACC_001', 'fee',       100, 'USD', 1727950100, 1, 'TX_001_a',   'committed', 'M_AMZ',    NULL);

-- ACC_002 (clean txs; stuck-hold cases live in holds table; funded by parentless refund)
INSERT INTO transactions (tx_id, account_id, kind, amount_minor, currency, ts_utc, sequence_id, parent_tx_id, status, merchant_id, fx_micro) VALUES
  ('TX_002_fund',  'ACC_002', 'refund',  10000, 'USD', 1727850000, 1, NULL,         'committed', NULL,        NULL),
  ('TX_002_a',     'ACC_002', 'capture',  2000, 'USD', 1727900000, 1, NULL,         'committed', 'M_NETFLIX', NULL),
  ('TX_002_a_fee', 'ACC_002', 'fee',        30, 'USD', 1727900100, 1, 'TX_002_a',   'committed', 'M_NETFLIX', NULL);

-- ACC_003 (closed_day=19970; root on day 19960 (pre-close), refund on day 19975 (post-close)
-- => post_close_chain_activity)
INSERT INTO transactions (tx_id, account_id, kind, amount_minor, currency, ts_utc, sequence_id, parent_tx_id, status, merchant_id, fx_micro) VALUES
  ('TX_003_root',     'ACC_003', 'capture', 1000, 'USD', 1724600000, 1, NULL,          'committed', 'M_AMZ', NULL),
  ('TX_003_root_fee', 'ACC_003', 'fee',       20, 'USD', 1724600100, 1, 'TX_003_root', 'committed', 'M_AMZ', NULL),
  ('TX_003_post',     'ACC_003', 'refund',  1000, 'USD', 1725900000, 1, 'TX_003_root', 'committed', 'M_AMZ', NULL);

-- ACC_004 (T_EUR base, EUR transactions, no FX; funded by parentless refund)
INSERT INTO transactions (tx_id, account_id, kind, amount_minor, currency, ts_utc, sequence_id, parent_tx_id, status, merchant_id, fx_micro) VALUES
  ('TX_004_fund',  'ACC_004', 'refund', 15000, 'EUR', 1727850000, 1, NULL,         'committed', NULL,     NULL),
  ('TX_004_a',     'ACC_004', 'capture', 3000, 'EUR', 1727950000, 1, NULL,         'committed', 'M_UBER', NULL),
  ('TX_004_a_fee', 'ACC_004', 'fee',       90, 'EUR', 1727950100, 1, 'TX_004_a',   'committed', 'M_UBER', NULL);

-- ACC_005 (T_USD base USD; non-USD transactions => FX cases)
--   TX_005_a: cap EUR 2000 with correct fx, no anomaly
--   TX_005_b: cap GBP 1500, no fx_rate row exists => fx_missing; no fee child => fee_missing
--   TX_005_c: cap EUR 4000, stored fx_micro=1095000 vs table 1100000 => fx_drift
INSERT INTO transactions (tx_id, account_id, kind, amount_minor, currency, ts_utc, sequence_id, parent_tx_id, status, merchant_id, fx_micro) VALUES
  ('TX_005_a',     'ACC_005', 'capture', 2000, 'EUR', 1728020000, 1, NULL,        'committed', 'M_AMZ',    1100000),
  ('TX_005_a_fee', 'ACC_005', 'fee',       40, 'EUR', 1728020100, 1, 'TX_005_a',  'committed', 'M_AMZ',    1100000),
  ('TX_005_b',     'ACC_005', 'capture', 1500, 'GBP', 1728025000, 1, NULL,        'committed', 'M_NETFLIX',1300000),
  ('TX_005_c',     'ACC_005', 'capture', 4000, 'EUR', 1728030000, 1, NULL,        'committed', 'M_AMZ',    1095000),
  ('TX_005_c_fee', 'ACC_005', 'fee',       80, 'EUR', 1728030100, 1, 'TX_005_c',  'committed', 'M_AMZ',    1100000);

-- ACC_006 (T_GBP base GBP; 6 captures on current_day => velocity_breach; small balance => available_below_floor)
INSERT INTO transactions (tx_id, account_id, kind, amount_minor, currency, ts_utc, sequence_id, parent_tx_id, status, merchant_id, fx_micro) VALUES
  ('TX_006_a',     'ACC_006', 'capture', 100, 'GBP', 1728001000, 1, NULL,        'committed', 'M_NETFLIX', NULL),
  ('TX_006_a_fee', 'ACC_006', 'fee',       2, 'GBP', 1728001100, 1, 'TX_006_a',  'committed', 'M_NETFLIX', NULL),
  ('TX_006_b',     'ACC_006', 'capture', 100, 'GBP', 1728002000, 1, NULL,        'committed', 'M_NETFLIX', NULL),
  ('TX_006_b_fee', 'ACC_006', 'fee',       2, 'GBP', 1728002100, 1, 'TX_006_b',  'committed', 'M_NETFLIX', NULL),
  ('TX_006_c',     'ACC_006', 'capture', 100, 'GBP', 1728003000, 1, NULL,        'committed', 'M_NETFLIX', NULL),
  ('TX_006_c_fee', 'ACC_006', 'fee',       2, 'GBP', 1728003100, 1, 'TX_006_c',  'committed', 'M_NETFLIX', NULL),
  ('TX_006_d',     'ACC_006', 'capture', 100, 'GBP', 1728004000, 1, NULL,        'committed', 'M_NETFLIX', NULL),
  ('TX_006_d_fee', 'ACC_006', 'fee',       2, 'GBP', 1728004100, 1, 'TX_006_d',  'committed', 'M_NETFLIX', NULL),
  ('TX_006_e',     'ACC_006', 'capture', 100, 'GBP', 1728005000, 1, NULL,        'committed', 'M_NETFLIX', NULL),
  ('TX_006_e_fee', 'ACC_006', 'fee',       2, 'GBP', 1728005100, 1, 'TX_006_e',  'committed', 'M_NETFLIX', NULL),
  ('TX_006_f',     'ACC_006', 'capture', 100, 'GBP', 1728006000, 1, NULL,        'committed', 'M_NETFLIX', NULL),
  ('TX_006_f_fee', 'ACC_006', 'fee',       2, 'GBP', 1728006100, 1, 'TX_006_f',  'committed', 'M_NETFLIX', NULL);

-- ACC_007 (fee_amount_mismatch; M_WEIRD matches R010 (prio 10) only => 400 bps; expected fee = 1000*400/10000 = 40; recorded = 35)
--   plus a parentless refund booster to keep open_balance positive (avoid spurious negative_open_balance)
INSERT INTO transactions (tx_id, account_id, kind, amount_minor, currency, ts_utc, sequence_id, parent_tx_id, status, merchant_id, fx_micro) VALUES
  ('TX_007_a',     'ACC_007', 'capture', 1000, 'USD', 1727850000, 1, NULL,        'committed', 'M_WEIRD', NULL),
  ('TX_007_a_fee', 'ACC_007', 'fee',       35, 'USD', 1727850100, 1, 'TX_007_a',  'committed', 'M_WEIRD', NULL),
  ('TX_007_b',     'ACC_007', 'refund',  2000, 'USD', 1727950000, 1, NULL,        'committed', NULL,      NULL);

-- ACC_008 (duplicate_refund + double_resolution)
INSERT INTO transactions (tx_id, account_id, kind, amount_minor, currency, ts_utc, sequence_id, parent_tx_id, status, merchant_id, fx_micro) VALUES
  ('TX_008_root',      'ACC_008', 'capture',    5000, 'USD', 1727900000, 1, NULL,                 'committed', 'M_AMZ', NULL),
  ('TX_008_root_fee',  'ACC_008', 'fee',         100, 'USD', 1727900100, 1, 'TX_008_root',        'committed', 'M_AMZ', NULL),
  ('TX_008_refund_a',  'ACC_008', 'refund',     5000, 'USD', 1727995000, 1, 'TX_008_root',        'committed', 'M_AMZ', NULL),
  ('TX_008_refund_b',  'ACC_008', 'refund',     5000, 'USD', 1727996000, 1, 'TX_008_root',        'committed', 'M_AMZ', NULL),
  ('TX_008_chargeback','ACC_008', 'chargeback', 5000, 'USD', 1727997000, 1, 'TX_008_refund_a',    'committed', 'M_AMZ', NULL);

-- ACC_009 (orphan tenant T_PHANTOM; its findings are skipped; counted in data_quality.orphan_tenant_accounts)
INSERT INTO transactions (tx_id, account_id, kind, amount_minor, currency, ts_utc, sequence_id, parent_tx_id, status, merchant_id, fx_micro) VALUES
  ('TX_009_a',     'ACC_009', 'capture', 1000, 'USD', 1727950000, 1, NULL,        'committed', 'M_AMZ', NULL),
  ('TX_009_a_fee', 'ACC_009', 'fee',       20, 'USD', 1727950100, 1, 'TX_009_a',  'committed', 'M_AMZ', NULL);

-- ACC_010 (chain cycle; plus fee_missing for both members)
INSERT INTO transactions (tx_id, account_id, kind, amount_minor, currency, ts_utc, sequence_id, parent_tx_id, status, merchant_id, fx_micro) VALUES
  ('TX_010_a', 'ACC_010', 'capture', 1000, 'USD', 1727860000, 1, 'TX_010_b', 'committed', 'M_AMZ', NULL),
  ('TX_010_b', 'ACC_010', 'capture', 1000, 'USD', 1727870000, 1, 'TX_010_a', 'committed', 'M_AMZ', NULL);

-- ACC_011 (5 small captures, all with correct fees, drives negative_open_balance only)
INSERT INTO transactions (tx_id, account_id, kind, amount_minor, currency, ts_utc, sequence_id, parent_tx_id, status, merchant_id, fx_micro) VALUES
  ('TX_011_a',     'ACC_011', 'capture', 200, 'USD', 1727870000, 1, NULL,        'committed', 'M_AMZ', NULL),
  ('TX_011_a_fee', 'ACC_011', 'fee',       4, 'USD', 1727870100, 1, 'TX_011_a',  'committed', 'M_AMZ', NULL),
  ('TX_011_b',     'ACC_011', 'capture', 200, 'USD', 1727871000, 1, NULL,        'committed', 'M_AMZ', NULL),
  ('TX_011_b_fee', 'ACC_011', 'fee',       4, 'USD', 1727871100, 1, 'TX_011_b',  'committed', 'M_AMZ', NULL),
  ('TX_011_c',     'ACC_011', 'capture', 200, 'USD', 1727872000, 1, NULL,        'committed', 'M_AMZ', NULL),
  ('TX_011_c_fee', 'ACC_011', 'fee',       4, 'USD', 1727872100, 1, 'TX_011_c',  'committed', 'M_AMZ', NULL),
  ('TX_011_d',     'ACC_011', 'capture', 200, 'USD', 1727873000, 1, NULL,        'committed', 'M_AMZ', NULL),
  ('TX_011_d_fee', 'ACC_011', 'fee',       4, 'USD', 1727873100, 1, 'TX_011_d',  'committed', 'M_AMZ', NULL),
  ('TX_011_e',     'ACC_011', 'capture', 200, 'USD', 1727874000, 1, NULL,        'committed', 'M_AMZ', NULL),
  ('TX_011_e_fee', 'ACC_011', 'fee',       4, 'USD', 1727874100, 1, 'TX_011_e',  'committed', 'M_AMZ', NULL);

-- ACC_012 (severe available_below_floor; positive open balance via refund booster + huge uncleared hold)
INSERT INTO transactions (tx_id, account_id, kind, amount_minor, currency, ts_utc, sequence_id, parent_tx_id, status, merchant_id, fx_micro) VALUES
  ('TX_012_a',     'ACC_012', 'capture', 1000000, 'USD', 1727980000, 1, NULL,        'committed', 'M_AMZ', NULL),
  ('TX_012_a_fee', 'ACC_012', 'fee',       20000, 'USD', 1727980100, 1, 'TX_012_a',  'committed', 'M_AMZ', NULL),
  ('TX_012_b',     'ACC_012', 'refund',  2500000, 'USD', 1727990000, 1, NULL,        'committed', NULL,    NULL);

-- ACC_013 (data quality stress: unknown kind, negative amount; both non-voided; both contribute zero-or-positive to balance)
INSERT INTO transactions (tx_id, account_id, kind, amount_minor, currency, ts_utc, sequence_id, parent_tx_id, status, merchant_id, fx_micro) VALUES
  ('TX_013_unknown',  'ACC_013', 'weird_kind', 0,    'USD', 1727950000, 1, NULL, 'committed', NULL, NULL),
  ('TX_013_negative', 'ACC_013', 'release',  -100,   'USD', 1727950500, 1, NULL, 'committed', NULL, NULL);

-- Holds
INSERT INTO holds (hold_id, account_id, amount_minor, placed_ts, expires_ts, released_ts, reason) VALUES
  ('H_002_a',  'ACC_002',     500, 1727800000, 1727900000, NULL,        'fraud_review'),
  ('H_002_b',  'ACC_002',     600, 1727800000, 1727900000, 1727900500,  'fraud_review'),
  ('H_002_c',  'ACC_002',     700, 1727800000, 1728086400, NULL,        'manual_review'),
  ('H_002_d',  'ACC_002',     800, 1727800000, 1728172800, NULL,        'manual_review'),
  ('H_005',    'ACC_PHANTOM',1500, 1727750000, 1727800000, NULL,        'orphan_check'),
  ('H_012_a',  'ACC_012', 2680000, 1727800000, 1728172800, NULL,        'risk_reserve');

-- Materialized view of daily balances. Most recent committed_ts across non-closed accounts is 1728080000
-- (=> staleness 6400 sec > 60min*60s = 3600 => view_stale = true).
-- ACC_003 (closed) has an older committed_ts and is excluded from the staleness MAX.
INSERT INTO mv_daily_balances (account_id, day, balance_minor, committed_ts) VALUES
  ('ACC_001', 19999, -5100,    1728080000),
  ('ACC_002', 19998, -2030,    1728080000),
  ('ACC_003', 19975,  -20,     1727900000),
  ('ACC_004', 19999, -3090,    1728080000),
  ('ACC_005', 20000, -7620,    1728080000),
  ('ACC_006', 20000,  -612,    1728080000),
  ('ACC_007', 19999,   965,    1728080000),
  ('ACC_008', 19999,  9900,    1728080000),
  ('ACC_009', 19999, -1020,    1728080000),
  ('ACC_010', 19998, -2000,    1728080000),
  ('ACC_011', 19998, -1020,    1728080000),
  ('ACC_012', 19999,  1480000, 1728080000),
  ('ACC_013', 19999,     0,    1728080000);
