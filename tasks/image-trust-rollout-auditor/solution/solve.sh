#!/bin/bash
set -euo pipefail

cat <<'RS' > /app/planner/src/main.rs
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::env;
use std::fs;
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, Deserialize)]
struct Key {
    key_id: String,
    owner_team: String,
    trust_tier: String,
    expires_day: i64,
}

#[derive(Debug, Clone, Deserialize)]
struct Service {
    service_id: String,
    environment: String,
    max_risk_allowed: i64,
}

#[derive(Debug, Clone, Deserialize)]
struct Image {
    image_id: String,
    service_id: String,
    digest: String,
    previous_digest: String,
    base_risk: i64,
    signatures: Vec<String>,
}

#[derive(Debug, Deserialize)]
struct Policy {
    min_signatures_by_env: HashMap<String, i64>,
    trusted_tiers_by_env: HashMap<String, Vec<String>>,
    insufficient_signature_penalty: i64,
    compromised_signature_penalty: i64,
    emergency_freeze_risk_threshold: i64,
}

#[derive(Debug, Deserialize)]
struct PoolState {
    current_day: i64,
}

#[derive(Debug, Clone, Deserialize)]
struct Incident {
    accepted: bool,
    day: i64,
    event_id: String,
    kind: String,
    key_id: Option<String>,
    image_id: Option<String>,
    risk_value: Option<i64>,
}

#[derive(Debug, Clone, Serialize)]
struct SignatureAuditRow {
    image_id: String,
    service_id: String,
    trusted_signature_count: i64,
    minimum_required_signatures: i64,
    expired_signing_keys: Vec<String>,
    compromised_signing_keys: Vec<String>,
    signature_status: String,
}

#[derive(Debug, Clone, Serialize)]
struct DeploymentGateRow {
    image_id: String,
    service_id: String,
    computed_risk: i64,
    max_risk_allowed: i64,
    force_allow_active: bool,
    decision: String,
}

#[derive(Debug, Clone, Serialize)]
struct KeyExposureRow {
    key_id: String,
    status: String,
    signed_image_count: i64,
    compromised_image_count: i64,
    impacted_images: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
struct QuarantineRow {
    service_id: String,
    status: String,
    blocked_images: Vec<String>,
    review_images: Vec<String>,
}

#[derive(Debug, Serialize)]
struct Summary {
    total_images: i64,
    services_lockdown: i64,
    services_monitor: i64,
    services_clear: i64,
    decision_counts: BTreeMap<String, i64>,
    signature_status_counts: BTreeMap<String, i64>,
    compromised_keys: i64,
    force_allow_applied: i64,
}

fn read_json<T: for<'de> Deserialize<'de>>(path: &Path) -> T {
    let content = fs::read_to_string(path).unwrap_or_else(|_| panic!("failed to read {}", path.display()));
    serde_json::from_str(&content).unwrap_or_else(|_| panic!("invalid json {}", path.display()))
}

fn write_json<T: Serialize>(path: &Path, value: &T) {
    let content = serde_json::to_string_pretty(value).expect("serialize failed");
    fs::write(path, content).unwrap_or_else(|_| panic!("failed to write {}", path.display()));
}

fn pick_latest_event(active: &[Incident], kind: &str) -> HashMap<String, (i64, String, i64)> {
    let mut picked: HashMap<String, (i64, String, i64)> = HashMap::new();
    for event in active {
        if event.kind != kind {
            continue;
        }
        let image_id = match &event.image_id {
            Some(v) => v.clone(),
            None => continue,
        };
        let risk = match event.risk_value {
            Some(v) => v,
            None => 0,
        };
        let candidate = (event.day, event.event_id.clone(), risk);
        match picked.get(&image_id) {
            None => {
                picked.insert(image_id, candidate);
            }
            Some((day, event_id, _)) => {
                if candidate.0 > *day || (candidate.0 == *day && candidate.1 < *event_id) {
                    picked.insert(image_id, candidate);
                }
            }
        }
    }
    picked
}

fn pick_latest_force_allow(active: &[Incident]) -> HashMap<String, (i64, String)> {
    let mut picked: HashMap<String, (i64, String)> = HashMap::new();
    for event in active {
        if event.kind != "force_allow" {
            continue;
        }
        let image_id = match &event.image_id {
            Some(v) => v.clone(),
            None => continue,
        };
        let candidate = (event.day, event.event_id.clone());
        match picked.get(&image_id) {
            None => {
                picked.insert(image_id, candidate);
            }
            Some((day, event_id)) => {
                if candidate.0 > *day || (candidate.0 == *day && candidate.1 < *event_id) {
                    picked.insert(image_id, candidate);
                }
            }
        }
    }
    picked
}

fn main() {
    let data_dir = PathBuf::from(env::var("ITR_DATA_DIR").unwrap_or_else(|_| "/app/registry".to_string()));
    let out_dir = PathBuf::from(env::var("ITR_OUTPUT_DIR").unwrap_or_else(|_| "/app/audit".to_string()));
    fs::create_dir_all(&out_dir).expect("failed to create output dir");

    let policy: Policy = read_json(&data_dir.join("policy.json"));
    let pool: PoolState = read_json(&data_dir.join("pool_state.json"));
    let incidents: Vec<Incident> = read_json(&data_dir.join("incident_log.json"));

    let mut keys: Vec<Key> = Vec::new();
    for entry in fs::read_dir(data_dir.join("keys")).expect("missing keys dir") {
        let path = entry.expect("bad keys dir entry").path();
        if path.extension().and_then(|s| s.to_str()) == Some("json") {
            keys.push(read_json(&path));
        }
    }
    keys.sort_by(|a, b| a.key_id.cmp(&b.key_id));

    let mut services: Vec<Service> = Vec::new();
    for entry in fs::read_dir(data_dir.join("services")).expect("missing services dir") {
        let path = entry.expect("bad services dir entry").path();
        if path.extension().and_then(|s| s.to_str()) == Some("json") {
            services.push(read_json(&path));
        }
    }
    services.sort_by(|a, b| a.service_id.cmp(&b.service_id));

    let mut images: Vec<Image> = Vec::new();
    for entry in fs::read_dir(data_dir.join("images")).expect("missing images dir") {
        let path = entry.expect("bad images dir entry").path();
        if path.extension().and_then(|s| s.to_str()) == Some("json") {
            images.push(read_json(&path));
        }
    }
    images.sort_by(|a, b| a.image_id.cmp(&b.image_id));

    let active_incidents: Vec<Incident> = incidents
        .into_iter()
        .filter(|e| e.accepted && e.day <= pool.current_day)
        .collect();

    let compromised_keys: BTreeSet<String> = active_incidents
        .iter()
        .filter(|e| e.kind == "key_compromise")
        .filter_map(|e| e.key_id.clone())
        .collect();

    let picked_risk = pick_latest_event(&active_incidents, "risk_override");
    let force_allow_events = pick_latest_force_allow(&active_incidents);

    let key_map: HashMap<String, Key> = keys
        .iter()
        .cloned()
        .map(|k| (k.key_id.clone(), k))
        .collect();
    let service_map: HashMap<String, Service> = services
        .iter()
        .cloned()
        .map(|s| (s.service_id.clone(), s))
        .collect();

    let mut signature_rows: Vec<SignatureAuditRow> = Vec::new();
    let mut sig_status_by_image: HashMap<String, String> = HashMap::new();
    let mut computed_risk_by_image: HashMap<String, i64> = HashMap::new();
    let mut service_lockdown: BTreeSet<String> = BTreeSet::new();

    for image in &images {
        let service = service_map
            .get(&image.service_id)
            .unwrap_or_else(|| panic!("missing service {}", image.service_id));
        let allowed_tiers = policy
            .trusted_tiers_by_env
            .get(&service.environment)
            .unwrap_or_else(|| panic!("missing tier policy for {}", service.environment));
        let min_required = *policy
            .min_signatures_by_env
            .get(&service.environment)
            .unwrap_or_else(|| panic!("missing min signatures policy for {}", service.environment));

        let mut trusted_count = 0_i64;
        let mut expired_keys: Vec<String> = Vec::new();
        let mut compromised_signers: Vec<String> = Vec::new();

        for key_id in &image.signatures {
            if compromised_keys.contains(key_id) {
                compromised_signers.push(key_id.clone());
            }
            if let Some(key) = key_map.get(key_id) {
                if key.expires_day < pool.current_day {
                    expired_keys.push(key_id.clone());
                    continue;
                }
                if allowed_tiers.iter().any(|t| t == &key.trust_tier) {
                    trusted_count += 1;
                }
            }
        }

        expired_keys.sort();
        compromised_signers.sort();
        compromised_signers.dedup();

        let signature_status = if !compromised_signers.is_empty() {
            "compromised".to_string()
        } else if trusted_count < min_required {
            "insufficient".to_string()
        } else {
            "valid".to_string()
        };

        if signature_status == "compromised" {
            service_lockdown.insert(service.service_id.clone());
        }

        let mut computed_risk = image.base_risk;
        if let Some((_, _, override_risk)) = picked_risk.get(&image.image_id) {
            computed_risk = *override_risk;
        }
        if signature_status == "insufficient" {
            computed_risk += policy.insufficient_signature_penalty;
        }
        if signature_status == "compromised" {
            computed_risk += policy.compromised_signature_penalty;
        }

        sig_status_by_image.insert(image.image_id.clone(), signature_status.clone());
        computed_risk_by_image.insert(image.image_id.clone(), computed_risk);
        signature_rows.push(SignatureAuditRow {
            image_id: image.image_id.clone(),
            service_id: image.service_id.clone(),
            trusted_signature_count: trusted_count,
            minimum_required_signatures: min_required,
            expired_signing_keys: expired_keys,
            compromised_signing_keys: compromised_signers,
            signature_status,
        });
    }
    signature_rows.sort_by(|a, b| a.image_id.cmp(&b.image_id));

    let mut gate_rows: Vec<DeploymentGateRow> = Vec::new();
    for image in &images {
        let service = service_map
            .get(&image.service_id)
            .unwrap_or_else(|| panic!("missing service {}", image.service_id));
        let signature_status = sig_status_by_image
            .get(&image.image_id)
            .cloned()
            .unwrap_or_else(|| panic!("missing signature status {}", image.image_id));
        let computed_risk = *computed_risk_by_image
            .get(&image.image_id)
            .unwrap_or_else(|| panic!("missing computed risk {}", image.image_id));

        let force_allow_active = force_allow_events.contains_key(&image.image_id);
        let force_allow_valid = force_allow_active && computed_risk < policy.emergency_freeze_risk_threshold;
        let in_lockdown = service_lockdown.contains(&service.service_id);

        let decision = if signature_status == "compromised" {
            "block_compromised".to_string()
        } else if in_lockdown && !force_allow_valid {
            "block_service_lockdown".to_string()
        } else if force_allow_valid {
            "allow_force".to_string()
        } else if computed_risk > service.max_risk_allowed {
            "block_risk".to_string()
        } else {
            "allow".to_string()
        };

        gate_rows.push(DeploymentGateRow {
            image_id: image.image_id.clone(),
            service_id: image.service_id.clone(),
            computed_risk,
            max_risk_allowed: service.max_risk_allowed,
            force_allow_active,
            decision,
        });
    }
    gate_rows.sort_by(|a, b| a.image_id.cmp(&b.image_id));

    let mut key_exposure_rows: Vec<KeyExposureRow> = Vec::new();
    for key in &keys {
        let impacted: Vec<&Image> = images
            .iter()
            .filter(|img| img.signatures.iter().any(|k| k == &key.key_id))
            .collect();
        let mut impacted_ids: Vec<String> = impacted.iter().map(|img| img.image_id.clone()).collect();
        impacted_ids.sort();
        let compromised_count = impacted
            .iter()
            .filter(|img| sig_status_by_image.get(&img.image_id).map(|s| s == "compromised").unwrap_or(false))
            .count() as i64;
        let status = if compromised_keys.contains(&key.key_id) {
            "compromised".to_string()
        } else if key.expires_day < pool.current_day {
            "expired".to_string()
        } else {
            "clean".to_string()
        };
        key_exposure_rows.push(KeyExposureRow {
            key_id: key.key_id.clone(),
            status,
            signed_image_count: impacted_ids.len() as i64,
            compromised_image_count: compromised_count,
            impacted_images: impacted_ids,
        });
    }
    key_exposure_rows.sort_by(|a, b| a.key_id.cmp(&b.key_id));

    let mut quarantine_rows: Vec<QuarantineRow> = Vec::new();
    for service in &services {
        let image_ids: Vec<String> = images
            .iter()
            .filter(|img| img.service_id == service.service_id)
            .map(|img| img.image_id.clone())
            .collect();
        let mut blocked: Vec<String> = Vec::new();
        let mut review: Vec<String> = Vec::new();
        for row in gate_rows.iter().filter(|row| row.service_id == service.service_id) {
            if row.decision.starts_with("block_") {
                blocked.push(row.image_id.clone());
            }
            if row.decision == "allow_force" {
                review.push(row.image_id.clone());
            }
        }
        blocked.sort();
        review.sort();

        let status = if service_lockdown.contains(&service.service_id) {
            "lockdown".to_string()
        } else if gate_rows.iter().any(|row| row.service_id == service.service_id && row.decision == "block_risk") {
            "monitor".to_string()
        } else {
            "clear".to_string()
        };

        let _ = image_ids;
        quarantine_rows.push(QuarantineRow {
            service_id: service.service_id.clone(),
            status,
            blocked_images: blocked,
            review_images: review,
        });
    }
    quarantine_rows.sort_by(|a, b| a.service_id.cmp(&b.service_id));

    let mut decision_counts: BTreeMap<String, i64> = BTreeMap::new();
    for row in &gate_rows {
        *decision_counts.entry(row.decision.clone()).or_insert(0) += 1;
    }

    let mut signature_status_counts: BTreeMap<String, i64> = BTreeMap::new();
    for row in &signature_rows {
        *signature_status_counts.entry(row.signature_status.clone()).or_insert(0) += 1;
    }

    let services_lockdown = quarantine_rows.iter().filter(|r| r.status == "lockdown").count() as i64;
    let services_monitor = quarantine_rows.iter().filter(|r| r.status == "monitor").count() as i64;
    let services_clear = quarantine_rows.iter().filter(|r| r.status == "clear").count() as i64;
    let force_allow_applied = gate_rows.iter().filter(|r| r.decision == "allow_force").count() as i64;

    let summary = Summary {
        total_images: images.len() as i64,
        services_lockdown,
        services_monitor,
        services_clear,
        decision_counts,
        signature_status_counts,
        compromised_keys: compromised_keys.len() as i64,
        force_allow_applied,
    };

    write_json(&out_dir.join("signature_audit.json"), &signature_rows);
    write_json(&out_dir.join("deployment_gate.json"), &gate_rows);
    write_json(&out_dir.join("key_exposure.json"), &key_exposure_rows);
    write_json(&out_dir.join("quarantine_plan.json"), &quarantine_rows);
    write_json(&out_dir.join("summary.json"), &summary);
}
RS

cd /app/planner
cargo build --quiet --release
cp /app/planner/target/release/image_trust_rollout_auditor /app/bin/trust-auditor
ITR_DATA_DIR="${ITR_DATA_DIR:-/app/registry}" ITR_OUTPUT_DIR="${ITR_OUTPUT_DIR:-/app/audit}" /app/bin/trust-auditor
