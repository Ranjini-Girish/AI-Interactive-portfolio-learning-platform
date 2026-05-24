import hashlib
import json
import os
import shutil
import subprocess
from collections import Counter, defaultdict, deque
from pathlib import Path


DATA_DIR = Path(os.environ.get("CDC_DATA_DIR", "/app/cdc"))
AUDIT_DIR = Path(os.environ.get("CDC_AUDIT_DIR", "/app/audit"))
EXPECTED_INPUT_HASH = "44ba20c7063306177b08f2b1003770e546af756e218967e68bf2aba6462cff86"
EXPECTED_FIELD_HASHES = {'partition_lag.json': '81307cd73c8b160f99493c21c995b9dbf37144340a16bd8c19fd042ae7437869', 'compaction_plan.json': '4a0225230caab86bc024cd3a9d18274a93393411d139318c469148ad8c2006ac', 'replay_risk.json': '981286747db577aedfc80a8843448643aee0473606569900fc7f3084843012d0', 'quarantine_graph.json': '42f08eebf455287295266ca4a18d01cb5754b4544232e5d77d9d9ea2f345b408', 'summary.json': '2a556e11fd3edade61cf948f98dfc4f6a01810fbb418ffd784b99f4604eaba94'}
REPORTS = [
    "partition_lag.json",
    "compaction_plan.json",
    "replay_risk.json",
    "quarantine_graph.json",
    "summary.json",
]


def parse_rows(path):
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            rows.append(line.split("|"))
    return rows


def canonical_hash(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def input_hash():
    chunks = []
    for path in sorted(p for p in DATA_DIR.rglob("*") if p.is_file()):
        chunks.append(path.relative_to(DATA_DIR).as_posix())
        chunks.append(path.read_text(encoding="utf-8"))
    return hashlib.sha256("\n".join(chunks).encode()).hexdigest()


def load_model():
    current_day = int(parse_rows(DATA_DIR / "pool_state.tsv")[0][1])
    policy = {}
    for tier, min_lag, max_lag, retention, merge_gap, tomb_cap, risk_weight in parse_rows(
        DATA_DIR / "policy.tsv"
    ):
        policy[tier] = {
            "min_lag": int(min_lag),
            "max_lag": int(max_lag),
            "retention": int(retention),
            "merge_gap": int(merge_gap),
            "tomb_cap": int(tomb_cap),
            "risk_weight": int(risk_weight),
        }
    streams = {}
    for stream, tier, upstreams, declared_state in parse_rows(DATA_DIR / "streams.tsv"):
        streams[stream] = {
            "tier": tier,
            "upstreams": [] if upstreams == "-" else upstreams.split(","),
            "declared_state": declared_state,
        }
    partitions = defaultdict(dict)
    for path in sorted((DATA_DIR / "partitions").glob("*.tsv")):
        for partition, last_source, last_sink, event_day in parse_rows(path):
            partitions[path.stem][partition] = {
                "last_source": int(last_source),
                "last_sink": int(last_sink),
                "event_day": int(event_day),
            }
    segments = defaultdict(list)
    for path in sorted((DATA_DIR / "segments").glob("*.tsv")):
        stream, partition = path.stem.rsplit("-", 1)
        for row in parse_rows(path):
            seg_id, low, high, bytes_, tombstones, family, max_event_day = row
            segments[(stream, partition)].append(
                {
                    "segment_id": seg_id,
                    "low": int(low),
                    "high": int(high),
                    "bytes": int(bytes_),
                    "tombstones": int(tombstones),
                    "family": family,
                    "max_event_day": int(max_event_day),
                }
            )
    return current_day, policy, streams, partitions, segments


def event_winner(events):
    return sorted(events, key=lambda event: (-event["day"], event["event_id"]))[0] if events else None


def grouped(events, *keys):
    groups = defaultdict(list)
    for event in events:
        groups[tuple(event[key] for key in keys)].append(event)
    return groups


def accepted_incidents(current_day, streams, partitions):
    supported = {
        "late_arrival_grace",
        "partition_rewind",
        "compaction_hold",
        "stream_compromise",
        "force_replay",
        "source_pause",
    }
    accepted = []
    ignored = 0
    for event_id, kind, stream, partition, day_s, accepted_s, value_a, _ in parse_rows(
        DATA_DIR / "incidents.tsv"
    ):
        day = int(day_s)
        valid = accepted_s == "true" and day <= current_day and kind in supported and stream in streams
        if valid and partition != "*" and partition not in partitions[stream]:
            valid = False
        if valid and kind in {"partition_rewind", "compaction_hold", "force_replay", "source_pause"} and partition == "*":
            valid = False
        if valid:
            accepted.append(
                {
                    "event_id": event_id,
                    "kind": kind,
                    "stream": stream,
                    "partition": partition,
                    "day": day,
                    "value_a": value_a,
                }
            )
        else:
            ignored += 1
    return accepted, ignored


def expected_reports():
    current_day, policy, streams, partitions, segments = load_model()
    incidents, ignored = accepted_incidents(current_day, streams, partitions)
    by_kind = defaultdict(list)
    for event in incidents:
        by_kind[event["kind"]].append(event)

    children = defaultdict(list)
    for stream, meta in streams.items():
        for upstream in meta["upstreams"]:
            children[upstream].append(stream)

    direct_quarantine = {event["stream"] for event in by_kind["stream_compromise"]}
    quarantined = set(direct_quarantine)
    inherited_from = {stream: set() for stream in streams}
    queue = deque((seed, seed) for seed in sorted(direct_quarantine))
    while queue:
        source, stream = queue.popleft()
        for child in sorted(children[stream]):
            inherited_from[child].add(source)
            if child not in quarantined:
                quarantined.add(child)
                queue.append((source, child))

    grace = {
        stream: int(event["value_a"])
        for stream in streams
        if (
            event := event_winner(
                [item for item in by_kind["late_arrival_grace"] if item["stream"] == stream]
            )
        )
    }
    rewinds = {
        (event["stream"], event["partition"]): int(event["value_a"])
        for event in [
            event_winner(items)
            for items in grouped(by_kind["partition_rewind"], "stream", "partition").values()
        ]
        if event
    }
    force_replay = {
        (event["stream"], event["partition"])
        for event in [
            event_winner(items)
            for items in grouped(by_kind["force_replay"], "stream", "partition").values()
        ]
        if event
    }
    active_pause = {
        (event["stream"], event["partition"])
        for event in [
            event_winner(items)
            for items in grouped(by_kind["source_pause"], "stream", "partition").values()
        ]
        if event and event["day"] <= current_day <= event["day"] + int(event["value_a"]) - 1
    }

    partition_rows = []
    part_status_by_stream = defaultdict(list)
    for stream in sorted(streams):
        tier_policy = policy[streams[stream]["tier"]]
        for partition in sorted(partitions[stream]):
            part = partitions[stream][partition]
            effective_sink = min(part["last_sink"], rewinds.get((stream, partition), part["last_sink"]))
            raw_lag = max(0, part["last_source"] - effective_sink)
            event_lag = max(0, current_day - part["event_day"] - grace.get(stream, 0))
            if stream in quarantined:
                status, reasons = "quarantined", ["stream_quarantine"]
            elif (stream, partition) in force_replay or (stream, partition) in rewinds:
                status = "replay_required"
                reasons = ["force_replay" if (stream, partition) in force_replay else "rewind"]
            elif (stream, partition) in active_pause:
                status, reasons = "paused", ["source_pause"]
            elif raw_lag > tier_policy["max_lag"] or event_lag > tier_policy["retention"]:
                status, reasons = "stale", ["lag_threshold"]
            elif raw_lag > tier_policy["min_lag"] or event_lag > 0:
                status, reasons = "lagging", ["within_recovery"]
            else:
                status, reasons = "caught_up", ["within_floor"]
            partition_rows.append(
                {
                    "effective_sink_lsn": effective_sink,
                    "event_lag_days": event_lag,
                    "partition": partition,
                    "raw_lag": raw_lag,
                    "reasons": reasons,
                    "status": status,
                    "stream": stream,
                }
            )
            part_status_by_stream[stream].append(status)

    stream_status = {}
    for stream in sorted(streams):
        statuses = set(part_status_by_stream[stream])
        if stream in quarantined:
            stream_status[stream] = "quarantined"
        elif statuses & {"replay_required", "stale"}:
            stream_status[stream] = "replay_required"
        elif statuses & {"lagging", "paused"}:
            stream_status[stream] = "degraded"
        else:
            stream_status[stream] = "healthy"
    changed = True
    while changed:
        changed = False
        for stream in sorted(streams):
            if stream_status[stream] in {"quarantined", "replay_required"}:
                continue
            if any(stream_status[upstream] in {"quarantined", "replay_required"} for upstream in streams[stream]["upstreams"]):
                if stream_status[stream] != "degraded":
                    stream_status[stream] = "degraded"
                    changed = True

    active_holds = {
        (event["stream"], event["partition"])
        for event in [
            event_winner(items)
            for items in grouped(by_kind["compaction_hold"], "stream", "partition").values()
        ]
        if event and event["day"] <= current_day <= event["day"] + int(event["value_a"]) - 1
    }
    groups = []
    for stream in sorted(streams):
        tier_policy = policy[streams[stream]["tier"]]
        for partition in sorted(partitions[stream]):
            part_segments = sorted(segments[(stream, partition)], key=lambda item: (item["low"], item["segment_id"]))
            if stream in quarantined or (stream, partition) in active_holds:
                action = "hold_quarantine" if stream in quarantined else "hold_incident"
                reason = "stream_quarantine" if stream in quarantined else "active_hold"
                for segment in part_segments:
                    groups.append(segment_group(stream, partition, [segment], action, reason))
                continue
            current = []
            for segment in part_segments:
                if not current:
                    current = [segment]
                    continue
                candidate = current + [segment]
                gap = segment["low"] - current[-1]["high"]
                same_family = segment["family"] == current[-1]["family"]
                tombstones = sum(item["tombstones"] for item in candidate)
                bytes_ = sum(item["bytes"] for item in candidate)
                if same_family and gap <= tier_policy["merge_gap"] and tombstones * 100 <= bytes_ * tier_policy["tomb_cap"]:
                    current.append(segment)
                else:
                    groups.append(decide_group(stream, partition, current, current_day, tier_policy))
                    current = [segment]
            if current:
                groups.append(decide_group(stream, partition, current, current_day, tier_policy))

    risk_rows = []
    for stream in sorted(streams):
        tier_policy = policy[streams[stream]["tier"]]
        lag_component = sum(row["raw_lag"] for row in partition_rows if row["stream"] == stream)
        upstream_q = sum(1 for upstream in streams[stream]["upstreams"] if upstream in quarantined)
        score = lag_component * tier_policy["risk_weight"] // 10
        reasons = []
        if stream_status[stream] == "quarantined":
            score += 100 if stream in direct_quarantine else 80
            reasons.append("quarantine")
        if stream_status[stream] == "replay_required":
            score += 25
            reasons.append("replay")
        if stream_status[stream] == "degraded":
            score += 10
            reasons.append("degraded")
        if upstream_q:
            score += 15 * upstream_q
            reasons.append("upstream_quarantine")
        if not reasons:
            reasons.append("nominal")
        risk_rows.append(
            {
                "reasons": reasons,
                "risk_score": score,
                "status": stream_status[stream],
                "stream": stream,
                "upstream_quarantine_count": upstream_q,
            }
        )
    risk_rows.sort(key=lambda row: (-row["risk_score"], row["stream"]))

    quarantine_rows = []
    for stream in sorted(streams):
        status = "direct" if stream in direct_quarantine else "inherited" if stream in quarantined else "none"
        quarantine_rows.append(
            {
                "inherited_from": sorted(inherited_from[stream]),
                "quarantine_status": status,
                "stream": stream,
            }
        )

    return {
        "partition_lag.json": {"partitions": partition_rows},
        "compaction_plan.json": {"groups": groups},
        "replay_risk.json": {"streams": risk_rows},
        "quarantine_graph.json": {"streams": quarantine_rows},
        "summary.json": {
            "compaction_action_counts": dict(sorted(Counter(group["action"] for group in groups).items())),
            "ignored_incident_events": ignored,
            "partition_status_counts": dict(sorted(Counter(row["status"] for row in partition_rows).items())),
            "stream_status_counts": dict(sorted(Counter(stream_status.values()).items())),
            "total_replay_risk": sum(row["risk_score"] for row in risk_rows),
        },
    }


def segment_group(stream, partition, segments, action, reason):
    return {
        "action": action,
        "bytes": sum(segment["bytes"] for segment in segments),
        "output_high_lsn": max(segment["high"] for segment in segments),
        "output_low_lsn": min(segment["low"] for segment in segments),
        "partition": partition,
        "reason": reason,
        "segment_ids": [segment["segment_id"] for segment in segments],
        "stream": stream,
    }


def decide_group(stream, partition, segments, current_day, tier_policy):
    if len(segments) >= 2:
        return segment_group(stream, partition, segments, "merge", "adjacent_eligible")
    if segments[0]["max_event_day"] <= current_day - tier_policy["retention"]:
        return segment_group(stream, partition, segments, "evict", "retention_expired")
    return segment_group(stream, partition, segments, "keep", "not_mergeable")


def read_report(name):
    return json.loads((AUDIT_DIR / name).read_text(encoding="utf-8"))


class TestInputIntegrity:
    def test_fixture_contents_are_unchanged(self):
        """The read-only input fixture tree keeps the expected canonical digest."""
        assert input_hash() == EXPECTED_INPUT_HASH


class TestReportStructure:
    def test_required_reports_exist_and_only_expected_reports_are_checked(self):
        """Each required report exists and is parseable JSON."""
        for name in REPORTS:
            assert (AUDIT_DIR / name).is_file()
            read_report(name)

    def test_report_hashes_match_expected_fields(self):
        """Every report matches the independently derived canonical field hash."""
        for name, expected_hash in EXPECTED_FIELD_HASHES.items():
            assert canonical_hash(read_report(name)) == expected_hash


class TestPartitionLag:
    def test_rewind_and_force_replay_partitions_are_reported(self):
        """Accepted rewind and force replay rows create replay-required partitions."""
        rows = {(row["stream"], row["partition"]): row for row in read_report("partition_lag.json")["partitions"]}
        assert rows[("payments", "p0")]["effective_sink_lsn"] == 275
        assert rows[("payments", "p0")]["status"] == "replay_required"
        assert rows[("notify", "p0")]["status"] == "replay_required"

    def test_quarantine_precedence_over_pause_and_lag(self):
        """Quarantine status wins before lower-priority partition states."""
        rows = {(row["stream"], row["partition"]): row for row in read_report("partition_lag.json")["partitions"]}
        assert rows[("archive", "p0")]["status"] == "quarantined"
        assert rows[("analytics", "p0")]["status"] == "quarantined"


class TestQuarantineAndRisk:
    def test_direct_and_inherited_quarantine_are_distinguished(self):
        """The quarantine graph records direct and transitive quarantine separately."""
        rows = {row["stream"]: row for row in read_report("quarantine_graph.json")["streams"]}
        assert rows["analytics"]["quarantine_status"] == "direct"
        assert rows["archive"]["quarantine_status"] == "inherited"
        assert rows["archive"]["inherited_from"] == ["analytics"]

    def test_risk_sorting_uses_score_then_stream_name(self):
        """Replay risk entries are ordered by descending score with stable stream ties."""
        rows = read_report("replay_risk.json")["streams"]
        assert rows == sorted(rows, key=lambda row: (-row["risk_score"], row["stream"]))
        assert rows[0]["stream"] == "payments"


class TestCompactionPlan:
    def test_quarantined_streams_hold_every_segment(self):
        """Every segment from a quarantined stream is held instead of merged or evicted."""
        rows = [row for row in read_report("compaction_plan.json")["groups"] if row["stream"] == "analytics"]
        assert rows
        assert {row["action"] for row in rows} == {"hold_quarantine"}

    def test_active_hold_blocks_otherwise_mergeable_partition(self):
        """An active compaction hold emits held single-segment groups for its target."""
        rows = [
            row
            for row in read_report("compaction_plan.json")["groups"]
            if row["stream"] == "fulfill" and row["partition"] == "p1"
        ]
        assert len(rows) == 2
        assert {row["action"] for row in rows} == {"hold_incident"}

    def test_merge_and_retention_actions_are_both_present(self):
        """The fixture exercises both mergeable adjacent groups and expired singletons."""
        actions = Counter(row["action"] for row in read_report("compaction_plan.json")["groups"])
        assert actions["merge"] >= 1
        assert actions["evict"] >= 1


class TestSummary:
    def test_summary_counts_are_recomputed_from_reports(self):
        """Summary aggregates match the statuses and actions in the detailed reports."""
        summary = read_report("summary.json")
        assert summary["partition_status_counts"] == dict(
            sorted(Counter(row["status"] for row in read_report("partition_lag.json")["partitions"]).items())
        )
        assert summary["compaction_action_counts"] == dict(
            sorted(Counter(row["action"] for row in read_report("compaction_plan.json")["groups"]).items())
        )


def _rust_source_bundle():
    source_files = list(Path("/app/auditor/src").glob("*.rs"))
    assert source_files, "expected Rust sources under /app/auditor/src"
    contents = "\n".join(path.read_text(encoding="utf-8") for path in source_files)
    total_lines = sum(len(path.read_text(encoding="utf-8").splitlines()) for path in source_files)
    assert total_lines >= 150, "Rust source is too small for the full audit contract"
    lowered = contents.lower()
    assert "serde" in lowered or "json" in lowered, "Rust source must parse or emit JSON"
    assert "fn main" in contents
    return contents


def _mutated_cdc_dir(tmp_path: Path) -> Path:
    copied = tmp_path / "cdc_mutated"
    shutil.copytree(DATA_DIR, copied)
    pool = copied / "pool_state.tsv"
    rows = pool.read_text(encoding="utf-8").splitlines()
    pool.write_text(rows[0].replace("|20", "|21") + "\n", encoding="utf-8")
    return copied


class TestRustExecutable:
    def test_rust_binary_recreates_reports(self, tmp_path):
        """The Rust executable recomputes reports from CDC_DATA_DIR, not cached audit files."""
        _rust_source_bundle()
        binary = Path("/app/bin/cdc-audit")
        assert binary.is_file()
        assert os.access(binary, os.X_OK)

        baseline = tmp_path / "audit_baseline"
        baseline.mkdir()
        env = os.environ.copy()
        env["CDC_DATA_DIR"] = str(DATA_DIR)
        env["CDC_AUDIT_DIR"] = str(baseline)
        subprocess.run([str(binary)], check=True, env=env)
        for name in REPORTS:
            assert json.loads((baseline / name).read_text(encoding="utf-8")) == read_report(name)

        mutated = _mutated_cdc_dir(tmp_path)
        regen = tmp_path / "audit_mutated"
        regen.mkdir()
        env["CDC_DATA_DIR"] = str(mutated)
        env["CDC_AUDIT_DIR"] = str(regen)
        subprocess.run([str(binary)], check=True, env=env)
        original_lag = read_report("partition_lag.json")
        mutated_lag = json.loads((regen / "partition_lag.json").read_text(encoding="utf-8"))
        assert mutated_lag != original_lag, "binary must recompute output when inputs change"
