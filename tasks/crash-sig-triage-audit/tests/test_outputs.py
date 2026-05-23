"""Behavioral tests for the crash-signature-triage task.

These tests assert the agent's outputs against the documented contract in
``instruction.md`` and ``/app/dumps/SPEC.md``. Hash-locked anti-cheat
fixtures are computed independently from the input data and compared
against the agent's emitted JSON files; an agent cannot pass these tests
by writing arbitrary or hand-tweaked output.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("CST_DATA_DIR", "/app/dumps"))
TRIAGE_DIR = Path(os.environ.get("CST_TRIAGE_DIR", "/app/triage"))

REQUIRED_OUTPUT_FILES = [
    "cluster_index.json",
    "attribution_report.json",
    "severity_ranking.json",
    "owner_assignment.json",
    "summary.json",
]

EXPECTED_INPUT_HASHES = {
    "SPEC.md":                   "669e71de5afb92c846e2ec7b1034f6c0176fcce8c42bc9afbe5b80ddea844196",
    "crashes/crash-001.json":    "2c04abcfdddacbf9e7229dae02c4b37c067e0ed0642cbe7cb14492562586657b",
    "crashes/crash-002.json":    "71100da5bec6437628ccfe46d195ea48042be7b8738956f0cf675171d71c0b47",
    "crashes/crash-003.json":    "7d8ee02608fc42cdb3507dd486f4dd4e75334126954184cb7758b21b93797d56",
    "crashes/crash-004.json":    "701413b855ec58d1de4470bc8e2ecc989a1ae43d4db8b2a5991ee983d8edf9bf",
    "crashes/crash-005.json":    "c1cca3dd180a7dd2b6ffa22d3209513c77be8537214f456a4bdd0f6ab162b07f",
    "crashes/crash-006.json":    "9aa0e04fc17c072f8b637633fa78ec6a1190ffb00bbdd8eec3b1048cbea4454b",
    "crashes/crash-007.json":    "27ad6d51e167d094d878b97343ede83932c79c133a5ff326062518fec4facac7",
    "crashes/crash-008.json":    "b49699f58b7ce10a2e774da00d2331cc1bef934fa79d4ecf6f01a28e4f9a523d",
    "crashes/crash-009.json":    "da78e5d14c590d74102dcaaf131796ace7e9f7e678e594e46e3f22bab1288ba1",
    "crashes/crash-010.json":    "621333c3cf83f27f4f48cdd31ecc7789c014e85138e2f6c8dd3f793eabdd1af8",
    "crashes/crash-011.json":    "cf1fbc58069da3a840d628b98bab4fca78d17621ebacc4c76f3db06c1e5c4428",
    "crashes/crash-012.json":    "509be3f72e2f26914280035435557f7d55c7385338298960574e18e5cb3c2712",
    "crashes/crash-013.json":    "8fbff49e898a785d65999e2dc98fca150336bbbb3f40ce221a2eb1a9824aff2b",
    "crashes/crash-014.json":    "659ce8d4957f3d6020943787136661da3220adada072927ef09828283b050837",
    "crashes/crash-015.json":    "b93b93144d36c8a4e0ea75e0cd16e60e58260dfaae009ba0a1d67d2550208a22",
    "crashes/crash-016.json":    "b8a07652a8b88931694a3a17ae846a700b81eab80a8b513f029428d4bd86b323",
    "crashes/crash-017.json":    "166cb18094369b8d9deb825162919467efc4f270f52bd8d7c1a5585cb93a55cd",
    "crashes/crash-018.json":    "6676f276ea88f6b71f8ddcfe16f87aa7b851b0747a21921de6201a1bd336a11b",
    "crashes/crash-019.json":    "54044e7c145453518afd883100ff88e1143bd9752a98b2a0b720b0159b8ef091",
    "crashes/crash-bad-1.json":  "5362f1bd4a9db230a35ed770af910fddadbcef6ccbb4615d2c0904fff8f76c1f",
    "crashes/crash-bad-2.json":  "0f0ea182a43e555ca91d44414ef02c472d8483adabeae8e7096d63694309e81c",
    "crashes/crash-bad-3.json":  "dc0708c7ebb7db6b9be88bac23187886b90798554c75fe1aa19e2d15f4efe7e2",
    "incident_log.json":         "8c07bc9372dfec6904b976b4b39cd607ccbe3cdbc5ec99ad9bb3f79158786c47",
    "module_map.json":           "9732f27e3b5092976a033d8fb0d0d27989c9c30985d2eb3e993092a573ae5936",
    "pool_state.json":           "4f49f05b88ec05fd0b0b09138220bfb8b29fcbebc334ec5a0cf8066a9501d7de",
    "releases/v1-0.json":        "cd3e772fe07c6c9ea0f2426cb939f40d7b58106d7e51256116d9310c098a3a15",
    "releases/v1-1.json":        "c7363bd6220f68a6ab0ce3038e18aaf109ad69004b91df61e00d1761f4624bd1",
    "releases/v1-2.json":        "10a0ed3859d03291ebf6df1059de44e886810c62b6490c39f5a9467b37334d8a",
    "releases/v1-3.json":        "52a9ee5f8ea3a74f56b00e9a6679b032786987a50ee5ad93a0d3ea1ef7996922",
    "releases/v1-4.json":        "f7d41961b7200fcea9c6a6a3b9b0bf857a77bebb322fde40ed610677daecdae7",
    "releases/v1-5.json":        "9fec7f081b52561eb04646ff4beb488a2aa2be1d7043701938bb24c095b6270f",
    "releases/v2-0.json":        "9d87224fec70d17ca521f35cb821da28a365ede574ad81044aeee3a3564bc310",
    "releases/v2-bad.json":      "875365e42a6a1b300db8a23c2af2a217511b340b1a08b43e30e568f5caefb8eb",
    "triage_config.json":        "82ac4c7f5ace7b711019b37108ccf1a6f07ff3b5c3458cc9ad32bb70c08c7643",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "attribution_report.json":  "689660dfbbaa8dd94d1f1c1d6e255d859948eea80a12e5d825e2e6310588586e",
    "cluster_index.json":       "f1b28619a2542a0b63058058b4769bd3141ec028890e9b642f2b274a54812f7b",
    "owner_assignment.json":    "df61d5415cc1156eb555007b27e8d12971e1b8a4d3513410cd83fa955208433b",
    "severity_ranking.json":    "7c472122b90e2d81449e378d44585c6f48729e3089c8415605374d20cd2e8447",
    "summary.json":             "7c42aa2985b87c7c67f07b4130eb0a4c57dace70dd50d9c73ecacbcdca355eeb",
}

EXPECTED_FIELD_HASHES = {
    "attribution_report.clusters":   "42d186b364e4a1561a41b048dbb14a44a2fde11eabe47c8b9a610ddee6bf1dda",
    "cluster_index.clusters":        "0482d910682b207764a058a3eda607063f9285b15a5afd2e9515ee7b0f60f4d5",
    "owner_assignment.clusters":     "624c5e54afff5d5814c68979a8f717ea9a400006f0236875592cd9abbe4ff094",
    "severity_ranking.clusters":     "b6f085f5621d91e53189425af08e901ee1b67385d0bc1423849999f6ac1aee59",
    "summary.by_assignment_reason":  "fe0b0d170b8873cb7e6eb5a8af75ccbfebe6a3017634fa5fd66e6604bfdfa74f",
    "summary.by_attribution_note":   "f46fdc59e5b8076a28938c6086f49118c5ad3b67bf58bc0e1f17e91d5b3e779f",
    "summary.by_severity":           "1b7706bdec1428af4a4ee5e574d6fd6f8d682610772aa30fa4d65bfe3cd293e5",
    "summary.current_day":           "97b912eb4a61df5f806ca6239dde3e1a4f51ad20aced1642cbb83dc510a5fa6b",
    "summary.poisoned_clusters":     "7684d532edd103d2024a7275df2e1ea1eae4da8e2f142c132c025cd12b05ddd0",
    "summary.totals":                "a1c4da169562c3dffa1f243fbdb0160b151eabd6488c3abc96f7c8487ca7b759",
    "summary.triage_version":        "0fb49fc712a709fda0e7b62fc41ae3d4da9c8adc53770988ebc96f052aa07f34",
}


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _canonical_bytes(obj) -> bytes:
    return (
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _canonical_sha256(obj) -> str:
    return _sha256_bytes(_canonical_bytes(obj))


@pytest.fixture(scope="module")
def loaded_outputs():
    out = {}
    for name in REQUIRED_OUTPUT_FILES:
        p = TRIAGE_DIR / name
        assert p.is_file(), f"missing required output file: {TRIAGE_DIR.as_posix()}/{name}"
        text = p.read_text(encoding="utf-8")
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as e:
            pytest.fail(f"output {TRIAGE_DIR.as_posix()}/{name} is not valid JSON: {e}")
        out[name] = {"text": text, "obj": obj, "bytes": text.encode("utf-8")}
    return out


class TestInputIntegrity:
    """Inputs must remain byte-identical to the original fixtures."""

    @pytest.mark.parametrize("rel,expected", sorted(EXPECTED_INPUT_HASHES.items()))
    def test_input_unchanged(self, rel, expected):
        """Each input file's canonical SHA-256 must match the locked baseline."""
        p = DATA_DIR / rel
        assert p.is_file(), f"missing input fixture: dumps/{rel}"
        if p.suffix == ".json":
            obj = json.loads(p.read_text(encoding="utf-8"))
            actual = _canonical_sha256(obj)
        else:
            actual = _sha256_bytes(p.read_bytes())
        assert actual == expected, f"input fixture dumps/{rel} was modified"


class TestReportStructure:
    """The five output files must exist with the right top-level shape and canonical encoding."""

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_required_file_exists(self, name, loaded_outputs):
        """Every required output file must be present and parseable."""
        assert name in loaded_outputs

    def test_canonical_hash_cluster_index(self, loaded_outputs):
        """cluster_index.json must hash to the locked canonical baseline."""
        assert _canonical_sha256(loaded_outputs["cluster_index.json"]["obj"]) == \
            EXPECTED_OUTPUT_CANONICAL_HASHES["cluster_index.json"]

    def test_canonical_hash_attribution_report(self, loaded_outputs):
        """attribution_report.json must hash to the locked canonical baseline."""
        assert _canonical_sha256(loaded_outputs["attribution_report.json"]["obj"]) == \
            EXPECTED_OUTPUT_CANONICAL_HASHES["attribution_report.json"]

    def test_canonical_hash_severity_ranking(self, loaded_outputs):
        """severity_ranking.json must hash to the locked canonical baseline."""
        assert _canonical_sha256(loaded_outputs["severity_ranking.json"]["obj"]) == \
            EXPECTED_OUTPUT_CANONICAL_HASHES["severity_ranking.json"]

    def test_canonical_hash_owner_assignment(self, loaded_outputs):
        """owner_assignment.json must hash to the locked canonical baseline."""
        assert _canonical_sha256(loaded_outputs["owner_assignment.json"]["obj"]) == \
            EXPECTED_OUTPUT_CANONICAL_HASHES["owner_assignment.json"]

    def test_canonical_hash_summary(self, loaded_outputs):
        """summary.json must hash to the locked canonical baseline."""
        assert _canonical_sha256(loaded_outputs["summary.json"]["obj"]) == \
            EXPECTED_OUTPUT_CANONICAL_HASHES["summary.json"]

    def test_files_are_pretty_printed(self, loaded_outputs):
        """Every output file must use 2-space indent and end with one trailing newline."""
        for name, data in loaded_outputs.items():
            text = data["text"]
            assert text.endswith("\n"), f"{name} must end with a newline"
            assert not text.endswith("\n\n"), f"{name} must not end with multiple newlines"
            expected = json.dumps(data["obj"], indent=2, sort_keys=True, ensure_ascii=False) + "\n"
            assert text == expected, (
                f"{name} is not canonical 2-space indented sorted JSON"
            )

    def test_top_level_keys_exactly(self, loaded_outputs):
        """Each output file must contain exactly its documented top-level keys."""
        expected_keys = {
            "cluster_index.json": {"clusters"},
            "attribution_report.json": {"clusters"},
            "severity_ranking.json": {"clusters"},
            "owner_assignment.json": {"clusters"},
            "summary.json": {
                "current_day", "triage_version", "totals",
                "by_severity", "by_attribution_note", "by_assignment_reason",
                "poisoned_clusters",
            },
        }
        for name, keys in expected_keys.items():
            assert set(loaded_outputs[name]["obj"].keys()) == keys, (
                f"{name} top-level keys must equal {sorted(keys)}"
            )


class TestClusterIndex:
    """Canonical signature, deduplication, short-stack handling, and merge effects."""

    def test_clusters_field_hash(self, loaded_outputs):
        """The full clusters list must match the locked canonical hash."""
        assert _canonical_sha256(loaded_outputs["cluster_index.json"]["obj"]["clusters"]) == \
            EXPECTED_FIELD_HASHES["cluster_index.clusters"]

    def test_clusters_sorted_by_signature(self, loaded_outputs):
        """`clusters` must be sorted by `signature` ascending."""
        sigs = [c["signature"] for c in loaded_outputs["cluster_index.json"]["obj"]["clusters"]]
        assert sigs == sorted(sigs)

    def test_canonical_signature_first3_last1(self, loaded_outputs):
        """Crashes that share the first-three + last-one frames cluster together regardless of middle frames."""
        clusters = {c["signature"]: c for c in loaded_outputs["cluster_index.json"]["obj"]["clusters"]}
        net = "net::tcp::send|net::tcp::ack|net::ssl::handshake|net::ssl::verify"
        assert net in clusters
        assert set(clusters[net]["crashes"]) == {"crash-006", "crash-007", "crash-008"}

    def test_canonical_signature_short_stack(self, loaded_outputs):
        """A frame_stack of length < 4 takes the entire stack as the signature."""
        clusters = {c["signature"]: c for c in loaded_outputs["cluster_index.json"]["obj"]["clusters"]}
        audio_3 = "audio::buffer::write|audio::mixer::mix|audio::driver::flush"
        assert audio_3 in clusters
        assert clusters[audio_3]["crashes"] == ["crash-011"]

    def test_canonical_signature_dedup_keeps_first(self, loaded_outputs):
        """When the last frame duplicates one of the first three, dedup keeps the first occurrence, producing a 3-frame signature."""
        clusters = {c["signature"]: c for c in loaded_outputs["cluster_index.json"]["obj"]["clusters"]}
        sched = "sched::yield|sched::wake|sched::idle"
        assert sched in clusters
        assert clusters[sched]["crashes"] == ["crash-019"]

    def test_invalid_crashes_silently_dropped(self, loaded_outputs):
        """Invalid crash records (bad hex env_hash, empty frame_stack, out-of-enum reproducibility) must not appear in any cluster."""
        all_crash_ids = {
            cid
            for c in loaded_outputs["cluster_index.json"]["obj"]["clusters"]
            for cid in c["crashes"]
        }
        for bad in ("crash-bad-1", "crash-bad-2", "crash-bad-3"):
            assert bad not in all_crash_ids

    def test_first_seen_and_last_seen_days(self, loaded_outputs):
        """first_seen_day and last_seen_day must equal the min/max of reported_day across the cluster's crashes."""
        clusters = {c["signature"]: c for c in loaded_outputs["cluster_index.json"]["obj"]["clusters"]}
        db = "db::query::parse|db::query::optimize|db::transaction::commit|db::transaction::rollback"
        assert clusters[db]["first_seen_day"] == 35
        assert clusters[db]["last_seen_day"] == 37

    def test_merge_absorbs_crashes_and_records_source(self, loaded_outputs):
        """An accepted cluster_merge moves the source cluster's crashes into the target and records the source signature in merged_from."""
        clusters = {c["signature"]: c for c in loaded_outputs["cluster_index.json"]["obj"]["clusters"]}
        render = "render::draw|render::clip|render::flush|render::commit"
        shader = "render::shader::compile|render::shader::link|render::vertex::upload|render::vertex::commit"
        assert render in clusters
        assert shader not in clusters
        assert set(clusters[render]["crashes"]) == {
            "crash-001", "crash-002", "crash-003", "crash-004", "crash-005",
            "crash-016", "crash-017",
        }
        assert clusters[render]["merged_from"] == [shader]

    def test_merge_shifts_first_seen_day_to_absorbed_minimum(self, loaded_outputs):
        """After a merge, first_seen_day reflects the minimum reported_day across the union of pre- and post-merge crashes."""
        clusters = {c["signature"]: c for c in loaded_outputs["cluster_index.json"]["obj"]["clusters"]}
        render = "render::draw|render::clip|render::flush|render::commit"
        assert clusters[render]["first_seen_day"] == 5

    def test_crashes_and_merged_from_are_sorted(self, loaded_outputs):
        """`crashes` and `merged_from` within each cluster must be sorted ascending."""
        for c in loaded_outputs["cluster_index.json"]["obj"]["clusters"]:
            assert c["crashes"] == sorted(c["crashes"])
            assert c["merged_from"] == sorted(c["merged_from"])


class TestAttributionReport:
    """Release-window attribution: smallest day >= first_seen_day, ASCII-smallest version tiebreak."""

    def test_clusters_field_hash(self, loaded_outputs):
        """The full clusters list must match the locked canonical hash."""
        assert _canonical_sha256(loaded_outputs["attribution_report.json"]["obj"]["clusters"]) == \
            EXPECTED_FIELD_HASHES["attribution_report.clusters"]

    def test_attribution_picks_smallest_day_ge_first_seen(self, loaded_outputs):
        """A cluster with first_seen_day=12 must be attributed to the release at the smallest day >= 12 (NOT the largest day <= 12)."""
        attrs = {a["signature"]: a for a in loaded_outputs["attribution_report.json"]["obj"]["clusters"]}
        render = "render::draw|render::clip|render::flush|render::commit"
        assert attrs[render]["attributed_release"] == "v1-0"

    def test_attribution_tied_day_picks_ascii_smallest_version(self, loaded_outputs):
        """When two releases share the same day at the chosen day, the ASCII-smallest version wins."""
        attrs = {a["signature"]: a for a in loaded_outputs["attribution_report.json"]["obj"]["clusters"]}
        net = "net::tcp::send|net::tcp::ack|net::ssl::handshake|net::ssl::verify"
        assert attrs[net]["attributed_release"] == "v1-2"
        assert attrs[net]["attributed_diff_hash"].startswith("cccc")

    def test_unattributed_cluster_when_no_release_ge_first_seen(self, loaded_outputs):
        """A cluster whose first_seen_day exceeds every valid release's day must be unattributed with null fields."""
        attrs = {a["signature"]: a for a in loaded_outputs["attribution_report.json"]["obj"]["clusters"]}
        audio = "audio::buffer::write|audio::mixer::mix|audio::driver::flush"
        assert attrs[audio]["attributed_release"] is None
        assert attrs[audio]["attributed_diff_hash"] is None
        assert attrs[audio]["attribution_note"] == "unattributed"

    def test_invalid_release_silently_dropped_from_attribution_candidates(self, loaded_outputs):
        """A release with an invalid diff_hash must not appear as any cluster's attributed_release."""
        attrs = {a["signature"]: a for a in loaded_outputs["attribution_report.json"]["obj"]["clusters"]}
        assert all(a["attributed_release"] != "v2-bad" for a in attrs.values())

    def test_poisoned_build_changes_attribution_note(self, loaded_outputs):
        """A cluster attributed to a release whose diff_hash matches a poisoned_build event gets attribution_note='poisoned_build'."""
        attrs = {a["signature"]: a for a in loaded_outputs["attribution_report.json"]["obj"]["clusters"]}
        poisoned = "auth::session::validate|auth::token::parse|auth::cache::lookup|auth::cache::evict"
        assert attrs[poisoned]["attribution_note"] == "poisoned_build"

    def test_non_poisoned_release_match_keeps_release_note(self, loaded_outputs):
        """A cluster attributed to a non-poisoned release keeps attribution_note='release_match'."""
        attrs = {a["signature"]: a for a in loaded_outputs["attribution_report.json"]["obj"]["clusters"]}
        clean_auth = "auth::otp::generate|auth::otp::deliver|auth::otp::verify|auth::otp::cleanup"
        assert attrs[clean_auth]["attribution_note"] == "release_match"


class TestSeverityRanking:
    """Severity escalation precedence: poisoned_build > reproducibility_always > cluster_size > max_observed."""

    def test_clusters_field_hash(self, loaded_outputs):
        """The full clusters list must match the locked canonical hash."""
        assert _canonical_sha256(loaded_outputs["severity_ranking.json"]["obj"]["clusters"]) == \
            EXPECTED_FIELD_HASHES["severity_ranking.clusters"]

    def test_max_observed_low(self, loaded_outputs):
        """A small cluster with no escalation reports the observed severity directly."""
        rows = {r["signature"]: r for r in loaded_outputs["severity_ranking.json"]["obj"]["clusters"]}
        audio = "audio::buffer::write|audio::mixer::mix|audio::driver::flush"
        assert rows[audio]["computed_severity"] == "low"
        assert rows[audio]["severity_reason"] == "max_observed_low"

    def test_max_observed_medium(self, loaded_outputs):
        """A 2-crash cluster of intermittent mediums computes severity=medium (no escalation)."""
        rows = {r["signature"]: r for r in loaded_outputs["severity_ranking.json"]["obj"]["clusters"]}
        db = "db::query::parse|db::query::optimize|db::transaction::commit|db::transaction::rollback"
        assert rows[db]["computed_severity"] == "medium"
        assert rows[db]["severity_reason"] == "max_observed_medium"

    def test_max_observed_high(self, loaded_outputs):
        """A 1-crash cluster reporting high severity stays at high without escalation."""
        rows = {r["signature"]: r for r in loaded_outputs["severity_ranking.json"]["obj"]["clusters"]}
        otp = "auth::otp::generate|auth::otp::deliver|auth::otp::verify|auth::otp::cleanup"
        assert rows[otp]["computed_severity"] == "high"
        assert rows[otp]["severity_reason"] == "max_observed_high"

    def test_escalated_reproducibility_always(self, loaded_outputs):
        """A cluster containing at least one reproducibility=always crash is escalated to critical with reason escalated_reproducibility_always."""
        rows = {r["signature"]: r for r in loaded_outputs["severity_ranking.json"]["obj"]["clusters"]}
        net = "net::tcp::send|net::tcp::ack|net::ssl::handshake|net::ssl::verify"
        assert rows[net]["computed_severity"] == "critical"
        assert rows[net]["severity_reason"] == "escalated_reproducibility_always"

    def test_escalated_cluster_size_includes_merged(self, loaded_outputs):
        """A cluster whose post-merge size meets or exceeds the threshold is escalated to critical with the exact crash count in the reason."""
        rows = {r["signature"]: r for r in loaded_outputs["severity_ranking.json"]["obj"]["clusters"]}
        render = "render::draw|render::clip|render::flush|render::commit"
        assert rows[render]["computed_severity"] == "critical"
        assert rows[render]["severity_reason"] == "escalated_cluster_size_7"

    def test_escalated_poisoned_build_wins_over_other_escalations(self, loaded_outputs):
        """A poisoned cluster is critical with reason escalated_poisoned_build, regardless of other escalation conditions."""
        rows = {r["signature"]: r for r in loaded_outputs["severity_ranking.json"]["obj"]["clusters"]}
        poisoned = "auth::session::validate|auth::token::parse|auth::cache::lookup|auth::cache::evict"
        assert rows[poisoned]["computed_severity"] == "critical"
        assert rows[poisoned]["severity_reason"] == "escalated_poisoned_build"

    def test_observed_severity_preserved_alongside_computed(self, loaded_outputs):
        """`observed_severity` must hold the max of crash severities even when `computed_severity` is escalated."""
        rows = {r["signature"]: r for r in loaded_outputs["severity_ranking.json"]["obj"]["clusters"]}
        net = "net::tcp::send|net::tcp::ack|net::ssl::handshake|net::ssl::verify"
        assert rows[net]["observed_severity"] == "medium"
        assert rows[net]["computed_severity"] == "critical"


class TestOwnerAssignment:
    """Owner precedence: poisoned_build > owner_reassign > module_match (longest-prefix) > release_default > default_owner."""

    def test_clusters_field_hash(self, loaded_outputs):
        """The full clusters list must match the locked canonical hash."""
        assert _canonical_sha256(loaded_outputs["owner_assignment.json"]["obj"]["clusters"]) == \
            EXPECTED_FIELD_HASHES["owner_assignment.clusters"]

    def test_poisoned_build_override_wins(self, loaded_outputs):
        """A poisoned cluster gets owner=release-engineering, overriding module_map and any other rule."""
        rows = {r["signature"]: r for r in loaded_outputs["owner_assignment.json"]["obj"]["clusters"]}
        poisoned = "auth::session::validate|auth::token::parse|auth::cache::lookup|auth::cache::evict"
        assert rows[poisoned]["assigned_owner_team"] == "release-engineering"
        assert rows[poisoned]["assignment_reason"] == "poisoned_build_override"

    def test_owner_reassign_wins_over_module_match(self, loaded_outputs):
        """An accepted owner_reassign event targeting a cluster's signature overrides any module_match (or release_default) for that cluster."""
        rows = {r["signature"]: r for r in loaded_outputs["owner_assignment.json"]["obj"]["clusters"]}
        ipc = "ipc::pipe::send|ipc::pipe::recv|ipc::pipe::close|ipc::pipe::reset"
        assert rows[ipc]["assigned_owner_team"] == "platform-team"
        assert rows[ipc]["assignment_reason"] == "owner_reassign"

    def test_module_match_longest_prefix_wins(self, loaded_outputs):
        """When the first frame is matched by multiple module prefixes, the longest prefix wins."""
        rows = {r["signature"]: r for r in loaded_outputs["owner_assignment.json"]["obj"]["clusters"]}
        otp = "auth::otp::generate|auth::otp::deliver|auth::otp::verify|auth::otp::cleanup"
        assert rows[otp]["assigned_owner_team"] == "identity-team"
        assert rows[otp]["assignment_reason"] == "module_match"

    def test_module_match_short_prefix_when_only_one_matches(self, loaded_outputs):
        """A cluster whose first frame matches exactly one module entry uses that entry's owner_team."""
        rows = {r["signature"]: r for r in loaded_outputs["owner_assignment.json"]["obj"]["clusters"]}
        render = "render::draw|render::clip|render::flush|render::commit"
        assert rows[render]["assigned_owner_team"] == "graphics-team"
        assert rows[render]["assignment_reason"] == "module_match"

    def test_release_default_when_no_module_match(self, loaded_outputs):
        """A cluster with no module match falls back to the attributed release's owner_team."""
        rows = {r["signature"]: r for r in loaded_outputs["owner_assignment.json"]["obj"]["clusters"]}
        mem = "mem::alloc|mem::free|mem::scrub|mem::commit"
        assert rows[mem]["assigned_owner_team"] == "db-team"
        assert rows[mem]["assignment_reason"] == "release_default"

    def test_default_owner_when_unattributed_and_no_module(self, loaded_outputs):
        """A cluster with neither a module match nor a release attribution falls back to triage_config.default_owner_team."""
        rows = {r["signature"]: r for r in loaded_outputs["owner_assignment.json"]["obj"]["clusters"]}
        audio = "audio::buffer::write|audio::mixer::mix|audio::driver::flush"
        assert rows[audio]["assigned_owner_team"] == "ops-team"
        assert rows[audio]["assignment_reason"] == "default_owner"

    def test_reassign_to_merged_away_signature_is_re_classified_ignored(self, loaded_outputs):
        """An owner_reassign targeting a signature that was merged away must NOT appear as an assignment_reason on the absorbing cluster."""
        rows = {r["signature"]: r for r in loaded_outputs["owner_assignment.json"]["obj"]["clusters"]}
        render = "render::draw|render::clip|render::flush|render::commit"
        assert rows[render]["assignment_reason"] != "owner_reassign"
        assert rows[render]["assigned_owner_team"] != "ghost-team"


class TestSummary:
    """Summary totals, breakdowns, and the poisoned_clusters list must agree with the other four outputs."""

    def test_totals_hash(self, loaded_outputs):
        """The totals sub-object must match the locked canonical hash."""
        assert _canonical_sha256(loaded_outputs["summary.json"]["obj"]["totals"]) == \
            EXPECTED_FIELD_HASHES["summary.totals"]

    def test_by_severity_hash(self, loaded_outputs):
        """by_severity counts must match the locked canonical hash."""
        assert _canonical_sha256(loaded_outputs["summary.json"]["obj"]["by_severity"]) == \
            EXPECTED_FIELD_HASHES["summary.by_severity"]

    def test_by_attribution_note_hash(self, loaded_outputs):
        """by_attribution_note counts must match the locked canonical hash."""
        assert _canonical_sha256(loaded_outputs["summary.json"]["obj"]["by_attribution_note"]) == \
            EXPECTED_FIELD_HASHES["summary.by_attribution_note"]

    def test_by_assignment_reason_hash(self, loaded_outputs):
        """by_assignment_reason counts must match the locked canonical hash."""
        assert _canonical_sha256(loaded_outputs["summary.json"]["obj"]["by_assignment_reason"]) == \
            EXPECTED_FIELD_HASHES["summary.by_assignment_reason"]

    def test_poisoned_clusters_hash(self, loaded_outputs):
        """poisoned_clusters must match the locked canonical hash."""
        assert _canonical_sha256(loaded_outputs["summary.json"]["obj"]["poisoned_clusters"]) == \
            EXPECTED_FIELD_HASHES["summary.poisoned_clusters"]

    def test_poisoned_clusters_matches_attribution(self, loaded_outputs):
        """poisoned_clusters must equal the sorted-ascending set of signatures whose attribution_note is 'poisoned_build'."""
        from_attribution = sorted(
            a["signature"]
            for a in loaded_outputs["attribution_report.json"]["obj"]["clusters"]
            if a["attribution_note"] == "poisoned_build"
        )
        assert loaded_outputs["summary.json"]["obj"]["poisoned_clusters"] == from_attribution

    def test_severity_totals_sum_to_cluster_count(self, loaded_outputs):
        """by_severity counts must sum to the total number of clusters."""
        bys = loaded_outputs["summary.json"]["obj"]["by_severity"]
        total_clusters = len(loaded_outputs["cluster_index.json"]["obj"]["clusters"])
        assert sum(bys.values()) == total_clusters

    def test_attribution_note_totals_sum_to_cluster_count(self, loaded_outputs):
        """by_attribution_note counts must sum to the total number of clusters."""
        bys = loaded_outputs["summary.json"]["obj"]["by_attribution_note"]
        total_clusters = len(loaded_outputs["cluster_index.json"]["obj"]["clusters"])
        assert sum(bys.values()) == total_clusters

    def test_assignment_reason_totals_sum_to_cluster_count(self, loaded_outputs):
        """by_assignment_reason counts must sum to the total number of clusters."""
        bys = loaded_outputs["summary.json"]["obj"]["by_assignment_reason"]
        total_clusters = len(loaded_outputs["cluster_index.json"]["obj"]["clusters"])
        assert sum(bys.values()) == total_clusters

    def test_ignored_incident_events_count(self, loaded_outputs):
        """ignored_incident_events must include every event that fails any acceptance rule, plus any owner_reassign re-classified after merges, plus any cluster_merge whose source was already absorbed."""
        assert loaded_outputs["summary.json"]["obj"]["totals"]["ignored_incident_events"] >= 6

    def test_merged_clusters_counts_only_applied_merges(self, loaded_outputs):
        """totals.merged_clusters counts only successfully-applied cluster_merge events."""
        assert loaded_outputs["summary.json"]["obj"]["totals"]["merged_clusters"] == 1

    def test_invalid_crashes_dropped(self, loaded_outputs):
        """totals.invalid_crashes_dropped equals the number of crash files that failed validation."""
        assert loaded_outputs["summary.json"]["obj"]["totals"]["invalid_crashes_dropped"] == 3

    def test_invalid_releases_dropped(self, loaded_outputs):
        """totals.invalid_releases_dropped equals the number of release files that failed validation."""
        assert loaded_outputs["summary.json"]["obj"]["totals"]["invalid_releases_dropped"] == 1

    def test_all_enum_keys_present(self, loaded_outputs):
        """Every documented enum value must appear as a key with an integer value (zero if absent)."""
        s = loaded_outputs["summary.json"]["obj"]
        for k in ("low", "medium", "high", "critical"):
            assert isinstance(s["by_severity"][k], int)
        for k in ("release_match", "unattributed", "poisoned_build"):
            assert isinstance(s["by_attribution_note"][k], int)
        for k in ("module_match", "release_default", "owner_reassign", "poisoned_build_override", "default_owner"):
            assert isinstance(s["by_assignment_reason"][k], int)

    def test_current_day_hash(self, loaded_outputs):
        """current_day must match the locked canonical hash."""
        assert _canonical_sha256(loaded_outputs["summary.json"]["obj"]["current_day"]) == \
            EXPECTED_FIELD_HASHES["summary.current_day"]

    def test_triage_version_hash(self, loaded_outputs):
        """triage_version must match the locked canonical hash."""
        assert _canonical_sha256(loaded_outputs["summary.json"]["obj"]["triage_version"]) == \
            EXPECTED_FIELD_HASHES["summary.triage_version"]
