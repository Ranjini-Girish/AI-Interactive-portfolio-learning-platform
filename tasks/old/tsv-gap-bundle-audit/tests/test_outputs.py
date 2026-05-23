"""Verifier suite for tsv-gap-bundle-audit (hard, Rust)."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest

DATA_DIR = Path(os.environ.get("TGB_DATA_DIR", "/app/tab_bundle"))
AUDIT_DIR = Path(os.environ.get("TGB_AUDIT_DIR", "/app/audit"))
REPORT = AUDIT_DIR / "gap_report.json"
BIN = Path("/app/target/release/tabgap")


EXPECTED_INPUT_HASHES: Dict[str, str] = {
    "SPEC.md": "849fedf606eb652f86f3b28f9502c269486a25f99651093df7b00486cda2bf85",
    "catalog.json": "58b85388b6a57c7b7d264651e8a6117f25ed3b9a73a8637779c6a481329b3c10",
    "policy.json": "7a7a9d8083b15171f309d1fdab4b8743557c507b8d739968cdc50e807e6ca51f",
    "data/alpha.tsv": "5366223e82df2bd48dc671e03028116859e7fe34850d786f6af05aa50895fa31",
    "data/bravo.tsv": "6b3fe8a206e611f401782337aca5a376485a8415e41adf7b7dff765b7e325e9a",
    "data/charlie.tsv": "ca301ab7d9a40d78ef6fcc014fc90e09c0d37398793915b2cc9464ea8d4aeaca",
    "data/delta.tsv": "35b8268e2ab2128c586514a85ac9a0bc96d45442bfbc50c93353f74f79493940",
    "data/echo.tsv": "d0a48f42ec4f802eeeb8e46d0392f97d4874f42b870d09a741df691a6f95b42f",
    "data/foxtrot.tsv": "729fa0bb548b5fa03e2c64b1a6bd73f00f16f621f528bcd695b70e298e4175fd",
    "deco/slot-a.txt": "f7956fc2c7c6797d0c6447f1227979453d2d0864d91e8f5dd3790e813fc5e9cf",
    "deco/slot-b.txt": "325442e439eb636cef787b2befb4cb1dd0399c9da29651acee1b61afad69c5e4",
    "deco/slot-c.txt": "343e5e21dd27e49980c0c0a90adf3173736ea6b6e47455dc07c095e54c111595",
    "deco/slot-d.txt": "cd432941b609230dd100642a2a762b6f40eec3bace4c0b15fdd69a801429275c",
    "deco/slot-e.txt": "c609b9f758475292409ea7a09b7f4187c94bb3e08f3ca5663ae2ffff7698d75c",
    "deco/slot-f.txt": "87d44e5b9eb767e9087f21efc670095251c094c098800e77298f19e80224c501",
    "deco/slot-g.txt": "fcb818b814d02719351486e0611dce5d6b826ed8d7daae40a147886d7b946115",
    "deco/slot-h.txt": "b36445d3184d40f46ae9c8a9736b037ef89620e948261c25f6e3fbb390faa4f3",
    "deco/slot-i.txt": "b1caf59678c7bc84db4d9973d1a3d5829b6d6b819d290421d97cbe930d4032e2",
    "deco/slot-j.txt": "fd35bc6e8e494f068204f87fab13f153a749f306ec8814e9d208cbd08b3479e6",
    "deco/slot-k.txt": "2c7d33abc6fd4f260f1dd0e97cc512871c9dc4d944914eae06befc4fa3f85464",
    "deco/slot-l.txt": "c44aa7d4da05760e4ebb561314b5560ebb6c045aa1b079d751c05507d2c87fed",
    "deco/slot-m.txt": "d97e95436ba73e4aa88168ced498e35f6daa277a3e3cdfbab28027e9526ccd23",
    "noise/unused-a.tsv": "2376b0498465f9f28919c74bbd872329f03fdf9779b871840305a3fc475994df",
    "noise/unused-b.tsv": "7a8d34250cbad481925acbfe9b9323aeb51f472622f97ef8900587bf20b1f034",
}


def _sha256_bytes(data: bytes) -> str:
    """Lowercase hex SHA-256 of a bytes blob."""
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    """Lowercase hex SHA-256 of the bytes of a file on disk."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canon_json(obj: Any) -> str:
    """Canonical JSON serialization matching the SPEC byte layout."""
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def _is_missing(value: str, extra: set) -> bool:
    """Apply the SPEC missing-value predicate to a single field string."""
    if value == "":
        return True
    if value and all(ch in " \t\r\n" for ch in value):
        return True
    if value == "NA":
        return True
    if value in extra:
        return True
    return False


def _read_tsv(path: Path) -> Tuple[List[str], List[List[str]]]:
    """Parse a TSV file into a header list and a list of padded data rows."""
    raw = path.read_text(encoding="utf-8")
    if not raw:
        return [], []
    lines = raw.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    if not lines:
        return [], []
    header = lines[0].split("\t")
    n = len(header)
    rows: List[List[str]] = []
    for ln in lines[1:]:
        if ln == "":
            rows.append([""] * n)
            continue
        parts = ln.split("\t")
        while len(parts) < n:
            parts.append("")
        rows.append(parts)
    return header, rows


def _format_pct(count: int, total: int) -> str:
    """Truncated six-decimal-digit percentage string per SPEC."""
    if total <= 0:
        return "0.000000"
    num = count * 100_000_000
    q = num // total
    int_part = q // 1_000_000
    frac = q - int_part * 1_000_000
    return f"{int_part}.{str(frac).zfill(6)}"


def compute_reference(base: Path) -> Dict[str, Any]:
    """Re-derive the full gap_report.json structure from the bundle on disk."""
    catalog = json.loads((base / "catalog.json").read_text(encoding="utf-8"))
    policy = json.loads((base / "policy.json").read_text(encoding="utf-8"))
    extra = set(policy.get("extra_missing_tokens", []))
    skip = set(policy.get("rollup_skip_columns", []))
    dedup_keys_sorted = sorted(policy.get("dedup_keys", []))
    global_keys_sorted = sorted(policy.get("global_keys", []))

    inputs = catalog["inputs"]

    per_table: List[Dict[str, Any]] = []
    union_kept: set = set()
    for entry in inputs:
        did = str(entry["dataset_id"])
        rel = str(entry["relative_path"])
        header, rows = _read_tsv(base / rel)
        kept = [c for c in header if c not in skip]
        union_kept.update(kept)
        per_table.append(
            {
                "dataset_id": did,
                "header": header,
                "rows": rows,
                "kept": kept,
            }
        )

    global_kept = sorted(union_kept)

    presence_rows: List[Dict[str, Any]] = []
    col_missing: Dict[str, int] = {c: 0 for c in global_kept}
    dataset_rollups: List[Dict[str, Any]] = []
    duplicate_events: List[Dict[str, Any]] = []
    global_events: List[Dict[str, Any]] = []
    global_first: Dict[Tuple[str, ...], Tuple[str, int]] = {}

    total_data_rows = 0
    global_index = 0

    for table in per_table:
        did = table["dataset_id"]
        header = table["header"]
        rows = table["rows"]
        kept = table["kept"]
        kept_set = set(kept)
        col_idx = {h: i for i, h in enumerate(header)}

        per_dataset_dup_enabled = all(k in kept_set for k in dedup_keys_sorted)
        per_dataset_first: Dict[Tuple[str, ...], int] = {}

        ds_missing = 0
        for ri, row in enumerate(rows, start=1):
            global_index += 1
            total_data_rows += 1
            mask_chars: List[str] = []
            for c in global_kept:
                if c in kept_set:
                    j = col_idx[c]
                    cell = row[j] if j < len(row) else ""
                    if _is_missing(cell, extra):
                        mask_chars.append("0")
                        col_missing[c] += 1
                        ds_missing += 1
                    else:
                        mask_chars.append("1")
                else:
                    mask_chars.append("0")
                    col_missing[c] += 1
                    ds_missing += 1
            mask = "".join(mask_chars)
            presence_rows.append(
                {"dataset_id": did, "mask": mask, "row_index": ri}
            )

            if per_dataset_dup_enabled:
                dk_values: List[str] = []
                any_missing = False
                for k in dedup_keys_sorted:
                    j = col_idx[k]
                    cell = row[j] if j < len(row) else ""
                    if _is_missing(cell, extra):
                        any_missing = True
                        break
                    dk_values.append(cell)
                if not any_missing:
                    key_tuple = tuple(dk_values)
                    if key_tuple in per_dataset_first:
                        duplicate_events.append(
                            {
                                "dataset_id": did,
                                "first_row_index": per_dataset_first[key_tuple],
                                "key_value": list(dk_values),
                                "later_row_index": ri,
                            }
                        )
                    else:
                        per_dataset_first[key_tuple] = ri

            gk_values: List[str] = []
            gk_missing = False
            for k in global_keys_sorted:
                if k not in kept_set:
                    gk_missing = True
                    break
                j = col_idx[k]
                cell = row[j] if j < len(row) else ""
                if _is_missing(cell, extra):
                    gk_missing = True
                    break
                gk_values.append(cell)
            if not gk_missing:
                gkey = tuple(gk_values)
                if gkey in global_first:
                    first_did, first_gidx = global_first[gkey]
                    global_events.append(
                        {
                            "first_dataset_id": first_did,
                            "first_global_index": first_gidx,
                            "key_value": list(gk_values),
                            "later_dataset_id": did,
                            "later_global_index": global_index,
                        }
                    )
                else:
                    global_first[gkey] = (did, global_index)

        cells_total = len(rows) * len(global_kept)
        if cells_total <= 0:
            ds_rate = "0.000000"
        elif ds_missing == cells_total:
            ds_rate = "100.000000"
        elif ds_missing == 0:
            ds_rate = "0.000000"
        else:
            ds_rate = _format_pct(ds_missing, cells_total)
        dataset_rollups.append(
            {
                "cells_total": cells_total,
                "data_rows": len(rows),
                "dataset_id": did,
                "kept_columns_present": sorted(kept),
                "missing_count": ds_missing,
                "missing_rate_dataset": ds_rate,
            }
        )

    column_rollups: List[Dict[str, Any]] = []
    for c in global_kept:
        m = col_missing[c]
        p = total_data_rows - m
        if total_data_rows <= 0:
            mr = "0.000000"
            pr = "0.000000"
        elif m == total_data_rows:
            mr = "100.000000"
            pr = "0.000000"
        elif p == total_data_rows:
            mr = "0.000000"
            pr = "100.000000"
        else:
            mr = _format_pct(m, total_data_rows)
            pr = _format_pct(p, total_data_rows)
        column_rollups.append(
            {
                "column_name": c,
                "missing_count": m,
                "missing_rate": mr,
                "present_count": p,
                "present_rate": pr,
                "total_rows": total_data_rows,
            }
        )

    column_rollups.sort(
        key=lambda o: (
            -Decimal(str(o["missing_rate"])),
            -int(o["missing_count"]),
            str(o["column_name"]),
        )
    )

    dataset_rollups.sort(
        key=lambda o: (
            -Decimal(str(o["missing_rate_dataset"])),
            -int(o["data_rows"]),
            str(o["dataset_id"]),
        )
    )

    presence_rows.sort(key=lambda o: (str(o["dataset_id"]), int(o["row_index"])))

    duplicate_events.sort(
        key=lambda o: (
            str(o["dataset_id"]),
            list(map(str, o["key_value"])),
            int(o["later_row_index"]),
            int(o["first_row_index"]),
        )
    )

    global_events.sort(
        key=lambda o: (
            list(map(str, o["key_value"])),
            int(o["later_global_index"]),
            int(o["first_global_index"]),
        )
    )

    summary = {
        "catalog_inputs": len(inputs),
        "duplicate_key_events": len(duplicate_events),
        "global_key_events": len(global_events),
        "kept_column_count": len(global_kept),
        "total_data_rows": total_data_rows,
    }

    meta = {
        "catalog_sha256": _sha256_file(base / "catalog.json"),
        "dedup_keys": dedup_keys_sorted,
        "extra_missing_tokens": sorted(extra),
        "global_keys": global_keys_sorted,
        "rollup_skip_columns": sorted(skip),
    }

    return {
        "column_rollups": column_rollups,
        "dataset_rollups": dataset_rollups,
        "duplicate_key_events": duplicate_events,
        "global_key_events": global_events,
        "meta": meta,
        "presence_rows": presence_rows,
        "summary": summary,
    }


@pytest.fixture(scope="session")
def expected_report() -> Dict[str, Any]:
    """Independent reference report rebuilt from /app/tab_bundle/."""
    return compute_reference(DATA_DIR)


@pytest.fixture(scope="session")
def actual_report() -> Dict[str, Any]:
    """Parsed agent-produced gap_report.json."""
    assert REPORT.is_file(), "missing /app/audit/gap_report.json"
    return json.loads(REPORT.read_text(encoding="utf-8"))


def test_bundled_data_unchanged() -> None:
    """Every bundled input under /app/tab_bundle/ must still match the shipped SHA-256."""
    for rel, expected in EXPECTED_INPUT_HASHES.items():
        path = DATA_DIR / rel
        assert path.is_file(), f"missing bundled input {rel}"
        assert _sha256_file(path) == expected, f"hash mismatch for {rel}"


def test_report_exists_and_audit_scope() -> None:
    """gap_report.json must exist as a regular file under /app/audit/."""
    assert AUDIT_DIR.is_dir(), "missing /app/audit directory"
    assert REPORT.is_file(), "missing /app/audit/gap_report.json"


def test_top_level_keys(actual_report: Dict[str, Any]) -> None:
    """Top-level object must contain exactly the seven contract keys."""
    assert set(actual_report.keys()) == {
        "column_rollups",
        "dataset_rollups",
        "duplicate_key_events",
        "global_key_events",
        "meta",
        "presence_rows",
        "summary",
    }


def test_canonical_bytes(actual_report: Dict[str, Any], expected_report: Dict[str, Any]) -> None:
    """Bytes on disk must match the canonical reference byte-for-byte."""
    assert actual_report == expected_report
    assert REPORT.read_text(encoding="utf-8") == _canon_json(expected_report)


def test_meta_section(actual_report: Dict[str, Any], expected_report: Dict[str, Any]) -> None:
    """meta must echo policy lists sorted and pin the catalog digest."""
    assert actual_report["meta"] == expected_report["meta"]
    catalog = DATA_DIR / "catalog.json"
    assert actual_report["meta"]["catalog_sha256"] == _sha256_file(catalog)
    assert actual_report["meta"]["extra_missing_tokens"] == sorted(
        actual_report["meta"]["extra_missing_tokens"]
    )
    assert actual_report["meta"]["dedup_keys"] == sorted(actual_report["meta"]["dedup_keys"])
    assert actual_report["meta"]["global_keys"] == sorted(actual_report["meta"]["global_keys"])
    assert actual_report["meta"]["rollup_skip_columns"] == sorted(
        actual_report["meta"]["rollup_skip_columns"]
    )


def test_summary_counts(actual_report: Dict[str, Any], expected_report: Dict[str, Any]) -> None:
    """summary counters must match the independent reference."""
    assert actual_report["summary"] == expected_report["summary"]


def test_column_rollups(actual_report: Dict[str, Any], expected_report: Dict[str, Any]) -> None:
    """column_rollups must use the global denominator and the three-level sort."""
    assert actual_report["column_rollups"] == expected_report["column_rollups"]
    seq = [
        (
            -Decimal(str(r["missing_rate"])),
            -int(r["missing_count"]),
            str(r["column_name"]),
        )
        for r in actual_report["column_rollups"]
    ]
    assert seq == sorted(seq)


def test_dataset_rollups(actual_report: Dict[str, Any], expected_report: Dict[str, Any]) -> None:
    """dataset_rollups must include absent global columns as missing cells."""
    assert actual_report["dataset_rollups"] == expected_report["dataset_rollups"]
    seq = [
        (
            -Decimal(str(r["missing_rate_dataset"])),
            -int(r["data_rows"]),
            str(r["dataset_id"]),
        )
        for r in actual_report["dataset_rollups"]
    ]
    assert seq == sorted(seq)


def test_presence_rows(actual_report: Dict[str, Any], expected_report: Dict[str, Any]) -> None:
    """presence_rows must contain one mask per data row over the global union of kept columns."""
    assert actual_report["presence_rows"] == expected_report["presence_rows"]
    for row in actual_report["presence_rows"]:
        assert len(row["mask"]) == actual_report["summary"]["kept_column_count"]
        assert all(ch in "01" for ch in row["mask"])


def test_duplicate_key_events(
    actual_report: Dict[str, Any], expected_report: Dict[str, Any]
) -> None:
    """Per-dataset duplicate events must skip dedup-disabled datasets and missing key values."""
    assert actual_report["duplicate_key_events"] == expected_report["duplicate_key_events"]


def test_global_key_events(
    actual_report: Dict[str, Any], expected_report: Dict[str, Any]
) -> None:
    """Global key events must be tracked with global indices in catalog order."""
    assert actual_report["global_key_events"] == expected_report["global_key_events"]


def test_release_binary_is_repeatable() -> None:
    """When the release binary is present, clearing the audit dir and re-running must reproduce the report bytes."""
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
