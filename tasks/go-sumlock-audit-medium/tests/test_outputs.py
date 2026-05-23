# scaffold-status: oracle-pending
import hashlib
import json
from pathlib import Path


ROOT = Path("/app")
DOMAIN = ROOT / "sumlock_audit"
OUT_PATH = ROOT / "out" / "sumlock.json"

EXPECTED_INPUT_FINGERPRINT = (
    "2b53e64e164a5aadb635d6e1b023bceec533fb0c73c283c23f71b27e83620a4c"
)

EXPECTED_FIELD_HASHES = {
    "cycles": "2e5d6df0a61d9d20c6afcf21cf228736dfed93d0c8cb5b810a304e51ed85c25b",
    "excluded": "9d19d03dca6d4132b5a69f22d15d5c6e196406d8a6b31bdbf72399cbe7e7d0ad",
    "violations": "564d39ddc0adc2b4273fac2abca85e42d863f4303d8c840336395a1066f83ace",
    "summary": "ffa9e8daa8eafc780a4eae582c7af2647cc3e49b19c33f8d71ebc38b7593680c",
    "modules": "fddce2037329bce996c470a9083c44d5bd2c4a642bdb3143cd9810aa05c01e11",
}


def _iter_files(root: Path):
    files = [p for p in root.rglob("*") if p.is_file()]
    return sorted(files, key=lambda p: p.as_posix())


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _workspace_fingerprint(root: Path) -> str:
    h = hashlib.sha256()
    for p in _iter_files(root):
        rel = p.relative_to(root).as_posix()
        h.update(rel.encode())
        h.update(b"\n")
        h.update(_file_sha256(p).encode())
        h.update(b"\n")
    return h.hexdigest()


def _stable_hash(value) -> str:
    s = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _load_report():
    raw = OUT_PATH.read_bytes()
    if raw.endswith(b"\n"):
        raise AssertionError("Output must not have a trailing newline.")
    return json.loads(raw.decode("utf-8"))


class TestInputIntegrity:
    def test_input_fingerprint_matches_fixture(self):
        """Verifies the input workspace matches the expected fixture contents."""
        assert _workspace_fingerprint(DOMAIN) == EXPECTED_INPUT_FINGERPRINT


class TestReportStructure:
    def test_report_file_exists(self):
        """Ensures the report file is created at the required absolute path."""
        assert OUT_PATH.exists()

    def test_top_level_keys_exact(self):
        """Ensures the report has exactly the required top-level keys."""
        report = _load_report()
        assert sorted(report.keys()) == [
            "cycles",
            "excluded",
            "modules",
            "summary",
            "violations",
        ]


class TestExcluded:
    def test_excluded_hash(self):
        """Hash-locks the canonical value of the excluded field."""
        report = _load_report()
        assert _stable_hash(report["excluded"]) == EXPECTED_FIELD_HASHES["excluded"]

    def test_excluded_sorted(self):
        """Excluded module paths are sorted ascending."""
        assert _load_report()["excluded"] == sorted(_load_report()["excluded"])

    def test_tagged_legacy_module_excluded(self):
        """Modules whose TAGS are not subset of ACTIVE_PROFILES appear in excluded."""
        assert "example.com/beta" in _load_report()["excluded"]


class TestModules:
    def test_modules_hash(self):
        """Hash-locks the canonical value of the modules field."""
        report = _load_report()
        assert _stable_hash(report["modules"]) == EXPECTED_FIELD_HASHES["modules"]

    def test_modules_sorted_by_name(self):
        """Active module entries are sorted by module name ascending."""
        names = [t["module"] for t in _load_report()["modules"]]
        assert names == sorted(names)

    def test_module_entries_sorted(self):
        """Each modules entry lists version strings in ascending order."""
        for entry in _load_report()["modules"]:
            assert entry["entries"] == sorted(entry["entries"])

    def test_module_status_values(self):
        """Module status is only ok or violation."""
        allowed = {"ok", "violation"}
        for entry in _load_report()["modules"]:
            assert entry["status"] in allowed

    def test_module_field_types(self):
        """Module entries use string module names and string version lists."""
        for entry in _load_report()["modules"]:
            assert isinstance(entry["module"], str)
            assert isinstance(entry["entries"], list)
            assert all(isinstance(v, str) for v in entry["entries"])


class TestViolations:
    def test_violations_hash(self):
        """Hash-locks the canonical value of the violations field."""
        report = _load_report()
        assert _stable_hash(report["violations"]) == EXPECTED_FIELD_HASHES["violations"]

    def test_violations_sorted(self):
        """Violations are sorted by code, module, source, then version."""
        items = _load_report()["violations"]
        keys = [(f["code"], f["module"], f["source"], f["version"]) for f in items]
        assert keys == sorted(keys)

    def test_missing_sum_present(self):
        """Owned generate lines without sumdb emit missing_sum."""
        assert any(f["code"] == "missing_sum" for f in _load_report()["violations"])

    def test_stale_sum_present(self):
        """Stamp hash mismatches emit stale_sum."""
        assert any(f["code"] == "stale_sum" for f in _load_report()["violations"])

    def test_orphan_sum_present(self):
        """Stamps without matching USE lines emit orphan_sum when not in lenient."""
        assert any(f["code"] == "orphan_sum" for f in _load_report()["violations"])

    def test_unknown_version_present(self):
        """Generate lines for outputs not owned by the winning manifest emit unknown_version."""
        assert any(f["code"] == "unknown_version" for f in _load_report()["violations"])

    def test_module_cycle_present(self):
        """Dependency cycles emit module_cycle on each cycle edge."""
        assert any(f["code"] == "module_cycle" for f in _load_report()["violations"])

    def test_violation_codes_allowed(self):
        """Violation code values are limited to the documented set."""
        allowed = {
            "missing_sum",
            "orphan_sum",
            "stale_sum",
            "module_cycle",
            "unknown_version",
        }
        for entry in _load_report()["violations"]:
            assert entry["code"] in allowed

    def test_violation_field_types(self):
        """Violation entries use string fields for code, module, source, and version."""
        for entry in _load_report()["violations"]:
            assert isinstance(entry["code"], str)
            assert isinstance(entry["module"], str)
            assert isinstance(entry["source"], str)
            assert isinstance(entry["version"], str)


class TestCycles:
    def test_cycles_hash(self):
        """Hash-locks the canonical value of the cycles field."""
        report = _load_report()
        assert _stable_hash(report["cycles"]) == EXPECTED_FIELD_HASHES["cycles"]

    def test_cycles_normalized_smallest_first(self):
        """Each reported cycle starts with its lexicographically smallest module."""
        for cyc in _load_report()["cycles"]:
            assert cyc[0] == min(cyc)

    def test_cycles_sorted_by_first_module(self):
        """Reported cycles are sorted by their first module path ascending."""
        firsts = [c[0] for c in _load_report()["cycles"]]
        assert firsts == sorted(firsts)

    def test_each_cycle_is_sorted_internally(self):
        """Each cycle array is sorted ascending as required by SPEC.md."""
        for cyc in _load_report()["cycles"]:
            assert cyc == sorted(cyc)


class TestSummary:
    def test_summary_hash(self):
        """Hash-locks the canonical value of the summary field."""
        report = _load_report()
        assert _stable_hash(report["summary"]) == EXPECTED_FIELD_HASHES["summary"]

    def test_summary_counts_match_arrays(self):
        """Summary totals align with report section lengths and violation codes."""
        r = _load_report()
        s = r["summary"]
        assert s["total_excluded"] == len(r["excluded"])
        assert s["total_modules"] == len(r["excluded"]) + len(r["modules"])
        assert s["total_active"] == len(r["modules"])
        assert s["total_violations"] == len(r["violations"])
        assert s["total_cycles"] == len(r["cycles"])
        assert s["total_missing"] == sum(
            1 for f in r["violations"] if f["code"] == "missing_sum"
        )
        assert s["total_stale"] == sum(
            1 for f in r["violations"] if f["code"] == "stale_sum"
        )
        assert s["total_orphan"] == sum(
            1 for f in r["violations"] if f["code"] == "orphan_sum"
        )
        assert s["total_unknown"] == sum(
            1 for f in r["violations"] if f["code"] == "unknown_version"
        )


class TestNestedSchema:
    def test_module_entry_keys_exact(self):
        """Each modules entry contains only module, status, and entries."""
        for entry in _load_report()["modules"]:
            assert sorted(entry.keys()) == ["entries", "module", "status"]

    def test_violation_entry_keys_exact(self):
        """Each violations entry contains only code, module, source, and version."""
        for entry in _load_report()["violations"]:
            assert sorted(entry.keys()) == ["code", "module", "source", "version"]

    def test_summary_keys_exact(self):
        """Summary object contains exactly nine documented counter fields."""
        assert sorted(_load_report()["summary"].keys()) == [
            "total_active",
            "total_cycles",
            "total_excluded",
            "total_missing",
            "total_modules",
            "total_orphan",
            "total_stale",
            "total_unknown",
            "total_violations",
        ]


class TestCanonicalEncoding:
    def test_utf8_decode_and_ends_with_brace(self):
        """Report is valid UTF-8 and ends immediately after the closing brace."""
        raw = OUT_PATH.read_bytes()
        text = raw.decode("utf-8")
        assert text.endswith("}")
        assert not text.endswith("}\n")

    def test_two_space_indentation(self):
        """Report uses two-space indentation per SPEC encoding rules."""
        assert "\n  " in OUT_PATH.read_text(encoding="utf-8")

    def test_object_keys_sorted_at_every_depth(self):
        """Every JSON object has keys sorted lexicographically."""

        def walk(node):
            if isinstance(node, dict):
                keys = list(node.keys())
                assert keys == sorted(keys)
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(_load_report())

    def test_on_disk_encoding_matches_canonical_dump(self):
        """On-disk bytes match json.dumps with indent=2, sort_keys, and compact separators."""
        data = _load_report()
        expected = json.dumps(data, indent=2, sort_keys=True, separators=(",", ":"))
        assert OUT_PATH.read_text(encoding="utf-8") == expected


def _parse_kv(path: Path) -> dict[str, list[str]]:
    hdr: dict[str, list[str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, val = line.split(":", 1)
        hdr.setdefault(key.strip(), []).append(val.strip())
    return hdr


class TestSpecMdRules:
    def test_inactive_profile_modules_only_in_excluded(self):
        """SPEC Twist 1: TAGS not subset of ACTIVE_PROFILES yields excluded-only modules."""
        excluded = set(_load_report()["excluded"])
        active = {m["module"] for m in _load_report()["modules"]}
        assert "example.com/beta" in excluded
        assert "example.com/beta" not in active

    def test_priority_winner_unknown_version(self):
        """SPEC Twist 2: USE versions outside winning ENTRY emit unknown_version."""
        assert any(v["code"] == "unknown_version" for v in _load_report()["violations"])

    def test_stale_sum_when_hash_mismatch(self):
        """SPEC Twist 3: HASH mismatch against blob emits stale_sum."""
        assert any(v["code"] == "stale_sum" for v in _load_report()["violations"])

    def test_orphan_sum_in_strict_mode(self):
        """SPEC Twist 3b: unreferenced sumdb pairs emit orphan_sum in strict audit mode."""
        ws = _parse_kv(DOMAIN / "workspace.wk")
        pol = _parse_kv(DOMAIN / "policies" / "lenient.pol")
        lenient = pol.get("FORCE_LENIENT", ["false"])[0].lower() == "true" or (
            ws.get("AUDIT_MODE", ["strict"])[0].lower() == "lenient"
        )
        if not lenient:
            assert any(v["code"] == "orphan_sum" for v in _load_report()["violations"])

    def test_module_cycle_from_depends(self):
        """SPEC Twist 3c: DEPENDS among active modules emit module_cycle."""
        assert any(v["code"] == "module_cycle" for v in _load_report()["violations"])


def _reference_report() -> dict:
    """Independent re-derivation implementing all rules in /app/sumlock_audit/SPEC.md."""

    def pick_winner(manifests: list[dict]) -> dict:
        return sorted(manifests, key=lambda m: (-m["priority"], m["file"]))[0]

    ws = _parse_kv(DOMAIN / "workspace.wk")
    profiles = {t.strip() for t in ws["ACTIVE_PROFILES"][0].split(",") if t.strip()}
    lenient = ws.get("AUDIT_MODE", ["strict"])[0].lower() == "lenient"
    pol = _parse_kv(DOMAIN / "policies" / "lenient.pol")
    if pol.get("FORCE_LENIENT", ["false"])[0].lower() == "true":
        lenient = True

    by_mod: dict[str, list[dict]] = {}
    for path in sorted((DOMAIN / "manifests").glob("*.mft")):
        kv = _parse_kv(path)
        name = kv["MODULE"][0]
        tags = (
            {t.strip() for t in kv["TAGS"][0].split(",") if t.strip()}
            if "TAGS" in kv
            else set()
        )
        by_mod.setdefault(name, []).append(
            {
                "tags": tags,
                "entries": kv.get("ENTRY", []),
                "depends": kv.get("DEPENDS", []),
                "priority": int(kv.get("PRIORITY", ["0"])[0]),
                "file": path.name,
            }
        )

    winners = {m: pick_winner(rs) for m, rs in by_mod.items()}

    def is_active(name: str) -> bool:
        w = winners[name]
        return not w["tags"] or w["tags"].issubset(profiles)

    excluded = sorted(m for m in by_mod if not is_active(m))
    active = {m: winners[m] for m in by_mod if m not in excluded}
    owned = {m: sorted(active[m]["entries"]) for m in active}

    uses: list[tuple[str, str, str]] = []
    for path in sorted((DOMAIN / "sources").glob("*.src")):
        kv = _parse_kv(path)
        src = kv["SOURCE"][0]
        for line in kv.get("USE", []):
            parts = line.split()
            if len(parts) == 2:
                uses.append((src, parts[0], parts[1]))

    sums: dict[tuple[str, str], str] = {}
    blobs: dict[tuple[str, str], str] = {}
    for path in sorted((DOMAIN / "sumdb").glob("*.sum")):
        kv = _parse_kv(path)
        mod, ver = kv["MODULE"][0], kv["VERSION"][0]
        sums[(mod, ver)] = kv["HASH"][0]
        blobs[(mod, ver)] = kv["BLOB"][0]

    violations = []
    use_pairs: set[tuple[str, str]] = set()

    for src, mod, ver in uses:
        if mod in excluded or mod not in active:
            continue
        use_pairs.add((mod, ver))
        if ver not in owned.get(mod, []):
            violations.append(
                {"code": "unknown_version", "module": mod, "source": src, "version": ver}
            )
            continue
        key = (mod, ver)
        if key not in sums:
            violations.append(
                {"code": "missing_sum", "module": mod, "source": src, "version": ver}
            )
            continue
        blob_path = DOMAIN / "blobs" / blobs[key]
        if sums[key] != _file_sha256(blob_path):
            violations.append(
                {"code": "stale_sum", "module": mod, "source": src, "version": ver}
            )

    if not lenient:
        for key in sums:
            mod, ver = key
            if mod in excluded:
                continue
            if key not in use_pairs:
                violations.append(
                    {"code": "orphan_sum", "module": mod, "source": "", "version": ver}
                )

    graph = {n: [d for d in active[n]["depends"] if d in active] for n in sorted(active)}
    cycles = []
    seen: set[tuple[str, ...]] = set()

    def normalize_cycle(cyc: list[str]) -> list[str]:
        pivot = min(cyc)
        idx = cyc.index(pivot)
        return cyc[idx:] + cyc[:idx]

    def dfs(node: str, path: list[str], stack: set[str]):
        if node in stack:
            idx = path.index(node)
            cyc = normalize_cycle(path[idx:] + [node])[:-1]
            cyc = sorted(cyc)
            t = tuple(cyc)
            if t not in seen:
                seen.add(t)
                cycles.append(list(cyc))
            return
        if node in path:
            return
        stack.add(node)
        path.append(node)
        for nxt in graph.get(node, []):
            dfs(nxt, path, stack)
        path.pop()
        stack.remove(node)

    for node in graph:
        dfs(node, [], set())
    cycles.sort(key=lambda c: c[0])

    for cyc in cycles:
        for idx, mod in enumerate(cyc):
            violations.append(
                {
                    "code": "module_cycle",
                    "module": mod,
                    "source": "",
                    "version": cyc[(idx + 1) % len(cyc)],
                }
            )

    violations.sort(key=lambda v: (v["code"], v["module"], v["source"], v["version"]))
    viol_mods = {v["module"] for v in violations}
    modules = [
        {
            "entries": owned[name],
            "module": name,
            "status": "violation" if name in viol_mods else "ok",
        }
        for name in sorted(active)
    ]
    summary = {
        "total_active": len(active),
        "total_cycles": len(cycles),
        "total_excluded": len(excluded),
        "total_missing": sum(1 for v in violations if v["code"] == "missing_sum"),
        "total_modules": len(by_mod),
        "total_orphan": sum(1 for v in violations if v["code"] == "orphan_sum"),
        "total_stale": sum(1 for v in violations if v["code"] == "stale_sum"),
        "total_unknown": sum(1 for v in violations if v["code"] == "unknown_version"),
        "total_violations": len(violations),
    }
    return {
        "cycles": cycles,
        "excluded": excluded,
        "modules": modules,
        "summary": summary,
        "violations": violations,
    }


class TestIndependentReference:
    def test_report_matches_spec_reference(self):
        """Full report equals an independent implementation of SPEC.md rules."""
        expected = _reference_report()
        actual = _load_report()
        for key in sorted(expected):
            assert _stable_hash(actual[key]) == _stable_hash(expected[key]), key
