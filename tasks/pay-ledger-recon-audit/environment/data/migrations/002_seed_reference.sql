-- Reference data: tenants, merchants, fee rules, FX rates.
-- Mirrors data/tenants.json and data/merchant_category_rules.json.

INSERT INTO tenants (tenant_id, jurisdiction, base_currency, audit_day_offset_min, minimum_balance_minor) VALUES
  ('T_USD', 'US', 'USD',    0, -100000),
  ('T_EUR', 'EU', 'EUR', -120,       0),
  ('T_GBP', 'UK', 'GBP',   60,  500000);

INSERT INTO merchants (merchant_id, name, mcc, kyc_status) VALUES
  ('M_AMZ',     'Amazon Inc',         '5942', 'verified'),
  ('M_UBER',    'Uber Eats Holdings', '5812', 'verified'),
  ('M_NETFLIX', 'Netflix Streaming',  '4899', 'verified'),
  ('M_RANDOM',  'RandomMart',         '9999', 'unverified'),
  ('M_WEIRD',   'Weird Things Inc',   '5942', 'verified');

INSERT INTO merchant_category_rules (rule_id, priority, pattern, mcc, fee_bps) VALUES
  ('R001', 10, 'amazon',  '5942', 200),
  ('R002', 20, 'uber',    '5812', 300),
  ('R003',  5, 'netflix', '4899', 150),
  ('R010', 10, 'weird',   '5942', 400);

INSERT INTO fx_rates (day, base, quote, rate_micro) VALUES
  (20000, 'EUR', 'USD', 1100000),
  (19999, 'EUR', 'USD', 1095000),
  (20000, 'USD', 'EUR',  909091);
