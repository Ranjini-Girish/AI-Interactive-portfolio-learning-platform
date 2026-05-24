"""Verifier suite for infer-blend-quota-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

APP_ROOT = Path("/app")
SOURCE_SUFFIXES = frozenset(
    {".c", ".cc", ".cpp", ".go", ".java", ".js", ".py", ".rs", ".sh", ".ts"}
)
_HELPER_SKIP_PARTS = frozenset({"infer_blend", "audit"})

DATA_DIR = Path(os.environ.get("IBQA_DATA_DIR", "/app/infer_blend"))
AUDIT_DIR = Path(os.environ.get("IBQA_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ("allocations.json", "pool_usage.json", "summary.json")


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "f158425f27ddec7097bcd76a73e871233897ece6f7e69a12c347e06531b0d910",
    "aux-meta.json": "010108a888b6278a35667b3d763ab5266acea0953bdffce5381886d3f5688f26",
    "aux2.json": "3b6bb4811dcb8ad72e619f5ef3e23b3ede404411cb2133ac08d92321a75e40d8",
    "incidents.json": "e9cbe5efca3aacbb1de4cd1cf49de38c6212788fafb046c836806a3007cb82d9",
    "policy.json": "6d98bc6df8e867c658e4bc87d5471f6ff31b2f3e46b8e653bc776b6631404493",
    "pools/p01.json": "0c38b552b7cd718f6aa90fc34c103d91cdf85abe8a3426c65b824bc4af126922",
    "pools/p02.json": "836825832fdeba86544089f744f289bd24520d495ad1be11fde9a4647327c397",
    "pools/p03.json": "0d3143f1e044dd22539998a0b9bb32c2931662d79a9198bb19e520363060775a",
    "pools/p04.json": "757963711e9e1b79a77792afeeec17752d4f311607f0a77e54930f89e4949f68",
    "pools/p05.json": "31611bfc4b81755b26739e6954cdc742fd099dc6055f8cd96bf00d9bed429327",
    "pools/p06.json": "54e22241b0954114435d35de521ab99e5122a4ce67ff48c52e707f99baa3da74",
    "routes/rt-a.json": "6c6ab13532fac12f06638976f927e4b981c898f66fe88a2aad587d3ca00ce7b9",
    "routes/rt-b.json": "b59326bea3d352447c87516c5439b97a15bcdce5e02d527267efda1753da6cf1",
    "routes/rt-c.json": "16e1d0307e613acc1f06c6c7e5d47e75f227311d9dff64f850de3317a4dc29fa",
    "routes/rt-d.json": "c46a37b6cc63ea20ad3869d345d1ccf3529d2e0ea9393f2a333e5f4cfeece006",
    "routes/rt-e.json": "4bfc852bf76a59ae22d761972fc79eff4fd67370fd89cd1ac8d3688a51c4f97f",
    "routes/rt-f.json": "e73b48e310640b8c55279a7bf6b888be97fb660434a3dce8797f6381298a20d7",
    "routes/rt-g.json": "328eb30735fd695878b26f159499b1dbe05c7f7f84ee63aa9ab4506b6933af33",
    "routes/rt-h.json": "17ea635b6e3db3663b65f57d0460ed99e280657f84a04780824e2f65cf457fa4",
    "routes/rt-i.json": "aed282fa7a599c189e9d36b10b43593d34b63ddccca432c3b27198fba761f5be",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "allocations.json": "6b2fbfd8be14c6ba30b09563a6788ccc730e93896aff38e1b86bb37878f045fa",
    "pool_usage.json": "f09efe391819e30a39d4ca9ab858236cded6c72465f7ed104c62a55a12ecc53d",
    "summary.json": "187c6c03063e50874ef979863fe907f6976ade7a63009c76afd47d4108479563",
}


EXPECTED_FIELD_HASHES = {
    "allocations.routes": "3188913edabeb46dbcdd5d88c5e853a98342e451783e7ab0c8406310a61dc219",
    "pool_usage.pools": "a06497124212c39138bf639e51315e4b23fb3516fe5c4507806e8258d1d1c613",
    "pool_usage.shared_groups": "12198bb7e1d91f4c71967e62c15650d67f4ac1e44039de402081e9ca48395e49",
    "summary.allocation_day": "73475cb40a568e8da8a045ced110137e159f890ac4da883b6b17dc651b3a8049",
    "summary.frozen_routes": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.groups_binding": "49eb12f85115a4b004a6588e76748e2561dcbed3604779203497b5ce89354354",
    "summary.pools_touched": "8dccf156a87b27b1090aa59732a7f60873384f350e276a53e0fa2d23f5a376e9",
    "summary.routes_processed": "19581e27de7ced00ff1ce50b2047e7a567c76b1cbaebabe5ef03f7c3017bb5b7",
    "summary.status_counts.both_shortfall": "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35",
    "summary.status_counts.canary_shortfall": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.status_counts.frozen": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.status_counts.ok": "4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a",
    "summary.status_counts.primary_shortfall": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _spec_json_bytes(value: object) -> bytes:
    """SPEC.md canonical JSON: UTF-8, two-space indent, ASCII, sorted keys, trailing newline."""
    text = json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    return text.encode("utf-8")


def _compiled_helpers_under_app() -> list[Path]:
    """ELF executables under /app/ outside the read-only data and audit trees."""
    helpers: list[Path] = []
    for path in APP_ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(APP_ROOT).parts
        if any(part in _HELPER_SKIP_PARTS for part in rel_parts):
            continue
        try:
            if path.read_bytes()[:4] != b"\x7fELF":
                continue
        except OSError:
            continue
        if os.access(path, os.X_OK):
            helpers.append(path)
    return helpers


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def outputs() -> dict[str, object]:
    """Load emitted audit artifacts once per session."""
    payload: dict[str, object] = {}
    for name in OUTPUT_FILES:
        path = AUDIT_DIR / name
        assert path.is_file(), f"missing emitted artifact: {name}"
        payload[name] = _load_json(path)
    return payload


class TestInputIntegrity:
    """Verify the mounted workspace matches the frozen reference bytes."""

    def test_each_input_file_sha256(self) -> None:
        """Every normative input file under the data directory must match its pinned digest."""
        for rel, expected in EXPECTED_INPUT_HASHES.items():
            path = DATA_DIR / rel
            assert path.is_file(), f"missing input fixture: {rel}"
            digest = _sha256_bytes(path.read_bytes())
            assert digest == expected, f"digest mismatch for {rel}"


class TestReportStructure:
    """Verify emitted JSON files exist and hash-lock to the canonical contract."""

    def test_output_canonical_hashes(self, outputs: dict[str, object]) -> None:
        """Each audit file must match the canonical minified JSON digest."""
        for name, expected in EXPECTED_OUTPUT_CANONICAL_HASHES.items():
            canon = _canonical(outputs[name])
            digest = _sha256_bytes(canon.encode("utf-8"))
            assert digest == expected, f"output mismatch for {name}"

    def test_output_on_disk_matches_spec_json_encoding(
        self, outputs: dict[str, object]
    ) -> None:
        """Each audit file's bytes must match SPEC.md canonical JSON formatting."""
        for name in OUTPUT_FILES:
            path = AUDIT_DIR / name
            raw = path.read_bytes()
            expected = _spec_json_bytes(outputs[name])
            assert raw == expected, f"encoding mismatch for {name}"

    def test_field_hashes(self, outputs: dict[str, object]) -> None:
        """Selected nested fields must match their pinned canonical digests."""
        routes = outputs["allocations.json"]["routes"]
        assert (
            _sha256_bytes(_canonical(routes).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["allocations.routes"]
        )
        pools = outputs["pool_usage.json"]["pools"]
        assert (
            _sha256_bytes(_canonical(pools).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["pool_usage.pools"]
        )
        sgroups = outputs["pool_usage.json"]["shared_groups"]
        assert (
            _sha256_bytes(_canonical(sgroups).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["pool_usage.shared_groups"]
        )
        summary = outputs["summary.json"]
        for key in (
            "allocation_day",
            "frozen_routes",
            "groups_binding",
            "pools_touched",
            "routes_processed",
        ):
            field = f"summary.{key}"
            assert (
                _sha256_bytes(_canonical(summary[key]).encode("utf-8"))
                == EXPECTED_FIELD_HASHES[field]
            )
        sc = summary["status_counts"]
        for subk in sorted(sc.keys()):
            field = f"summary.status_counts.{subk}"
            assert (
                _sha256_bytes(_canonical(sc[subk]).encode("utf-8"))
                == EXPECTED_FIELD_HASHES[field]
            )


class TestStatusCoverage:
    """Exercise every documented route status on concrete fixtures."""

    def test_ok_on_rt_a(self, outputs: dict[str, object]) -> None:
        """Route rt-a must be fully satisfied with status ok."""
        routes = {r["route_id"]: r for r in outputs["allocations.json"]["routes"]}
        row = routes["rt-a"]
        assert row["status"] == "ok"
        assert row["primary_requested"] == row["primary_allocated"]
        assert row["canary_requested"] == row["canary_allocated"]

    def test_primary_shortfall_on_rt_b(self, outputs: dict[str, object]) -> None:
        """Route rt-b must show primary shortfall with shared group exhaustion."""
        routes = {r["route_id"]: r for r in outputs["allocations.json"]["routes"]}
        row = routes["rt-b"]
        assert row["status"] == "primary_shortfall"
        assert "primary_pool_exhausted" in row["reasons"]
        assert "shared_group_exhausted" in row["reasons"]

    def test_frozen_route_rt_h(self, outputs: dict[str, object]) -> None:
        """Route rt-h must be frozen with zero demands and empty reasons."""
        routes = {r["route_id"]: r for r in outputs["allocations.json"]["routes"]}
        row = routes["rt-h"]
        assert row["status"] == "frozen"
        assert row["primary_requested"] == 0
        assert row["canary_requested"] == 0
        assert row["reasons"] == []

    def test_shadow_canary_rt_f(self, outputs: dict[str, object]) -> None:
        """Route rt-f must keep shadow canary at zero draw while requests stay nonzero."""
        routes = {r["route_id"]: r for r in outputs["allocations.json"]["routes"]}
        row = routes["rt-f"]
        assert row["shadow_canary"] is True
        assert row["canary_allocated"] == 0
        assert row["canary_requested"] > 0
        assert row["status"] == "both_shortfall"

    def test_canary_shortfall_on_rt_i(self, outputs: dict[str, object]) -> None:
        """Route rt-i must surface canary-only shortfall after upstream drains."""
        routes = {r["route_id"]: r for r in outputs["allocations.json"]["routes"]}
        row = routes["rt-i"]
        assert row["status"] == "canary_shortfall"
        assert row["canary_requested"] > row["canary_allocated"]
        assert row["primary_requested"] == row["primary_allocated"]
        assert "canary_pool_exhausted" in row["reasons"]

    def test_both_shortfall_on_rt_g(self, outputs: dict[str, object]) -> None:
        """Route rt-g must show both sides short after the canary pool is exhausted."""
        routes = {r["route_id"]: r for r in outputs["allocations.json"]["routes"]}
        row = routes["rt-g"]
        assert row["status"] == "both_shortfall"


class TestHelperSources:
    """Optional compiled helpers must ship sources alongside them under /app/."""

    def test_compiled_helpers_have_source_files_alongside(self) -> None:
        """Every ELF helper under /app must have a source file in the same directory."""
        for binary in _compiled_helpers_under_app():
            parent = binary.parent
            sources = [
                entry
                for entry in parent.iterdir()
                if entry.is_file() and entry.suffix in SOURCE_SUFFIXES
            ]
            assert sources, (
                f"compiled helper {binary} requires a source file alongside it in {parent}"
            )


class TestSummarySemantics:
    """Cross-check high-level counters against the emitted route table."""

    def test_routes_processed_matches_fixture_count(self, outputs: dict[str, object]) -> None:
        """summary.routes_processed must equal the number of route JSON files."""
        route_dir = DATA_DIR / "routes"
        n = len(list(route_dir.glob("*.json")))
        assert outputs["summary.json"]["routes_processed"] == n

    def test_frozen_counter_matches_frozen_rows(self, outputs: dict[str, object]) -> None:
        """Frozen counts in summary must match frozen rows in allocations."""
        routes = outputs["allocations.json"]["routes"]
        frozen_rows = sum(1 for r in routes if r["status"] == "frozen")
        summary = outputs["summary.json"]
        assert summary["frozen_routes"] == frozen_rows
        assert summary["status_counts"]["frozen"] == frozen_rows
