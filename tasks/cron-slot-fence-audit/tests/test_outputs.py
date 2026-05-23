# scaffold-status: oracle-pending
"""Verifier suite for cron-slot-fence-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("CSF_DATA_DIR", "/app/cronfence"))
AUDIT_DIR = Path(os.environ.get("CSF_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ('blackout_hits.json', 'host_schedules.json', 'job_states.json', 'overlap_pairs.json', 'summary.json')

EXPECTED_INPUT_HASHES = {
    "anchors/a1.txt": "f4921416950240a66e5ed288f06440315cb5d561f88441db9029008c324081b6",
    "anchors/a2.txt": "f4921416950240a66e5ed288f06440315cb5d561f88441db9029008c324081b6",
    "ancillary/meta.json": "53b957e5e396c71aaf528fac246f1b8cf7bb4c249682b26acf59ebcc1e6d6626",
    "ancillary/notes.json": "e0f5fcae30068156d37c73608f46020562e6e97bb4d89e3240ffd041cb2d6fcf",
    "blackouts.json": "b703ad35e103a4064eb66360f3a69d1158eb24021908584575bf244fdefcacb7",
    "grid/dims.json": "59e2181df33492f98008f5cbc12af8976756ead8b59550500b5863b7b4e6346f",
    "hosts/h1.json": "4604723582e5295d8288c7644ef1a0857b10f1b144f09aedf9cfa4e5242cf447",
    "hosts/h2.json": "6f5c5b9e845072ec58c5f17ea1def9eff73bde3dcc91e011e68ef8a8e8347eac",
    "hosts/h3.json": "3c3f693ebd74608848092be4e876879199fc55321c9dc004f62bd69f7fed6328",
    "hosts/h4.json": "64b10a6b1ed649a2ec10b6c8695ae79cdc1040f292658a8681ad959c73613fa3",
    "hosts/h5.json": "19478f9f91d07edc75b50721e3d5936f3b94beb7a3c6a8b33886269540779458",
    "hosts/h6.json": "8e311293dd5d40bf304ac7e44a0710fd3dcb474874bb589fd2e81ddc203b83d5",
    "hosts/h7.json": "23938e7b4b8e0473d0788836bfbcedbbbce11b609d81025c6a6ef91f3dffc362",
    "jobs/shards/j01.json": "eb78f94e66ed7e438a590a1f01e49a41c83d9699ea7d94c41955890e2ed77930",
    "jobs/shards/j02.json": "8e06d2b5c3a08bb23e221368face73b5c720fb0837c41ab8ee2a95cc9dbe3b3d",
    "jobs/shards/j03.json": "b35ab4c08058cd5280dae8a5e5262c9a42bdf60c54d09b71b7c7e28302676038",
    "jobs/shards/j04.json": "b3dd837f6f2f3fb82dcb66cf594b6dda23bd32e80df95a9da5911503d0de71c0",
    "jobs/shards/j05.json": "7d25fb611a75fa90177ccf74561dd69d37d068927cfa6fb4bd4688bd0ff99b4f",
    "jobs/shards/j06.json": "78e6d6cca13b744da6959586aa858de33197339a743a2471ed0ab4ab80ab5e9b",
    "jobs/shards/j07.json": "0386290cfc2d9a63902e284a92703c3fc63172ca63fc68295a620e501e1de1ac",
    "jobs/shards/j08.json": "714476e03760a2cc9cfd766ca93dc636849d4e727b7a4c435b92ae95d478cf47",
    "jobs/shards/j09.json": "9db3d2af0593f981ad2716c98e5d9d38cd9260093be6b770a4216b65fee47d09",
    "jobs/shards/j10.json": "ab7aba2b0a44615b9193da0cd5532ae07062af23e463d4334561b25c0f55a58e",
    "jobs/shards/j11.json": "abec197662da0b863948367506ec2d44dd2dc3c1780a07ad9a3a9c638d66f817",
    "jobs/shards/j12.json": "f141e7a457f6e01faae587fabbb6d2e32094e928484bff89f185a8d532f71ad1",
    "jobs/shards/j13.json": "ca69b281a03fb9cc17275cbc9b6e2b16bbeab75b073fe9f86430923ad560df81",
    "jobs/shards/j14.json": "7ad73c38d81e0ace500f6023ff4b4eca197889bea6dcdabee545fa760e61de4c",
    "jobs/shards/j15.json": "79d5727a058392e210c1430ea82ca020faa41381e900b0743bee255f0239ad62",
    "jobs/shards/j16.json": "253269f2bf540317b0f5b058620d94913c1a99dc098adc7d320d5513557692e6",
    "jobs.json": "b1eff910da98cf46ee75f0eacf6b318dea81658a77d31947b9b9470baffd0b35",
    "manifest.json": "37e30c66db734c2cae34f9b9f8256bd3b25307570af7ba1b72ab7d9b9ff502c0",
    "meta/seq.json": "5f13187a33f202a8e711072610ef96aabfc4906f846beba6e67f8ce44056f56e",
    "policy.json": "dfb8357d08e934bf80a998689bc45d38928491281a1985f1f25572044537be7d",
    "SPEC.md": "26093b9b2b2985cb59613cde3b06682cf38b4b54f4cc0d8e4e85880c422987d6"
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "blackout_hits.json": "7989b3e4d341dcb2d20bcbe8fd7b936c03ad332c0656a265c69dcd92a9dacbc7",
    "host_schedules.json": "1e7fde13fd3916ec0cdf6b373b53a223d0177246c60c0f0877ddbacd6cf121d6",
    "job_states.json": "98056d9630c2e3b48f144a91bd342e5b607f3cdc67b5314fae6541747d21bf23",
    "overlap_pairs.json": "2f4be52a3b6be4dcd66fda47daabcdcd269a9a3636541c3bdb6afab70f922822",
    "summary.json": "5827557cb666a8c883aec83a111d07bee75da0ce53069f74384044aaa6c09d21"
}

EXPECTED_OUTPUT_RAW_HASHES = {
    "blackout_hits.json": "77045fdc23654580835c2eff9f6af413bbeea63587d0e0c4c4a54a1544dd54a7",
    "host_schedules.json": "ccf384895db9f3589f486e3f1cdfadf30bbd9677a7d7f9d50b01fca3e31c4f7f",
    "job_states.json": "cbea0a1f853ba6764eb9ce0e31371e029033dc1945a543085c2a694d3a623bb9",
    "overlap_pairs.json": "fca8183c4bd36b800df894752ada7d22cdf02b38b93bf2ddaabc5927fd877b3f",
    "summary.json": "5777cda8eeb95c76fa6402ffcd2da30c48d9e9172d3b1947e47e17c20dbbbcf3"
}

EXPECTED_FIELD_HASHES = {
    "job_states.j16": "ac40013531c08237b3e8359a2e20a414bdae054343002930f42bde28d98d5d3e",
    "summary.overlap_hard_total": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b"
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


class TestCronSemantics:
    """Semantic checks for zone boost, dependencies, overlaps, and blackouts."""

    def test_j16_overlap_hard_status(self, outputs: dict[str, object]) -> None:
        """High-priority overlap on host h7 must classify the later job as overlap_hard."""
        jobs = {r["job_id"]: r for r in outputs["job_states.json"]["jobs"]}
        assert jobs["j16"]["status"] == "overlap_hard"

    def test_j07_orphan_dep_status(self, outputs: dict[str, object]) -> None:
        """A dependency on a missing parent id must yield orphan_dep."""
        jobs = {r["job_id"]: r for r in outputs["job_states.json"]["jobs"]}
        assert jobs["j07"]["status"] == "orphan_dep"

    def test_cycle_jobs_dep_blocked(self, outputs: dict[str, object]) -> None:
        """Mutual depends_on links must mark both jobs dep_blocked."""
        jobs = {r["job_id"]: r for r in outputs["job_states.json"]["jobs"]}
        assert jobs["j11"]["status"] == "dep_blocked"
        assert jobs["j12"]["status"] == "dep_blocked"

    def test_j13_blackout_hard_status(self, outputs: dict[str, object]) -> None:
        """A hard blackout window must classify intersecting jobs as blackout_hard."""
        jobs = {r["job_id"]: r for r in outputs["job_states.json"]["jobs"]}
        assert jobs["j13"]["status"] == "blackout_hard"

    def test_j09_blackout_soft_status(self, outputs: dict[str, object]) -> None:
        """A soft blackout without harder rules must yield blackout_soft."""
        jobs = {r["job_id"]: r for r in outputs["job_states.json"]["jobs"]}
        assert jobs["j09"]["status"] == "blackout_soft"

    def test_zone_mismatch_extends_duration(self, outputs: dict[str, object]) -> None:
        """Mismatched zone tags must boost effective duration for every job."""
        jobs = {r["job_id"]: r for r in outputs["job_states.json"]["jobs"]}
        assert jobs["j01"]["effective_duration_min"] == 45
