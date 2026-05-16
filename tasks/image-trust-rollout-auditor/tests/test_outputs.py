import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path


DATA_DIR = Path(os.environ.get("ITR_DATA_DIR", "/app/registry"))
OUT_DIR = Path(os.environ.get("ITR_OUTPUT_DIR", "/app/audit"))
PLANNER_DIR = Path("/app/planner")

EXPECTED_FILES = [
    "signature_audit.json",
    "deployment_gate.json",
    "key_exposure.json",
    "quarantine_plan.json",
    "summary.json",
]

EXPECTED_INPUT_HASHES = {
    "incident_log.json": "c3d5c6b130f2522481c09d1ed42a20947cfe32da0f85ccdc98159a8a8cc31c06",
    "policy.json": "3cf93beac3e05fdc92321a5f6117908799f97451817c45740ca4c47934e6d4ff",
    "pool_state.json": "68a83509dd28fa3a4e58eff93faaef086aac9ce1f282883e7fbb85073818658c",
}

EXPECTED_FIELD_HASHES = {
    "signature_audit": "48deaefc1d0b54b25dd725defdd4f58ef1e8fbf405373bccab429b2666c76042",
    "deployment_gate": "8ac30897d2f40eb92d5fcff05d9d0533e567e0f1ce9eeac7d4f0154266c604af",
    "key_exposure": "c7cf317d91c0a7478db24891ff12adb24aeec1135e32ed954430d07873782286",
    "quarantine_plan": "d43b869d417acb0f890e50561a84a8afeb380dc1f2873b5b10ff7eb58b55354e",
    "summary": "854262437dd04fd95d46ad5e03feed871992b2b6c48aa7e90863832a86fb8876",
}


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _file_hash(path: Path) -> str:
    return _sha256_text(path.read_text(encoding="utf-8"))


def derive_expected_outputs():
    """Re-derive all expected reports directly from fixtures and spec rules."""
    policy = _read_json(DATA_DIR / "policy.json")
    pool_state = _read_json(DATA_DIR / "pool_state.json")
    incidents = _read_json(DATA_DIR / "incident_log.json")

    keys = sorted(
        [_read_json(p) for p in (DATA_DIR / "keys").glob("*.json")],
        key=lambda x: x["key_id"],
    )
    services = sorted(
        [_read_json(p) for p in (DATA_DIR / "services").glob("*.json")],
        key=lambda x: x["service_id"],
    )
    images = sorted(
        [_read_json(p) for p in (DATA_DIR / "images").glob("*.json")],
        key=lambda x: x["image_id"],
    )
    key_map = {k["key_id"]: k for k in keys}
    service_map = {s["service_id"]: s for s in services}

    current_day = pool_state["current_day"]
    active_incidents = [
        e for e in incidents if e.get("accepted") and e.get("day", 10**9) <= current_day
    ]

    compromised_keys = {
        e["key_id"]
        for e in active_incidents
        if e.get("kind") == "key_compromise" and e.get("key_id")
    }

    risk_override = {}
    force_allow = {}
    for event in active_incidents:
        if event.get("kind") == "risk_override" and event.get("image_id"):
            image_id = event["image_id"]
            candidate = (event["day"], event["event_id"], event["risk_value"])
            prior = risk_override.get(image_id)
            if prior is None or candidate[0] > prior[0] or (
                candidate[0] == prior[0] and candidate[1] < prior[1]
            ):
                risk_override[image_id] = candidate
        if event.get("kind") == "force_allow" and event.get("image_id"):
            image_id = event["image_id"]
            candidate = (event["day"], event["event_id"])
            prior = force_allow.get(image_id)
            if prior is None or candidate[0] > prior[0] or (
                candidate[0] == prior[0] and candidate[1] < prior[1]
            ):
                force_allow[image_id] = candidate

    signature_audit = []
    signature_status_by_image = {}
    computed_risk_by_image = {}
    services_lockdown = set()
    for image in images:
        service = service_map[image["service_id"]]
        allowed_tiers = set(policy["trusted_tiers_by_env"][service["environment"]])
        min_required = policy["min_signatures_by_env"][service["environment"]]

        trusted_count = 0
        expired_signing_keys = []
        compromised_signing_keys = []
        for key_id in image["signatures"]:
            if key_id in compromised_keys:
                compromised_signing_keys.append(key_id)
            key = key_map.get(key_id)
            if key is None:
                continue
            if key["expires_day"] < current_day:
                expired_signing_keys.append(key_id)
                continue
            if key["trust_tier"] in allowed_tiers:
                trusted_count += 1

        expired_signing_keys.sort()
        compromised_signing_keys = sorted(set(compromised_signing_keys))
        if compromised_signing_keys:
            signature_status = "compromised"
            services_lockdown.add(image["service_id"])
        elif trusted_count < min_required:
            signature_status = "insufficient"
        else:
            signature_status = "valid"

        computed_risk = image["base_risk"]
        if image["image_id"] in risk_override:
            computed_risk = risk_override[image["image_id"]][2]
        if signature_status == "insufficient":
            computed_risk += policy["insufficient_signature_penalty"]
        if signature_status == "compromised":
            computed_risk += policy["compromised_signature_penalty"]

        signature_status_by_image[image["image_id"]] = signature_status
        computed_risk_by_image[image["image_id"]] = computed_risk
        signature_audit.append(
            {
                "image_id": image["image_id"],
                "service_id": image["service_id"],
                "trusted_signature_count": trusted_count,
                "minimum_required_signatures": min_required,
                "expired_signing_keys": expired_signing_keys,
                "compromised_signing_keys": compromised_signing_keys,
                "signature_status": signature_status,
            }
        )

    signature_audit.sort(key=lambda x: x["image_id"])

    deployment_gate = []
    for image in images:
        service = service_map[image["service_id"]]
        computed_risk = computed_risk_by_image[image["image_id"]]
        signature_status = signature_status_by_image[image["image_id"]]
        force_allow_active = image["image_id"] in force_allow
        force_allow_valid = (
            force_allow_active
            and computed_risk < policy["emergency_freeze_risk_threshold"]
        )
        if signature_status == "compromised":
            decision = "block_compromised"
        elif image["service_id"] in services_lockdown and not force_allow_valid:
            decision = "block_service_lockdown"
        elif force_allow_valid:
            decision = "allow_force"
        elif computed_risk > service["max_risk_allowed"]:
            decision = "block_risk"
        else:
            decision = "allow"

        deployment_gate.append(
            {
                "image_id": image["image_id"],
                "service_id": image["service_id"],
                "computed_risk": computed_risk,
                "max_risk_allowed": service["max_risk_allowed"],
                "force_allow_active": force_allow_active,
                "decision": decision,
            }
        )

    deployment_gate.sort(key=lambda x: x["image_id"])

    key_exposure = []
    for key in keys:
        impacted_images = sorted(
            [image["image_id"] for image in images if key["key_id"] in image["signatures"]]
        )
        compromised_image_count = sum(
            1
            for image_id in impacted_images
            if signature_status_by_image[image_id] == "compromised"
        )
        if key["key_id"] in compromised_keys:
            key_status = "compromised"
        elif key["expires_day"] < current_day:
            key_status = "expired"
        else:
            key_status = "clean"
        key_exposure.append(
            {
                "key_id": key["key_id"],
                "status": key_status,
                "signed_image_count": len(impacted_images),
                "compromised_image_count": compromised_image_count,
                "impacted_images": impacted_images,
            }
        )

    key_exposure.sort(key=lambda x: x["key_id"])

    quarantine_plan = []
    for service in services:
        rows = [r for r in deployment_gate if r["service_id"] == service["service_id"]]
        blocked_images = sorted(
            [r["image_id"] for r in rows if r["decision"].startswith("block_")]
        )
        review_images = sorted(
            [r["image_id"] for r in rows if r["decision"] == "allow_force"]
        )
        if service["service_id"] in services_lockdown:
            status = "lockdown"
        elif any(r["decision"] == "block_risk" for r in rows):
            status = "monitor"
        else:
            status = "clear"
        quarantine_plan.append(
            {
                "service_id": service["service_id"],
                "status": status,
                "blocked_images": blocked_images,
                "review_images": review_images,
            }
        )

    summary = {
        "total_images": len(images),
        "services_lockdown": sum(1 for x in quarantine_plan if x["status"] == "lockdown"),
        "services_monitor": sum(1 for x in quarantine_plan if x["status"] == "monitor"),
        "services_clear": sum(1 for x in quarantine_plan if x["status"] == "clear"),
        "decision_counts": {
            decision: sum(1 for row in deployment_gate if row["decision"] == decision)
            for decision in sorted({row["decision"] for row in deployment_gate})
        },
        "signature_status_counts": {
            status: sum(1 for row in signature_audit if row["signature_status"] == status)
            for status in sorted({row["signature_status"] for row in signature_audit})
        },
        "compromised_keys": len(compromised_keys),
        "force_allow_applied": sum(
            1 for row in deployment_gate if row["decision"] == "allow_force"
        ),
    }

    return {
        "signature_audit": signature_audit,
        "deployment_gate": deployment_gate,
        "key_exposure": key_exposure,
        "quarantine_plan": quarantine_plan,
        "summary": summary,
    }


class TestReportPresence:
    def test_all_report_files_exist(self):
        """Every required output report exists after planner execution."""
        for filename in EXPECTED_FILES:
            assert (OUT_DIR / filename).exists(), f"Missing output file: {filename}"


class TestInputIntegrity:
    def test_input_hashes(self):
        """Input fixtures are unchanged from the task's published baseline."""
        for filename, expected_hash in EXPECTED_INPUT_HASHES.items():
            observed = _file_hash(DATA_DIR / filename)
            assert (
                observed == expected_hash
            ), f"{filename} hash mismatch: {observed} != {expected_hash}"


class TestFieldHashes:
    def test_output_field_hashes(self):
        """Each output field matches the canonical expected content hash."""
        outputs = {
            "signature_audit": _read_json(OUT_DIR / "signature_audit.json"),
            "deployment_gate": _read_json(OUT_DIR / "deployment_gate.json"),
            "key_exposure": _read_json(OUT_DIR / "key_exposure.json"),
            "quarantine_plan": _read_json(OUT_DIR / "quarantine_plan.json"),
            "summary": _read_json(OUT_DIR / "summary.json"),
        }
        for field_name, expected_hash in EXPECTED_FIELD_HASHES.items():
            observed_hash = _sha256_text(_canonical(outputs[field_name]))
            assert (
                observed_hash == expected_hash
            ), f"{field_name} hash mismatch: {observed_hash} != {expected_hash}"

    def test_outputs_match_independent_derivation(self):
        """Output data equals an independent in-test derivation from the spec."""
        expected = derive_expected_outputs()
        observed = {
            "signature_audit": _read_json(OUT_DIR / "signature_audit.json"),
            "deployment_gate": _read_json(OUT_DIR / "deployment_gate.json"),
            "key_exposure": _read_json(OUT_DIR / "key_exposure.json"),
            "quarantine_plan": _read_json(OUT_DIR / "quarantine_plan.json"),
            "summary": _read_json(OUT_DIR / "summary.json"),
        }
        assert observed == expected


class TestEnumCoverage:
    def test_signature_status_values_present(self):
        """Dataset exercises valid, insufficient, and compromised signature statuses."""
        signature_audit = _read_json(OUT_DIR / "signature_audit.json")
        values = {row["signature_status"] for row in signature_audit}
        assert values == {"valid", "insufficient", "compromised"}

    def test_deployment_decisions_values_present(self):
        """Dataset exercises allow, allow_force, block_compromised, and block_risk decisions."""
        deployment_gate = _read_json(OUT_DIR / "deployment_gate.json")
        values = {row["decision"] for row in deployment_gate}
        assert values == {"allow", "allow_force", "block_compromised", "block_risk"}

    def test_quarantine_status_values_present(self):
        """Dataset exercises clear, monitor, and lockdown service statuses."""
        quarantine_plan = _read_json(OUT_DIR / "quarantine_plan.json")
        values = {row["status"] for row in quarantine_plan}
        assert values == {"clear", "monitor", "lockdown"}

    def test_key_status_values_present(self):
        """Dataset exercises clean, expired, and compromised key statuses."""
        key_exposure = _read_json(OUT_DIR / "key_exposure.json")
        values = {row["status"] for row in key_exposure}
        assert values == {"clean", "expired", "compromised"}


class TestImplementationLanguage:
    def test_rust_source_exists(self):
        """Planner source exists and is implemented as Rust."""
        src_main = PLANNER_DIR / "src" / "main.rs"
        content = src_main.read_text(encoding="utf-8")
        assert "fn main()" in content
        assert "use " in content

    def test_compiled_binary_reproduces_outputs(self):
        """Compiled Rust binary reproduces published audit outputs byte-for-byte."""
        subprocess.run(
            ["cargo", "build", "--quiet", "--release"],
            cwd=PLANNER_DIR,
            check=True,
        )
        binary_path = PLANNER_DIR / "target" / "release" / "image_trust_rollout_auditor"
        assert binary_path.exists(), "Expected Rust release binary to be present"

        with tempfile.TemporaryDirectory() as tmp:
            tmp_out = Path(tmp) / "audit"
            tmp_out.mkdir(parents=True, exist_ok=True)
            env = os.environ.copy()
            env["ITR_DATA_DIR"] = str(DATA_DIR)
            env["ITR_OUTPUT_DIR"] = str(tmp_out)
            subprocess.run([str(binary_path)], env=env, check=True)

            for filename in EXPECTED_FILES:
                expected_hash = _file_hash(OUT_DIR / filename)
                observed_hash = _file_hash(tmp_out / filename)
                assert observed_hash == expected_hash, (
                    f"binary output mismatch for {filename}: "
                    f"{observed_hash} != {expected_hash}"
                )
