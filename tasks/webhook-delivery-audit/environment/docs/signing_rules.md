# Webhook signature rules

Each attempt includes `sent_at` (ms), `body` (object), and `signature` (hex string, no prefix).

Canonical body: recursively sort object keys; arrays keep element order; serialize with `JSON.stringify` on the canonical form (compact, no extra spaces). Numbers and booleans use JSON forms.

Signing input string: `{sent_at}.{canonical_body}` (sent_at as decimal digits, no quotes).

Expected signature: HMAC-SHA256 using the endpoint `secret` as key, digest encoded as lowercase hex.

Compare to attempt `signature` field exactly.
