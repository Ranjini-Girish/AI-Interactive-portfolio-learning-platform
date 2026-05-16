"""Behavioral tests for the ml-experiment-ledger-auditor task.

These tests assert the agent's outputs against the documented contract in
``instruction.md`` and ``/app/ledger/SPEC.md``. Hash-locked anti-cheat
fixtures are computed independently from the input data and compared
against the agent's emitted JSON files; an agent cannot pass these tests
by writing arbitrary or hand-tweaked output.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("MEL_DATA_DIR", "/app/ledger"))
AUDIT_DIR = Path(os.environ.get("MEL_AUDIT_DIR", "/app/audit"))

REQUIRED_OUTPUT_FILES = [
    "run_status.json",
    "lineage_graph.json",
    "checkpoint_disposition.json",
    "registry_promotion.json",
    "summary.json",
]

EXPECTED_INPUT_HASHES = {
    "checkpoints/ckpt-A.json":             "48f266d871269291645d5d089d58214a40d4dbd0653ce8a1af6ceaec47fda4dc",
    "checkpoints/ckpt-B.json":             "89e8ea6b2cb30f1e4ee34fa78f6946e54b4cd7d73c174ee64dee0c54da3fd86b",
    "checkpoints/ckpt-C.json":             "08aa7335cc5bcedf6190f152cba0f0a2ff8d5389daa2bff3269f38edc2824298",
    "checkpoints/ckpt-D.json":             "1fa20c7e5f5f1f7ed8f7971639ee0f7cfd465ce1153c96b4c657c3d9fd87fa23",
    "checkpoints/ckpt-E.json":             "ae3ddde75e1e3647d2f0588acae3334e5e7ff5e1fab7fca86c43228ce2e102fd",
    "checkpoints/ckpt-F.json":             "92fa7ea323b0365b069b0ba511858ba43ebb8831bcb3d728a974852904f1ae66",
    "checkpoints/ckpt-G.json":             "2d9f163040a0457d284bdf26c92a26f937348141f3c02364f16f0f9d996ef786",
    "checkpoints/ckpt-H.json":             "ad6273c2da183cac83180d5de8438708607f25ac3a670472fe9637cec0b169c7",
    "checkpoints/ckpt-I.json":             "6f1ac53a8c429008e2205b92d1579ebe5b22c59813307b019977c516c5e71125",
    "checkpoints/ckpt-J.json":             "3e286035f5bc46aff7b8d2ce4f72806c3d98e065dcc06a0fb8173077003cd51b",
    "checkpoints/ckpt-K.json":             "b1f7a5f51f3d75009eb1f8f1893f8f3771bbe02501b2f7fd2b341efee733aef8",
    "checkpoints/ckpt-L.json":             "d37f674c2ce42638160dbe58f91ad33feb1589df9ec49405ac99bd255d78541b",
    "checkpoints/ckpt-M.json":             "b01f35a6b9dadee249e688ead882e7bb69baf3f2b05004f04c909d542cd20952",
    "checkpoints/ckpt-N.json":             "2e4bf5e44ff8da8bbad960f9cfc0f3889327c5d9808b1b97745dbce00bae3f3c",
    "checkpoints/ckpt-O.json":             "9b3f90272536c3f22726c2366ac182443ffd8e7d6b0b43a26ecd628ebe2630c2",
    "checkpoints/ckpt-P.json":             "485d99fdb6a878538a109558c87db0444079763ef2fcc7f3b4590909863196c0",
    "checkpoints/ckpt-Q.json":             "3e0e2fcc9985c5ca180379e57e8ba1e969d1a301caaa13f918209dfc8abe51d7",
    "checkpoints/ckpt-R.json":             "8cc22ccc7befd41a7a6069454d088ee9e0270600be721b1d576601f35157e55f",
    "checkpoints/ckpt-S.json":             "1e44f05c0b2e3804fdc20a85873f5973dae7693116f459313f2a1a751916778c",
    "datasets/ds-cleared-corpus.json":     "cc5ae25556cdea39f69ee708a517e92ab323e214a151c2f4f51a16606e7e9a50",
    "datasets/ds-curated-clicks.json":     "618f8f4715760614c1e8f89ea8a8c22deabe594531800512e98deac7955472e3",
    "datasets/ds-curated-text.json":       "52daab18b13758479690f0ccc56668e81261de39b5cb7f14ceecfa2de15be9e3",
    "datasets/ds-cyclic-loop.json":        "99b168d1e325890479d2cfc886cc976a4f5569b024db1c7105380aea897f33c8",
    "datasets/ds-gold-clicks.json":        "da62addc2fe30aa77761c7cf10f6299bec804667855e64c1dafdb76a9e568407",
    "datasets/ds-purged-archive.json":     "acfd783694882e4eedc30f5621a90c60aaca29661aad5c1423855e0630dbf93b",
    "datasets/ds-raw-clicks.json":         "63725bb2b8963c6892bd84051a4c043b09d5d1ba6d1b85ea13555be4074e9e11",
    "datasets/ds-raw-text.json":           "21e0e1334b812b0e614e63cecb206cd0c0bc708138f02184da74a98d65dc7c66",
    "governance_config.json":              "1e9459bd24b43a6dc6c0351d68af5a5e4e5cd558d68cf597badd546360a086ba",
    "incident_log.json":                   "a0edf88464deafa8d67f597d56b63eacf451c7a5d98edcf56f159a104f6a037b",
    "pool_state.json":                     "4beae506986770884a0cecab66582205d82ebe6d30e7175d4ff14701b6c47990",
    "registry/model-broken-ref.json":      "e5878030f86fcba03b4b031721dd632010af83867e1d3f1fdb582a72bc8a984c",
    "registry/model-cascade-probe.json":   "5ae997bbb1d3c18997359620c12fb961453c42d1709f0c133203009f5209d911",
    "registry/model-classify-clicks.json": "dbc3ec6277ed2323e7cd772ec841e1ed8e6cf377f56c22470595468b03960e05",
    "registry/model-classify-text.json":   "4413ec0eb649c409211d3e2fe975c686467ff82b31b012a3cdab872da8edc719",
    "registry/model-cleared-deploy.json":  "0144b3a98a9dca6ed70cbc41f4b5e410f12a6465addf1272b0e9e9b5979a3e15",
    "registry/model-deboost.json":         "fe420d5175999343126ff484079946dc3c0d15cfd0b7da6d9999d4f16c7543dd",
    "registry/model-eval-low.json":        "e086882c70e23b3447586c8d256ca308df8c9fe50b7081352a0314e9c4395268",
    "registry/model-fresh-staging.json":   "ad85201a8e0e45ac87e6a23bd05cb50d8791521b663ad146e62904d7a6b7ee7d",
    "registry/model-pending-promo.json":   "006ac6a463ca910ca581a67b6d456e4bb3b49ea323d19b7fa4b3ab81bb744c2b",
    "registry/model-prod-launch.json":     "bf9ecebfb6796801943ea7d24b6f081fe6c5a544cd658730b0eb391b54735523",
    "registry/model-rank-clicks.json":     "d1ebe972167714f8d60f7a27aae4422c9f9e25a082ff73c6dc631265dfe924e7",
    "registry/model-rd-classifier.json":   "b64f8ebcb395901d3bef710d3c86bc19fd6160bf2dd1a5f2d4727123351d9e0e",
    "registry/model-retracted.json":       "6605aefde999a7ae34a2123e8d10b0d37c00ddad89e5c8b10abca2f9791b018f",
    "registry/model-retry-stress.json":    "c551009da02ec4befc4291aaaf81e9e2d128b85c4325152e542426acaba7059d",
    "registry/model-runtime-blown.json":   "739b28a587b95c6c752097408918584f70f162ec56feeae0a6345a99a9dbbb9c",
    "registry/model-search-v2.json":       "47d10088452d69b64e2f8db7ce693cd68d2d3720c6c1e8fa1aa7bf622d39c83d",
    "registry/model-summarize-v1.json":    "bed2302ed439c30d45bc0a8ba98595a3242e7bff59d472be2d901628711e808e",
    "runs/run-001.json":                   "2e688a313afcf77dc79c2168dfcd9cd74416a79bcedcc7ab057eeea157e6e887",
    "runs/run-002.json":                   "383f6d546eafa65bd2ec28437570066e0e41d7b7e5afac84b9e870ed5aa6ec80",
    "runs/run-003.json":                   "9c8eb9444ad3b88a6e56643e1e9c357aabc7b0c83291a2b10568ed19c76c58e3",
    "runs/run-004.json":                   "bea0ac9b2d40cd59da4762f0146f14fd3a62f420df5ab955b9c06f1bb3ee0f92",
    "runs/run-005.json":                   "38b33730a991351076e72dd63616fc8866811829f3fa9535410c61544619098c",
    "runs/run-006.json":                   "23c74db583429e7f967aefb1103c9985106110cbd9007f5e1fb9c3c48230a8bb",
    "runs/run-007.json":                   "a2860529e7dd569151aa623487ed625b408ea349a16514e6c34d511b8945e3ef",
    "runs/run-008.json":                   "7d0ffc1bc643b291e16a8120821d58c22fe37be6d31364527480a6f800ace45b",
    "runs/run-009.json":                   "f0ba4e6f23e415ecfb3bbdd8d7d68fab848c26db509e8c8177224a7903664212",
    "runs/run-010.json":                   "678fba1e05f83552df3ee64c1f475e25f3912d4bf1c3f72c56cae929b214fe8a",
    "runs/run-011.json":                   "91fac4db1f96f5eeb862464dc58356625f6d3faf7f9fc085792ebcffac63476a",
    "runs/run-012.json":                   "6849455491377b6abf0fb5567d7ea3e5f6895b403d6ecddd91344cf0795036e7",
    "runs/run-013.json":                   "e308cbfda628a586ff2c65e60191add2aea4dfbad92d9c7f71d45c7ba37883cb",
    "runs/run-014.json":                   "6bcc4aee73a3ce5531673abffb394cfdb5fadc55d1cc4cbb098811dff58499ee",
    "runs/run-015.json":                   "872ac3a38f8a4179f8da03376dfc856e52a9d01730065c0538b772776f1954d0",
    "runs/run-016.json":                   "c013c9de30ba9c8ad55598dfc4dddfc47303941861a572a4807d8751bff0bee4",
    "runs/run-017.json":                   "2ff779118e81a8fddbd9138bed290b8b2597f86ecb252c44fe9ec9648950e75c",
    "runs/run-018.json":                   "ea6dc009d99d432ede423796b7ef18bad6fdfcb556292d00e1c2ddb9ea69e3d1",
    "runs/run-019.json":                   "e88d7268fac03e52c59130264b73d71b31b51ef4e7ce09830a334451cd465887",
    "runs/run-020.json":                   "8a5b1163ec532ba5d8fd5b459ad152f9752b3bbccda367c6f3ba394f672aab69",
    "reason_contract.txt":                 "f39e6f7c08d25f1bac2691a7acead3aa8cfbf749f89f4b8ae41a2855693410fa",
    "registry/model-staging-raw-hygiene.json": "98db7f6d27e23dbd96d79ff7f8c08eeecd7d1be840d32bcc0ad0c9f27119c634",
    "SPEC.md":                             "13d051818949e1184c096a3ffb4e0fcc5b3107a0737e02ab993645c0ada99f9e",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "checkpoint_disposition.json": "bfb54197335afcc3b33e8ac7b17247d60acde29ceb1bbe3d16440f3f5eb83970",
    "lineage_graph.json":          "45e3c24ffdf812ef3e6a6f3d372222f6bfe8787240837185af41acc7f05ee37a",
    "registry_promotion.json":     "ecc2723797e0e568f385d7d33e06b539030688062fb5ec84e2e19c2f3946fecb",
    "run_status.json":             "be0190e6243c6af51d616058c6bd77df8530412e9949d3bd287f0dee4907a815",
    "summary.json":                "4d50556fc80267f3527153c8895ca3d24032f084fda9858ca2cdf853909ab731",
}

EXPECTED_FIELD_HASHES = {
    "checkpoint_disposition.checkpoints": "8384b4cfad828bc4df1c45848df7150aa7b423be30117a05f33008e50bc38c9d",
    "lineage_graph.datasets":             "46e660bdca5b86ec304e837e4e840b969ff15fc073f49aaa26500e4c290e2759",
    "registry_promotion.models":          "a85ade85dc3a67a8cb648930488065432c0ae1c3c89c4e0a351d8c685affdbed",
    "run_status.runs":                    "283d33a6ff3f0d60efef7fea2b82b9ae768b9069711199a5ced505563def4ec9",
    "summary.by_compromise_status":       "392f18d69a961ab1420bd8f85c46afefc765b5630434dc142e49368f68b41d5b",
    "summary.by_decision":                "8a769d6b941592a73238acc7b65010aa7b164e69b117848775984ecfc1b8063c",
    "summary.by_disposition":             "e05f6b0090802fc54a5573097f3aff32fd86403f4b9f5020cb7aa49564e48318",
    "summary.by_run_status":              "216b3b4841854f455f76fd78684577d8e9c30e96455f79986634e5a3a989ab05",
    "summary.compromised_run_ids":        "61031bbeea047dfcb89699ed8f246d732c9bc3c22050cac8ad24041833a9cd25",
    "summary.current_day":                "97b912eb4a61df5f806ca6239dde3e1a4f51ad20aced1642cbb83dc510a5fa6b",
    "summary.ledger_version":             "e36d2b534c12eb6039ce1b3e60efa8b133c40811064d3c64f62c6738730a14f0",
    "summary.totals":                     "563f4011e5edfd1d440bcea4e26e640c1be9b833c95ed6866ef52c545ac97792",
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
        p = AUDIT_DIR / name
        assert p.is_file(), f"missing required output file: {AUDIT_DIR.as_posix()}/{name}"
        text = p.read_text(encoding="utf-8")
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as e:
            pytest.fail(f"output {AUDIT_DIR.as_posix()}/{name} is not valid JSON: {e}")
        out[name] = {"text": text, "obj": obj, "bytes": text.encode("utf-8")}
    return out


class TestInputIntegrity:
    """Inputs must remain byte-identical to the original fixtures."""

    @pytest.mark.parametrize("rel,expected", sorted(EXPECTED_INPUT_HASHES.items()))
    def test_input_unchanged(self, rel, expected):
        """Each input file's canonical SHA-256 must match the locked baseline."""
        p = DATA_DIR / rel
        assert p.is_file(), f"missing input fixture: ledger/{rel}"
        if p.suffix == ".json":
            obj = json.loads(p.read_text(encoding="utf-8"))
            actual = _canonical_sha256(obj)
        else:
            actual = _sha256_bytes(p.read_bytes())
        assert actual == expected, f"input fixture ledger/{rel} was modified"


class TestReportStructure:
    """The five output files must exist with the right top-level shape."""

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_required_file_exists(self, name, loaded_outputs):
        """Every required output file must be present and parseable."""
        assert name in loaded_outputs

    def test_canonical_hash_run_status(self, loaded_outputs):
        """run_status.json must hash to the locked canonical baseline."""
        assert _canonical_sha256(loaded_outputs["run_status.json"]["obj"]) == \
            EXPECTED_OUTPUT_CANONICAL_HASHES["run_status.json"]

    def test_canonical_hash_lineage_graph(self, loaded_outputs):
        """lineage_graph.json must hash to the locked canonical baseline."""
        assert _canonical_sha256(loaded_outputs["lineage_graph.json"]["obj"]) == \
            EXPECTED_OUTPUT_CANONICAL_HASHES["lineage_graph.json"]

    def test_canonical_hash_checkpoint_disposition(self, loaded_outputs):
        """checkpoint_disposition.json must hash to the locked canonical baseline."""
        assert _canonical_sha256(loaded_outputs["checkpoint_disposition.json"]["obj"]) == \
            EXPECTED_OUTPUT_CANONICAL_HASHES["checkpoint_disposition.json"]

    def test_canonical_hash_registry_promotion(self, loaded_outputs):
        """registry_promotion.json must hash to the locked canonical baseline."""
        assert _canonical_sha256(loaded_outputs["registry_promotion.json"]["obj"]) == \
            EXPECTED_OUTPUT_CANONICAL_HASHES["registry_promotion.json"]

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
            "run_status.json": {"runs"},
            "lineage_graph.json": {"datasets"},
            "checkpoint_disposition.json": {"checkpoints"},
            "registry_promotion.json": {"models"},
            "summary.json": {
                "current_day", "ledger_version", "totals",
                "by_run_status", "by_compromise_status",
                "by_disposition", "by_decision", "compromised_run_ids",
            },
        }
        for name, keys in expected_keys.items():
            assert set(loaded_outputs[name]["obj"].keys()) == keys, (
                f"{name} top-level keys must equal {sorted(keys)}"
            )


class TestRunStatus:
    """Every valid run must be classified with the documented precedence (tainted > inherited > runtime > replay > declared)."""

    def test_runs_field_hash(self, loaded_outputs):
        """The full runs list (canonical JSON) must match the locked field hash."""
        assert _canonical_sha256(loaded_outputs["run_status.json"]["obj"]["runs"]) == \
            EXPECTED_FIELD_HASHES["run_status.runs"]

    def test_runs_sorted_by_id(self, loaded_outputs):
        """`runs` must be sorted by `id` ascending."""
        ids = [r["id"] for r in loaded_outputs["run_status.json"]["obj"]["runs"]]
        assert ids == sorted(ids)

    def test_invalid_run_silently_dropped(self, loaded_outputs):
        """A run whose claimed_eval_metric is out of [0,1] must be absent from output."""
        ids = {r["id"] for r in loaded_outputs["run_status.json"]["obj"]["runs"]}
        assert "run-009" not in ids

    def test_succeeded_classification(self, loaded_outputs):
        """A run on a clean dataset with no taint, no inherited fail, and no replay mismatch is `succeeded` with reason `ok`."""
        runs = {r["id"]: r for r in loaded_outputs["run_status.json"]["obj"]["runs"]}
        assert runs["run-001"]["status"] == "succeeded"
        assert runs["run-001"]["reason"] == "ok"

    def test_failed_classification(self, loaded_outputs):
        """A run declared as failed (no overriding rule) must propagate to status=failed with reason `declared_failed`."""
        runs = {r["id"]: r for r in loaded_outputs["run_status.json"]["obj"]["runs"]}
        assert runs["run-006"]["status"] == "failed"
        assert runs["run-006"]["reason"] == "declared_failed"

    def test_aborted_classification(self, loaded_outputs):
        """A run declared as aborted on a clean dataset with no parent must yield status=aborted with reason `declared_aborted`."""
        runs = {r["id"]: r for r in loaded_outputs["run_status.json"]["obj"]["runs"]}
        assert runs["run-004"]["status"] == "aborted"
        assert runs["run-004"]["reason"] == "declared_aborted"

    def test_tainted_via_compromised_dataset(self, loaded_outputs):
        """A run whose base_dataset is `compromised` becomes tainted_run with the compromise_source id."""
        runs = {r["id"]: r for r in loaded_outputs["run_status.json"]["obj"]["runs"]}
        assert runs["run-002"]["status"] == "tainted_run"
        assert runs["run-002"]["reason"] == "tainted_via_ds-raw-clicks"

    def test_taint_overrides_declared_status(self, loaded_outputs):
        """A run on a compromised dataset whose status_declared is `aborted` still becomes tainted_run (rule 1 wins)."""
        runs = {r["id"]: r for r in loaded_outputs["run_status.json"]["obj"]["runs"]}
        assert runs["run-003"]["status"] == "tainted_run"

    def test_tainted_via_cyclic_dataset(self, loaded_outputs):
        """A run whose base_dataset participates in a lineage cycle becomes tainted_run with the cyclic dataset's own id."""
        runs = {r["id"]: r for r in loaded_outputs["run_status.json"]["obj"]["runs"]}
        assert runs["run-011"]["status"] == "tainted_run"
        assert runs["run-011"]["reason"] == "tainted_via_ds-cyclic-loop"

    def test_inherited_invalid_from_direct_parent(self, loaded_outputs):
        """A run whose immediate parent_run is aborted becomes inherited_invalid naming the offending parent."""
        runs = {r["id"]: r for r in loaded_outputs["run_status.json"]["obj"]["runs"]}
        assert runs["run-005"]["status"] == "inherited_invalid"
        assert runs["run-005"]["reason"] == "parent_aborted_run-004"

    def test_inherited_invalid_via_transitive_chain(self, loaded_outputs):
        """A run two hops from an aborted ancestor must still be inherited_invalid, naming the ASCII-smallest offending ancestor."""
        runs = {r["id"]: r for r in loaded_outputs["run_status.json"]["obj"]["runs"]}
        assert runs["run-008"]["status"] == "inherited_invalid"
        assert runs["run-008"]["reason"] == "parent_aborted_run-004"

    def test_succeeded_with_clean_parent_chain(self, loaded_outputs):
        """A run whose parent chain is entirely succeeded must remain succeeded (no false propagation)."""
        runs = {r["id"]: r for r in loaded_outputs["run_status.json"]["obj"]["runs"]}
        assert runs["run-010"]["status"] == "succeeded"
        assert runs["run-010"]["reason"] == "ok"

    def test_replay_mismatch_with_latest_replay(self, loaded_outputs):
        """A run with an accepted replay that disagrees beyond the tolerance becomes replay_mismatch."""
        runs = {r["id"]: r for r in loaded_outputs["run_status.json"]["obj"]["runs"]}
        assert runs["run-007"]["status"] == "replay_mismatch"
        assert "replay_mismatch_replayed_0.4000_claimed_0.6500" in runs["run-007"]["reason"]

    def test_replay_metric_populated_even_when_no_mismatch(self, loaded_outputs):
        """A run with an accepted replay within tolerance must still report the latest replay's metric."""
        runs = {r["id"]: r for r in loaded_outputs["run_status.json"]["obj"]["runs"]}
        assert runs["run-001"]["replay_metric"] == 0.93

    def test_replay_metric_null_without_accepted_replay(self, loaded_outputs):
        """A run with no accepted replay events must report replay_metric=null."""
        runs = {r["id"]: r for r in loaded_outputs["run_status.json"]["obj"]["runs"]}
        assert runs["run-004"]["replay_metric"] is None

    def test_replay_tiebreak_picks_ascii_smallest_event_id(self, loaded_outputs):
        """When multiple replays share the latest day, the ASCII-smallest event_id wins."""
        runs = {r["id"]: r for r in loaded_outputs["run_status.json"]["obj"]["runs"]}
        assert runs["run-007"]["replay_metric"] == 0.4

    def test_inherited_invalid_from_replay_mismatch_parent(self, loaded_outputs):
        """A run whose transitive parent_run has computed status=replay_mismatch propagates as inherited_invalid."""
        runs = {r["id"]: r for r in loaded_outputs["run_status.json"]["obj"]["runs"]}
        assert runs["run-013"]["status"] == "inherited_invalid"
        assert runs["run-013"]["reason"] == "parent_replay_mismatch_run-007"

    def test_compromise_lift_clears_local_dataset_taint(self, loaded_outputs):
        """A dataset with local compromise followed by compromise_lift must not taint runs when ancestors are clean and no retract invalidates the lift."""
        runs = {r["id"]: r for r in loaded_outputs["run_status.json"]["obj"]["runs"]}
        assert runs["run-014"]["status"] == "succeeded"
        assert runs["run-014"]["reason"] == "ok"

    def test_per_tier_replay_tolerance_uses_declared_target(self, loaded_outputs):
        """Replay mismatch threshold must come from the run's declared target tier tolerance."""
        runs = {r["id"]: r for r in loaded_outputs["run_status.json"]["obj"]["runs"]}
        assert runs["run-015"]["declared_tier_target"] == "research"
        assert runs["run-015"]["replay_metric"] == 0.58
        assert runs["run-015"]["status"] == "succeeded"

    def test_retracted_lift_re_exposes_compromise_run(self, loaded_outputs):
        """A run on a dataset whose lifting was retracted must surface as tainted_run via the retracted dataset id."""
        runs = {r["id"]: r for r in loaded_outputs["run_status.json"]["obj"]["runs"]}
        assert runs["run-016"]["status"] == "tainted_run"
        assert runs["run-016"]["reason"] == "tainted_via_ds-purged-archive"

    def test_runtime_exceeded_uses_tier_budget(self, loaded_outputs):
        """A run whose runtime_minutes_observed exceeds the declared tier's runtime_budget_minutes is `runtime_exceeded` with the observed and budget integers."""
        runs = {r["id"]: r for r in loaded_outputs["run_status.json"]["obj"]["runs"]}
        assert runs["run-017"]["status"] == "runtime_exceeded"
        assert runs["run-017"]["reason"] == "runtime_exceeded_observed_400_budget_300"

    def test_inherited_invalid_from_runtime_exceeded_parent(self, loaded_outputs):
        """A descendant of a runtime_exceeded ancestor must be inherited_invalid with reason `parent_runtime_exceeded_<rid>`."""
        runs = {r["id"]: r for r in loaded_outputs["run_status.json"]["obj"]["runs"]}
        assert runs["run-018"]["status"] == "inherited_invalid"
        assert runs["run-018"]["reason"] == "parent_runtime_exceeded_run-017"


class TestLineageGraph:
    """Dataset compromise propagation, cycles, depths, and lift-retract overlays must follow the contract."""

    def test_datasets_field_hash(self, loaded_outputs):
        """The full datasets list must match the locked canonical hash."""
        assert _canonical_sha256(loaded_outputs["lineage_graph.json"]["obj"]["datasets"]) == \
            EXPECTED_FIELD_HASHES["lineage_graph.datasets"]

    def test_datasets_sorted_by_id(self, loaded_outputs):
        """`datasets` must be sorted by `id` ascending."""
        ids = [d["id"] for d in loaded_outputs["lineage_graph.json"]["obj"]["datasets"]]
        assert ids == sorted(ids)

    def test_clean_dataset_classification(self, loaded_outputs):
        """A root dataset with no compromise event is clean with compromise_source=null."""
        ds = {d["id"]: d for d in loaded_outputs["lineage_graph.json"]["obj"]["datasets"]}
        assert ds["ds-raw-text"]["compromise_status"] == "clean"
        assert ds["ds-raw-text"]["compromise_source"] is None

    def test_directly_compromised_dataset(self, loaded_outputs):
        """A dataset directly named by an accepted dataset_compromise event becomes compromised with itself as source."""
        ds = {d["id"]: d for d in loaded_outputs["lineage_graph.json"]["obj"]["datasets"]}
        assert ds["ds-raw-clicks"]["compromise_status"] == "compromised"
        assert ds["ds-raw-clicks"]["compromise_source"] == "ds-raw-clicks"

    def test_transitively_compromised_dataset(self, loaded_outputs):
        """A descendant of a compromised dataset inherits compromise_status with the smallest-depth source."""
        ds = {d["id"]: d for d in loaded_outputs["lineage_graph.json"]["obj"]["datasets"]}
        assert ds["ds-gold-clicks"]["compromise_status"] == "compromised"
        assert ds["ds-gold-clicks"]["compromise_source"] == "ds-raw-clicks"

    def test_cyclic_dataset_classification(self, loaded_outputs):
        """A dataset on a path back to itself is `cyclic`, with null source and depth=-1."""
        ds = {d["id"]: d for d in loaded_outputs["lineage_graph.json"]["obj"]["datasets"]}
        assert ds["ds-cyclic-loop"]["compromise_status"] == "cyclic"
        assert ds["ds-cyclic-loop"]["compromise_source"] is None
        assert ds["ds-cyclic-loop"]["lineage_depth"] == -1

    def test_compromise_lift_keeps_dataset_clean(self, loaded_outputs):
        """A lifted local compromise must leave the dataset clean with null compromise_source (vacuous early retracts must not affect this)."""
        ds = {d["id"]: d for d in loaded_outputs["lineage_graph.json"]["obj"]["datasets"]}
        assert ds["ds-cleared-corpus"]["compromise_status"] == "clean"
        assert ds["ds-cleared-corpus"]["compromise_source"] is None

    def test_retracted_lift_surfaces_compromise(self, loaded_outputs):
        """A dataset whose only lift is invalidated by a later compromise_retract event must end up compromised again with itself as source."""
        ds = {d["id"]: d for d in loaded_outputs["lineage_graph.json"]["obj"]["datasets"]}
        assert ds["ds-purged-archive"]["compromise_status"] == "compromised"
        assert ds["ds-purged-archive"]["compromise_source"] == "ds-purged-archive"

    def test_lineage_depth_increments_with_parent_chain(self, loaded_outputs):
        """lineage_depth equals the longest parent chain length."""
        ds = {d["id"]: d for d in loaded_outputs["lineage_graph.json"]["obj"]["datasets"]}
        assert ds["ds-raw-clicks"]["lineage_depth"] == 0
        assert ds["ds-curated-clicks"]["lineage_depth"] == 1
        assert ds["ds-gold-clicks"]["lineage_depth"] == 2

    def test_unresolvable_parent_silently_filtered(self, loaded_outputs):
        """A dataset listing an unresolvable lineage_parent must still load (parent filtered out) and be treated as a root."""
        ds = {d["id"]: d for d in loaded_outputs["lineage_graph.json"]["obj"]["datasets"]}
        assert ds["ds-raw-text"]["lineage_depth"] == 0
        assert ds["ds-raw-text"]["compromise_status"] == "clean"

    def test_downstream_runs_includes_self_and_descendants(self, loaded_outputs):
        """downstream_runs lists every valid run whose base_dataset is the dataset itself or a transitive descendant."""
        ds = {d["id"]: d for d in loaded_outputs["lineage_graph.json"]["obj"]["datasets"]}
        assert ds["ds-raw-clicks"]["downstream_runs"] == ["run-002", "run-003"]

    def test_downstream_runs_is_sorted(self, loaded_outputs):
        """downstream_runs must be sorted ascending."""
        for d in loaded_outputs["lineage_graph.json"]["obj"]["datasets"]:
            assert d["downstream_runs"] == sorted(d["downstream_runs"])

    def test_cyclic_dataset_has_no_downstream_runs(self, loaded_outputs):
        """A cyclic dataset must report no downstream_runs (even if a run uses it as base)."""
        ds = {d["id"]: d for d in loaded_outputs["lineage_graph.json"]["obj"]["datasets"]}
        assert ds["ds-cyclic-loop"]["downstream_runs"] == []

    def test_cyclic_direct_reference_run_still_appears_in_compromised_run_ids(self, loaded_outputs):
        """A run whose base_dataset is cyclic is excluded from every downstream_runs list but is still reported as tainted_run."""
        ds = {d["id"]: d for d in loaded_outputs["lineage_graph.json"]["obj"]["datasets"]}
        for entry in ds.values():
            assert "run-011" not in entry["downstream_runs"], (
                f"run-011 (whose base_dataset is the cyclic dataset) must not appear in any "
                f"downstream_runs list, but was listed under {entry['id']}"
            )
        compromised = loaded_outputs["summary.json"]["obj"]["compromised_run_ids"]
        assert "run-011" in compromised


class TestCheckpointDisposition:
    """Checkpoint quarantine precedence must follow the contract: taint > revoked > unstable > lowscore > keep."""

    def test_checkpoints_field_hash(self, loaded_outputs):
        """The full checkpoints list must match the locked canonical hash."""
        assert _canonical_sha256(loaded_outputs["checkpoint_disposition.json"]["obj"]["checkpoints"]) == \
            EXPECTED_FIELD_HASHES["checkpoint_disposition.checkpoints"]

    def test_checkpoints_sorted_by_id(self, loaded_outputs):
        """`checkpoints` must be sorted by `id` ascending."""
        ids = [c["id"] for c in loaded_outputs["checkpoint_disposition.json"]["obj"]["checkpoints"]]
        assert ids == sorted(ids)

    def test_invalid_checkpoint_silently_dropped(self, loaded_outputs):
        """A checkpoint with step<0 (or any other invalid field) must be absent from the output."""
        ids = {c["id"] for c in loaded_outputs["checkpoint_disposition.json"]["obj"]["checkpoints"]}
        assert "ckpt-K" not in ids

    def test_keep_disposition_for_clean_succeeded_checkpoint(self, loaded_outputs):
        """A checkpoint with a succeeded parent, clean dataset, score above the floor, and no revoked key is kept."""
        ck = {c["id"]: c for c in loaded_outputs["checkpoint_disposition.json"]["obj"]["checkpoints"]}
        assert ck["ckpt-A"]["disposition"] == "keep"
        assert ck["ckpt-A"]["reason"] == "ok"
        assert ck["ckpt-A"]["size_mb_kept"] == 1200

    def test_quarantine_tainted_via_compromised_parent(self, loaded_outputs):
        """A checkpoint whose parent run is tainted_run is quarantine_tainted regardless of eval_score."""
        ck = {c["id"]: c for c in loaded_outputs["checkpoint_disposition.json"]["obj"]["checkpoints"]}
        assert ck["ckpt-B"]["disposition"] == "quarantine_tainted"
        assert ck["ckpt-B"]["reason"] == "tainted_via_ds-raw-clicks"

    def test_taint_overrides_revoked_key(self, loaded_outputs):
        """When the parent run is tainted AND the signature matches a revoked prefix, taint wins."""
        ck = {c["id"]: c for c in loaded_outputs["checkpoint_disposition.json"]["obj"]["checkpoints"]}
        assert ck["ckpt-B"]["disposition"] == "quarantine_tainted"

    def test_quarantine_revoked_key(self, loaded_outputs):
        """A checkpoint whose signature_hash starts with an accepted revoked prefix is quarantine_revoked_key."""
        ck = {c["id"]: c for c in loaded_outputs["checkpoint_disposition.json"]["obj"]["checkpoints"]}
        assert ck["ckpt-I"]["disposition"] == "quarantine_revoked_key"
        assert ck["ckpt-I"]["reason"] == "revoked_prefix_deadbeef"

    def test_revocation_effective_day_gates_quarantine(self, loaded_outputs):
        """A matching revoked prefix applies only when effective_day <= parent run started_day."""
        ck = {c["id"]: c for c in loaded_outputs["checkpoint_disposition.json"]["obj"]["checkpoints"]}
        assert ck["ckpt-M"]["disposition"] == "quarantine_unstable_run"
        assert ck["ckpt-M"]["reason"] == "parent_inherited_invalid"

    def test_quarantine_unstable_run_aborted_parent(self, loaded_outputs):
        """A checkpoint whose parent run is aborted is quarantine_unstable_run."""
        ck = {c["id"]: c for c in loaded_outputs["checkpoint_disposition.json"]["obj"]["checkpoints"]}
        assert ck["ckpt-D"]["disposition"] == "quarantine_unstable_run"
        assert ck["ckpt-D"]["reason"] == "parent_aborted"

    def test_quarantine_unstable_run_inherited_invalid_parent(self, loaded_outputs):
        """A checkpoint whose parent run is inherited_invalid is quarantine_unstable_run."""
        ck = {c["id"]: c for c in loaded_outputs["checkpoint_disposition.json"]["obj"]["checkpoints"]}
        assert ck["ckpt-E"]["disposition"] == "quarantine_unstable_run"
        assert ck["ckpt-E"]["reason"] == "parent_inherited_invalid"

    def test_quarantine_unstable_run_failed_parent(self, loaded_outputs):
        """A checkpoint whose parent run is failed is quarantine_unstable_run, even when eval_score is below the floor."""
        ck = {c["id"]: c for c in loaded_outputs["checkpoint_disposition.json"]["obj"]["checkpoints"]}
        assert ck["ckpt-F"]["disposition"] == "quarantine_unstable_run"
        assert ck["ckpt-F"]["eval_score"] < 0.4

    def test_quarantine_unstable_run_replay_mismatch_parent(self, loaded_outputs):
        """A checkpoint whose parent run is replay_mismatch is quarantine_unstable_run."""
        ck = {c["id"]: c for c in loaded_outputs["checkpoint_disposition.json"]["obj"]["checkpoints"]}
        assert ck["ckpt-G"]["disposition"] == "quarantine_unstable_run"
        assert ck["ckpt-G"]["reason"] == "parent_replay_mismatch"

    def test_quarantine_unstable_run_runtime_exceeded_parent(self, loaded_outputs):
        """A checkpoint whose parent run is runtime_exceeded is quarantine_unstable_run with reason parent_runtime_exceeded."""
        ck = {c["id"]: c for c in loaded_outputs["checkpoint_disposition.json"]["obj"]["checkpoints"]}
        assert ck["ckpt-Q"]["disposition"] == "quarantine_unstable_run"
        assert ck["ckpt-Q"]["reason"] == "parent_runtime_exceeded"

    def test_quarantine_tainted_after_retract(self, loaded_outputs):
        """A checkpoint whose parent run is tainted by a retract-resurfaced compromise carries the retracted dataset id in its reason."""
        ck = {c["id"]: c for c in loaded_outputs["checkpoint_disposition.json"]["obj"]["checkpoints"]}
        assert ck["ckpt-P"]["disposition"] == "quarantine_tainted"
        assert ck["ckpt-P"]["reason"] == "tainted_via_ds-purged-archive"

    def test_quarantine_lowscore(self, loaded_outputs):
        """A checkpoint on a succeeded parent run with eval_score below the floor is quarantine_lowscore."""
        ck = {c["id"]: c for c in loaded_outputs["checkpoint_disposition.json"]["obj"]["checkpoints"]}
        assert ck["ckpt-H"]["disposition"] == "quarantine_lowscore"
        assert re.fullmatch(r"below_floor_\d+\.\d{4}", ck["ckpt-H"]["reason"])

    def test_size_mb_kept_is_zero_for_quarantined(self, loaded_outputs):
        """Every non-kept checkpoint reports size_mb_kept=0."""
        for c in loaded_outputs["checkpoint_disposition.json"]["obj"]["checkpoints"]:
            if c["disposition"] != "keep":
                assert c["size_mb_kept"] == 0


class TestRegistryPromotion:
    """Registry decisions must follow the precedence: disposition gates, review gates, raw-base hygiene when the tier demands it, then retry, lineage depth, eval floor, and audit-age."""

    def test_models_field_hash(self, loaded_outputs):
        """The full models list must match the locked canonical hash."""
        assert _canonical_sha256(loaded_outputs["registry_promotion.json"]["obj"]["models"]) == \
            EXPECTED_FIELD_HASHES["registry_promotion.models"]

    def test_models_sorted_by_id(self, loaded_outputs):
        """`models` must be sorted by `id` ascending."""
        ids = [m["id"] for m in loaded_outputs["registry_promotion.json"]["obj"]["models"]]
        assert ids == sorted(ids)

    def test_invalid_registry_entry_silently_dropped(self, loaded_outputs):
        """A registry entry whose candidate_checkpoint does not resolve is absent from the output."""
        ids = {m["id"] for m in loaded_outputs["registry_promotion.json"]["obj"]["models"]}
        assert "model-broken-ref" not in ids

    def test_promoted_decision(self, loaded_outputs):
        """A registry entry with a kept candidate, approved review, no retry/eval gate failure, is promoted."""
        mods = {m["id"]: m for m in loaded_outputs["registry_promotion.json"]["obj"]["models"]}
        assert mods["model-classify-clicks"]["decision"] == "promoted"
        assert mods["model-classify-clicks"]["reason"] == "ok"

    def test_promoted_after_compromise_lift(self, loaded_outputs):
        """A candidate from a run on a lifted dataset (with no invalidating retract) should remain eligible for promotion."""
        mods = {m["id"]: m for m in loaded_outputs["registry_promotion.json"]["obj"]["models"]}
        assert mods["model-cleared-deploy"]["decision"] == "promoted"

    def test_research_tolerance_allows_borderline_replay_run(self, loaded_outputs):
        """A research-tier run near replay boundary should not be rejected via unstable candidate."""
        mods = {m["id"]: m for m in loaded_outputs["registry_promotion.json"]["obj"]["models"]}
        assert mods["model-rd-classifier"]["decision"] == "promoted"

    def test_force_rejected_compromise(self, loaded_outputs):
        """A registry entry whose candidate is quarantine_tainted is force_rejected_compromise."""
        mods = {m["id"]: m for m in loaded_outputs["registry_promotion.json"]["obj"]["models"]}
        assert mods["model-rank-clicks"]["decision"] == "force_rejected_compromise"

    def test_force_rejected_compromise_via_retract(self, loaded_outputs):
        """A registry entry whose candidate's parent run is tainted by a retract-resurfaced compromise must also be force_rejected_compromise."""
        mods = {m["id"]: m for m in loaded_outputs["registry_promotion.json"]["obj"]["models"]}
        assert mods["model-retracted"]["decision"] == "force_rejected_compromise"

    def test_rejected_revoked_signature(self, loaded_outputs):
        """A registry entry whose candidate is quarantine_revoked_key is rejected_revoked_signature."""
        mods = {m["id"]: m for m in loaded_outputs["registry_promotion.json"]["obj"]["models"]}
        assert mods["model-search-v2"]["decision"] == "rejected_revoked_signature"

    def test_rejected_unstable_candidate(self, loaded_outputs):
        """A registry entry whose candidate is quarantine_unstable_run is rejected_unstable_candidate."""
        mods = {m["id"]: m for m in loaded_outputs["registry_promotion.json"]["obj"]["models"]}
        assert mods["model-summarize-v1"]["decision"] == "rejected_unstable_candidate"

    def test_rejected_unstable_candidate_from_runtime_exceeded(self, loaded_outputs):
        """A registry entry whose candidate's parent run is runtime_exceeded must also be rejected_unstable_candidate."""
        mods = {m["id"]: m for m in loaded_outputs["registry_promotion.json"]["obj"]["models"]}
        assert mods["model-runtime-blown"]["decision"] == "rejected_unstable_candidate"

    def test_rejected_lowscore_candidate(self, loaded_outputs):
        """A registry entry whose candidate is quarantine_lowscore is rejected_lowscore_candidate."""
        mods = {m["id"]: m for m in loaded_outputs["registry_promotion.json"]["obj"]["models"]}
        assert mods["model-classify-text"]["decision"] == "rejected_lowscore_candidate"

    def test_rejected_review(self, loaded_outputs):
        """A registry entry on a kept candidate with governance_review_status=rejected is rejected_review."""
        mods = {m["id"]: m for m in loaded_outputs["registry_promotion.json"]["obj"]["models"]}
        assert mods["model-deboost"]["decision"] == "rejected_review"

    def test_rejected_review_pending(self, loaded_outputs):
        """A registry entry on a kept candidate with governance_review_status=pending is rejected_review_pending."""
        mods = {m["id"]: m for m in loaded_outputs["registry_promotion.json"]["obj"]["models"]}
        assert mods["model-pending-promo"]["decision"] == "rejected_review_pending"

    def test_rejected_raw_base_tier_for_staging(self, loaded_outputs):
        """When the target tier sets requires_clean_dataset_lineage true, a kept candidate whose parent run uses a raw-tier base dataset is rejected_raw_base_tier."""
        mods = {m["id"]: m for m in loaded_outputs["registry_promotion.json"]["obj"]["models"]}
        m = mods["model-staging-raw-hygiene"]
        assert m["decision"] == "rejected_raw_base_tier"
        assert m["reason"] == "rejected_raw_base_tier_via_ckpt-S"

    def test_rejected_retry_cap_with_observed_count(self, loaded_outputs):
        """A registry entry whose parent run has retry_count_observed above the target tier's max is rejected_retry_cap, naming both numbers."""
        mods = {m["id"]: m for m in loaded_outputs["registry_promotion.json"]["obj"]["models"]}
        assert mods["model-retry-stress"]["decision"] == "rejected_retry_cap"
        assert "observed_5_max_3" in mods["model-retry-stress"]["reason"]

    def test_rejected_eval_floor_with_formatted_numbers(self, loaded_outputs):
        """A registry entry whose parent run's claimed_eval_metric is below the target tier's min_eval_floor is rejected_eval_floor."""
        mods = {m["id"]: m for m in loaded_outputs["registry_promotion.json"]["obj"]["models"]}
        assert mods["model-eval-low"]["decision"] == "rejected_eval_floor"
        assert re.search(r"observed_0\.\d{4}_floor_0\.\d{4}", mods["model-eval-low"]["reason"])

    def test_applied_eval_floor_matches_target_tier(self, loaded_outputs):
        """applied_eval_floor must equal governance_config.tiers[target_tier].min_eval_floor."""
        floors_by_tier = {"research": 0.5, "staging": 0.7, "prod": 0.85}
        for m in loaded_outputs["registry_promotion.json"]["obj"]["models"]:
            assert m["applied_eval_floor"] == floors_by_tier[m["target_tier"]]

    def test_rejected_lineage_floor_with_integer_numbers(self, loaded_outputs):
        """A registry entry whose parent run's base_dataset lineage_depth is below the target tier's min_lineage_depth is rejected_lineage_floor, with both observed and min as plain integers."""
        mods = {m["id"]: m for m in loaded_outputs["registry_promotion.json"]["obj"]["models"]}
        assert mods["model-prod-launch"]["decision"] == "rejected_lineage_floor"
        assert re.search(
            r"rejected_lineage_floor_observed_\d+_min_\d+",
            mods["model-prod-launch"]["reason"],
        )

    def test_lineage_floor_gate_fires_between_retry_and_eval_floor(self, loaded_outputs):
        """The lineage_floor gate must fire strictly after retry_cap and the raw-base hygiene gate but strictly before eval_floor; a candidate that would otherwise hit eval_floor must hit lineage_floor first when both apply."""
        mods = {m["id"]: m for m in loaded_outputs["registry_promotion.json"]["obj"]["models"]}
        m = mods["model-prod-launch"]
        assert m["decision"] == "rejected_lineage_floor"
        assert m["target_tier"] == "prod"
        assert m["applied_eval_floor"] == 0.85

    def test_rejected_audit_pending_uses_age_and_min(self, loaded_outputs):
        """A registry entry whose parent run started fewer than tiers[target_tier].min_audit_age_days days before current_day is rejected_audit_pending."""
        mods = {m["id"]: m for m in loaded_outputs["registry_promotion.json"]["obj"]["models"]}
        assert mods["model-fresh-staging"]["decision"] == "rejected_audit_pending"
        assert re.search(
            r"rejected_audit_pending_age_\d+_min_\d+",
            mods["model-fresh-staging"]["reason"],
        )

    def test_audit_age_gate_fires_after_eval_floor(self, loaded_outputs):
        """The audit-age gate must fire only after every higher-precedence rejection has been ruled out; a sufficiently old approved candidate must therefore reach `promoted` even when its tier's min_audit_age_days is non-zero."""
        mods = {m["id"]: m for m in loaded_outputs["registry_promotion.json"]["obj"]["models"]}
        assert mods["model-classify-clicks"]["decision"] == "promoted"


class TestSummary:
    """Summary totals, breakdowns, and the compromised_run_ids list must agree with the other four outputs."""

    def test_totals_hash(self, loaded_outputs):
        """The totals sub-object must match the locked canonical hash."""
        assert _canonical_sha256(loaded_outputs["summary.json"]["obj"]["totals"]) == \
            EXPECTED_FIELD_HASHES["summary.totals"]

    def test_by_run_status_hash(self, loaded_outputs):
        """by_run_status counts must match the locked canonical hash."""
        assert _canonical_sha256(loaded_outputs["summary.json"]["obj"]["by_run_status"]) == \
            EXPECTED_FIELD_HASHES["summary.by_run_status"]

    def test_by_compromise_status_hash(self, loaded_outputs):
        """by_compromise_status counts must match the locked canonical hash."""
        assert _canonical_sha256(loaded_outputs["summary.json"]["obj"]["by_compromise_status"]) == \
            EXPECTED_FIELD_HASHES["summary.by_compromise_status"]

    def test_by_disposition_hash(self, loaded_outputs):
        """by_disposition counts must match the locked canonical hash."""
        assert _canonical_sha256(loaded_outputs["summary.json"]["obj"]["by_disposition"]) == \
            EXPECTED_FIELD_HASHES["summary.by_disposition"]

    def test_by_decision_hash(self, loaded_outputs):
        """by_decision counts must match the locked canonical hash."""
        assert _canonical_sha256(loaded_outputs["summary.json"]["obj"]["by_decision"]) == \
            EXPECTED_FIELD_HASHES["summary.by_decision"]

    def test_compromised_run_ids_hash(self, loaded_outputs):
        """compromised_run_ids must match the locked canonical hash."""
        assert _canonical_sha256(loaded_outputs["summary.json"]["obj"]["compromised_run_ids"]) == \
            EXPECTED_FIELD_HASHES["summary.compromised_run_ids"]

    def test_compromised_run_ids_is_sorted_and_matches_run_status(self, loaded_outputs):
        """compromised_run_ids must be the sorted-ascending set of run ids whose status is tainted_run."""
        tainted_runs = sorted(
            r["id"] for r in loaded_outputs["run_status.json"]["obj"]["runs"]
            if r["status"] == "tainted_run"
        )
        assert loaded_outputs["summary.json"]["obj"]["compromised_run_ids"] == tainted_runs

    def test_run_status_totals_match_run_status_file(self, loaded_outputs):
        """by_run_status counts must sum to the number of valid runs in run_status.json."""
        bys = loaded_outputs["summary.json"]["obj"]["by_run_status"]
        total_runs = len(loaded_outputs["run_status.json"]["obj"]["runs"])
        assert sum(bys.values()) == total_runs

    def test_disposition_totals_match_checkpoint_file(self, loaded_outputs):
        """by_disposition counts must sum to the number of valid checkpoints."""
        bys = loaded_outputs["summary.json"]["obj"]["by_disposition"]
        total_ckpts = len(loaded_outputs["checkpoint_disposition.json"]["obj"]["checkpoints"])
        assert sum(bys.values()) == total_ckpts

    def test_decision_totals_match_registry_file(self, loaded_outputs):
        """by_decision counts must sum to the number of valid registry entries."""
        bys = loaded_outputs["summary.json"]["obj"]["by_decision"]
        total_models = len(loaded_outputs["registry_promotion.json"]["obj"]["models"])
        assert sum(bys.values()) == total_models

    def test_ignored_incident_events_count(self, loaded_outputs):
        """The ignored_incident_events counter must include every event that fails any acceptance rule, including those referencing invalid runs and any unresolved or future-dated retract events."""
        assert loaded_outputs["summary.json"]["obj"]["totals"]["ignored_incident_events"] == 10

    def test_all_enum_keys_present(self, loaded_outputs):
        """Every documented enum value must appear as a key with an integer value (zero if absent)."""
        s = loaded_outputs["summary.json"]["obj"]
        for k in ("succeeded", "failed", "aborted", "inherited_invalid",
                  "replay_mismatch", "runtime_exceeded", "tainted_run"):
            assert isinstance(s["by_run_status"][k], int)
        for k in ("clean", "compromised", "cyclic"):
            assert isinstance(s["by_compromise_status"][k], int)
        for k in ("keep", "quarantine_lowscore", "quarantine_unstable_run",
                  "quarantine_revoked_key", "quarantine_tainted"):
            assert isinstance(s["by_disposition"][k], int)
        for k in ("promoted", "rejected_audit_pending", "rejected_eval_floor",
                  "rejected_lineage_floor", "rejected_raw_base_tier", "rejected_retry_cap",
                  "rejected_review", "rejected_review_pending", "rejected_lowscore_candidate",
                  "rejected_unstable_candidate", "rejected_revoked_signature",
                  "force_rejected_compromise"):
            assert isinstance(s["by_decision"][k], int)

    def test_current_day_hash(self, loaded_outputs):
        """current_day must match the locked canonical hash."""
        assert _canonical_sha256(loaded_outputs["summary.json"]["obj"]["current_day"]) == \
            EXPECTED_FIELD_HASHES["summary.current_day"]

    def test_ledger_version_hash(self, loaded_outputs):
        """ledger_version must match the locked canonical hash."""
        assert _canonical_sha256(loaded_outputs["summary.json"]["obj"]["ledger_version"]) == \
            EXPECTED_FIELD_HASHES["summary.ledger_version"]
