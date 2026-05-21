"""Verifier suite for the io-credit-window-audit task."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("IOC_DATA_DIR", "/app/ioc_lab"))
AUDIT_DIR = Path(os.environ.get("IOC_AUDIT_DIR", "/app/audit"))

OUTPUT_FILE = "report.json"

EXPECTED_INPUT_HASHES = {
    "SPEC.md": "9887aec07e5dad3800414b61af484992143704fbc01b22d1a69b9b5a4ddb78d3",
    "devices.json": "ec8554bc954a9f7ce30b97b879d3ca440f782f924819be47b9256a44ed1a8007",
    "incidents.json": "20aebcbb912b7fa493b4b2dc0cc529e3cfad8f5fc3a68140407062d714f9610a",
    "loads/01.json": "e27c93481170c8eff4e7be9a97c367adbd84a5b4ab5a77f013a06c8ada3ff1c3",
    "loads/02.json": "acb61cabf811d12f6c79fea7de50ab83ecacb23d07b15556727829a084a7a32e",
    "loads/03.json": "eaf76f3328be3cb1a790c850183d30f61a213a8103e65612f8fd49656e9b3f36",
    "loads/04.json": "816fa7da9e8257338d870a9d0655e04e3a61c04ab3024b6822d02ceac910ad6d",
    "loads/05.json": "770c17d495ee49431c7f8fa5a1bc84f5449d50eb8f13e771c580dc4fdac5ba58",
    "loads/06.json": "95f3104ddfe84d43ed157b48840cd9312a3f2450d967bf3dcf0c915e2e5e9dc9",
    "loads/07.json": "51f03e9e4752a00d33cb40f417e2923b3af4bcbb8f8a984b8022677da5036538",
    "loads/08.json": "81f17c622dd02b7ec89cafdc7af4a7008895924449c9a3ac2633a2619b2f2477",
    "loads/09.json": "fce8c4a2ad9b178ef5550128a253a1e418f3d9c9e80c387941a58ef86cc179cd",
    "loads/10.json": "890c57d7cc5c1c6238acee19da82d7f472a67eb1a27485db4f915a1a866e61fe",
    "loads/11.json": "ba9e7cc4b34f4f95820bcb31074ac34767cf27f38439dc9e7ced82f6e9702433",
    "loads/12.json": "c4f208aa0bae950861061aaf45e28b7074be3fab9f5331eb96e1a9196d4a8b1c",
    "loads/13.json": "0d1d47b323f1a2b53536576f6657e31aaf704376343b589899fca2c48fba0f95",
    "loads/14.json": "76c825fa2a08c832f5d1e6a4ed91d9271f0e2933f34fb585eadb268d0c993a68",
    "loads/15.json": "e8f6f05586d8cdbd99840c0a7a35e5aa2345a4dabe02df7a3edc4b780e0d10e6",
    "loads/16.json": "ed4895d7c5660a516b16a7c195b50faf10c4957e6d3f017ef7fac287e3a72285",
    "loads/17.json": "e6ef198f79e818612a0d4325f991c60c35f17a945eda9bb9a5c9413c84ef82a1",
    "loads/18.json": "aff2e7d91d99d36d9dbe7e555ca636b78b5d31ef1372ccb8733d3655256a5464",
    "policy.json": "c20440be5870d084c0d043ae3ec3860c33d2b4767be54b0d4a06be2f9e6cfbf4",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "report.json": "f9351fd226751fdd741fd1ed4aba62978af52a02e8e14a66ca81f90ef1d7b21e",
}

EXPECTED_FIELD_HASHES = {
    "summary": "1e1b1c79553ba4a4ba1090f5febc80f2535a54aa51c2535f3ac12135ea7ee99d",
    "devices": "4a971d78617c911432da0d359d16e255419c239671a2aee8d733dcc149d59d26",
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _median_int(vals: list[int]) -> int:
    if not vals:
        return 0
    s = sorted(vals)
    n = len(s)
    mid = n // 2
    if n % 2:
        return s[mid]
    return (s[mid - 1] + s[mid]) // 2


def _compute_reference() -> dict[str, object]:
    """Independent re-derivation from bundled inputs and SPEC.md."""
    policy_obj = _load_json(DATA_DIR / "policy.json")
    devices = _load_json(DATA_DIR / "devices.json")
    incidents_obj = _load_json(DATA_DIR / "incidents.json")
    assert isinstance(policy_obj, dict)
    assert isinstance(devices, list)
    assert isinstance(incidents_obj, dict)

    hot_util = int(policy_obj["hot_util"])
    median_k = int(policy_obj["median_k"])
    merge_gap_tol = int(policy_obj["merge_gap_tol"])
    relief_delta = int(policy_obj["relief_delta"])
    depth_cap = float(policy_obj["depth_cap"])
    depth_per_qd = float(policy_obj["depth_per_qd"])
    h = median_k // 2
    assert median_k % 2 == 1 and median_k >= 1

    spans = incidents_obj.get("spans", [])
    assert isinstance(spans, list)

    depth_by: dict[str, int] = {}
    for row in devices:
        assert isinstance(row, dict)
        depth_by[str(row["device_id"])] = int(row["queue_depth"])

    matches = sorted((DATA_DIR / "loads").glob("*.json"))
    samples: dict[str, dict[int, int]] = {}
    for path in matches:
        obj = _load_json(path)
        assert isinstance(obj, dict)
        dev = str(obj["device_id"])
        ticks = obj.get("ticks", [])
        assert isinstance(ticks, list)
        if dev not in samples:
            samples[dev] = {}
        for te in ticks:
            assert isinstance(te, dict)
            samples[dev][int(te["t"])] = int(te["util"])

    def freeze_active(t: int) -> bool:
        for sp in spans:
            assert isinstance(sp, dict)
            if str(sp.get("kind")) != "freeze":
                continue
            if int(sp["start_t"]) <= t <= int(sp["end_t"]):
                return True
        return False

    def embargo_active(dev: str, t: int) -> bool:
        for sp in spans:
            assert isinstance(sp, dict)
            if str(sp.get("kind")) != "embargo":
                continue
            if str(sp.get("device_id")) != dev:
                continue
            if int(sp["start_t"]) <= t <= int(sp["end_t"]):
                return True
        return False

    def relief_active(dev: str, t: int) -> bool:
        for sp in spans:
            assert isinstance(sp, dict)
            if str(sp.get("kind")) != "credit_relief":
                continue
            if str(sp.get("device_id")) != dev:
                continue
            if int(sp["start_t"]) <= t <= int(sp["end_t"]):
                return True
        return False

    def thr(dev: str) -> int:
        qd = depth_by[dev]
        factor = min(depth_cap, 1.0 + qd * depth_per_qd)
        return int(math.ceil(float(hot_util) * factor))

    def smoothed(dev: str, t: int) -> int:
        m = samples.get(dev, {})
        vals = []
        for dt in range(-h, h + 1):
            if t + dt in m:
                vals.append(m[t + dt])
        return _median_int(vals)

    def would_hot(dev: str, t: int) -> bool:
        if embargo_active(dev, t):
            return False
        u = smoothed(dev, t)
        if u == 0 and not samples.get(dev):
            return False
        base = thr(dev)
        if relief_active(dev, t):
            base = max(0, base - relief_delta)
        return u >= base

    def is_hot(dev: str, t: int) -> bool:
        if freeze_active(t):
            return False
        return would_hot(dev, t)

    freeze_suppressed = 0
    relief_ticks = 0
    for row in devices:
        dev = str(row["device_id"])
        m = samples.get(dev, {})
        if not m:
            continue
        keys = sorted(m.keys())
        t_min, t_max = keys[0], keys[-1]
        for t in range(t_min, t_max + 1):
            if relief_active(dev, t):
                relief_ticks += 1
            if freeze_active(t) and would_hot(dev, t):
                freeze_suppressed += 1

    def merge_ticks(ticks: list[int], tol: int) -> list[list[int]]:
        if not ticks:
            return []
        ticks = sorted(ticks)
        out: list[list[int]] = []
        cur_s, cur_e = ticks[0], ticks[0]
        for t in ticks[1:]:
            if t <= cur_e + 1 + tol:
                if t > cur_e:
                    cur_e = t
            else:
                out.append([cur_s, cur_e])
                cur_s, cur_e = t, t
        out.append([cur_s, cur_e])
        return out

    total_hot = 0
    total_windows = 0
    v_hot = v_warm = v_cool = 0
    out_devs: list[dict[str, object]] = []
    for row in devices:
        dev = str(row["device_id"])
        m = samples.get(dev, {})
        hot_ticks: list[int] = []
        if m:
            keys = sorted(m.keys())
            t_min, t_max = keys[0], keys[-1]
            for t in range(t_min, t_max + 1):
                if is_hot(dev, t):
                    hot_ticks.append(t)
                    total_hot += 1
        windows = merge_ticks(hot_ticks, merge_gap_tol)
        total_windows += len(windows)
        verdict = "cool"
        if hot_ticks:
            verdict = "warm"
            for w in windows:
                if w[1] - w[0] + 1 >= 3:
                    verdict = "hot"
                    break
        if verdict == "hot":
            v_hot += 1
        elif verdict == "warm":
            v_warm += 1
        else:
            v_cool += 1
        out_devs.append({"device_id": dev, "hot_windows": windows, "verdict": verdict})

    out_devs.sort(key=lambda x: str(x["device_id"]))
    return {
        "summary": {
            "devices_scanned": len(devices),
            "total_hot_ticks": total_hot,
            "total_windows": total_windows,
            "verdict_hot": v_hot,
            "verdict_warm": v_warm,
            "verdict_cool": v_cool,
            "freeze_suppressed_ticks": freeze_suppressed,
            "relief_active_ticks": relief_ticks,
        },
        "devices": out_devs,
    }


class TestInputIntegrity:
    """SHA-256 gates for bundled inputs."""

    def test_spec_present(self) -> None:
        """SPEC.md must exist for the agent-facing contract."""
        assert (DATA_DIR / "SPEC.md").is_file()

    @pytest.mark.parametrize("rel_path,expected_sha", sorted(EXPECTED_INPUT_HASHES.items()))
    def test_input_hashes(self, rel_path: str, expected_sha: str) -> None:
        """Every bundled input file must match its pinned digest."""
        path = DATA_DIR / rel_path.replace("/", os.sep)
        assert path.is_file(), f"missing {rel_path}"
        digest = _sha256_bytes(path.read_bytes())
        assert digest == expected_sha, f"hash mismatch for {rel_path}"


class TestReportStructure:
    """Output path and canonical hashing."""

    def test_report_exists(self) -> None:
        """The audit report must be written next to the spec tree."""
        assert (AUDIT_DIR / OUTPUT_FILE).is_file()

    def test_report_canonical_hash(self) -> None:
        """Byte-stable semantic hash for the entire report object."""
        raw = json.loads((AUDIT_DIR / OUTPUT_FILE).read_text(encoding="utf-8"))
        digest = _sha256_bytes(_canonical(raw).encode("utf-8"))
        assert digest == EXPECTED_OUTPUT_CANONICAL_HASHES[OUTPUT_FILE]

    @pytest.mark.parametrize("field,expected_sha", sorted(EXPECTED_FIELD_HASHES.items()))
    def test_field_hashes(self, field: str, expected_sha: str) -> None:
        """Pinned hashes for summary and device tables."""
        raw = json.loads((AUDIT_DIR / OUTPUT_FILE).read_text(encoding="utf-8"))
        assert isinstance(raw, dict)
        fragment = raw[field]
        digest = _sha256_bytes(_canonical(fragment).encode("utf-8"))
        assert digest == expected_sha


class TestReferenceAgreement:
    """Cross-check disk output against the in-test reference."""

    def test_disk_matches_reference(self) -> None:
        """The authored dataset must agree with the deterministic reference."""
        ref = _compute_reference()
        disk = json.loads((AUDIT_DIR / OUTPUT_FILE).read_text(encoding="utf-8"))
        assert disk == ref


class TestSemanticCoverage:
    """Positive coverage for verdict classes and overlays."""

    def test_dataset_has_hot_verdict(self) -> None:
        """At least one device reaches the hot verdict via long windows."""
        disk = json.loads((AUDIT_DIR / OUTPUT_FILE).read_text(encoding="utf-8"))
        verdicts = {str(d["verdict"]) for d in disk["devices"]}
        assert "hot" in verdicts

    def test_dataset_has_warm_verdict(self) -> None:
        """At least one device reaches the warm verdict with short bursts only."""
        disk = json.loads((AUDIT_DIR / OUTPUT_FILE).read_text(encoding="utf-8"))
        verdicts = {str(d["verdict"]) for d in disk["devices"]}
        assert "warm" in verdicts

    def test_dataset_has_cool_verdict(self) -> None:
        """At least one device stays cool under the bundled policy."""
        disk = json.loads((AUDIT_DIR / OUTPUT_FILE).read_text(encoding="utf-8"))
        verdicts = {str(d["verdict"]) for d in disk["devices"]}
        assert "cool" in verdicts

    def test_freeze_suppressed_nonzero(self) -> None:
        """Freeze spans must suppress at least one would-be hot tick."""
        disk = json.loads((AUDIT_DIR / OUTPUT_FILE).read_text(encoding="utf-8"))
        assert int(disk["summary"]["freeze_suppressed_ticks"]) > 0

    def test_relief_ticks_nonzero(self) -> None:
        """Credit relief spans must cover at least one tick in-range."""
        disk = json.loads((AUDIT_DIR / OUTPUT_FILE).read_text(encoding="utf-8"))
        assert int(disk["summary"]["relief_active_ticks"]) > 0

    def test_embargo_splits_d3_windows(self) -> None:
        """Embargoed ticks must break d3 hot windows around the embargo span."""
        disk = json.loads((AUDIT_DIR / OUTPUT_FILE).read_text(encoding="utf-8"))
        d3 = next(d for d in disk["devices"] if d["device_id"] == "d3")
        wins = d3["hot_windows"]
        assert isinstance(wins, list)
        assert len(wins) >= 2

    def test_d4_gap_merge(self) -> None:
        """d4 uses merge_gap_tol to join separated bursts into one window."""
        disk = json.loads((AUDIT_DIR / OUTPUT_FILE).read_text(encoding="utf-8"))
        d4 = next(d for d in disk["devices"] if d["device_id"] == "d4")
        wins = d4["hot_windows"]
        assert any((w[1] - w[0] + 1) >= 4 for w in wins)
