"""Verifier suite for the i2c-mux-shadow-audit task.

These checks enforce the published contract in ``instruction.md`` and the
normative rules in ``/app/i2c_bus/SPEC.md``. Hash-locked fixtures bind the
inputs and the canonical JSON outputs so agents cannot pass by mutating the
dataset or by hand-tuning bytes without implementing the Go auditor described
in the prompt.
"""

from __future__ import annotations

import collections
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

BUS_DIR = Path(os.environ.get("IMX_BUS_DIR", "/app/i2c_bus"))
AUDIT_DIR = Path(os.environ.get("IMX_AUDIT_DIR", "/app/audit"))
SRC_DIR = Path(os.environ.get("IMX_SRC_DIR", "/app/src"))
BIN_PATH = Path(os.environ.get("IMX_BIN_PATH", "/app/bin/i2caudit"))

REQUIRED_OUTPUT_FILES = [
    "node_status.json",
    "collision_edges.json",
    "segment_ledger.json",
    "timing_merge.json",
    "summary.json",
]

EXPECTED_INPUT_HASHES = {
    "SPEC.md": "87ecdef2e698be4469787ea419080069bba338729f6d9207e7ce810846f8e55a",
    "clock.tsv": "caa177487355c8d20225657f1ebcd0785f6f422ff23cd3475b92d3e2f2bedbe4",
    "incidents.tsv": "daf3387a3d00fdb30137141e1961aac650b18027cf6e013214e36d516fe7afe7",
    "nodes.tsv": "5b1c9866edc4375127f0784606426ad7811701b5925d6ea33c3a0d9afa7cf83b",
    "policy.tsv": "25227518654c4f621f274cd2d53ca2ef051fa69858583b9cd41570ad77a59877",
    "probes/p01.tsv": "581744c0f9a93d16871fe36fae97668bda4b515f651df1168e7b0a576a28b5fc",
    "probes/p02.tsv": "3a8247860e7964005ba11acb47605d8619af35daec7513853ff0ff502c7b6047",
    "probes/p03.tsv": "2652ea5e712d7af4b89f4691f55f53147dc5f298046319eccd772e048d9ab75e",
    "probes/p04.tsv": "4254eba37268834f8fd191597ace88e0dd85cc0c03f5b4f28e08ecc6f068d182",
    "probes/p05.tsv": "04fa97e97ad1f19090bcc3e0c3fbb92e3697c19c8cf3d124fb9f63e4bc7e0f5c",
    "probes/p06.tsv": "9243d9f5d7e83f3cebf004680d90cc85517b6c48cab4e4dadb3e75b83568f624",
    "probes/p07.tsv": "56780489ade4373e0050bff346f9a6d772521fd6978d32fca030a36bf9c61cd5",
    "probes/p08.tsv": "833680bad14381083fe91717ef49d511d8ffdd7202c3751da9f396489bc6a940",
    "probes/p09.tsv": "7c82f375e73bf255d95f785c894f51abef07291d9a2fd3944f922c82ff2fa167",
    "probes/p10.tsv": "88acb98b9249cf000b75bc5134b4eb3b7f8c3f3a0228dc6a8b3036ea33ae7f01",
    "probes/p11.tsv": "df82f69a809c3a754556c4987a5ac99ed672d185bc8a1e3333ccb9047583c622",
    "probes/p12.tsv": "4477fdc40cd296fcf4d0a09c984e330ec7b9343adc11632e7df65959ac87e5bc",
    "probes/p13.tsv": "a3c7508314ae2b6a5e1bf577f4b848249086ef83966a393afe39822fe25e8d5a",
    "probes/p14.tsv": "9a78a3d76d09b1830d179602d9a3234beff94f5687f041efe7c1c43d21419aac",
    "probes/p15.tsv": "b0a992be1f34cf772e418f8ef6e355dd3f8aba6790f005dbe11b3efaf0a25c44",
    "probes/p16.tsv": "624845cc7955b520a0fd97e5a0b5bf9c6183497bb9b81ef82445984365db8930",
    "probes/p17.tsv": "170d969210eb41b64dd5f4ee3c60b536f1ed7bb1e2909fd76a48ae7466ba44d0",
    "probes/p18.tsv": "dd1af5f624abf58c9b14a3e23135ad44cd315152453de9476db011ebd5f4c35a",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "node_status.json": "41ad9130e876f733bbd1942c6f36573213a16503c4986ba7ccac5b67c1f5cbdd",
    "collision_edges.json": "1a8f498038a8848bc2be18174536d932ec253f53f7535994477e237bce429c3f",
    "segment_ledger.json": "b3e4bf9eb8d597162c454f89829eac1e2a1b9e110b6e64c6c2d1200f5aefcf86",
    "timing_merge.json": "b1c9aa97e5b44ef3cc27ba8f5bf8bf7b89802933d31a2a2bfe9025462658cd70",
    "summary.json": "f427a84a8035a5e5416156402984305d2e364577eb6941bd3604131a3175a8f2",
}

EXPECTED_FIELD_HASHES = {
    "collision_edges.edges": "47a70b2df773aeee3536525d611e666e21e162356c89983d48a9cde31ee07dfe",
    "node_status.nodes": "7d9f44777952e37c7c885fc2219c84ecf0a80a7d7cc85d506db20275ae1ac73e",
    "segment_ledger.segments": "ece08e0639a29699794a9b6ff2f4124a97b22dd021d2aa2203de2f8ec72a44e0",
    "summary.collision_edge_count": "7de1555df0c2700329e815b93b32c571c3ea54dc967b89e81ab73b9972b72d1d",
    "summary.frozen_segments": "4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865",
    "summary.ignored_incident_events": "06e9d52c1720fca412803e3b07c4b228ff113e303f4c7ab94665319d832bbfb7",
    "summary.nodes_by_status": "22b74a88948c54790be63706260ff0095a5d6b886022dbee020a8e8e210c1eda",
    "summary.quarantined_nodes": "53c234e5e8472b6ac51c1ae1cab3fe06fad053beb8ebfd8977b010655bfdd3c3",
    "timing_merge.nodes": "ae9430daec58180babb888fd5458c687a2c4879ac96efa75326b3744b88b99fc",
}


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _canonical_bytes(obj: object) -> bytes:
    return (
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _canonical_sha256(obj: object) -> str:
    return _sha256_bytes(_canonical_bytes(obj))


@pytest.fixture(scope="module")
def loaded_outputs():
    out: dict = {}
    for name in REQUIRED_OUTPUT_FILES:
        p = AUDIT_DIR / name
        assert p.is_file(), f"missing required output file: /app/audit/{name}"
        text = p.read_text(encoding="utf-8")
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as e:
            pytest.fail(f"output /app/audit/{name} is not valid JSON: {e}")
        out[name] = {"text": text, "obj": obj, "bytes": text.encode("utf-8")}
    return out


class TestInputIntegrity:
    """The dataset under ``/app/i2c_bus/`` must remain byte-identical to the
    shipped fixtures for the duration of the agent run."""

    @pytest.mark.parametrize("rel", list(EXPECTED_INPUT_HASHES.keys()))
    def test_input_file_unchanged(self, rel: str):
        """Each fixture file's SHA-256 digest must match the pinned value."""
        path = BUS_DIR / rel
        assert path.is_file(), f"required input file missing: {path}"
        actual = _sha256_bytes(path.read_bytes())
        expected = EXPECTED_INPUT_HASHES[rel]
        assert actual == expected, (
            f"input file /app/i2c_bus/{rel} was modified during execution "
            f"(expected {expected}, got {actual})"
        )


class TestOutputStructure:
    """Shape, encoding, and hash locks for the five audit JSON files."""

    def test_audit_directory_exists(self):
        """``/app/audit`` must exist as a directory after the agent runs."""
        assert AUDIT_DIR.is_dir(), "/app/audit must exist as a directory"

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_output_file_exists(self, name: str):
        """Each required output file must exist under ``/app/audit/``."""
        assert (AUDIT_DIR / name).is_file(), f"missing /app/audit/{name}"

    def test_no_extra_files_in_audit_dir(self):
        """``/app/audit/`` must contain exactly the five required files."""
        actual = sorted(p.name for p in AUDIT_DIR.iterdir() if p.is_file())
        assert actual == sorted(REQUIRED_OUTPUT_FILES), (
            f"/app/audit must contain exactly {sorted(REQUIRED_OUTPUT_FILES)}; found {actual}"
        )

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_output_ends_with_single_newline(self, loaded_outputs, name: str):
        """Each output file ends with exactly one trailing newline."""
        b = loaded_outputs[name]["bytes"]
        assert b.endswith(b"\n"), f"{name} must end with a trailing newline"
        assert not b.endswith(b"\n\n"), f"{name} must end with exactly one trailing newline"

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_output_matches_canonical_pretty_form(self, loaded_outputs, name: str):
        """On-disk bytes must match ``json.dumps(..., indent=2, sort_keys=True)``."""
        obj = loaded_outputs[name]["obj"]
        expected_bytes = (
            json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        ).encode("utf-8")
        actual_bytes = loaded_outputs[name]["bytes"]
        assert actual_bytes == expected_bytes, (
            f"/app/audit/{name} bytes do not match canonical pretty JSON encoding"
        )

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_object_keys_sorted_on_disk(self, name: str):
        """Every nested JSON object must serialize keys in sorted order."""
        path = AUDIT_DIR / name
        ordered = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=collections.OrderedDict,
        )
        violations: list[str] = []

        def walk(node: object, path_str: str) -> None:
            if isinstance(node, collections.OrderedDict):
                keys = list(node.keys())
                if keys != sorted(keys):
                    violations.append(
                        f"{path_str}: keys not sorted; got {keys}, expected {sorted(keys)}"
                    )
                for key, value in node.items():
                    walk(value, f"{path_str}.{key}")
            elif isinstance(node, list):
                for index, item in enumerate(node):
                    walk(item, f"{path_str}[{index}]")

        walk(ordered, name)
        assert not violations, "key-order violations:\n  - " + "\n  - ".join(violations)

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_output_canonical_hash(self, loaded_outputs, name: str):
        """Compact canonical SHA-256 must match the pinned reference."""
        actual = _canonical_sha256(loaded_outputs[name]["obj"])
        expected = EXPECTED_OUTPUT_CANONICAL_HASHES[name]
        assert actual == expected, f"/app/audit/{name} canonical SHA-256 mismatch"


class TestSummaryFields:
    """Pinned scalar and map fragments inside ``summary.json``."""

    @pytest.mark.parametrize(
        "key",
        [
            "collision_edge_count",
            "frozen_segments",
            "ignored_incident_events",
            "nodes_by_status",
            "quarantined_nodes",
        ],
    )
    def test_summary_field_hash(self, loaded_outputs, key: str):
        """Each documented ``summary`` field must match its canonical digest."""
        summary = loaded_outputs["summary.json"]["obj"]
        value = summary[key]
        actual = _canonical_sha256(value)
        field_key = f"summary.{key}"
        assert actual == EXPECTED_FIELD_HASHES[field_key], (
            f"summary.{key} canonical SHA-256 mismatch (expected {EXPECTED_FIELD_HASHES[field_key]})"
        )


class TestArrayFieldHashes:
    """Large array outputs are pinned independently of the surrounding file."""

    def test_node_status_nodes_hash(self, loaded_outputs):
        """``node_status.nodes`` must match the pinned canonical hash."""
        nodes = loaded_outputs["node_status.json"]["obj"]["nodes"]
        assert _canonical_sha256(nodes) == EXPECTED_FIELD_HASHES["node_status.nodes"]

    def test_collision_edges_hash(self, loaded_outputs):
        """``collision_edges.edges`` must match the pinned canonical hash."""
        edges = loaded_outputs["collision_edges.json"]["obj"]["edges"]
        assert _canonical_sha256(edges) == EXPECTED_FIELD_HASHES["collision_edges.edges"]

    def test_segment_ledger_hash(self, loaded_outputs):
        """``segment_ledger.segments`` must match the pinned canonical hash."""
        segs = loaded_outputs["segment_ledger.json"]["obj"]["segments"]
        assert _canonical_sha256(segs) == EXPECTED_FIELD_HASHES["segment_ledger.segments"]

    def test_timing_merge_hash(self, loaded_outputs):
        """``timing_merge.nodes`` must match the pinned canonical hash."""
        nodes = loaded_outputs["timing_merge.json"]["obj"]["nodes"]
        assert _canonical_sha256(nodes) == EXPECTED_FIELD_HASHES["timing_merge.nodes"]


class TestStatusCoverage:
    """The bundled dataset reaches every documented node status string."""

    def _by_status(self, loaded_outputs, st: str):
        return [
            n
            for n in loaded_outputs["node_status.json"]["obj"]["nodes"]
            if n["status"] == st
        ]

    def test_active_status_present(self, loaded_outputs):
        """At least one node must finish in ``active`` state."""
        assert self._by_status(loaded_outputs, "active"), "expected at least one active node"

    def test_shadowed_status_present(self, loaded_outputs):
        """Collision losers must surface as ``shadowed``."""
        assert self._by_status(loaded_outputs, "shadowed"), "expected shadowed collision losers"

    def test_quarantined_status_present(self, loaded_outputs):
        """Quarantine must mark the compromised hub and its descendant."""
        rows = self._by_status(loaded_outputs, "quarantined")
        assert {r["node_id"] for r in rows} >= {
            "n_quarantine_hub",
            "n_quarantine_child",
        }

    def test_frozen_status_present(self, loaded_outputs):
        """Mux freeze must mark the node on the frozen segment."""
        rows = self._by_status(loaded_outputs, "frozen")
        assert any(r["node_id"] == "n_frozen" for r in rows)

    def test_degraded_status_present(self, loaded_outputs):
        """A winning ``nak_burst`` must degrade an otherwise healthy node."""
        rows = self._by_status(loaded_outputs, "degraded")
        assert any(r["node_id"] == "n_lonely" for r in rows)


class TestImplementationLanguage:
    """The deliverable must be a Go-built ELF at ``/app/bin/i2caudit``."""

    def test_go_source_present(self):
        """``/app/src`` must contain Go sources with ``package main``."""
        assert SRC_DIR.is_dir(), f"{SRC_DIR} must exist"
        go_files = list(SRC_DIR.rglob("*.go"))
        assert go_files, f"no .go files under {SRC_DIR}"
        has_main = False
        for gf in go_files:
            text = gf.read_text(encoding="utf-8", errors="replace")
            if re.search(r"^\s*package\s+main\b", text, re.MULTILINE):
                has_main = True
                break
        assert has_main, "no Go file under /app/src declares package main"

    def test_binary_present(self):
        """The compiled auditor must exist and be executable."""
        assert BIN_PATH.is_file(), f"{BIN_PATH} must exist"
        assert os.access(BIN_PATH, os.X_OK), f"{BIN_PATH} must be executable"

    def test_binary_is_native_elf_executable(self):
        """Reject script wrappers masquerading as the auditor binary."""
        head = BIN_PATH.read_bytes()[:4]
        assert head != b"#!/b" and head != b"#!/u" and head != b"#!/p"
        assert head == b"\x7fELF", f"{BIN_PATH} must be an ELF executable (header={head!r})"

    def test_binary_built_from_go(self):
        """The ELF must embed Go toolchain metadata."""
        go_bin = shutil.which("go")
        if go_bin:
            result = subprocess.run(
                [go_bin, "version", "-m", str(BIN_PATH)],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            first_line = (result.stdout or "").splitlines()[0] if result.stdout else ""
            assert result.returncode == 0 and re.search(r"\bgo1\.\d+", first_line), (
                f"go version -m did not identify a Go binary (rc={result.returncode}, line={first_line!r})"
            )
            assert "\tmod\t" in result.stdout or "\tpath\t" in result.stdout, (
                "go version -m did not report module/path build info"
            )
        else:
            data = BIN_PATH.read_bytes()
            assert (
                b"go.buildinfo" in data or b"Go build" in data or b"runtime.go" in data
            ), "missing Go build metadata"

    def test_binary_reproduces_audit(self):
        """Re-running the binary into a fresh directory must recreate the audit."""
        saved = {name: (AUDIT_DIR / name).read_bytes() for name in REQUIRED_OUTPUT_FILES}
        backup = AUDIT_DIR.parent / (AUDIT_DIR.name + ".anti_cheat_backup")
        if backup.exists():
            shutil.rmtree(backup)
        shutil.move(str(AUDIT_DIR), str(backup))
        try:
            with tempfile.TemporaryDirectory() as td:
                env = os.environ.copy()
                env["IMX_BUS_DIR"] = str(BUS_DIR)
                env["IMX_AUDIT_DIR"] = td
                res = subprocess.run(
                    [str(BIN_PATH)],
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                assert res.returncode == 0, (
                    f"binary rc={res.returncode}\nstdout:\n{res.stdout}\nstderr:\n{res.stderr}"
                )
                for name in REQUIRED_OUTPUT_FILES:
                    fresh = Path(td) / name
                    assert fresh.is_file(), f"missing {name} after rerun"
                    obj = json.loads(fresh.read_text(encoding="utf-8"))
                    assert _canonical_sha256(obj) == EXPECTED_OUTPUT_CANONICAL_HASHES[name]
                    assert fresh.read_bytes() == saved[name]
        finally:
            shutil.move(str(backup), str(AUDIT_DIR))
