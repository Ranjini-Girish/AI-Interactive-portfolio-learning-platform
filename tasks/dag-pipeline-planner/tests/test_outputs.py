"""Behavioral tests for the dag-pipeline-planner task.

These tests assert the agent's outputs against the documented contract in
``instruction.md`` and ``/app/pipelines/SPEC.md``. Hash-locked anti-cheat
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

DATA_DIR = Path(os.environ.get("DAG_DATA_DIR", "/app/pipelines"))
PLAN_DIR = Path(os.environ.get("DAG_PLAN_DIR", "/app/plan"))

REQUIRED_OUTPUT_FILES = [
    "schedule_plan.json",
    "cycle_report.json",
    "resource_utilization.json",
    "quarantine_status.json",
    "wave_plan.json",
    "summary.json",
]

EXPECTED_INPUT_HASHES = {
    "SPEC.md":                                       "dd5f66449662cc1b352bb63add8fe85bff6ee71f0feb683dee98e8b2da3ce677",
    "cluster.json":                                  "69d43972221a106534f1952b79d0ee315284973701a5808559e4db393c4814b1",
    "consumers.json":                                "b94f1aa6b87f5a119193b95100e6deb6dac3d28fe61f334243929b64f072781b",
    "incident_log.json":                             "5849ce733e799c3f995ea9661f55fbc5a1a97e534310726196780f17ee80da93",
    "pool_state.json":                               "0e6bf1b36a2aabed1041f126a9ca1b01a8c456d40dca8130e2b9e6f3ee03e89e",
    "pipelines/data-quality/manifest.json":          "bcd1be14df7d25741b7ebdd90e45e47afc70617c60f12db88d537dc74363fb1f",
    "pipelines/data-quality/jobs/report.json":       "ecae35501e24d54747043bd03d3e79dd5140511bc43ccaff0de0c1ff0190e4b6",
    "pipelines/data-quality/jobs/scan.json":         "9b507db6243a16041986741a4fa28a8998883bf29f3d67b2997be06dba59248c",
    "pipelines/etl-daily/manifest.json":             "48fb7366506f224f224bfb99571daa4c959944007cfe1f1ada68139202e9c8b4",
    "pipelines/etl-daily/jobs/extract.json":         "bde68fb122fee0f9805c17f605130a5eb3e108c3f06ec3a38cd605e018bfe3a3",
    "pipelines/etl-daily/jobs/load.json":            "5dd8f7076c8f69860448afd3212ab3a7aad464f8c2777c7c3935751217b1b803",
    "pipelines/etl-daily/jobs/transform.json":       "f9773aa8a9b52d1a96b991945836844f1de61b6f740822edfca90f82c205e590",
    "pipelines/feature-store/manifest.json":         "47e09e3290d2289b46db684862f8fcdcfa63e1c09dee78f4653c043b496ec7c8",
    "pipelines/feature-store/jobs/compute.json":     "8d7ebb4d6e74dff9cfc0494bbfab5ff2fed3dbb32aa782d7307dfc67668c77a7",
    "pipelines/feature-store/jobs/snapshot.json":    "0e11912e237efc2f337cc28366422a1e1fdbd7d8528efb6f837e2bef8cbde67b",
    "pipelines/log-archive/manifest.json":           "80f762e084f26665ba16dbe8d827a8c0d7aacff4ccb2fb4cc5af22371021f586",
    "pipelines/log-archive/jobs/collect.json":       "81b08afe52761d6badbae88cd6129ddaaf4fe6a9901281876a0e7c28bae9c71d",
    "pipelines/log-archive/jobs/compress.json":      "e7a912c10ef8ac928f402be8d3cd19f3115b54367aa993aa180b99d24164a404",
    "pipelines/ml-training/manifest.json":           "76b0746cef1a96c7872debc0d4b0d9c2e09afadd9dd7ba9c7ce0a0f7a472d9e6",
    "pipelines/ml-training/jobs/evaluate.json":      "a63f3cfd22844480a68dc87c77ff3a0c86f9e95eaf1e6c83f59799d250141b74",
    "pipelines/ml-training/jobs/prep.json":          "1c124b3e69deff2525cc60380296d9abb26ea33575525ccac5996863da6b9302",
    "pipelines/ml-training/jobs/train.json":         "9664738fbbf9a6e0d2aa01824489768d2fe4eb5165af3fb262f18da554610d36",
    "pipelines/realtime-ingest/manifest.json":       "d9c210f59a93d1078bd7e5b14631d0bde7b642132d18a16c9f38f65dca764be2",
    "pipelines/realtime-ingest/jobs/dedupe.json":    "d51df6e4d06e69238b167900eebe2f77838d90119abe4184512d97ccc3c05d47",
    "pipelines/realtime-ingest/jobs/enrich.json":    "1040e37e2594e4c1f3c8c52dd99f6504743babee817a98cf9f0c229e379daaae",
    "pipelines/realtime-ingest/jobs/ingest.json":    "f3eb7cae43cacadd76b79dba1d816681ffd8aadcb9c8260d89ad842bfb54a483",
    "pipelines/reporting/manifest.json":             "7b328e9c019b6e4e5ea0413b6ac6a77053c7d3eabaf5497e810e14c9ea1f0a59",
    "pipelines/reporting/jobs/fetch_data.json":      "810f83d1e678fbd836db42c797a03f02d0de7cecc23d8a369434f4db0a3c1cf1",
    "pipelines/reporting/jobs/publish.json":         "bd59274eee148bc09a42826359f655b7d57a3d461185c412fe4a2fe7e5c78e3a",
    "pipelines/reporting/jobs/render_csv.json":      "ced676e3443991ddb5d878c0a535bee2a0bd76f3a90266d7f06799dd9a8fae2b",
    "pipelines/reporting/jobs/render_html.json":     "d3ff5291588a1add7698786a0d2e0485f4966e19ec95210f72d275bba75b96a2",
    "pipelines/reporting/jobs/render_pdf.json":      "65fe47dc7103a91c125512445484358049a4786678652a48c8bb91de56fe12e4",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "schedule_plan.json":         "57f1d2acb910a192143f77db6b792853ea2a08e77a082056bac43ec5a82eb437",
    "cycle_report.json":          "dcd5dd43e203e4c731a7453e87104f76c2f0f838d914c0f18016e2ccb46a5ed0",
    "resource_utilization.json":  "3a1981fc1965d24120fb9383494b7b3157598b01dee036dc7a7a396714af806b",
    "quarantine_status.json":     "2a5c9679e4b1372f246543942589825a8c3bb81a5f15475f53f49ec98204c2b5",
    "wave_plan.json":             "31dfb5fd43c2d6f03aaea19f46f65cdacbfdedbb7c34e41e95eb1ed862707c71",
    "summary.json":               "758972aec65b991a28366331f4c5b0cfe7c2395b424b7781c21e7e5562894e33",
}

EXPECTED_FIELD_HASHES = {
    "schedule_plan.pipelines":                 "10b1598062bc3006dffe3f2b4d314d1c8d2ef522aad5b21696a8ab3f45eb3b83",
    "cycle_report.pipelines":                  "fe49a07978b4ba6990e38a6521098fdc4a198a42bc6d4d14a810c1501d7da593",
    "resource_utilization.by_resource_class":  "652bf20a76583a267e94750cd35a01d6bd5b6eb56076a1dc56603d3ba67ac627",
    "quarantine_status.pipelines":             "92fcf4ff4f743db8e81ebd35d203e61af229b7d006b65bedbeeecd417b607df1",
    "wave_plan.pipelines":                     "8676303aabe738b70519fa03eeef31545cd726c5139319472cd4de68817d379c",
    "summary.by_pipeline_status":              "407bff08c276df661561fdb73fef6500364f999773f42ffd97aa8db7876c510a",
    "summary.by_job_status":                   "65d8743f218d51b0a034e5151900f78baac777ded5a1db7d43a458a3b9c51c6a",
    "summary.sla_violations":                  "8bad033525a4f5d579a6ed01f723b4ddffb8d3cd4823be0b2ffc1175772c3ad9",
    "summary.burst_pressure_total":            "53c234e5e8472b6ac51c1ae1cab3fe06fad053beb8ebfd8977b010655bfdd3c3",
}


def _impaired_slots_for_status(pstatus, slots, carve_out):
    if pstatus in ("degraded", "partial_resource_block"):
        return {rc: max(1, s - carve_out.get(rc, 0)) for rc, s in slots.items()}
    return dict(slots)


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
        p = PLAN_DIR / name
        assert p.is_file(), f"missing required output file: /app/plan/{name}"
        text = p.read_text(encoding="utf-8")
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as e:
            pytest.fail(f"output /app/plan/{name} is not valid JSON: {e}")
        out[name] = {"text": text, "obj": obj, "bytes": text.encode("utf-8")}
    return out


# ---------------------------------------------------------------------------
# Input integrity
# ---------------------------------------------------------------------------


class TestInputIntegrity:
    """Inputs must remain byte-identical to the original fixtures."""

    @pytest.mark.parametrize("rel,expected", sorted(EXPECTED_INPUT_HASHES.items()))
    def test_input_unchanged(self, rel, expected):
        """Each input file's SHA-256 must match the locked baseline."""
        p = DATA_DIR / rel
        assert p.is_file(), f"input file missing: {rel}"
        actual = _sha256_bytes(p.read_bytes())
        assert actual == expected, (
            f"input file {rel} was modified (sha256 {actual} != {expected})"
        )


# ---------------------------------------------------------------------------
# Report structure & whole-output hashes
# ---------------------------------------------------------------------------


class TestReportStructure:
    """Top-level structural and canonical-hash invariants."""

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_required_file_exists(self, name):
        """Each required output file must exist and be a regular file."""
        assert (PLAN_DIR / name).is_file()

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_output_canonical_hash(self, name, loaded_outputs):
        """Canonical SHA-256 of each output must match the locked baseline."""
        actual = _canonical_sha256(loaded_outputs[name]["obj"])
        expected = EXPECTED_OUTPUT_CANONICAL_HASHES[name]
        assert actual == expected

    def test_schedule_plan_top_level(self, loaded_outputs):
        """schedule_plan.json must have exactly one top-level key 'pipelines'."""
        assert set(loaded_outputs["schedule_plan.json"]["obj"].keys()) == {"pipelines"}

    def test_cycle_report_top_level(self, loaded_outputs):
        """cycle_report.json must have exactly one top-level key 'pipelines'."""
        assert set(loaded_outputs["cycle_report.json"]["obj"].keys()) == {"pipelines"}

    def test_resource_utilization_top_level(self, loaded_outputs):
        """resource_utilization.json must have exactly one top-level key 'by_resource_class'."""
        assert set(loaded_outputs["resource_utilization.json"]["obj"].keys()) == {"by_resource_class"}

    def test_quarantine_status_top_level(self, loaded_outputs):
        """quarantine_status.json must have exactly one top-level key 'pipelines'."""
        assert set(loaded_outputs["quarantine_status.json"]["obj"].keys()) == {"pipelines"}

    def test_wave_plan_top_level(self, loaded_outputs):
        """wave_plan.json must have exactly one top-level key 'pipelines'."""
        assert set(loaded_outputs["wave_plan.json"]["obj"].keys()) == {"pipelines"}

    def test_summary_top_level_keys(self, loaded_outputs):
        """summary.json must have exactly the documented top-level keys."""
        obj = loaded_outputs["summary.json"]["obj"]
        expected = {
            "current_day", "scheduler_version", "total_pipelines", "total_jobs",
            "ignored_incident_events", "by_pipeline_status", "by_job_status",
            "sla_violations", "burst_pressure_total",
        }
        assert set(obj.keys()) == expected


# ---------------------------------------------------------------------------
# Field-level hashes
# ---------------------------------------------------------------------------


class TestFieldHashes:
    """Per-field canonical hashes pinpoint which output is wrong."""

    def test_schedule_plan_pipelines(self, loaded_outputs):
        """schedule_plan.pipelines must canonicalise to the locked hash."""
        v = loaded_outputs["schedule_plan.json"]["obj"]["pipelines"]
        assert _canonical_sha256(v) == EXPECTED_FIELD_HASHES["schedule_plan.pipelines"]

    def test_cycle_report_pipelines(self, loaded_outputs):
        """cycle_report.pipelines must canonicalise to the locked hash."""
        v = loaded_outputs["cycle_report.json"]["obj"]["pipelines"]
        assert _canonical_sha256(v) == EXPECTED_FIELD_HASHES["cycle_report.pipelines"]

    def test_resource_utilization_by_rc(self, loaded_outputs):
        """resource_utilization.by_resource_class must canonicalise to the locked hash."""
        v = loaded_outputs["resource_utilization.json"]["obj"]["by_resource_class"]
        assert _canonical_sha256(v) == EXPECTED_FIELD_HASHES["resource_utilization.by_resource_class"]

    def test_quarantine_status_pipelines(self, loaded_outputs):
        """quarantine_status.pipelines must canonicalise to the locked hash."""
        v = loaded_outputs["quarantine_status.json"]["obj"]["pipelines"]
        assert _canonical_sha256(v) == EXPECTED_FIELD_HASHES["quarantine_status.pipelines"]

    def test_wave_plan_pipelines(self, loaded_outputs):
        """wave_plan.pipelines must canonicalise to the locked hash."""
        v = loaded_outputs["wave_plan.json"]["obj"]["pipelines"]
        assert _canonical_sha256(v) == EXPECTED_FIELD_HASHES["wave_plan.pipelines"]

    def test_summary_by_pipeline_status(self, loaded_outputs):
        """summary.by_pipeline_status must canonicalise to the locked hash."""
        v = loaded_outputs["summary.json"]["obj"]["by_pipeline_status"]
        assert _canonical_sha256(v) == EXPECTED_FIELD_HASHES["summary.by_pipeline_status"]

    def test_summary_by_job_status(self, loaded_outputs):
        """summary.by_job_status must canonicalise to the locked hash."""
        v = loaded_outputs["summary.json"]["obj"]["by_job_status"]
        assert _canonical_sha256(v) == EXPECTED_FIELD_HASHES["summary.by_job_status"]

    def test_summary_sla_violations(self, loaded_outputs):
        """summary.sla_violations must canonicalise to the locked hash."""
        v = loaded_outputs["summary.json"]["obj"]["sla_violations"]
        assert _canonical_sha256(v) == EXPECTED_FIELD_HASHES["summary.sla_violations"]

    def test_summary_burst_pressure_total(self, loaded_outputs):
        """summary.burst_pressure_total must canonicalise to the locked hash."""
        v = loaded_outputs["summary.json"]["obj"]["burst_pressure_total"]
        assert _canonical_sha256(v) == EXPECTED_FIELD_HASHES["summary.burst_pressure_total"]


# ---------------------------------------------------------------------------
# Schedule plan behaviour
# ---------------------------------------------------------------------------


class TestSchedulePlan:
    """Schedule-plan rules covering every documented status label."""

    def test_pipelines_sorted(self, loaded_outputs):
        """pipelines list is sorted ascending by 'name'."""
        names = [p["name"] for p in loaded_outputs["schedule_plan.json"]["obj"]["pipelines"]]
        assert names == sorted(names)

    def test_every_pipeline_present(self, loaded_outputs):
        """Each pipeline directory appears exactly once."""
        on_disk = sorted(p.name for p in (DATA_DIR / "pipelines").iterdir() if p.is_dir())
        seen = sorted(p["name"] for p in loaded_outputs["schedule_plan.json"]["obj"]["pipelines"])
        assert seen == on_disk

    def test_pipeline_status_enum(self, loaded_outputs):
        """pipeline_status must be one of the five documented values."""
        allowed = {
            "scheduled", "degraded", "partial_resource_block",
            "blocked_quarantine", "blocked_cycle",
        }
        for p in loaded_outputs["schedule_plan.json"]["obj"]["pipelines"]:
            assert p["pipeline_status"] in allowed

    def test_job_status_enum(self, loaded_outputs):
        """Every job status must be one of the five documented values."""
        allowed = {
            "scheduled", "degraded", "blocked_resource_freeze",
            "blocked_quarantine", "blocked_cycle",
        }
        for p in loaded_outputs["schedule_plan.json"]["obj"]["pipelines"]:
            for j in p["jobs"]:
                assert j["status"] in allowed

    def test_pipeline_has_exact_keys(self, loaded_outputs):
        """Each pipeline entry has exactly the eight documented keys, including upstream_offset_minutes."""
        expected = {
            "name", "tier", "pipeline_status", "upstream_offset_minutes",
            "effective_sla_minutes", "total_runtime_minutes", "sla_met", "jobs",
        }
        for p in loaded_outputs["schedule_plan.json"]["obj"]["pipelines"]:
            assert set(p.keys()) == expected

    def test_jobs_have_exact_keys(self, loaded_outputs):
        """Each job entry has exactly the eight documented keys."""
        expected = {
            "name", "phase", "effective_priority", "resource_class",
            "runtime_minutes", "start_minute", "end_minute", "status",
        }
        for p in loaded_outputs["schedule_plan.json"]["obj"]["pipelines"]:
            for j in p["jobs"]:
                assert set(j.keys()) == expected

    def test_blocked_pipelines_have_null_times(self, loaded_outputs):
        """Cycle and quarantine pipelines have null start/end and zero total."""
        for p in loaded_outputs["schedule_plan.json"]["obj"]["pipelines"]:
            if p["pipeline_status"] in ("blocked_cycle", "blocked_quarantine"):
                assert p["total_runtime_minutes"] == 0
                for j in p["jobs"]:
                    assert j["start_minute"] is None and j["end_minute"] is None

    def test_known_quarantine_pipeline(self, loaded_outputs):
        """feature-store has a quarantine event so pipeline_status=blocked_quarantine, all jobs blocked_quarantine."""
        p = next(p for p in loaded_outputs["schedule_plan.json"]["obj"]["pipelines"] if p["name"] == "feature-store")
        assert p["pipeline_status"] == "blocked_quarantine"
        for j in p["jobs"]:
            assert j["status"] == "blocked_quarantine"

    def test_known_quarantine_pipeline_ml_training(self, loaded_outputs):
        """ml-training has an accepted quarantine event so pipeline_status=blocked_quarantine, all jobs blocked_quarantine."""
        p = next(p for p in loaded_outputs["schedule_plan.json"]["obj"]["pipelines"] if p["name"] == "ml-training")
        assert p["pipeline_status"] == "blocked_quarantine"
        for j in p["jobs"]:
            assert j["status"] == "blocked_quarantine"

    def test_known_cycle_pipeline(self, loaded_outputs):
        """data-quality has a cycle so pipeline_status=blocked_cycle, all jobs blocked_cycle."""
        p = next(p for p in loaded_outputs["schedule_plan.json"]["obj"]["pipelines"] if p["name"] == "data-quality")
        assert p["pipeline_status"] == "blocked_cycle"
        for j in p["jobs"]:
            assert j["status"] == "blocked_cycle"

    def test_known_degraded_pipeline(self, loaded_outputs):
        """log-archive is downstream of feature-store so pipeline_status=degraded."""
        p = next(p for p in loaded_outputs["schedule_plan.json"]["obj"]["pipelines"] if p["name"] == "log-archive")
        assert p["pipeline_status"] == "degraded"

    def test_known_partial_resource_block_pipeline(self, loaded_outputs):
        """etl-daily has cpu_large frozen so pipeline_status=partial_resource_block, transform blocked directly, load blocked indirectly via depends_on, extract still scheduled."""
        p = next(p for p in loaded_outputs["schedule_plan.json"]["obj"]["pipelines"] if p["name"] == "etl-daily")
        assert p["pipeline_status"] == "partial_resource_block"
        statuses = {j["name"]: j["status"] for j in p["jobs"]}
        assert statuses["transform"] == "blocked_resource_freeze"
        assert statuses["load"] == "blocked_resource_freeze"
        assert statuses["extract"] == "scheduled"

    def test_known_indirect_resource_freeze_propagation(self, loaded_outputs):
        """A job whose own resource_class is not frozen still becomes blocked_resource_freeze when it transitively depends on a directly-frozen job in the same pipeline (etl-daily/load uses cpu_small but depends_on cpu_large transform)."""
        p = next(p for p in loaded_outputs["schedule_plan.json"]["obj"]["pipelines"] if p["name"] == "etl-daily")
        load = next(j for j in p["jobs"] if j["name"] == "load")
        assert load["resource_class"] == "cpu_small"
        assert load["status"] == "blocked_resource_freeze"

    def test_known_quarantined_pipeline_preserves_phase_topology(self, loaded_outputs):
        """A blocked_quarantine pipeline keeps its topological phase values; only blocked_cycle collapses them to 0. feature-store/snapshot depends on compute, so its phase is 1 even though the pipeline is blocked_quarantine."""
        p = next(p for p in loaded_outputs["schedule_plan.json"]["obj"]["pipelines"] if p["name"] == "feature-store")
        assert p["pipeline_status"] == "blocked_quarantine"
        phases = {j["name"]: j["phase"] for j in p["jobs"]}
        assert phases["compute"] == 0
        assert phases["snapshot"] == 1

    def test_known_scheduled_pipeline(self, loaded_outputs):
        """realtime-ingest is clean so pipeline_status=scheduled."""
        p = next(p for p in loaded_outputs["schedule_plan.json"]["obj"]["pipelines"] if p["name"] == "realtime-ingest")
        assert p["pipeline_status"] == "scheduled"
        for j in p["jobs"]:
            assert j["status"] == "scheduled"

    def test_known_degraded_job_with_resource_freeze_wins(self, loaded_outputs):
        """log-archive's compress uses cpu_large (frozen) so status=blocked_resource_freeze, not degraded."""
        p = next(p for p in loaded_outputs["schedule_plan.json"]["obj"]["pipelines"] if p["name"] == "log-archive")
        compress = next(j for j in p["jobs"] if j["name"] == "compress")
        assert compress["status"] == "blocked_resource_freeze"

    def test_known_degraded_job(self, loaded_outputs):
        """log-archive's collect uses cpu_small (not frozen) but pipeline is degraded so status=degraded."""
        p = next(p for p in loaded_outputs["schedule_plan.json"]["obj"]["pipelines"] if p["name"] == "log-archive")
        collect = next(j for j in p["jobs"] if j["name"] == "collect")
        assert collect["status"] == "degraded"

    def test_degraded_pipeline_priority_deboost(self, loaded_outputs):
        """A degraded pipeline's jobs have effective_priority shifted by +100 over the base*tier_modifier value."""
        with open(DATA_DIR / "cluster.json", encoding="utf-8") as f:
            cluster = json.load(f)
        p = next(p for p in loaded_outputs["schedule_plan.json"]["obj"]["pipelines"] if p["name"] == "log-archive")
        manifest = json.loads((DATA_DIR / "pipelines" / "log-archive" / "manifest.json").read_text(encoding="utf-8"))
        tier_int = cluster["tier_priority_modifier_int"][manifest["tier"]]
        for j in p["jobs"]:
            base_p = json.loads((DATA_DIR / "pipelines" / "log-archive" / "jobs" / f"{j['name']}.json").read_text(encoding="utf-8"))["base_priority"]
            assert j["effective_priority"] == base_p * tier_int + 100

    def test_partial_resource_block_cascades_to_degraded(self, loaded_outputs):
        """reporting consumes from etl-daily (which is partial_resource_block), so reporting's pipeline_status is degraded and all its jobs without their own freeze become degraded."""
        p = next(p for p in loaded_outputs["schedule_plan.json"]["obj"]["pipelines"] if p["name"] == "reporting")
        assert p["pipeline_status"] == "degraded"
        for j in p["jobs"]:
            assert j["status"] == "degraded"

    def test_emitted_runtime_minutes_is_raw_input(self, loaded_outputs):
        """The emitted runtime_minutes field on each job is the raw input value, not effective_runtime_minutes (the retry-augmented value never appears in the output)."""
        p = next(p for p in loaded_outputs["schedule_plan.json"]["obj"]["pipelines"] if p["name"] == "etl-daily")
        for j in p["jobs"]:
            decl = json.loads((DATA_DIR / "pipelines" / "etl-daily" / "jobs" / f"{j['name']}.json").read_text(encoding="utf-8"))
            assert j["runtime_minutes"] == decl["runtime_minutes"]

    def test_blocked_pipelines_have_null_times_extras(self, loaded_outputs):
        """ml-training is blocked_quarantine: all jobs have null timing and total_runtime_minutes is 0, even though the underlying jobs would otherwise run."""
        p = next(p for p in loaded_outputs["schedule_plan.json"]["obj"]["pipelines"] if p["name"] == "ml-training")
        assert p["pipeline_status"] == "blocked_quarantine"
        assert p["total_runtime_minutes"] == 0
        for j in p["jobs"]:
            assert j["start_minute"] is None and j["end_minute"] is None


# ---------------------------------------------------------------------------
# Phase compaction: frozen jobs contribute 0 to phase_runtime and have null times
# ---------------------------------------------------------------------------


class TestPhaseCompaction:
    """Frozen jobs are excluded from phase_runtime and emit null start/end times."""

    def test_frozen_jobs_have_null_times_in_prb(self, loaded_outputs):
        """In a partial_resource_block pipeline, every job whose status is 'blocked_resource_freeze' has null start_minute and end_minute."""
        p = next(p for p in loaded_outputs["schedule_plan.json"]["obj"]["pipelines"] if p["name"] == "etl-daily")
        for j in p["jobs"]:
            if j["status"] == "blocked_resource_freeze":
                assert j["start_minute"] is None and j["end_minute"] is None

    def test_frozen_job_in_degraded_pipeline_has_null_times(self, loaded_outputs):
        """A degraded pipeline's frozen job (log-archive/compress on cpu_large) still emits null start/end times."""
        p = next(p for p in loaded_outputs["schedule_plan.json"]["obj"]["pipelines"] if p["name"] == "log-archive")
        compress = next(j for j in p["jobs"] if j["name"] == "compress")
        assert compress["status"] == "blocked_resource_freeze"
        assert compress["start_minute"] is None and compress["end_minute"] is None

    def test_non_frozen_extract_has_concrete_times(self, loaded_outputs):
        """In partial_resource_block etl-daily, extract is the only non-frozen job in phase 0 and there is a single wave per resource class; its start_minute equals the pipeline's upstream_offset_minutes and end_minute equals start + (runtime + retry*penalty)."""
        p = next(p for p in loaded_outputs["schedule_plan.json"]["obj"]["pipelines"] if p["name"] == "etl-daily")
        extract = next(j for j in p["jobs"] if j["name"] == "extract")
        with open(DATA_DIR / "cluster.json", encoding="utf-8") as f:
            cluster = json.load(f)
        manifest = json.loads((DATA_DIR / "pipelines" / "etl-daily" / "manifest.json").read_text(encoding="utf-8"))
        decl = json.loads((DATA_DIR / "pipelines" / "etl-daily" / "jobs" / "extract.json").read_text(encoding="utf-8"))
        penalty = cluster["retry_penalty_minutes_per_tier"][manifest["tier"]]
        eff = decl["runtime_minutes"] + decl["retry_count"] * penalty
        assert extract["start_minute"] == p["upstream_offset_minutes"]
        assert extract["end_minute"] == extract["start_minute"] + eff

    def test_total_runtime_uses_wave_aware_phase_sum(self, loaded_outputs):
        """total_runtime_minutes equals upstream_offset_minutes plus the sum over phases of phase_runtime; phase_runtime is the max over resource classes of class_runtime, where class_runtime is the sum of wave durations from the LPT-then-slot partition over non-frozen jobs of that class, using impaired_slots(P, c) when the pipeline_status is degraded or partial_resource_block and the un-carved slot count when it is scheduled. Independently re-derived from the per-job inputs and cluster.retry_penalty_minutes_per_tier / slots_per_resource_class / impaired_slot_carve_out_per_class."""
        with open(DATA_DIR / "cluster.json", encoding="utf-8") as f:
            cluster = json.load(f)
        slots = cluster["slots_per_resource_class"]
        carve_out = cluster["impaired_slot_carve_out_per_class"]
        for p in loaded_outputs["schedule_plan.json"]["obj"]["pipelines"]:
            if p["pipeline_status"] in ("blocked_cycle", "blocked_quarantine"):
                continue
            manifest = json.loads((DATA_DIR / "pipelines" / p["name"] / "manifest.json").read_text(encoding="utf-8"))
            penalty = cluster["retry_penalty_minutes_per_tier"][manifest["tier"]]
            impaired = _impaired_slots_for_status(p["pipeline_status"], slots, carve_out)
            per_phase_class = {}
            for j in p["jobs"]:
                if j["status"] == "blocked_resource_freeze":
                    continue
                decl = json.loads((DATA_DIR / "pipelines" / p["name"] / "jobs" / f"{j['name']}.json").read_text(encoding="utf-8"))
                eff = decl["runtime_minutes"] + decl["retry_count"] * penalty
                per_phase_class.setdefault((j["phase"], j["resource_class"]), []).append((eff, j["name"]))
            phase_runtimes = {}
            for (ph, rc), entries in per_phase_class.items():
                entries.sort(key=lambda t: (-t[0], t[1]))
                S = impaired[rc]
                class_total = 0
                for i in range(0, len(entries), S):
                    wave = entries[i:i + S]
                    class_total += max(eff for eff, _n in wave)
                if class_total > phase_runtimes.get(ph, 0):
                    phase_runtimes[ph] = class_total
            expected = p["upstream_offset_minutes"] + sum(phase_runtimes.values())
            assert p["total_runtime_minutes"] == expected, (
                f"{p['name']}: total={p['total_runtime_minutes']} expected={expected}"
            )

    def test_all_frozen_phase_contributes_zero(self, loaded_outputs):
        """In etl-daily phase 1 (only transform, frozen) and phase 2 (only load, frozen), the phase contributes 0 to total_runtime_minutes; total equals upstream_offset_minutes + extract's effective runtime."""
        p = next(p for p in loaded_outputs["schedule_plan.json"]["obj"]["pipelines"] if p["name"] == "etl-daily")
        with open(DATA_DIR / "cluster.json", encoding="utf-8") as f:
            cluster = json.load(f)
        manifest = json.loads((DATA_DIR / "pipelines" / "etl-daily" / "manifest.json").read_text(encoding="utf-8"))
        penalty = cluster["retry_penalty_minutes_per_tier"][manifest["tier"]]
        decl = json.loads((DATA_DIR / "pipelines" / "etl-daily" / "jobs" / "extract.json").read_text(encoding="utf-8"))
        eff = decl["runtime_minutes"] + decl["retry_count"] * penalty
        assert p["total_runtime_minutes"] == p["upstream_offset_minutes"] + eff


# ---------------------------------------------------------------------------
# Wave-based intra-phase scheduling
# ---------------------------------------------------------------------------


class TestWaveScheduling:
    """Within each phase jobs of the same resource_class run in waves of at most slots[c] jobs each, in LPT order, and phase_runtime is the max over classes of class_runtime."""

    def test_realtime_ingest_first_wave_jobs_start_at_offset(self, loaded_outputs):
        """In realtime-ingest phase 0 (3 cpu_small jobs, slots=2), the LPT-first wave contains the two longest jobs and they share start_minute = upstream_offset_minutes (which is 0 for a scheduled pipeline)."""
        p = next(p for p in loaded_outputs["schedule_plan.json"]["obj"]["pipelines"] if p["name"] == "realtime-ingest")
        with open(DATA_DIR / "cluster.json", encoding="utf-8") as f:
            cluster = json.load(f)
        manifest = json.loads((DATA_DIR / "pipelines" / "realtime-ingest" / "manifest.json").read_text(encoding="utf-8"))
        penalty = cluster["retry_penalty_minutes_per_tier"][manifest["tier"]]
        effs = {}
        for jname in ("dedupe", "enrich", "ingest"):
            decl = json.loads((DATA_DIR / "pipelines" / "realtime-ingest" / "jobs" / f"{jname}.json").read_text(encoding="utf-8"))
            effs[jname] = decl["runtime_minutes"] + decl["retry_count"] * penalty
        ordered = sorted(effs.items(), key=lambda kv: (-kv[1], kv[0]))
        first_wave = {n for n, _e in ordered[:2]}
        second_wave = {n for n, _e in ordered[2:]}
        for j in p["jobs"]:
            if j["name"] in first_wave:
                assert j["start_minute"] == p["upstream_offset_minutes"]
            elif j["name"] in second_wave:
                assert j["start_minute"] > p["upstream_offset_minutes"]

    def test_realtime_ingest_second_wave_starts_after_first(self, loaded_outputs):
        """The second wave's start_minute equals upstream_offset + duration of wave 0 (= max effective runtime among wave-0 jobs)."""
        p = next(p for p in loaded_outputs["schedule_plan.json"]["obj"]["pipelines"] if p["name"] == "realtime-ingest")
        with open(DATA_DIR / "cluster.json", encoding="utf-8") as f:
            cluster = json.load(f)
        manifest = json.loads((DATA_DIR / "pipelines" / "realtime-ingest" / "manifest.json").read_text(encoding="utf-8"))
        penalty = cluster["retry_penalty_minutes_per_tier"][manifest["tier"]]
        effs = {}
        for jname in ("dedupe", "enrich", "ingest"):
            decl = json.loads((DATA_DIR / "pipelines" / "realtime-ingest" / "jobs" / f"{jname}.json").read_text(encoding="utf-8"))
            effs[jname] = decl["runtime_minutes"] + decl["retry_count"] * penalty
        ordered = sorted(effs.items(), key=lambda kv: (-kv[1], kv[0]))
        wave0 = ordered[:2]
        wave1 = ordered[2:]
        wave0_dur = max(e for _n, e in wave0)
        for n, _e in wave1:
            j = next(j for j in p["jobs"] if j["name"] == n)
            assert j["start_minute"] == p["upstream_offset_minutes"] + wave0_dur

    def test_phase_runtime_is_class_wave_sum_max(self, loaded_outputs):
        """For every non-blocked pipeline and every phase, phase_runtime = max over resource classes c of (sum of wave_duration(p, c, w) for w in 0..ceil(N_c / impaired_slots_c)). Impaired-slot count applies to degraded and partial_resource_block pipelines; scheduled pipelines use the un-carved slot count. Re-derived from job inputs."""
        with open(DATA_DIR / "cluster.json", encoding="utf-8") as f:
            cluster = json.load(f)
        slots = cluster["slots_per_resource_class"]
        carve_out = cluster["impaired_slot_carve_out_per_class"]
        for p in loaded_outputs["schedule_plan.json"]["obj"]["pipelines"]:
            if p["pipeline_status"] in ("blocked_cycle", "blocked_quarantine"):
                continue
            manifest = json.loads((DATA_DIR / "pipelines" / p["name"] / "manifest.json").read_text(encoding="utf-8"))
            penalty = cluster["retry_penalty_minutes_per_tier"][manifest["tier"]]
            impaired = _impaired_slots_for_status(p["pipeline_status"], slots, carve_out)
            phase_to_jobs: dict[int, list] = {}
            for j in p["jobs"]:
                phase_to_jobs.setdefault(j["phase"], []).append(j)
            for ph, jlist in phase_to_jobs.items():
                grouped: dict[str, list] = {}
                for j in jlist:
                    if j["status"] == "blocked_resource_freeze":
                        continue
                    decl = json.loads((DATA_DIR / "pipelines" / p["name"] / "jobs" / f"{j['name']}.json").read_text(encoding="utf-8"))
                    eff = decl["runtime_minutes"] + decl["retry_count"] * penalty
                    grouped.setdefault(j["resource_class"], []).append((eff, j["name"]))
                if not grouped:
                    expected_phase_runtime = 0
                else:
                    candidates = []
                    for rc, entries in grouped.items():
                        entries.sort(key=lambda t: (-t[0], t[1]))
                        S = impaired[rc]
                        cls_total = 0
                        for i in range(0, len(entries), S):
                            wave = entries[i:i + S]
                            cls_total += max(e for e, _n in wave)
                        candidates.append(cls_total)
                    expected_phase_runtime = max(candidates)
                non_frozen = [j for j in jlist if j["status"] != "blocked_resource_freeze"]
                if not non_frozen:
                    continue
                phase_starts = sorted({j["start_minute"] for j in non_frozen if j["start_minute"] is not None})
                if ph + 1 in phase_to_jobs:
                    next_non_frozen = [j for j in phase_to_jobs[ph + 1] if j["status"] != "blocked_resource_freeze" and j["start_minute"] is not None]
                    if next_non_frozen:
                        next_phase_start = min(j["start_minute"] for j in next_non_frozen)
                        observed = next_phase_start - phase_starts[0]
                        assert observed == expected_phase_runtime, (
                            f"{p['name']} phase {ph}: observed={observed} expected={expected_phase_runtime}"
                        )

    def test_jobs_share_start_within_a_wave(self, loaded_outputs):
        """All non-frozen jobs that share (phase, resource_class, wave) emit identical start_minute. Wave membership is determined under impaired_slots(P, c) when the pipeline is degraded or partial_resource_block, otherwise under the un-carved slot count."""
        with open(DATA_DIR / "cluster.json", encoding="utf-8") as f:
            cluster = json.load(f)
        slots = cluster["slots_per_resource_class"]
        carve_out = cluster["impaired_slot_carve_out_per_class"]
        for p in loaded_outputs["schedule_plan.json"]["obj"]["pipelines"]:
            if p["pipeline_status"] in ("blocked_cycle", "blocked_quarantine"):
                continue
            manifest = json.loads((DATA_DIR / "pipelines" / p["name"] / "manifest.json").read_text(encoding="utf-8"))
            penalty = cluster["retry_penalty_minutes_per_tier"][manifest["tier"]]
            impaired = _impaired_slots_for_status(p["pipeline_status"], slots, carve_out)
            grouped: dict[tuple[int, str], list] = {}
            for j in p["jobs"]:
                if j["status"] == "blocked_resource_freeze":
                    continue
                decl = json.loads((DATA_DIR / "pipelines" / p["name"] / "jobs" / f"{j['name']}.json").read_text(encoding="utf-8"))
                eff = decl["runtime_minutes"] + decl["retry_count"] * penalty
                grouped.setdefault((j["phase"], j["resource_class"]), []).append((eff, j))
            for (ph, rc), entries in grouped.items():
                entries.sort(key=lambda t: (-t[0], t[1]["name"]))
                S = impaired[rc]
                for i in range(0, len(entries), S):
                    wave_jobs = [item[1] for item in entries[i:i + S]]
                    starts = {wj["start_minute"] for wj in wave_jobs}
                    assert len(starts) == 1, (
                        f"{p['name']} phase {ph} class {rc} wave {i // S}: jobs disagree on start: {starts}"
                    )

    def test_end_minute_equals_start_plus_effective_runtime(self, loaded_outputs):
        """For every non-frozen non-blocked job, end_minute == start_minute + effective_runtime_minutes."""
        with open(DATA_DIR / "cluster.json", encoding="utf-8") as f:
            cluster = json.load(f)
        for p in loaded_outputs["schedule_plan.json"]["obj"]["pipelines"]:
            if p["pipeline_status"] in ("blocked_cycle", "blocked_quarantine"):
                continue
            manifest = json.loads((DATA_DIR / "pipelines" / p["name"] / "manifest.json").read_text(encoding="utf-8"))
            penalty = cluster["retry_penalty_minutes_per_tier"][manifest["tier"]]
            for j in p["jobs"]:
                if j["status"] == "blocked_resource_freeze":
                    continue
                decl = json.loads((DATA_DIR / "pipelines" / p["name"] / "jobs" / f"{j['name']}.json").read_text(encoding="utf-8"))
                eff = decl["runtime_minutes"] + decl["retry_count"] * penalty
                assert j["end_minute"] - j["start_minute"] == eff


# ---------------------------------------------------------------------------
# Cross-pipeline upstream offset propagation
# ---------------------------------------------------------------------------


class TestUpstreamOffset:
    """upstream_offset_minutes is the max total_runtime_minutes over transitive non-blocked producers."""

    def test_scheduled_pipeline_offset_is_zero(self, loaded_outputs):
        """A pipeline whose pipeline_status is 'scheduled' has upstream_offset_minutes == 0."""
        p = next(p for p in loaded_outputs["schedule_plan.json"]["obj"]["pipelines"] if p["name"] == "realtime-ingest")
        assert p["upstream_offset_minutes"] == 0

    def test_quarantined_pipeline_offset_is_zero(self, loaded_outputs):
        """A blocked_quarantine pipeline emits upstream_offset_minutes == 0."""
        p = next(p for p in loaded_outputs["schedule_plan.json"]["obj"]["pipelines"] if p["name"] == "feature-store")
        assert p["upstream_offset_minutes"] == 0

    def test_cyclic_pipeline_offset_is_zero(self, loaded_outputs):
        """A blocked_cycle pipeline emits upstream_offset_minutes == 0."""
        p = next(p for p in loaded_outputs["schedule_plan.json"]["obj"]["pipelines"] if p["name"] == "data-quality")
        assert p["upstream_offset_minutes"] == 0

    def test_prb_with_no_producers_offset_zero(self, loaded_outputs):
        """etl-daily is partial_resource_block but has no producers in consumers.edges, so its upstream_offset_minutes is 0."""
        p = next(p for p in loaded_outputs["schedule_plan.json"]["obj"]["pipelines"] if p["name"] == "etl-daily")
        assert p["upstream_offset_minutes"] == 0

    def test_reporting_offset_equals_etl_daily_total(self, loaded_outputs):
        """reporting consumes from etl-daily (partial_resource_block) only; its upstream_offset_minutes equals etl-daily.total_runtime_minutes."""
        pipes = {p["name"]: p for p in loaded_outputs["schedule_plan.json"]["obj"]["pipelines"]}
        assert pipes["reporting"]["upstream_offset_minutes"] == pipes["etl-daily"]["total_runtime_minutes"]

    def test_log_archive_offset_excludes_quarantined_producers(self, loaded_outputs):
        """log-archive's transitive producers are feature-store (blocked_quarantine, contributes 0), ml-training (blocked_quarantine, contributes 0), realtime-ingest (scheduled, contributes its total), reporting (degraded, contributes its total), and etl-daily (partial_resource_block, contributes its total reachable both directly and via reporting). upstream_offset_minutes equals the maximum total over the non-blocked producers, which here is reporting.total_runtime_minutes (the longest staged producer)."""
        pipes = {p["name"]: p for p in loaded_outputs["schedule_plan.json"]["obj"]["pipelines"]}
        non_blocked_producer_totals = [
            pipes["etl-daily"]["total_runtime_minutes"],
            pipes["realtime-ingest"]["total_runtime_minutes"],
            pipes["reporting"]["total_runtime_minutes"],
        ]
        expected = max(non_blocked_producer_totals)
        assert pipes["log-archive"]["upstream_offset_minutes"] == expected
        assert pipes["log-archive"]["upstream_offset_minutes"] == pipes["reporting"]["total_runtime_minutes"]
        assert pipes["log-archive"]["upstream_offset_minutes"] > pipes["etl-daily"]["total_runtime_minutes"]

    def test_phase_zero_first_wave_start_equals_offset(self, loaded_outputs):
        """For every non-blocked pipeline, the first wave's non-frozen phase-0 jobs start at upstream_offset_minutes; later waves of the same class start strictly after."""
        for p in loaded_outputs["schedule_plan.json"]["obj"]["pipelines"]:
            if p["pipeline_status"] in ("blocked_cycle", "blocked_quarantine"):
                continue
            phase0_starts = [j["start_minute"] for j in p["jobs"] if j["phase"] == 0 and j["status"] != "blocked_resource_freeze"]
            if phase0_starts:
                assert min(phase0_starts) == p["upstream_offset_minutes"], (
                    f"{p['name']}: min phase-0 start {min(phase0_starts)} != offset {p['upstream_offset_minutes']}"
                )


# ---------------------------------------------------------------------------
# Burst-pressure SLA debit
# ---------------------------------------------------------------------------


class TestBurstPressureSla:
    """Burst pressure debits effective_sla_minutes for non-blocked pipelines after every other SLA rule, and the critical-chain debit applies after that."""

    def test_realtime_ingest_burst_pressure_debit(self, loaded_outputs):
        """realtime-ingest is scheduled with three cpu_small jobs in phase 0 (3 > slots=2 so burst_pressure=1); effective_sla_minutes folds in the burst debit and then the critical-chain debit. critical_chain_depth=1 (one non-blocked downstream consumer, log-archive)."""
        p = next(p for p in loaded_outputs["schedule_plan.json"]["obj"]["pipelines"] if p["name"] == "realtime-ingest")
        with open(DATA_DIR / "cluster.json", encoding="utf-8") as f:
            cluster = json.load(f)
        manifest = json.loads((DATA_DIR / "pipelines" / "realtime-ingest" / "manifest.json").read_text(encoding="utf-8"))
        base = manifest["sla_hours"] * 60
        debit = cluster["wave_pressure_debit_per_burst"]
        chain = cluster["critical_chain_debit_per_link"]
        burst_sla = max(0, base - debit * 1)
        assert p["effective_sla_minutes"] == max(0, burst_sla - chain * 1)

    def test_etl_daily_no_burst_pressure_keeps_partial_block_value_minus_chain(self, loaded_outputs):
        """etl-daily's only non-frozen job (extract) is alone in phase 0 (1 < slots=2 cpu_small) so burst_pressure=0; pre_sla applies the partial-block multiplier; the chain debit then subtracts critical_chain_debit_per_link * 2 (etl-daily reaches reporting, then log-archive, both non-blocked)."""
        p = next(p for p in loaded_outputs["schedule_plan.json"]["obj"]["pipelines"] if p["name"] == "etl-daily")
        with open(DATA_DIR / "cluster.json", encoding="utf-8") as f:
            cluster = json.load(f)
        manifest = json.loads((DATA_DIR / "pipelines" / "etl-daily" / "manifest.json").read_text(encoding="utf-8"))
        base = manifest["sla_hours"] * 60
        mult = cluster["partial_block_sla_multiplier_pct_per_tier"][manifest["tier"]]
        chain = cluster["critical_chain_debit_per_link"]
        pre = (base * mult) // 100
        assert p["effective_sla_minutes"] == max(0, pre - chain * 2)

    def test_reporting_burst_pressure_debit_after_degraded_debit(self, loaded_outputs):
        """reporting is degraded (via etl-daily upstream prb) and has 3 cpu_small jobs in phase 1 (3 > slots=2 so burst_pressure=1); effective_sla_minutes equals max(0, pre - wave_debit * 1 - chain_debit * 1) where pre is the degraded-debit formula (here equal to base_sla because upstream_quarantined is empty) and the chain depth is 1 (reporting reaches log-archive only)."""
        p = next(p for p in loaded_outputs["schedule_plan.json"]["obj"]["pipelines"] if p["name"] == "reporting")
        with open(DATA_DIR / "cluster.json", encoding="utf-8") as f:
            cluster = json.load(f)
        manifest = json.loads((DATA_DIR / "pipelines" / "reporting" / "manifest.json").read_text(encoding="utf-8"))
        base = manifest["sla_hours"] * 60
        for ev in json.loads((DATA_DIR / "incident_log.json").read_text(encoding="utf-8")).get("events", []):
            if ev.get("kind") == "sla_breach_grace" and ev.get("pipeline") == "reporting":
                base += ev["extension_minutes"]
        debit = cluster["wave_pressure_debit_per_burst"]
        debit_per_q = cluster["degraded_sla_debit_per_upstream_quarantine"]
        chain = cluster["critical_chain_debit_per_link"]
        q = next(q for q in loaded_outputs["quarantine_status.json"]["obj"]["pipelines"] if q["name"] == "reporting")
        pre = max(0, base - debit_per_q * len(q["upstream_quarantined"]))
        burst_sla = max(0, pre - debit * 1)
        assert p["effective_sla_minutes"] == max(0, burst_sla - chain * 1)

    def test_log_archive_zero_burst_pressure_and_zero_chain(self, loaded_outputs):
        """log-archive's only non-frozen job (collect) is alone in phase 0 (cpu_small, 1 < slots=2) so burst_pressure=0; log-archive has no non-blocked downstream consumers so critical_chain_depth=0 and the chain debit contributes 0. effective_sla_minutes equals the degraded-debit formula unchanged."""
        p = next(p for p in loaded_outputs["schedule_plan.json"]["obj"]["pipelines"] if p["name"] == "log-archive")
        with open(DATA_DIR / "cluster.json", encoding="utf-8") as f:
            cluster = json.load(f)
        manifest = json.loads((DATA_DIR / "pipelines" / "log-archive" / "manifest.json").read_text(encoding="utf-8"))
        base = manifest["sla_hours"] * 60
        debit = cluster["degraded_sla_debit_per_upstream_quarantine"]
        q = next(q for q in loaded_outputs["quarantine_status.json"]["obj"]["pipelines"] if q["name"] == "log-archive")
        assert p["effective_sla_minutes"] == max(0, base - debit * len(q["upstream_quarantined"]))

    def test_burst_total_is_sum_per_pipeline(self, loaded_outputs):
        """summary.burst_pressure_total is the sum of burst_pressure across every wave_plan pipeline (blocked pipelines contribute zero and do not appear in wave_plan)."""
        s = loaded_outputs["summary.json"]["obj"]["burst_pressure_total"]
        wp = loaded_outputs["wave_plan.json"]["obj"]["pipelines"]
        assert s == sum(p["burst_pressure"] for p in wp)


# ---------------------------------------------------------------------------
# Wave plan output
# ---------------------------------------------------------------------------


class TestWavePlan:
    """wave_plan.json materialises the per-pipeline / per-phase / per-resource-class wave layout."""

    def test_wave_plan_pipelines_sorted(self, loaded_outputs):
        """pipelines list is sorted ascending by name."""
        names = [p["name"] for p in loaded_outputs["wave_plan.json"]["obj"]["pipelines"]]
        assert names == sorted(names)

    def test_wave_plan_excludes_blocked_pipelines(self, loaded_outputs):
        """blocked_cycle and blocked_quarantine pipelines are absent from wave_plan.json."""
        names = {p["name"] for p in loaded_outputs["wave_plan.json"]["obj"]["pipelines"]}
        assert "data-quality" not in names
        assert "feature-store" not in names
        assert "ml-training" not in names

    def test_wave_plan_includes_every_non_blocked_pipeline(self, loaded_outputs):
        """Every pipeline whose pipeline_status is in {scheduled, degraded, partial_resource_block} appears in wave_plan.json."""
        non_blocked = {
            p["name"]
            for p in loaded_outputs["schedule_plan.json"]["obj"]["pipelines"]
            if p["pipeline_status"] in ("scheduled", "degraded", "partial_resource_block")
        }
        seen = {p["name"] for p in loaded_outputs["wave_plan.json"]["obj"]["pipelines"]}
        assert seen == non_blocked

    def test_wave_plan_phase_sorted_and_resource_class_sorted(self, loaded_outputs):
        """Within each pipeline, phases are sorted ascending by phase number; within each phase, resource_classes are sorted ascending; within each resource_class, waves are sorted ascending by wave_index."""
        for p in loaded_outputs["wave_plan.json"]["obj"]["pipelines"]:
            phase_nums = [ph["phase"] for ph in p["phases"]]
            assert phase_nums == sorted(phase_nums)
            for ph in p["phases"]:
                rcs = [r["resource_class"] for r in ph["resource_classes"]]
                assert rcs == sorted(rcs)
                for r in ph["resource_classes"]:
                    widx = [w["wave_index"] for w in r["waves"]]
                    assert widx == sorted(widx)

    def test_wave_plan_jobs_sorted_within_wave(self, loaded_outputs):
        """Inside a wave, the jobs list is sorted ascending by name (the LPT order is used only to determine wave membership)."""
        for p in loaded_outputs["wave_plan.json"]["obj"]["pipelines"]:
            for ph in p["phases"]:
                for r in ph["resource_classes"]:
                    for w in r["waves"]:
                        assert w["jobs"] == sorted(w["jobs"])

    def test_realtime_ingest_two_waves(self, loaded_outputs):
        """realtime-ingest's only phase has cpu_small jobs partitioned into 2 waves of size at most slots=2 in LPT order."""
        with open(DATA_DIR / "cluster.json", encoding="utf-8") as f:
            cluster = json.load(f)
        manifest = json.loads((DATA_DIR / "pipelines" / "realtime-ingest" / "manifest.json").read_text(encoding="utf-8"))
        penalty = cluster["retry_penalty_minutes_per_tier"][manifest["tier"]]
        effs = {}
        for jname in ("dedupe", "enrich", "ingest"):
            decl = json.loads((DATA_DIR / "pipelines" / "realtime-ingest" / "jobs" / f"{jname}.json").read_text(encoding="utf-8"))
            effs[jname] = decl["runtime_minutes"] + decl["retry_count"] * penalty
        ordered = [n for n, _e in sorted(effs.items(), key=lambda kv: (-kv[1], kv[0]))]
        wave0_members = sorted(ordered[:2])
        wave1_members = sorted(ordered[2:])
        p = next(p for p in loaded_outputs["wave_plan.json"]["obj"]["pipelines"] if p["name"] == "realtime-ingest")
        phase0 = next(ph for ph in p["phases"] if ph["phase"] == 0)
        cs = next(r for r in phase0["resource_classes"] if r["resource_class"] == "cpu_small")
        waves = cs["waves"]
        assert len(waves) == 2
        assert waves[0]["wave_index"] == 0
        assert waves[0]["jobs"] == wave0_members
        assert waves[0]["duration_minutes"] == max(effs[n] for n in wave0_members)
        assert waves[1]["wave_index"] == 1
        assert waves[1]["jobs"] == wave1_members
        assert waves[1]["duration_minutes"] == max(effs[n] for n in wave1_members)

    def test_etl_daily_omits_all_frozen_phases(self, loaded_outputs):
        """etl-daily's phase 1 (transform frozen) and phase 2 (load frozen) contain no non-frozen jobs and are absent from wave_plan; only phase 0 remains."""
        p = next(p for p in loaded_outputs["wave_plan.json"]["obj"]["pipelines"] if p["name"] == "etl-daily")
        phase_nums = [ph["phase"] for ph in p["phases"]]
        assert phase_nums == [0]

    def test_wave_plan_wave_duration_matches_max_eff(self, loaded_outputs):
        """For every wave, duration_minutes equals max(effective_runtime_minutes(j) for j in wave) recomputed from per-job inputs."""
        with open(DATA_DIR / "cluster.json", encoding="utf-8") as f:
            cluster = json.load(f)
        for p in loaded_outputs["wave_plan.json"]["obj"]["pipelines"]:
            manifest = json.loads((DATA_DIR / "pipelines" / p["name"] / "manifest.json").read_text(encoding="utf-8"))
            penalty = cluster["retry_penalty_minutes_per_tier"][manifest["tier"]]
            for ph in p["phases"]:
                for r in ph["resource_classes"]:
                    for w in r["waves"]:
                        effs = []
                        for jn in w["jobs"]:
                            decl = json.loads((DATA_DIR / "pipelines" / p["name"] / "jobs" / f"{jn}.json").read_text(encoding="utf-8"))
                            effs.append(decl["runtime_minutes"] + decl["retry_count"] * penalty)
                        assert w["duration_minutes"] == max(effs), (
                            f"{p['name']} ph{ph['phase']} {r['resource_class']} wave {w['wave_index']}: "
                            f"duration={w['duration_minutes']} expected={max(effs)}"
                        )

    def test_wave_plan_burst_pressure_uses_uncarved_slot_count(self, loaded_outputs):
        """A pipeline's burst_pressure equals the number of (phase, resource_class) entries whose total non-frozen job count exceeds cluster.slots_per_resource_class[c] (the un-carved installed capacity), regardless of how many waves the impaired-slot partition produced. For a degraded or partial_resource_block pipeline whose carve-out is non-zero, a (p, c) can have multiple waves yet still contribute zero to burst_pressure when its job count does not exceed the un-carved slot count."""
        with open(DATA_DIR / "cluster.json", encoding="utf-8") as f:
            cluster = json.load(f)
        slots = cluster["slots_per_resource_class"]
        for p in loaded_outputs["wave_plan.json"]["obj"]["pipelines"]:
            count = 0
            for ph in p["phases"]:
                for r in ph["resource_classes"]:
                    job_count = sum(len(w["jobs"]) for w in r["waves"])
                    if job_count > slots[r["resource_class"]]:
                        count += 1
            assert p["burst_pressure"] == count, (
                f"{p['name']}: burst_pressure={p['burst_pressure']} expected={count}"
            )


# ---------------------------------------------------------------------------
# Cycle report
# ---------------------------------------------------------------------------


class TestCycleReport:
    """Cycle detection per pipeline."""

    def test_pipelines_sorted(self, loaded_outputs):
        """pipelines list is sorted ascending by 'name'."""
        names = [p["name"] for p in loaded_outputs["cycle_report.json"]["obj"]["pipelines"]]
        assert names == sorted(names)

    def test_every_pipeline_present(self, loaded_outputs):
        """Each pipeline appears exactly once."""
        on_disk = sorted(p.name for p in (DATA_DIR / "pipelines").iterdir() if p.is_dir())
        seen = sorted(p["name"] for p in loaded_outputs["cycle_report.json"]["obj"]["pipelines"])
        assert seen == on_disk

    def test_known_cyclic_pipeline_lists_cycle_jobs(self, loaded_outputs):
        """data-quality has a scan/report cycle so both job names appear sorted in cycle_jobs."""
        p = next(p for p in loaded_outputs["cycle_report.json"]["obj"]["pipelines"] if p["name"] == "data-quality")
        assert p["has_cycle"] is True
        assert p["cycle_jobs"] == ["report", "scan"]

    def test_acyclic_pipelines_have_empty_cycle_jobs(self, loaded_outputs):
        """For pipelines without cycles, has_cycle is false and cycle_jobs is []."""
        for p in loaded_outputs["cycle_report.json"]["obj"]["pipelines"]:
            if p["name"] != "data-quality":
                assert p["has_cycle"] is False
                assert p["cycle_jobs"] == []


# ---------------------------------------------------------------------------
# Resource utilization
# ---------------------------------------------------------------------------


class TestResourceUtilization:
    """Resource-class utilization roll-up."""

    def test_by_rc_sorted(self, loaded_outputs):
        """by_resource_class is sorted by resource_class ascending."""
        rcs = [e["resource_class"] for e in loaded_outputs["resource_utilization.json"]["obj"]["by_resource_class"]]
        assert rcs == sorted(rcs)

    def test_every_rc_present(self, loaded_outputs):
        """Every key of cluster.slots_per_resource_class is present."""
        with open(DATA_DIR / "cluster.json", encoding="utf-8") as f:
            cluster = json.load(f)
        on_disk = sorted(cluster["slots_per_resource_class"].keys())
        seen = sorted(e["resource_class"] for e in loaded_outputs["resource_utilization.json"]["obj"]["by_resource_class"])
        assert seen == on_disk

    def test_active_freeze_matches_input(self, loaded_outputs):
        """active_freeze is true iff there's an active resource_pool_freeze for that class."""
        with open(DATA_DIR / "incident_log.json", encoding="utf-8") as f:
            log = json.load(f)
        with open(DATA_DIR / "pool_state.json", encoding="utf-8") as f:
            cd = json.load(f)["current_day"]
        with open(DATA_DIR / "cluster.json", encoding="utf-8") as f:
            rcs = set(json.load(f)["slots_per_resource_class"].keys())
        active = set()
        for ev in log["events"]:
            if ev.get("kind") != "resource_pool_freeze":
                continue
            d = ev.get("day")
            dur = ev.get("duration_days")
            rc = ev.get("resource_class")
            if not (isinstance(d, int) and not isinstance(d, bool)):
                continue
            if rc not in rcs:
                continue
            if not (isinstance(dur, int) and not isinstance(dur, bool) and dur > 0):
                continue
            if d > cd:
                continue
            if d <= cd <= d + dur - 1:
                active.add(rc)
        for e in loaded_outputs["resource_utilization.json"]["obj"]["by_resource_class"]:
            assert e["active_freeze"] == (e["resource_class"] in active)


# ---------------------------------------------------------------------------
# Quarantine status
# ---------------------------------------------------------------------------


class TestQuarantineStatus:
    """Quarantine cascade and downstream propagation."""

    def test_pipelines_sorted(self, loaded_outputs):
        """pipelines list is sorted ascending by 'name'."""
        names = [p["name"] for p in loaded_outputs["quarantine_status.json"]["obj"]["pipelines"]]
        assert names == sorted(names)

    def test_state_enum(self, loaded_outputs):
        """quarantine_state must be one of the three documented values."""
        for p in loaded_outputs["quarantine_status.json"]["obj"]["pipelines"]:
            assert p["quarantine_state"] in {"quarantined", "degraded", "normal"}

    def test_known_quarantined(self, loaded_outputs):
        """feature-store is quarantined with quarantined_jobs=[compute]."""
        p = next(p for p in loaded_outputs["quarantine_status.json"]["obj"]["pipelines"] if p["name"] == "feature-store")
        assert p["quarantine_state"] == "quarantined"
        assert p["quarantined_jobs"] == ["compute"]
        assert p["upstream_quarantined"] == []

    def test_known_quarantined_ml_training(self, loaded_outputs):
        """ml-training is quarantined with quarantined_jobs=[prep]."""
        p = next(p for p in loaded_outputs["quarantine_status.json"]["obj"]["pipelines"] if p["name"] == "ml-training")
        assert p["quarantine_state"] == "quarantined"
        assert p["quarantined_jobs"] == ["prep"]
        assert p["upstream_quarantined"] == []

    def test_known_degraded(self, loaded_outputs):
        """log-archive is degraded; its upstream_quarantined includes both feature-store and ml-training (transitively reachable through the feature-store producer edge). The reporting and realtime-ingest producer edges add non-quarantined transitive producers, not extra quarantined ones, so upstream_quarantined remains the same two-element list."""
        p = next(p for p in loaded_outputs["quarantine_status.json"]["obj"]["pipelines"] if p["name"] == "log-archive")
        assert p["quarantine_state"] == "degraded"
        assert p["upstream_quarantined"] == ["feature-store", "ml-training"]
        assert p["quarantined_jobs"] == []

    def test_degraded_via_partial_resource_block_has_no_upstream_quarantine(self, loaded_outputs):
        """reporting is degraded only because etl-daily (its sole producer) is partial_resource_block; its upstream_quarantined is empty because none of its producers are quarantined."""
        p = next(p for p in loaded_outputs["quarantine_status.json"]["obj"]["pipelines"] if p["name"] == "reporting")
        assert p["quarantine_state"] == "degraded"
        assert p["upstream_quarantined"] == []
        assert p["quarantined_jobs"] == []


# ---------------------------------------------------------------------------
# Critical-chain SLA debit
# ---------------------------------------------------------------------------


def _critical_chain_depth(name, pstatus_by_pipe, producer_to_consumers, memo):
    if name in memo:
        return memo[name]
    if pstatus_by_pipe.get(name) not in ("scheduled", "degraded", "partial_resource_block"):
        memo[name] = 0
        return 0
    best = 0
    found = False
    for c in producer_to_consumers.get(name, []):
        if pstatus_by_pipe.get(c) in ("scheduled", "degraded", "partial_resource_block"):
            found = True
            best = max(best, 1 + _critical_chain_depth(c, pstatus_by_pipe, producer_to_consumers, memo))
    memo[name] = best if found else 0
    return memo[name]


def _build_chain_inputs(loaded_outputs):
    pstatus_by_pipe = {p["name"]: p["pipeline_status"] for p in loaded_outputs["schedule_plan.json"]["obj"]["pipelines"]}
    consumers_doc = json.loads((DATA_DIR / "consumers.json").read_text(encoding="utf-8"))
    producer_to_consumers = {}
    for e in consumers_doc["edges"]:
        producer_to_consumers.setdefault(e["producer"], set()).add(e["consumer"])
    memo = {}
    chain_depth = {}
    for name in pstatus_by_pipe:
        chain_depth[name] = _critical_chain_depth(name, pstatus_by_pipe, producer_to_consumers, memo)
    return pstatus_by_pipe, chain_depth


class TestCriticalChainDebit:
    """The critical-chain debit subtracts critical_chain_debit_per_link * critical_chain_depth(P) from effective_sla_minutes after the burst-pressure debit, clamped at zero."""

    def test_critical_chain_depth_etl_daily(self, loaded_outputs):
        """etl-daily is partial_resource_block. Its non-blocked downstream chain reaches reporting (degraded), and reporting reaches log-archive (degraded). Depth = 2 (two consecutive consumer edges)."""
        _pstatus, chain = _build_chain_inputs(loaded_outputs)
        assert chain["etl-daily"] == 2

    def test_critical_chain_depth_reporting(self, loaded_outputs):
        """reporting is degraded. Its only non-blocked downstream consumer is log-archive (degraded), which has none. Depth = 1."""
        _pstatus, chain = _build_chain_inputs(loaded_outputs)
        assert chain["reporting"] == 1

    def test_critical_chain_depth_realtime_ingest(self, loaded_outputs):
        """realtime-ingest is scheduled. Its only consumer is log-archive (degraded, non-blocked); log-archive itself has no non-blocked consumer. Depth = 1."""
        _pstatus, chain = _build_chain_inputs(loaded_outputs)
        assert chain["realtime-ingest"] == 1

    def test_critical_chain_depth_log_archive(self, loaded_outputs):
        """log-archive is degraded but has no consumers in the producer-to-consumer graph; depth = 0 and no chain debit is applied."""
        _pstatus, chain = _build_chain_inputs(loaded_outputs)
        assert chain["log-archive"] == 0

    def test_blocked_pipelines_have_zero_chain_depth(self, loaded_outputs):
        """A blocked_cycle or blocked_quarantine pipeline contributes a depth of 0 by definition (the path walk skips blocked pipelines and a blocked pipeline cannot be a chain root). The chain debit therefore never moves their effective_sla_minutes off the burst-pressure value."""
        pstatus, chain = _build_chain_inputs(loaded_outputs)
        for name, ps in pstatus.items():
            if ps in ("blocked_cycle", "blocked_quarantine"):
                assert chain[name] == 0

    def test_chain_walk_skips_blocked_consumer(self, loaded_outputs):
        """etl-daily's edges produce consumers feature-store (blocked_quarantine) and reporting (degraded). Only reporting contributes to the chain; the blocked feature-store is dropped, so etl-daily's depth comes from the reporting -> log-archive chain (1 + 1 = 2), not from any path through feature-store."""
        with open(DATA_DIR / "consumers.json", encoding="utf-8") as f:
            consumers_doc = json.load(f)
        producers_of_etl_consumers = {e["consumer"] for e in consumers_doc["edges"] if e["producer"] == "etl-daily"}
        assert "feature-store" in producers_of_etl_consumers
        assert "reporting" in producers_of_etl_consumers
        _pstatus, chain = _build_chain_inputs(loaded_outputs)
        assert chain["etl-daily"] == 1 + chain["reporting"]

    def test_etl_daily_eff_sla_includes_chain_debit(self, loaded_outputs):
        """etl-daily.effective_sla_minutes equals the partial-block multiplier value minus critical_chain_debit_per_link * 2 (depth=2). With base_sla=240, mult=70%, pre=168, burst=0 → burst_sla=168, then -25*2 = 118."""
        with open(DATA_DIR / "cluster.json", encoding="utf-8") as f:
            cluster = json.load(f)
        manifest = json.loads((DATA_DIR / "pipelines" / "etl-daily" / "manifest.json").read_text(encoding="utf-8"))
        base = manifest["sla_hours"] * 60
        mult = cluster["partial_block_sla_multiplier_pct_per_tier"][manifest["tier"]]
        chain = cluster["critical_chain_debit_per_link"]
        pre = (base * mult) // 100
        expected = max(0, pre - chain * 2)
        p = next(p for p in loaded_outputs["schedule_plan.json"]["obj"]["pipelines"] if p["name"] == "etl-daily")
        assert p["effective_sla_minutes"] == expected

    def test_chain_debit_is_clamped_at_zero(self, loaded_outputs):
        """For any pipeline, effective_sla_minutes is non-negative. realtime-ingest in particular has burst_sla=30 and chain_debit=25, so eff_sla=5. Even when burst_sla < chain_debit * depth, clamping keeps the value at 0 rather than going negative."""
        for p in loaded_outputs["schedule_plan.json"]["obj"]["pipelines"]:
            assert p["effective_sla_minutes"] >= 0


# ---------------------------------------------------------------------------
# Impaired-pipeline slot carve-out
# ---------------------------------------------------------------------------


class TestImpairedSlotCarveOut:
    """Degraded and partial_resource_block pipelines partition each (phase, resource_class) into waves of size at most max(1, slots[c] - impaired_slot_carve_out_per_class[c]); scheduled pipelines partition with the un-carved slot count."""

    def test_scheduled_pipeline_uses_uncarved_slot_count(self, loaded_outputs):
        """realtime-ingest is scheduled. Its phase 0 has 3 cpu_small jobs; with the un-carved slot count of 2, the wave plan has exactly 2 waves whose sizes are 2 and 1 (LPT order)."""
        with open(DATA_DIR / "cluster.json", encoding="utf-8") as f:
            cluster = json.load(f)
        slots = cluster["slots_per_resource_class"]
        p = next(p for p in loaded_outputs["wave_plan.json"]["obj"]["pipelines"] if p["name"] == "realtime-ingest")
        phase0 = next(ph for ph in p["phases"] if ph["phase"] == 0)
        cs = next(r for r in phase0["resource_classes"] if r["resource_class"] == "cpu_small")
        wave_sizes = [len(w["jobs"]) for w in cs["waves"]]
        assert wave_sizes == [slots["cpu_small"], 1]

    def test_degraded_pipeline_uses_carved_out_slot_count(self, loaded_outputs):
        """reporting is degraded. Its phase 1 has 3 cpu_small jobs; with cpu_small carve-out = 1 the impaired slot count is max(1, 2-1) = 1, so the wave plan has 3 single-job waves (one per job, in LPT order with alphabetical wave-membership emission)."""
        with open(DATA_DIR / "cluster.json", encoding="utf-8") as f:
            cluster = json.load(f)
        slots = cluster["slots_per_resource_class"]
        carve_out = cluster["impaired_slot_carve_out_per_class"]
        impaired = max(1, slots["cpu_small"] - carve_out["cpu_small"])
        p = next(p for p in loaded_outputs["wave_plan.json"]["obj"]["pipelines"] if p["name"] == "reporting")
        phase1 = next(ph for ph in p["phases"] if ph["phase"] == 1)
        cs = next(r for r in phase1["resource_classes"] if r["resource_class"] == "cpu_small")
        for w in cs["waves"]:
            assert len(w["jobs"]) <= impaired
        assert len(cs["waves"]) == 3

    def test_carve_out_clamps_at_one_slot_minimum(self, loaded_outputs):
        """The carve-out formula floors at 1: even when the carve-out integer equals the un-carved slot count, the impaired_slots value is 1 (so a single job per wave, never zero). The cluster does not currently force this clamp on any class but the formula must still tolerate it; we assert the rule by recomputing impaired_slots for every (degraded or partial_resource_block) pipeline class and confirming each value is at least 1."""
        with open(DATA_DIR / "cluster.json", encoding="utf-8") as f:
            cluster = json.load(f)
        slots = cluster["slots_per_resource_class"]
        carve_out = cluster["impaired_slot_carve_out_per_class"]
        for rc in slots:
            assert max(1, slots[rc] - carve_out.get(rc, 0)) >= 1

    def test_partial_resource_block_pipeline_uses_carved_count(self, loaded_outputs):
        """etl-daily is partial_resource_block. Its only non-frozen job (extract on cpu_small) sits alone in phase 0 and so produces a single wave under either the un-carved (2) or carved (1) cpu_small slot count. The wave plan must still apply the impaired_slots formula consistently with reporting."""
        p = next(p for p in loaded_outputs["wave_plan.json"]["obj"]["pipelines"] if p["name"] == "etl-daily")
        phase0 = next(ph for ph in p["phases"] if ph["phase"] == 0)
        cs = next(r for r in phase0["resource_classes"] if r["resource_class"] == "cpu_small")
        assert len(cs["waves"]) == 1

    def test_burst_pressure_metric_ignores_carve_out(self, loaded_outputs):
        """A degraded pipeline's burst_pressure must be measured against the un-carved cluster.slots_per_resource_class[c], not against impaired_slots(P, c). reporting's phase 1 produces 3 carved waves under impaired_slots=1 yet still has burst_pressure=1 because 3 > 2 (the un-carved cpu_small slot count); reporting's phase 0 and phase 2 produce 1 wave each but neither contributes to burst_pressure since 1 <= 2."""
        with open(DATA_DIR / "cluster.json", encoding="utf-8") as f:
            cluster = json.load(f)
        slots = cluster["slots_per_resource_class"]
        p = next(p for p in loaded_outputs["wave_plan.json"]["obj"]["pipelines"] if p["name"] == "reporting")
        observed_carved_wave_count = sum(
            1
            for ph in p["phases"]
            for r in ph["resource_classes"]
            if len(r["waves"]) > 1
        )
        assert observed_carved_wave_count == 1
        expected_burst = sum(
            1
            for ph in p["phases"]
            for r in ph["resource_classes"]
            if sum(len(w["jobs"]) for w in r["waves"]) > slots[r["resource_class"]]
        )
        assert p["burst_pressure"] == expected_burst == 1

    def test_carved_partition_changes_total_runtime(self, loaded_outputs):
        """reporting's total_runtime_minutes must include the sum of carved-wave durations in phase 1. Re-derived from per-job inputs under cpu_small impaired_slots=1: phase 1 sums to render_pdf(20) + render_html(15) + render_csv(12) = 47, which is strictly greater than the same partition under un-carved slots=2 (which would sum to render_pdf(20) + render_csv(12) = 32). The agent must therefore use the impaired-slot count, not the cluster.slots_per_resource_class value, for impaired pipelines."""
        with open(DATA_DIR / "cluster.json", encoding="utf-8") as f:
            cluster = json.load(f)
        manifest = json.loads((DATA_DIR / "pipelines" / "reporting" / "manifest.json").read_text(encoding="utf-8"))
        penalty = cluster["retry_penalty_minutes_per_tier"][manifest["tier"]]
        effs = []
        for jname in ("render_csv", "render_html", "render_pdf"):
            decl = json.loads((DATA_DIR / "pipelines" / "reporting" / "jobs" / f"{jname}.json").read_text(encoding="utf-8"))
            effs.append(decl["runtime_minutes"] + decl["retry_count"] * penalty)
        carved_phase_runtime = sum(effs)
        uncarved_phase_runtime = max(effs[0], effs[1]) + effs[2] if len(effs) == 3 else 0
        assert carved_phase_runtime > uncarved_phase_runtime
        p = next(p for p in loaded_outputs["schedule_plan.json"]["obj"]["pipelines"] if p["name"] == "reporting")
        fetch_decl = json.loads((DATA_DIR / "pipelines" / "reporting" / "jobs" / "fetch_data.json").read_text(encoding="utf-8"))
        publish_decl = json.loads((DATA_DIR / "pipelines" / "reporting" / "jobs" / "publish.json").read_text(encoding="utf-8"))
        fetch_eff = fetch_decl["runtime_minutes"] + fetch_decl["retry_count"] * penalty
        publish_eff = publish_decl["runtime_minutes"] + publish_decl["retry_count"] * penalty
        expected_total = p["upstream_offset_minutes"] + fetch_eff + carved_phase_runtime + publish_eff
        assert p["total_runtime_minutes"] == expected_total


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


class TestSummary:
    """Summary aggregates must agree with individual reports."""

    def test_total_pipelines(self, loaded_outputs):
        """summary.total_pipelines equals the number of pipeline directories."""
        on_disk = sum(1 for p in (DATA_DIR / "pipelines").iterdir() if p.is_dir())
        assert loaded_outputs["summary.json"]["obj"]["total_pipelines"] == on_disk

    def test_total_jobs(self, loaded_outputs):
        """summary.total_jobs equals the sum of job files across all pipelines."""
        total = 0
        for p in (DATA_DIR / "pipelines").iterdir():
            if not p.is_dir():
                continue
            total += sum(1 for _ in (p / "jobs").glob("*.json"))
        assert loaded_outputs["summary.json"]["obj"]["total_jobs"] == total

    def test_by_pipeline_status_keys(self, loaded_outputs):
        """summary.by_pipeline_status has all five documented keys."""
        d = loaded_outputs["summary.json"]["obj"]["by_pipeline_status"]
        assert set(d.keys()) == {
            "scheduled", "degraded", "partial_resource_block",
            "blocked_quarantine", "blocked_cycle",
        }

    def test_by_job_status_keys(self, loaded_outputs):
        """summary.by_job_status has all five documented keys."""
        d = loaded_outputs["summary.json"]["obj"]["by_job_status"]
        assert set(d.keys()) == {
            "scheduled", "degraded", "blocked_resource_freeze",
            "blocked_quarantine", "blocked_cycle",
        }

    def test_by_pipeline_status_sums_to_total(self, loaded_outputs):
        """summary.by_pipeline_status values sum to total_pipelines."""
        s = loaded_outputs["summary.json"]["obj"]
        assert sum(s["by_pipeline_status"].values()) == s["total_pipelines"]

    def test_by_job_status_sums_to_total(self, loaded_outputs):
        """summary.by_job_status values sum to total_jobs."""
        s = loaded_outputs["summary.json"]["obj"]
        assert sum(s["by_job_status"].values()) == s["total_jobs"]

    def test_sla_violations_complete(self, loaded_outputs):
        """The dataset has exactly three SLA-violating pipelines: log-archive (degraded, upstream offset alone exceeds the upstream-quarantine-debited SLA), realtime-ingest (scheduled but the burst-pressure debit and the chain debit together drive the SLA below the wave-aware total), and reporting (degraded, tight grace-extended SLA against an offset-delayed schedule plus burst debit and chain debit)."""
        violations = loaded_outputs["summary.json"]["obj"]["sla_violations"]
        assert violations == ["log-archive", "realtime-ingest", "reporting"]

    def test_burst_pressure_total_value(self, loaded_outputs):
        """summary.burst_pressure_total counts every (pipeline, phase, resource_class) where non-frozen jobs exceed the slot count; this dataset has exactly two such triples (realtime-ingest phase 0 cpu_small with 3 jobs and reporting phase 1 cpu_small with 3 jobs)."""
        s = loaded_outputs["summary.json"]["obj"]
        assert s["burst_pressure_total"] == 2

    def test_pass_through_fields(self, loaded_outputs):
        """summary.current_day and scheduler_version come straight from pool_state."""
        with open(DATA_DIR / "pool_state.json", encoding="utf-8") as f:
            ps = json.load(f)
        s = loaded_outputs["summary.json"]["obj"]
        assert s["current_day"] == ps["current_day"]
        assert s["scheduler_version"] == ps["scheduler_version"]
