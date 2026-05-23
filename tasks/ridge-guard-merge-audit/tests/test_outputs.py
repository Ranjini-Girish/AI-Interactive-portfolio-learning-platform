# scaffold-status: oracle-pending
"""Verifier suite for ridge-guard-merge-audit (hard, Java-authored stack)."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest

DATA_DIR = Path(os.environ.get("RGMA_DATA_DIR", "/app/rgma_lab"))
AUDIT_DIR = Path(os.environ.get("RGMA_AUDIT_DIR", "/app/audit"))
BUILD_DIR = Path("/app/build")
GSON_CP = "/opt/gson.jar"

OUTPUT_FILES = ["ridge_report.json", "summary.json"]

EXPECTED_INPUT_HASHES = {
    "SPEC.md": "39badb148bbdb4ab3090f31d71c67c83ef545ba35b1edc94078936b1a792d64b",
    "anchors/day_floor.json": "033009a00107f3d7feeb8ee3fe60d8357877d2f24b218a23b4b2c9be63b29d70",
    "anchors/window.json": "e0e4369b966b519d90ba68ff507afd0cf2cd7a64bf0c27d3d9675f34be8390e7",
    "ancillary/meta.json": "6ab66447fdf3b5aef47ebce5b79e7e888ab0ffd7f8c6e464d8f233ccdc1cb752",
    "ancillary/notes.json": "754c4df8f98fd2672eb62a12fb77b047ad70c49b9637aadeedfc1e6e05e6c278",
    "domain_layout.json": "e04b2738c38a8c805f8fccd31b38de7cd4641cc8868230f6675a5af6eab779c9",
    "hosts/h00.json": "2d521d68d19f78c9d50538cdba02a278559691197f898de6a5db73e00692cf25",
    "hosts/h01.json": "cb2bccf2fb52be50cb69426acba6453441994246f2deb55746cfb66b82cd6925",
    "hosts/h02.json": "7674cef1e21e0a7abb955e201ff367c4796ae3bc9eac2de5f0078548fadf70e8",
    "hosts/h03.json": "036eba712e0d8aaefa5a56f60386b2478d94fc7806e93c08bfc084b1d90ec07a",
    "hosts/h04.json": "3302f2cdbaf44ec7b31e994b374c242d1a97bd765b2e12b2417d0a4710dff2bc",
    "hosts/h05.json": "f4fc0256fa7b8ec179d8cc5c478b01ba04d29b5815be5bfe4df387bf668805c6",
    "hosts/h06.json": "d4becaa8b8a3d8dc6647c72a24a77705bcc0f44f6122982571196d7e30fddf63",
    "hosts/h07.json": "6d33f002c7f360b9f21ee3f6bad4ef1cdde249d6a88d95c4fb585e54c8c68bad",
    "hosts/h08.json": "d1d92ef761449313b2620a2cae36cd24a047b855041e7bac65a0bab90f71e38e",
    "hosts/h09.json": "e34fdfd47a39b669d152a6c8d21f02ac72c787044fa69795bbccb6ea2b6a0c4b",
    "hosts/h10.json": "f6428f792c13e8da4e5e8387a5840d7da45bf8f2bff750282f67a542416a528c",
    "hosts/h11.json": "e8dd8d8a12cb312e1e946636e7c323e5aa78096d431b4439372eb1b643e4fb0c",
    "incident_log.json": "d95bc072716230e458a11f371f07d0ed179e1fedfe163ee31a38846811854ecc",
    "policy.json": "6a32eb3dfc316712fe7d719fa2d3bfd9d7949b3333ab6cc66cfd2cb1b1e58c13",
    "pool_state.json": "f15f7075b8f3c07263032cdd054017fb2032bf6a496f2edad4d33b5623f59c9b",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "ridge_report.json": "7adf2974f5ed12056d6f828de85aa4ea54cf5b371d3d2786a7b0f776457a5ad2",
    "summary.json": "8c4a7cffccce86397d569b94e617384204cadefa9511e2cd0b5bccb0d4ae27b9",
}

EXPECTED_FIELD_HASHES = {
    "ridge_report.json.anchor_factor": "dd024733e8e4a8a7c7837a72855fd7a61db0a20ef0f706d3b6588a958f2fa735",
    "ridge_report.json.entries": "c6811e524bfbb220a980445cd0b56f73a30821a32da1f297d13079b8c66213a6",
    "ridge_report.json.schema_version": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.json.anchor_overlap_days": "4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a",
    "summary.json.entries_total": "6b51d431df5d7f141cbececcf79edf3dd861c3b4069f0b11661a3eefacbba918",
    "summary.json.frozen_total": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.json.lambda_cap_micro": "5826ecc4d11e82b52e711bc41978052483102366d2b36e1a61831880d8fe2c00",
    "summary.json.merged_groups": "4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce",
    "summary.json.schema_version": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
}


def _java_cmd(data_dir: Path, out_dir: Path) -> list[str]:
    """Build argv for invoking the Java audit entrypoint."""
    return [
        "java",
        "-cp",
        f"{BUILD_DIR}:{GSON_CP}",
        "RgmaAudit",
        str(data_dir),
        str(out_dir),
    ]


def _java_class_ready() -> bool:
    """True when the compiled Java class for the audit entrypoint exists."""
    return (BUILD_DIR / "RgmaAudit.class").is_file()


def _sha256_bytes(data: bytes) -> str:
    """Return the lowercase hex SHA-256 digest for bytes."""
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    """Serialize using the verifier's canonical minified JSON."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _load_json(path: Path) -> object:
    """Parse UTF-8 JSON from disk."""
    return json.loads(path.read_text(encoding="utf-8"))


def _micro_from_scaled(s: float) -> int:
    """Scale a float to microlambda using SPEC decimal rules."""
    s_str = format(float(s), ".17g")
    d = Decimal(s_str)
    return int((d * Decimal("1000000")).to_integral_value(rounding=ROUND_HALF_EVEN))


def _micro_from_cap(cap: float) -> int:
    """Convert the policy cap float to integer microlambda."""
    cap_str = format(float(cap), ".17g")
    d = Decimal(cap_str)
    return int((d * Decimal("1000000")).to_integral_value(rounding=ROUND_HALF_EVEN))


class _Dsu:
    """Disjoint-set union for alias ridge components."""

    def __init__(self) -> None:
        """Create an empty parent map."""
        self.parent: Dict[str, str] = {}

    def make_set(self, x: str) -> None:
        """Ensure x is present as its own set root."""
        self.parent.setdefault(x, x)

    def find(self, x: str) -> str:
        """Return the representative id for x with path compression."""
        self.parent.setdefault(x, x)
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, a: str, b: str) -> None:
        """Merge the sets containing a and b."""
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def _compute_reference(base: Path) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Re-derive ridge_report and summary objects from a lab directory tree."""
    policy = json.loads((base / "policy.json").read_text(encoding="utf-8"))
    layout = json.loads((base / "domain_layout.json").read_text(encoding="utf-8"))
    pool = json.loads((base / "pool_state.json").read_text(encoding="utf-8"))
    incidents_raw = json.loads((base / "incident_log.json").read_text(encoding="utf-8"))
    window = json.loads((base / "anchors" / "window.json").read_text(encoding="utf-8"))
    day_floor = json.loads((base / "anchors" / "day_floor.json").read_text(encoding="utf-8"))
    meta = json.loads((base / "ancillary" / "meta.json").read_text(encoding="utf-8"))

    if not isinstance(policy, dict) or not isinstance(layout, dict):
        raise ValueError("bad policy or layout")
    if not isinstance(pool, dict) or not isinstance(pool.get("revision"), str):
        raise ValueError("bad pool")
    if not isinstance(incidents_raw, list):
        raise ValueError("bad incidents")
    if not isinstance(window, dict) or not isinstance(meta, dict):
        raise ValueError("bad window or meta")
    if not isinstance(day_floor, dict):
        raise ValueError("bad day_floor")

    tiers = policy["tiers"]
    day_start = int(policy["day_start"])
    day_end = int(policy["day_end"])
    floor_day = int(day_floor["floor_day"])
    d0 = max(day_start, floor_day)
    d1 = day_end
    if d1 < d0:
        raise ValueError("invalid effective day window after floor")
    anchor_start = int(window["start"])
    anchor_end = int(window["end"])
    alias_guard = bool(policy["alias_guard"])
    signal_cutoff = float(policy["signal_cutoff"])
    lambda_cap = float(policy["lambda_cap"])

    overlap_low = max(d0, anchor_start)
    overlap_high = min(d1, anchor_end)
    overlap_days = max(0, overlap_high - overlap_low + 1) if overlap_high >= overlap_low else 0
    k = min(overlap_days, 5)
    f_anchor = 1.0 + 0.01 * k
    anchor_factor = float(f"{f_anchor:.12f}")

    hosts: Dict[str, Dict[str, Any]] = {}
    host_dir = base / "hosts"
    for path in sorted(host_dir.glob("*.json")):
        rec = json.loads(path.read_text(encoding="utf-8"))
        hid = str(rec["host_id"])
        hosts[hid] = {
            "tier": rec["tier"],
            "raw_lambda": float(rec["raw_lambda"]),
            "bias_signal": float(rec["bias_signal"]),
            "frozen": False,
        }

    expected_ids = {str(x) for x in layout["hosts"]}
    if set(hosts.keys()) != expected_ids:
        raise ValueError("host set mismatch")

    def _inc_key(inc: Dict[str, Any]) -> Tuple[int, str, str, str]:
        hid = inc.get("host_id", "")
        if not isinstance(hid, str):
            hid = ""
        canon = json.dumps(inc, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        return (int(inc["seq"]), str(inc["kind"]), hid, canon)

    for inc in sorted(incidents_raw, key=_inc_key):
        kind = inc["kind"]
        hid = inc.get("host_id")
        if kind == "bump_lambda":
            if not isinstance(hid, str) or hid not in hosts or hosts[hid]["frozen"]:
                continue
            hosts[hid]["raw_lambda"] = float(hosts[hid]["raw_lambda"]) + float(inc["delta"])
        elif kind == "freeze_host":
            if isinstance(hid, str) and hid in hosts:
                hosts[hid]["frozen"] = True
        elif kind == "lift_freeze":
            if isinstance(hid, str) and hid in hosts:
                hosts[hid]["frozen"] = False
        else:
            raise ValueError("unknown incident kind")

    cap_micro = _micro_from_cap(lambda_cap)

    micros: Dict[str, Optional[int]] = {}
    entries: List[Dict[str, Any]] = []
    frozen_total = 0

    for hid in sorted(hosts.keys()):
        st = hosts[hid]
        if st["frozen"]:
            frozen_total += 1
            micros[hid] = None
            entries.append(
                {
                    "bias_class": "frozen",
                    "host_id": hid,
                    "microlambda": None,
                    "tier": st["tier"],
                }
            )
            continue
        tier = str(st["tier"])
        raw_lambda = float(st["raw_lambda"])
        tier_scale = float(tiers[tier])
        s = raw_lambda * tier_scale * anchor_factor
        m = _micro_from_scaled(s)
        micros[hid] = m
        bias = float(st["bias_signal"])
        if bias > signal_cutoff:
            bclass = "high"
        elif bias < -signal_cutoff:
            bclass = "low"
        else:
            bclass = "mid"
        entries.append(
            {
                "bias_class": bclass,
                "host_id": hid,
                "microlambda": m,
                "tier": tier,
            }
        )

    merged_groups = 0
    if alias_guard:
        groups = meta["alias_groups"]
        for group in groups:
            live = [h for h in group if h in hosts and not hosts[h]["frozen"]]
            if len(live) >= 2:
                merged_groups += 1

        dsu = _Dsu()
        for hid in hosts:
            if not hosts[hid]["frozen"]:
                dsu.make_set(hid)
        for group in groups:
            live = [h for h in group if h in hosts and not hosts[h]["frozen"]]
            if len(live) < 2:
                continue
            base_id = live[0]
            for h in live[1:]:
                dsu.union(base_id, h)

        comp_max: Dict[str, int] = {}
        for hid in hosts:
            if hosts[hid]["frozen"] or micros[hid] is None:
                continue
            r = dsu.find(hid)
            m = int(micros[hid])
            comp_max[r] = max(comp_max.get(r, m), m)

        comp_sz: Dict[str, int] = {}
        for hid in hosts:
            if hosts[hid]["frozen"]:
                continue
            r = dsu.find(hid)
            comp_sz[r] = comp_sz.get(r, 0) + 1

        for hid in hosts:
            if hosts[hid]["frozen"] or micros[hid] is None:
                continue
            r = dsu.find(hid)
            if comp_sz.get(r, 0) >= 2:
                micros[hid] = comp_max[r]

        for ent in entries:
            hid = str(ent["host_id"])
            if ent["microlambda"] is None:
                continue
            ent["microlambda"] = micros[hid]

    for ent in entries:
        if ent["microlambda"] is None:
            continue
        ent["microlambda"] = min(int(ent["microlambda"]), cap_micro)

    report = {
        "anchor_factor": anchor_factor,
        "entries": entries,
        "schema_version": 1,
    }
    summary = {
        "anchor_overlap_days": overlap_days,
        "entries_total": len(hosts),
        "frozen_total": frozen_total,
        "lambda_cap_micro": cap_micro,
        "merged_groups": merged_groups,
        "schema_version": 1,
    }
    return report, summary


@pytest.fixture(scope="session")
def outputs() -> dict[str, object]:
    """Load emitted audit artifacts once per session."""
    payload: dict[str, object] = {}
    for name in OUTPUT_FILES:
        path = AUDIT_DIR / name
        assert path.is_file(), f"missing emitted artifact: {name}"
        payload[name] = _load_json(path)
    return payload


@pytest.fixture(scope="session")
def entries_by_host(outputs: dict[str, object]) -> dict[str, dict[str, object]]:
    """Index ridge report entries by host id."""
    report = outputs["ridge_report.json"]
    assert isinstance(report, dict)
    raw_entries = report["entries"]
    assert isinstance(raw_entries, list)
    out: dict[str, dict[str, object]] = {}
    for ent in raw_entries:
        assert isinstance(ent, dict)
        hid = str(ent["host_id"])
        out[hid] = ent
    return out


@pytest.fixture(scope="session")
def expected_bundle() -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Independent reference structures rebuilt from the bundled lab tree."""
    return _compute_reference(DATA_DIR)


class TestInputIntegrity:
    """Pinned fixture bytes."""

    def test_each_input_file_sha256(self) -> None:
        """Every input file under the domain directory matches its digest."""
        for rel, expected in EXPECTED_INPUT_HASHES.items():
            path = DATA_DIR / rel
            assert path.is_file(), f"missing input fixture: {rel}"
            digest = _sha256_bytes(path.read_bytes())
            assert digest == expected, f"digest mismatch for {rel}"

    def test_witness_pool_state_unchanged(self) -> None:
        """pool_state.json bytes match the pinned witness digest."""
        path = DATA_DIR / "pool_state.json"
        digest = _sha256_bytes(path.read_bytes())
        assert digest == EXPECTED_INPUT_HASHES["pool_state.json"]

    def test_witness_domain_layout_unchanged(self) -> None:
        """domain_layout.json bytes match the pinned witness digest."""
        path = DATA_DIR / "domain_layout.json"
        digest = _sha256_bytes(path.read_bytes())
        assert digest == EXPECTED_INPUT_HASHES["domain_layout.json"]


class TestReportStructure:
    """Hash-locked outputs."""

    def test_output_canonical_hashes(self, outputs: dict[str, object]) -> None:
        """Each audit file matches the canonical minified JSON digest."""
        for name, expected in EXPECTED_OUTPUT_CANONICAL_HASHES.items():
            canon = _canonical(outputs[name])
            digest = _sha256_bytes(canon.encode("utf-8"))
            assert digest == expected, f"output mismatch for {name}"

    def test_field_hashes(self, outputs: dict[str, object]) -> None:
        """Nested summaries remain stable."""
        for field, expected in EXPECTED_FIELD_HASHES.items():
            head, sep, rest = field.partition(".json.")
            assert sep, f"bad field hash key: {field}"
            fname = head + ".json"
            key = rest.lstrip(".")
            obj = outputs[fname]
            assert isinstance(obj, dict)
            fragment = obj[key]
            digest = _sha256_bytes(_canonical(fragment).encode("utf-8"))
            assert digest == expected, f"field mismatch for {field}"


class TestBiasClasses:
    """Enum coverage for bias_class."""

    def test_dataset_has_high_bias_class(self, entries_by_host: dict[str, dict[str, object]]) -> None:
        """At least one host is classified as high bias under the bundled policy."""
        assert entries_by_host["h01"]["bias_class"] == "high"

    def test_dataset_has_low_bias_class(self, entries_by_host: dict[str, dict[str, object]]) -> None:
        """At least one host is classified as low bias under the bundled policy."""
        assert entries_by_host["h03"]["bias_class"] == "low"

    def test_dataset_has_mid_bias_class(self, entries_by_host: dict[str, dict[str, object]]) -> None:
        """At least one host is classified as mid bias under the bundled policy."""
        assert entries_by_host["h00"]["bias_class"] == "mid"

    def test_dataset_has_frozen_bias_class(self, entries_by_host: dict[str, dict[str, object]]) -> None:
        """Frozen hosts surface as frozen with null microlambda."""
        ent = entries_by_host["h02"]
        assert ent["bias_class"] == "frozen"
        assert ent["microlambda"] is None


class TestSummarySemantics:
    """Structural checks aligned with the bundled fixture."""

    def test_summary_anchor_overlap_matches_report_factor(self, outputs: dict[str, object]) -> None:
        """Overlap days and anchor factor match the bundled policy, window anchor, and day-floor clip."""
        summary = outputs["summary.json"]
        assert isinstance(summary, dict)
        assert summary["anchor_overlap_days"] == 4
        report = outputs["ridge_report.json"]
        assert isinstance(report, dict)
        assert report["anchor_factor"] == 1.04

    def test_summary_counts_merged_alias_rows(self, outputs: dict[str, object]) -> None:
        """Three alias rows qualify under the bundled policy with guard enabled."""
        summary = outputs["summary.json"]
        assert isinstance(summary, dict)
        assert summary["merged_groups"] == 3

    def test_alias_merge_lifted_cap_on_gold_pair(self, entries_by_host: dict[str, dict[str, object]]) -> None:
        """Merged gold hosts share the capped microlambda after alias merge."""
        assert entries_by_host["h04"]["microlambda"] == 480000
        assert entries_by_host["h05"]["microlambda"] == 480000

    def test_alias_ridge_propagates_across_linked_silver_hosts(
        self, entries_by_host: dict[str, dict[str, object]]
    ) -> None:
        """Silver hosts linked through overlapping alias rows share one microlambda under the clipped anchor."""
        m1 = entries_by_host["h01"]["microlambda"]
        m3 = entries_by_host["h03"]["microlambda"]
        m6 = entries_by_host["h06"]["microlambda"]
        assert m1 == m3 == m6 == 354640


class TestBinaryContract:
    """CLI and isolation checks for the release binary when it exists."""

    def test_binary_rejects_wrong_arg_count(self, tmp_path: Path) -> None:
        """The program exits non-zero unless exactly two lab paths follow the class name."""
        if not _java_class_ready():
            pytest.skip("compiled Java class not built yet")
        out = tmp_path / "o"
        out.mkdir()
        base_cp = f"{BUILD_DIR}:{GSON_CP}"
        r0 = subprocess.run(["java", "-cp", base_cp, "RgmaAudit"], capture_output=True, text=True, timeout=60)
        r1 = subprocess.run(
            ["java", "-cp", base_cp, "RgmaAudit", str(DATA_DIR)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        r3 = subprocess.run(
            ["java", "-cp", base_cp, "RgmaAudit", str(DATA_DIR), str(out), str(out)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert r0.returncode != 0
        assert r1.returncode != 0
        assert r3.returncode != 0

    def test_binary_writes_only_into_argv_audit_dir(self, tmp_path: Path) -> None:
        """Outputs land in the directory passed as the second argument, not the default audit path."""
        if not _java_class_ready():
            pytest.skip("compiled Java class not built yet")
        out_dir = tmp_path / "argv_out"
        out_dir.mkdir()
        for name in OUTPUT_FILES:
            p = out_dir / name
            if p.is_file():
                p.unlink()
        res = subprocess.run(
            _java_cmd(DATA_DIR, out_dir),
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert res.returncode == 0, res.stderr
        for name in OUTPUT_FILES:
            assert (out_dir / name).is_file()

    def test_binary_output_matches_independent_reference(
        self, tmp_path: Path, expected_bundle: Tuple[Dict[str, Any], Dict[str, Any]]
    ) -> None:
        """Parsed JSON from a fresh argv run matches the in-test recomputation."""
        if not _java_class_ready():
            pytest.skip("compiled Java class not built yet")
        out_dir = tmp_path / "cmp_out"
        out_dir.mkdir()
        res = subprocess.run(
            _java_cmd(DATA_DIR, out_dir),
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert res.returncode == 0, res.stderr
        er, es = expected_bundle
        got_r = _load_json(out_dir / "ridge_report.json")
        got_s = _load_json(out_dir / "summary.json")
        assert got_r == er
        assert got_s == es


class TestReferenceSanity:
    """Cross-check that the in-test recomputation tracks the bundled hashes."""

    def test_reference_matches_output_hashes(
        self, expected_bundle: Tuple[Dict[str, Any], Dict[str, Any]]
    ) -> None:
        """The recomputed objects minify to the same digests as the emitted audit files."""
        er, es = expected_bundle
        assert _sha256_bytes(_canonical(er).encode("utf-8")) == EXPECTED_OUTPUT_CANONICAL_HASHES["ridge_report.json"]
        assert _sha256_bytes(_canonical(es).encode("utf-8")) == EXPECTED_OUTPUT_CANONICAL_HASHES["summary.json"]
