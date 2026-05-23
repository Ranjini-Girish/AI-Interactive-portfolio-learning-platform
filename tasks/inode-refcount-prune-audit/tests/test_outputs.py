# scaffold-status: oracle-pending
"""Verifier suite for inode-refcount-prune-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("IRP_DATA_DIR", "/app/inoderef"))
AUDIT_DIR = Path(os.environ.get("IRP_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ('inode_states.json', 'parent_rollups.json', 'pin_report.json', 'prune_plan.json', 'summary.json')

EXPECTED_INPUT_HASHES = {
    "anchors/a1.txt": "f4921416950240a66e5ed288f06440315cb5d561f88441db9029008c324081b6",
    "anchors/a2.txt": "f4921416950240a66e5ed288f06440315cb5d561f88441db9029008c324081b6",
    "ancillary/meta.json": "6cc9f8843dad734657ec42e1462cc1195b6b68887af88e3fd5f748f54de79339",
    "ancillary/notes.json": "e0f5fcae30068156d37c73608f46020562e6e97bb4d89e3240ffd041cb2d6fcf",
    "epochs.json": "74d0df6b2da068335c9f47cea7a106bda059a331139ac65ba0f0f6873fad0aa0",
    "grid/dims.json": "59e2181df33492f98008f5cbc12af8976756ead8b59550500b5863b7b4e6346f",
    "inodes/i01.json": "490a47de8c69e9be89197a8e5840c3d6dbe5529e2e916f2a0e6aeb569a475999",
    "inodes/i02.json": "4cb41db02e779141de2c77a2308562b904b5b2c43fff96e5fbd6837707f89de0",
    "inodes/i03.json": "3c6bedd1a1dcfd7f88c308f3485a5174799d605708c477f273b9a25a9c20f6ce",
    "inodes/i04.json": "66e6b7595697a8e48cfea2ecd13fcdf4480eee607d0823b999bd75e30509cb74",
    "inodes/i05.json": "d70afd74fbe5945e18ce789a54b3ed077c62174dfd46fc422b666add1fa0c933",
    "inodes/i06.json": "8c63faa86fbeb65a6888cf22737d69cbd0d9cb8d3989fef4b98b068227072eb3",
    "inodes/i07.json": "3d249681bc534b6d9c4a7eed02cf541ba5c84a2782d7efc6e09de128501adef9",
    "inodes/i08.json": "278f9f9c406ece3d9e55c37ae4edfa7135dd2184ccd688979a4ca1eb6f6cc13b",
    "inodes/i09.json": "dd7d4fd769280484cbc98584430266c35a32ff6bf002226312a30aca3988296e",
    "inodes/i10.json": "5d93aeb6c8b030f3f38cfe9da9f4d0873ccbe106dc908af3ae40bd3ad02f2def",
    "inodes/i11.json": "3c728f937a23b7ef91da8ba4ceded918a8ffa099e8f65d2499c1e2eb3ca2cfb5",
    "inodes/i12.json": "e32fe6b0e26bb8b61ff151359ef498a2d04638dfe241a7a7fe319010ed8fed84",
    "manifest.json": "cb9d089f14f739a0d3e36684aec034d813592c0119e78b7cde22b055506a21a6",
    "meta/seq.json": "5f13187a33f202a8e711072610ef96aabfc4906f846beba6e67f8ce44056f56e",
    "pins.json": "7e4499d3fadf0281c1892efa6505275f7cc8bad8efe0ace77911a7b08df56d76",
    "policy.json": "9325d8a7782c490483cb46581aa75639baf5d80ba14cf78d8291e511d4b6f1ff",
    "SPEC.md": "7f8f1a76c89436253fcf0d74598ef6bfa5479d56e6d9c791448a1f4d92e38a16"
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "inode_states.json": "9d314bbfa26cbf4353a8a55132a7355db5bec0a0d1f43a66b4b927ffc2b1a0ed",
    "parent_rollups.json": "a612327eaff9ada03b031dab422155db07033b2da00b845101c48045cddd33ea",
    "pin_report.json": "541e97efb112a7e1cba7f2dae04ecd86ef33535a8a1c1429210e805127f52196",
    "prune_plan.json": "d2e2ff734da7cd6e4595eacabb433a0f4c267519dcc36c1d763c2f6ca16c1b06",
    "summary.json": "9953f515a9f73a3045d8b92f6fe80847765f677a6d30a54a0849ec8e82b62b99"
}

EXPECTED_OUTPUT_RAW_HASHES = {
    "inode_states.json": "e0e274805da8515337c105ec732ef4f573039526ddfc381cba8131583a4ef0b6",
    "parent_rollups.json": "3d6064c4cf7d376692c9305d760e09deb12fda72df933904dea623626e2e5248",
    "pin_report.json": "d95739de1da9d3406d388f3ec88ca1b6494a73475d3163e46655f84f3f3f0134",
    "prune_plan.json": "84639da86792fbd0f9efb3310f2de704ae80598084d2612cf7336d1f8be709b8",
    "summary.json": "56e09d174f7d6507aa79dc08e4790e83564a1a42a0c946a41c79140488c43637"
}

EXPECTED_FIELD_HASHES = {
    "inode_states.i07": "3a64ecbc90d36eed6ecd1da0f418ffe4978f62da84f658084a708650eaa4489b",
    "summary.effective_threshold": "2c624232cdd221771294dfbb310aca000a0df6ac8b66b696d90ef06fdefb64a3"
}


def _sha256_bytes(data: bytes) -> str:
    """Return hex SHA-256 of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    """Minified canonical JSON for hash comparison."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _load_json(path: Path) -> object:
    """Load UTF-8 JSON from path."""
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

    def test_output_raw_byte_hashes(self) -> None:
        """Each audit file UTF-8 bytes must match normative layout."""
        for name, expected in EXPECTED_OUTPUT_RAW_HASHES.items():
            digest = _sha256_bytes((AUDIT_DIR / name).read_bytes())
            assert digest == expected, f"raw byte mismatch for {name}"

    def test_output_canonical_hashes(self, outputs: dict[str, object]) -> None:
        """Each audit file must match the canonical minified JSON digest."""
        for name, expected in EXPECTED_OUTPUT_CANONICAL_HASHES.items():
            canon = _canonical(outputs[name])
            digest = _sha256_bytes(canon.encode("utf-8"))
            assert digest == expected, f"output mismatch for {name}"

    def test_output_files_single_trailing_newline(self) -> None:
        """Root JSON objects must end with exactly one line feed after the closing brace."""
        for name in OUTPUT_FILES:
            raw = (AUDIT_DIR / name).read_text(encoding="utf-8")
            assert raw.endswith("}\n"), f"{name} must end with exactly one LF after root brace"

    def test_field_hashes(self, outputs: dict[str, object]) -> None:
        """Selected nested fields must match pinned canonical digests."""
        for key, expected in EXPECTED_FIELD_HASHES.items():
            top, field = key.split(".", 1)
            if top == "job_states":
                jobs = {r["job_id"]: r for r in outputs["job_states.json"]["jobs"]}
                val = jobs[field]
            elif top == "inode_states":
                nodes = {r["inode_id"]: r for r in outputs["inode_states.json"]["inodes"]}
                val = nodes[field]
            else:
                val = outputs["summary.json"][field]
            assert _sha256_bytes(_canonical(val).encode()) == expected


class TestInodeSemantics:
    """Semantic checks for shared refs, pins, frozen epochs, and orphans."""

    def test_i03_pruned_with_shared_ref(self, outputs: dict[str, object]) -> None:
        """A parent whose children contribute enough shared ref must be pruned."""
        nodes = {r["inode_id"]: r for r in outputs["inode_states.json"]["inodes"]}
        assert nodes["i03"]["status"] == "pruned"

    def test_i09_pinned_status(self, outputs: dict[str, object]) -> None:
        """Pinned inode ids must remain pinned regardless of refcount."""
        nodes = {r["inode_id"]: r for r in outputs["inode_states.json"]["inodes"]}
        assert nodes["i09"]["status"] == "pinned"

    def test_i11_frozen_status(self, outputs: dict[str, object]) -> None:
        """Epochs below current_epoch-1 must be frozen."""
        nodes = {r["inode_id"]: r for r in outputs["inode_states.json"]["inodes"]}
        assert nodes["i11"]["status"] == "frozen"

    def test_i07_orphan_inode_status(self, outputs: dict[str, object]) -> None:
        """A parent_id pointing outside the inode set must be orphan_inode."""
        nodes = {r["inode_id"]: r for r in outputs["inode_states.json"]["inodes"]}
        assert nodes["i07"]["status"] == "orphan_inode"

    def test_store_mismatch_raises_threshold(self, outputs: dict[str, object]) -> None:
        """Mismatched store tags must raise the effective prune threshold in summary."""
        assert outputs["summary.json"]["effective_threshold"] == 8
