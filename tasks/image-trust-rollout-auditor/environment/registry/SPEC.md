Image Trust Rollout Auditor Specification

Input root: `/app/registry`
Output root: `/app/audit`

The program reads JSON fixtures from:
- `/app/registry/keys/*.json`
- `/app/registry/services/*.json`
- `/app/registry/images/*.json`
- `/app/registry/policy.json`
- `/app/registry/pool_state.json`
- `/app/registry/incident_log.json`

The program writes exactly five JSON files:
- `/app/audit/signature_audit.json`
- `/app/audit/deployment_gate.json`
- `/app/audit/key_exposure.json`
- `/app/audit/quarantine_plan.json`
- `/app/audit/summary.json`

Time model:
- `current_day = pool_state.current_day`.
- An incident is active when `accepted == true` and `day <= current_day`.

Incident kinds:
- `key_compromise` (`key_id`)
- `risk_override` (`image_id`, `risk_value`)
- `force_allow` (`image_id`)

Duplicate-resolution rules:
1. For `risk_override`, resolve per `image_id` by highest `day`, then ASCII-smallest `event_id`.
2. For `force_allow`, resolve per `image_id` by highest `day`, then ASCII-smallest `event_id`.
3. For `key_compromise`, any active event marks the key compromised.

Trust rules:
- Allowed key tiers by service environment:
  - `prod`: `["primary"]`
  - `staging`: `["primary", "secondary"]`
  - `dev`: `["primary", "secondary", "legacy"]`
- Minimum trusted signatures by environment:
  - `prod`: `2`
  - `staging`: `1`
  - `dev`: `1`
- A signature is trusted only if:
  - referenced key exists,
  - key `expires_day >= current_day`,
  - key `trust_tier` is allowed for the image's service environment.

Per-image `signature_status`:
- `compromised` if any signing key is compromised.
- Else `insufficient` if trusted signature count is below environment minimum.
- Else `valid`.

Risk computation per image:
1. Start with `base_risk`.
2. If a resolved `risk_override` exists, replace risk with `risk_value`.
3. If `signature_status == "insufficient"`, add `policy.insufficient_signature_penalty`.
4. If `signature_status == "compromised"`, add `policy.compromised_signature_penalty`.

Service quarantine rule:
- A service enters lockdown if any of its images has `signature_status == "compromised"`.

Deployment decision precedence (top to bottom):
1. `block_compromised` when image `signature_status == "compromised"`.
2. `block_service_lockdown` when image service is in lockdown and no valid force-allow applies.
3. `allow_force` when force-allow exists and computed risk is strictly less than `policy.emergency_freeze_risk_threshold`.
4. `block_risk` when computed risk is greater than service `max_risk_allowed`.
5. `allow` otherwise.

Quarantine service status:
- `lockdown` when service is in lockdown.
- `monitor` when service is not in lockdown and at least one image for that service has `decision == "block_risk"`.
- `clear` otherwise.

Output schemas:

1) `signature_audit.json`: list of objects sorted by `image_id`:
- `image_id`
- `service_id`
- `trusted_signature_count`
- `minimum_required_signatures`
- `expired_signing_keys` (ASCII-sorted list)
- `compromised_signing_keys` (ASCII-sorted list)
- `signature_status`

2) `deployment_gate.json`: list sorted by `image_id`:
- `image_id`
- `service_id`
- `computed_risk`
- `max_risk_allowed`
- `force_allow_active` (boolean, true only when resolved force-allow exists)
- `decision`

3) `key_exposure.json`: list sorted by `key_id`:
- `key_id`
- `status` (`clean`, `expired`, `compromised`) where `compromised` outranks `expired`
- `signed_image_count`
- `compromised_image_count`
- `impacted_images` (ASCII-sorted list of image IDs signed by this key)

4) `quarantine_plan.json`: list sorted by `service_id`:
- `service_id`
- `status`
- `blocked_images` (ASCII-sorted list of image IDs with decisions starting with `block_`)
- `review_images` (ASCII-sorted list of image IDs with `decision == "allow_force"`)

5) `summary.json`: object with keys:
- `total_images`
- `services_lockdown`
- `services_monitor`
- `services_clear`
- `decision_counts` (object keyed by decision string)
- `signature_status_counts` (object keyed by signature status string)
- `compromised_keys`
- `force_allow_applied` (count of images with `decision == "allow_force"`)

Canonical JSON encoding for every output:
- `json.dumps(value, sort_keys=True, indent=2, separators=(",", ": "))`
