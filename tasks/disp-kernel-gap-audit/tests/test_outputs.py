"""Verifier suite for disp-kernel-gap-audit (hard, Go)."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

import pytest

DATA_DIR = Path(os.environ.get("DISPK_DATA_DIR", "/app/disp_kernel_lab"))
AUDIT_DIR = Path(os.environ.get("DISPK_AUDIT_DIR", "/app/audit"))
REPORT = AUDIT_DIR / "disp_gap.json"
BIN = Path("/app/dispbin/dispkernel")

EXPECTED_INPUT_HASHES: Dict[str, str] = {
    "SPEC.md": "2b3c8a53a8dc0032f9b23ee992177c3206cd477351acbc1e13323640007ff506",
    "lab_aux/flags.json": "2baa92fb81b3391d247c2aac4fe6c6419919e1d4055f113761097427b207e80e",
    "lab_aux/meta.json": "27c107d5d679d1c47424ac0fb2e1c07244eeec17baeb0e094d01af05f4ce6618",
    "catalog.json": "93e4fd8a17ac2002789ad77ccfedf6037a7a68db50a153e8ba8e6d488f779808",
    "incidents.json": "239ca0c1fcec6950dcd0538d4d35ba4b8e2451398985fe272ef8e670e0fb285e",
    "knots.json": "a08815707ac8761ecfdd1f8022c7f06fbf3a1807a419df7fbb7c025061e61ddb",
    "pads/placeholder.json": "d861afbb62d1c7a9627cad318ac232f28e0d6b2b5f9d6b642e55f0b04948deae",
    "policy.json": "c9c579df6a276681806b1091766d2583c419f5f9e815ea742a7552772d3ea66b",
    "pool_state.json": "8bbda948563802f5dd2bcc71307a80bd9c0f461d9ec097e814ba7f056953588c",
    "tracks/t00.json": "09f232e1f6134b6c47ad2fd2c9b9c9ab9886ccf9d56df07b0a167fa222728635",
    "tracks/t01.json": "a4358719006d3db8d44ee06a85b5449035a8ae9619fd3b9e8e5c15c42bd4cabe",
    "tracks/t02.json": "46c4278c3d9ba0dfc5bf578817d91b4905fb1653838f359a7585db7cc731457f",
    "tracks/t03.json": "9ceae9e09f7f7b2fe589bfb841b34107c5b6c014bb77d6d9930920546d885688",
    "tracks/t04.json": "b1d569b54488b33a21b8ff9e14dd3811951ad07c66663b72b7d6f788956eef41",
    "tracks/t05.json": "4b7f282da2a00d4d95e80098092100cebc823dcaa3c9769ef90b3ed7059d6342",
    "tracks/t06.json": "aa8bd25ba81817eaa25f00d683c7ea3467651d840a9eb1d626ebf374b69fa26d",
    "tracks/t07.json": "487306d8c1aea27f420eb5051096171af4f6583b5b833a3891d7c79ab5a305ee",
    "tracks/t08.json": "cb0ecd5f5fbfdc2e1674ab4663380c6ba99d75dee12fe30460bdef191eca668f",
    "tracks/t09.json": "1e395ac7132190a47c004b89246d6215e4101340d8f562605b4953380b9ba711",
    "tracks/t10.json": "970f49c19f661d24d6ee16e1fa077d7569ca14cfe7a9062d2650c36b035c29a8",
    "tracks/t11.json": "9880c0a3557698696c714ea12966959ea9bd2eed4cf1a3e83748e67dc3588bcd",
    "tracks/t12.json": "193cb82ce2b9763beec68b33947a97fbe50c8023971b73e833af848b52871cb5",
    "tracks/t13.json": "95ff70106e267b1906897f428d89a97eb21148e63df2e0854e0262e2fba81741",
}


def _sha256_file(path: Path) -> str:
    """Return lowercase hex SHA-256 of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canon_json(obj: Any) -> str:
    """Canonical JSON matching SPEC on-disk layout."""
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def _interp_n(knots: List[Dict[str, int]], L: int, diags: Set[str]) -> int:
    """Interpolate n_q at wavelength L per SPEC."""
    ks = [(int(k["lambda_q"]), int(k["n_q"])) for k in knots]
    if not ks:
        return 0
    for lam, nq in ks:
        if lam == L:
            return nq
    if L < ks[0][0]:
        diags.add("extrap_low")
        return ks[0][1]
    if L > ks[-1][0]:
        diags.add("extrap_high")
        return ks[-1][1]
    for i in range(len(ks) - 1):
        l0, n0 = ks[i]
        l1, n1 = ks[i + 1]
        if l0 < L < l1:
            step = (n1 - n0) * (L - l0) // (l1 - l0)
            return n0 + step
    return ks[-1][1]


def compute_reference(base: Path) -> Dict[str, Any]:
    """Re-derive disp_gap.json from fixtures under base."""
    policy = json.loads((base / "policy.json").read_text(encoding="utf-8"))
    knots = json.loads((base / "knots.json").read_text(encoding="utf-8"))["knots"]
    catalog = json.loads((base / "catalog.json").read_text(encoding="utf-8"))
    incidents = json.loads((base / "incidents.json").read_text(encoding="utf-8"))
    pool = json.loads((base / "pool_state.json").read_text(encoding="utf-8"))

    day = int(policy["current_day"])
    b = int(policy["base"])
    init = int(policy["init"])
    mod = int(policy["modulus"])
    jump = int(policy["phase_jump_q"])
    collapse = bool(policy["collapse_lambda"])
    band_bias = {str(k): int(v) for k, v in policy["band_bias"].items()}

    cap_raw = pool.get("terminal_sum_cap")
    cap: int | None = int(cap_raw) if cap_raw is not None else None

    suppressed: Set[Tuple[str, str]] = set()
    band_inc_bias: Dict[str, int] = {}
    compromised: Set[str] = set()
    for ev in incidents.get("events", []):
        kind = str(ev.get("kind", ""))
        if kind == "suppress_sample":
            if int(ev["start_day"]) <= day <= int(ev["end_day"]):
                suppressed.add((str(ev["track_id"]), str(ev["sample_id"])))
        elif kind == "bias_band":
            if int(ev["start_day"]) <= day <= int(ev["end_day"]):
                bid = str(ev["band_id"])
                band_inc_bias[bid] = band_inc_bias.get(bid, 0) + int(ev["bias_q"])
        elif kind == "compromise_track":
            if bool(ev.get("accepted", False)) and day >= int(ev["day"]):
                compromised.add(str(ev["track_id"]))

    total_cataloged = 0
    rollups: List[Dict[str, Any]] = []

    for tr in sorted(catalog["tracks"], key=lambda o: str(o["track_id"])):
        tid = str(tr["track_id"])
        path = str(tr["path"])
        raw = json.loads((base / path).read_text(encoding="utf-8"))
        samples = [dict(s) for s in raw.get("samples", [])]
        total_cataloged += len(samples)

        if tid in compromised:
            rollups.append(
                {
                    "diagnostics": ["track_compromised"],
                    "gap_mix_steps": 0,
                    "samples_kept": 0,
                    "status": "quarantined",
                    "terminal_digest": 0,
                    "track_id": tid,
                }
            )
            continue

        kept: List[Dict[str, Any]] = []
        for s in samples:
            sid = str(s["sample_id"])
            if (tid, sid) in suppressed:
                continue
            kept.append(s)

        diags: Set[str] = set()
        if collapse:
            by_lam: Dict[int, List[Dict[str, Any]]] = {}
            for s in kept:
                by_lam.setdefault(int(s["lambda_q"]), []).append(s)
            merged: List[Dict[str, Any]] = []
            for lam in sorted(by_lam.keys()):
                grp = sorted(by_lam[lam], key=lambda o: str(o["sample_id"]))
                merged.append(grp[0])
                if len(grp) > 1:
                    diags.add("lambda_collapsed")
            kept = merged

        kept.sort(key=lambda o: (int(o["lambda_q"]), str(o["sample_id"])))

        for i in range(len(kept) - 1):
            p0 = int(kept[i]["phase_q"])
            p1 = int(kept[i + 1]["phase_q"])
            if abs(p1 - p0) > jump:
                diags.add("phase_discontinuity")
                break

        h = init % mod
        for s in kept:
            L = int(s["lambda_q"])
            meas = int(s["n_meas_q"])
            bid = str(s["band_id"])
            local_diags: Set[str] = set()
            n_i = _interp_n(knots, L, local_diags)
            diags |= local_diags
            signed = meas - n_i
            if bid in band_bias:
                signed += band_bias[bid]
            else:
                diags.add("unknown_band")
            signed += band_inc_bias.get(bid, 0)
            gap = abs(signed)
            h = (h * b + gap) % mod

        rollups.append(
            {
                "diagnostics": sorted(diags),
                "gap_mix_steps": len(kept),
                "samples_kept": len(kept),
                "status": "ok",
                "terminal_digest": int(h),
                "track_id": tid,
            }
        )

    raw_by = {str(r["track_id"]): int(r["terminal_digest"]) for r in rollups if r["status"] == "ok"}
    s_sum = sum(raw_by.values())
    cap_applied = False
    scaled_sum: int | None = None
    if cap is not None and s_sum > cap:
        cap_applied = True
        c = int(cap)
        scaled_sum = 0
        for r in rollups:
            if r["status"] != "ok":
                continue
            tid = str(r["track_id"])
            raw = raw_by[tid]
            new_v = (raw * c) // s_sum if s_sum > 0 else 0
            r["terminal_digest"] = int(new_v)
            scaled_sum += int(new_v)
    else:
        for r in rollups:
            if r["status"] == "ok":
                tid = str(r["track_id"])
                r["terminal_digest"] = raw_by[tid]

    n_quar = sum(1 for r in rollups if r["status"] == "quarantined")
    kept_total = sum(int(r["samples_kept"]) for r in rollups)

    meta = {
        "base": b,
        "catalog_sha256": _sha256_file(base / "catalog.json"),
        "current_day": day,
        "incidents_sha256": _sha256_file(base / "incidents.json"),
        "init": init,
        "knots_sha256": _sha256_file(base / "knots.json"),
        "modulus": mod,
        "policy_sha256": _sha256_file(base / "policy.json"),
        "pool_sha256": _sha256_file(base / "pool_state.json"),
    }
    summary = {
        "cap_applied": cap_applied,
        "quarantined_tracks": int(n_quar),
        "scaled_sum": scaled_sum,
        "total_samples_cataloged": int(total_cataloged),
        "total_samples_kept": int(kept_total),
        "tracks": int(len(rollups)),
    }
    return {"meta": meta, "summary": summary, "track_rollups": rollups}


@pytest.fixture(scope="session")
def expected_report() -> Dict[str, Any]:
    """Reference report rebuilt from bundled fixtures."""
    return compute_reference(DATA_DIR)


@pytest.fixture(scope="session")
def actual_report() -> Dict[str, Any]:
    """Parsed agent-produced disp_gap.json."""
    assert REPORT.is_file(), "missing /app/audit/disp_gap.json"
    return json.loads(REPORT.read_text(encoding="utf-8"))


def test_bundled_data_unchanged() -> None:
    """Bundled inputs under the lab directory must match pinned SHA-256 values."""
    for rel, expected in EXPECTED_INPUT_HASHES.items():
        path = DATA_DIR / rel
        assert path.is_file(), f"missing bundled input {rel}"
        assert _sha256_file(path) == expected, f"hash mismatch for {rel}"


def test_report_exists() -> None:
    """disp_gap.json must exist under the audit directory."""
    assert AUDIT_DIR.is_dir(), "missing /app/audit directory"
    assert REPORT.is_file(), "missing /app/audit/disp_gap.json"


def test_top_level_keys(actual_report: Dict[str, Any]) -> None:
    """Top-level JSON must contain exactly meta, track_rollups, summary."""
    assert set(actual_report.keys()) == {"meta", "summary", "track_rollups"}


def test_canonical_bytes(actual_report: Dict[str, Any], expected_report: Dict[str, Any]) -> None:
    """On-disk bytes must match canonical reference serialization."""
    assert actual_report == expected_report
    assert REPORT.read_text(encoding="utf-8") == _canon_json(expected_report)


def test_meta_hashes(actual_report: Dict[str, Any], expected_report: Dict[str, Any]) -> None:
    """meta must pin every policy input file and echo numeric knobs."""
    assert actual_report["meta"] == expected_report["meta"]


def test_track_rollups_sorted_and_fields(
    actual_report: Dict[str, Any], expected_report: Dict[str, Any]
) -> None:
    """track_rollups must be sorted and carry the contract fields."""
    assert actual_report["track_rollups"] == expected_report["track_rollups"]
    ids = [str(r["track_id"]) for r in actual_report["track_rollups"]]
    assert ids == sorted(ids)
    for r in actual_report["track_rollups"]:
        assert set(r.keys()) == {
            "diagnostics",
            "gap_mix_steps",
            "samples_kept",
            "status",
            "terminal_digest",
            "track_id",
        }
        assert r["diagnostics"] == sorted(set(r["diagnostics"]))


def test_summary_counters(actual_report: Dict[str, Any], expected_report: Dict[str, Any]) -> None:
    """summary block must match the reference counters and scaling flag."""
    assert actual_report["summary"] == expected_report["summary"]


def test_trk04_quarantined(actual_report: Dict[str, Any]) -> None:
    """trk-04 must be quarantined with the compromise diagnostic only."""
    row = next(r for r in actual_report["track_rollups"] if r["track_id"] == "trk-04")
    assert row["status"] == "quarantined"
    assert row["samples_kept"] == 0
    assert row["terminal_digest"] == 0
    assert row["diagnostics"] == ["track_compromised"]


def test_trk02_lambda_collapsed(actual_report: Dict[str, Any]) -> None:
    """trk-02 must record lambda_collapsed after duplicate wavelengths merge."""
    row = next(r for r in actual_report["track_rollups"] if r["track_id"] == "trk-02")
    assert row["status"] == "ok"
    assert "lambda_collapsed" in row["diagnostics"]
    assert row["samples_kept"] == 1


def test_trk01_extrap_low_and_bias(actual_report: Dict[str, Any]) -> None:
    """trk-01 must carry extrap_low from sub-first-knot wavelength."""
    row = next(r for r in actual_report["track_rollups"] if r["track_id"] == "trk-01")
    assert row["diagnostics"] == ["extrap_low"]


def test_cap_applied_when_pool_tight(actual_report: Dict[str, Any]) -> None:
    """When raw digests exceed the pool cap, summary.cap_applied is true."""
    assert actual_report["summary"]["cap_applied"] is True
    assert isinstance(actual_report["summary"]["scaled_sum"], int)


def test_unknown_band_on_trk05(actual_report: Dict[str, Any]) -> None:
    """trk-05 must flag unknown_band for an unlisted band_id."""
    row = next(r for r in actual_report["track_rollups"] if r["track_id"] == "trk-05")
    assert "unknown_band" in row["diagnostics"]


def test_release_binary_is_repeatable() -> None:
    """Re-running the release binary on a clean audit dir reproduces the report."""
    if not BIN.is_file():
        pytest.skip("release binary not present")
    assert AUDIT_DIR.is_dir()
    for child in AUDIT_DIR.iterdir():
        if child.is_file():
            child.unlink()
    res = subprocess.run([str(BIN)], cwd="/app", capture_output=True, text=True, timeout=120)
    assert res.returncode == 0, res.stderr
    assert REPORT.is_file()
    assert json.loads(REPORT.read_text(encoding="utf-8")) == compute_reference(DATA_DIR)
