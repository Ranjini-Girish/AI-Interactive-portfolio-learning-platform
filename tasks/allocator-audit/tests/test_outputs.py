"""Verification suite for the Rust memory allocator simulator."""
import json
import math
import pathlib
import shutil
import subprocess

ROOT = pathlib.Path("/app")


OUT_DIR = pathlib.pathlib.Path('/app/output')
BUILD = ROOT / "build"
DATA_DIR = pathlib.pathlib.Path('/app/data')

FLOAT_TOL = 5e-7


def load_report():
    p = OUT_DIR / "allocator_report.json"
    assert p.is_file(), f"Missing output file: {p}"
    return json.loads(p.read_text(encoding="utf-8"))


R = load_report()


def tr(trace_id):
    for t in R["traces"]:
        if t["trace_id"] == trace_id:
            return t
    raise AssertionError(f"Trace {trace_id} not found in report")


# ─── Output file and structure ───────────────────────────────────────────────


def test_output_file_exists():
    assert (OUT_DIR / "allocator_report.json").is_file()


def test_top_level_keys():
    assert set(R.keys()) == {"pool_config", "traces", "summary"}


def test_pool_config_fields():
    cfg = R["pool_config"]
    assert cfg["pool_size"] == 1024
    assert cfg["header_size"] == 16
    assert cfg["min_alignment"] == 8


def test_traces_is_list():
    assert isinstance(R["traces"], list)


def test_traces_count():
    assert len(R["traces"]) == 12


def test_traces_sorted():
    ids = [t["trace_id"] for t in R["traces"]]
    assert ids == sorted(ids)


def test_trace_ids_complete():
    ids = {t["trace_id"] for t in R["traces"]}
    expected = {f"trace_{i:02d}" for i in range(1, 13)}
    assert ids == expected


def test_trace_required_keys():
    required = {"trace_id", "total_operations", "successful_allocs",
                "failed_allocs", "successful_reallocs", "failed_reallocs",
                "deallocs", "errors", "final_state", "high_water_mark",
                "peak_live_blocks"}
    for t in R["traces"]:
        assert set(t.keys()) == required, f"{t['trace_id']} keys: {sorted(t.keys())}"


def test_final_state_keys():
    required = {"live_allocations", "free_blocks", "largest_free_usable",
                "total_free_usable", "total_allocated_bytes",
                "pool_utilization", "external_fragmentation",
                "internal_fragmentation"}
    for t in R["traces"]:
        assert set(t["final_state"].keys()) == required


def test_summary_keys():
    required = {"total_traces", "total_operations", "total_errors",
                "total_oom_events", "traces_with_errors", "traces_fully_freed"}
    assert set(R["summary"].keys()) == required


def test_json_trailing_newline():
    raw = (OUT_DIR / "allocator_report.json").read_text(encoding="utf-8")
    assert raw.endswith("\n")


def test_json_two_space_indent():
    raw = (OUT_DIR / "allocator_report.json").read_text(encoding="utf-8")
    json.loads(raw)
    lines = raw.rstrip("\n").split("\n")
    assert len(lines) > 1
    for i, line in enumerate(lines):
        stripped = line.lstrip(" ")
        indent = len(line) - len(stripped)
        assert "\t" not in line, f"Line {i+1} uses tab"
        if stripped and indent > 0:
            assert indent % 2 == 0, f"Line {i+1}: indent {indent} not multiple of 2"


# ─── Summary tests ──────────────────────────────────────────────────────────


def test_summary_total_traces():
    assert R["summary"]["total_traces"] == 12


def test_summary_total_operations():
    total = sum(t["total_operations"] for t in R["traces"])
    assert R["summary"]["total_operations"] == total
    assert R["summary"]["total_operations"] == 158


def test_summary_total_errors():
    total = sum(len(t["errors"]) for t in R["traces"])
    assert R["summary"]["total_errors"] == total
    assert R["summary"]["total_errors"] == 10


def test_summary_total_oom_events():
    total = sum(
        sum(1 for e in t["errors"] if e["error_type"] == "oom")
        for t in R["traces"]
    )
    assert R["summary"]["total_oom_events"] == total
    assert R["summary"]["total_oom_events"] == 5


def test_summary_traces_with_errors():
    count = sum(1 for t in R["traces"] if t["errors"])
    assert R["summary"]["traces_with_errors"] == count
    assert R["summary"]["traces_with_errors"] == 6


def test_summary_traces_fully_freed():
    count = sum(1 for t in R["traces"]
                if t["final_state"]["live_allocations"] == 0)
    assert R["summary"]["traces_fully_freed"] == count
    assert R["summary"]["traces_fully_freed"] == 8


# ─── Trace 01: Basic alloc/dealloc ──────────────────────────────────────────


def test_t01_operations():
    assert tr("trace_01")["total_operations"] == 8


def test_t01_allocs():
    assert tr("trace_01")["successful_allocs"] == 4
    assert tr("trace_01")["failed_allocs"] == 0


def test_t01_deallocs():
    assert tr("trace_01")["deallocs"] == 4


def test_t01_no_errors():
    assert tr("trace_01")["errors"] == []


def test_t01_fully_freed():
    assert tr("trace_01")["final_state"]["live_allocations"] == 0


def test_t01_single_free_block():
    assert tr("trace_01")["final_state"]["free_blocks"] == 1


def test_t01_largest_free():
    assert tr("trace_01")["final_state"]["largest_free_usable"] == 1008


def test_t01_total_free():
    assert tr("trace_01")["final_state"]["total_free_usable"] == 1008


def test_t01_high_water_mark():
    assert tr("trace_01")["high_water_mark"] == 224


def test_t01_peak_live():
    assert tr("trace_01")["peak_live_blocks"] == 3


def test_t01_pool_utilization():
    assert tr("trace_01")["final_state"]["pool_utilization"] == 0.0


def test_t01_ext_frag():
    assert tr("trace_01")["final_state"]["external_fragmentation"] == 0.0


# ─── Trace 02: Alignment stress ─────────────────────────────────────────────


def test_t02_operations():
    assert tr("trace_02")["total_operations"] == 16


def test_t02_all_allocs_succeed():
    assert tr("trace_02")["successful_allocs"] == 8
    assert tr("trace_02")["failed_allocs"] == 0


def test_t02_fully_freed():
    assert tr("trace_02")["final_state"]["live_allocations"] == 0


def test_t02_high_water_mark():
    assert tr("trace_02")["high_water_mark"] == 68


def test_t02_peak_live():
    assert tr("trace_02")["peak_live_blocks"] == 8


def test_t02_coalesced():
    assert tr("trace_02")["final_state"]["free_blocks"] == 1


# ─── Trace 03: Coalescing ───────────────────────────────────────────────────


def test_t03_operations():
    assert tr("trace_03")["total_operations"] == 7


def test_t03_live_at_end():
    assert tr("trace_03")["final_state"]["live_allocations"] == 1


def test_t03_free_blocks():
    assert tr("trace_03")["final_state"]["free_blocks"] == 2


def test_t03_high_water_mark():
    assert tr("trace_03")["high_water_mark"] == 256


def test_t03_ext_frag():
    f = tr("trace_03")["final_state"]["external_fragmentation"]
    assert math.isclose(f, 0.245614, abs_tol=FLOAT_TOL)


def test_t03_pool_util():
    assert math.isclose(tr("trace_03")["final_state"]["pool_utilization"],
                         0.078125, abs_tol=FLOAT_TOL)


def test_t03_allocated_bytes():
    assert tr("trace_03")["final_state"]["total_allocated_bytes"] == 80


def test_t03_largest_free():
    assert tr("trace_03")["final_state"]["largest_free_usable"] == 688


def test_t03_total_free():
    assert tr("trace_03")["final_state"]["total_free_usable"] == 912


# ─── Trace 04: Realloc ──────────────────────────────────────────────────────


def test_t04_operations():
    assert tr("trace_04")["total_operations"] == 11


def test_t04_reallocs():
    assert tr("trace_04")["successful_reallocs"] == 3
    assert tr("trace_04")["failed_reallocs"] == 0


def test_t04_allocs():
    assert tr("trace_04")["successful_allocs"] == 4


def test_t04_fully_freed():
    assert tr("trace_04")["final_state"]["live_allocations"] == 0


def test_t04_no_errors():
    assert tr("trace_04")["errors"] == []


def test_t04_high_water_mark():
    assert tr("trace_04")["high_water_mark"] == 244


# ─── Trace 05: OOM conditions ───────────────────────────────────────────────


def test_t05_operations():
    assert tr("trace_05")["total_operations"] == 8


def test_t05_failed_allocs():
    assert tr("trace_05")["failed_allocs"] == 2


def test_t05_successful_allocs():
    assert tr("trace_05")["successful_allocs"] == 3


def test_t05_error_count():
    assert len(tr("trace_05")["errors"]) == 2


def test_t05_error_types():
    for e in tr("trace_05")["errors"]:
        assert e["error_type"] == "oom"


def test_t05_oom1_index():
    assert tr("trace_05")["errors"][0]["operation_index"] == 2
    assert tr("trace_05")["errors"][0]["id"] == "oom1"


def test_t05_oom2_index():
    assert tr("trace_05")["errors"][1]["operation_index"] == 5
    assert tr("trace_05")["errors"][1]["id"] == "oom2"


def test_t05_high_water_mark():
    assert tr("trace_05")["high_water_mark"] == 800


def test_t05_fully_freed():
    assert tr("trace_05")["final_state"]["live_allocations"] == 0


# ─── Trace 06: Double-free and use-after-free ────────────────────────────────


def test_t06_operations():
    assert tr("trace_06")["total_operations"] == 8


def test_t06_error_count():
    assert len(tr("trace_06")["errors"]) == 4


def test_t06_double_free_p1():
    e = tr("trace_06")["errors"][0]
    assert e["operation_index"] == 3
    assert e["error_type"] == "double_free"
    assert e["id"] == "p1"


def test_t06_use_after_free_p1():
    e = tr("trace_06")["errors"][1]
    assert e["operation_index"] == 4
    assert e["error_type"] == "use_after_free"
    assert e["id"] == "p1"


def test_t06_double_free_p2():
    e = tr("trace_06")["errors"][2]
    assert e["operation_index"] == 6
    assert e["error_type"] == "double_free"
    assert e["id"] == "p2"


def test_t06_unknown_dealloc():
    e = tr("trace_06")["errors"][3]
    assert e["operation_index"] == 7
    assert e["error_type"] == "double_free"
    assert e["id"] == "nonexistent"


def test_t06_valid_deallocs():
    assert tr("trace_06")["deallocs"] == 2


def test_t06_failed_reallocs():
    assert tr("trace_06")["failed_reallocs"] == 1


def test_t06_fully_freed():
    assert tr("trace_06")["final_state"]["live_allocations"] == 0


def test_t06_high_water_mark():
    assert tr("trace_06")["high_water_mark"] == 128


# ─── Trace 07: Zero-size allocations ────────────────────────────────────────


def test_t07_operations():
    assert tr("trace_07")["total_operations"] == 10


def test_t07_allocs():
    assert tr("trace_07")["successful_allocs"] == 5


def test_t07_no_errors():
    assert tr("trace_07")["errors"] == []


def test_t07_fully_freed():
    assert tr("trace_07")["final_state"]["live_allocations"] == 0


def test_t07_high_water_mark():
    assert tr("trace_07")["high_water_mark"] == 96


def test_t07_peak_live():
    assert tr("trace_07")["peak_live_blocks"] == 4


# ─── Trace 08: Fragmentation stress ─────────────────────────────────────────


def test_t08_operations():
    assert tr("trace_08")["total_operations"] == 10


def test_t08_live_at_end():
    assert tr("trace_08")["final_state"]["live_allocations"] == 4


def test_t08_free_blocks():
    assert tr("trace_08")["final_state"]["free_blocks"] == 4


def test_t08_ext_frag():
    f = tr("trace_08")["final_state"]["external_fragmentation"]
    assert math.isclose(f, 0.137931, abs_tol=FLOAT_TOL)


def test_t08_int_frag():
    f = tr("trace_08")["final_state"]["internal_fragmentation"]
    assert math.isclose(f, 0.015152, abs_tol=FLOAT_TOL)


def test_t08_pool_util():
    u = tr("trace_08")["final_state"]["pool_utilization"]
    assert math.isclose(u, 0.257813, abs_tol=FLOAT_TOL)


def test_t08_allocated_bytes():
    assert tr("trace_08")["final_state"]["total_allocated_bytes"] == 264


def test_t08_largest_free():
    assert tr("trace_08")["final_state"]["largest_free_usable"] == 600


def test_t08_total_free():
    assert tr("trace_08")["final_state"]["total_free_usable"] == 696


def test_t08_high_water_mark():
    assert tr("trace_08")["high_water_mark"] == 196


def test_t08_peak_live():
    assert tr("trace_08")["peak_live_blocks"] == 6


# ─── Trace 09: Many small allocations ───────────────────────────────────────


def test_t09_operations():
    assert tr("trace_09")["total_operations"] == 43


def test_t09_successful_allocs():
    assert tr("trace_09")["successful_allocs"] == 42
    assert tr("trace_09")["failed_allocs"] == 1


def test_t09_live_at_end():
    assert tr("trace_09")["final_state"]["live_allocations"] == 42


def test_t09_no_free_blocks():
    assert tr("trace_09")["final_state"]["free_blocks"] == 0


def test_t09_full_utilization():
    assert tr("trace_09")["final_state"]["pool_utilization"] == 1.0


def test_t09_total_allocated():
    assert tr("trace_09")["final_state"]["total_allocated_bytes"] == 1024


def test_t09_int_frag():
    f = tr("trace_09")["final_state"]["internal_fragmentation"]
    assert math.isclose(f, 0.015625, abs_tol=FLOAT_TOL)


def test_t09_ext_frag():
    assert tr("trace_09")["final_state"]["external_fragmentation"] == 0.0


def test_t09_oom_error():
    assert len(tr("trace_09")["errors"]) == 1
    e = tr("trace_09")["errors"][0]
    assert e["error_type"] == "oom"
    assert e["id"] == "overflow"
    assert e["operation_index"] == 42


def test_t09_high_water_mark():
    assert tr("trace_09")["high_water_mark"] == 336


def test_t09_peak_live():
    assert tr("trace_09")["peak_live_blocks"] == 42


def test_t09_largest_free_zero():
    assert tr("trace_09")["final_state"]["largest_free_usable"] == 0


# ─── Trace 10: Combined edge cases ──────────────────────────────────────────


def test_t10_operations():
    assert tr("trace_10")["total_operations"] == 14


def test_t10_allocs():
    assert tr("trace_10")["successful_allocs"] == 6


def test_t10_reallocs():
    assert tr("trace_10")["successful_reallocs"] == 2


def test_t10_deallocs():
    assert tr("trace_10")["deallocs"] == 5


def test_t10_error_count():
    assert len(tr("trace_10")["errors"]) == 1


def test_t10_double_free():
    e = tr("trace_10")["errors"][0]
    assert e["operation_index"] == 11
    assert e["error_type"] == "double_free"
    assert e["id"] == "m1"


def test_t10_live_at_end():
    assert tr("trace_10")["final_state"]["live_allocations"] == 1


def test_t10_free_blocks():
    assert tr("trace_10")["final_state"]["free_blocks"] == 1


def test_t10_allocated_bytes():
    assert tr("trace_10")["final_state"]["total_allocated_bytes"] == 920


def test_t10_pool_util():
    u = tr("trace_10")["final_state"]["pool_utilization"]
    assert math.isclose(u, 0.898438, abs_tol=FLOAT_TOL)


def test_t10_ext_frag():
    assert tr("trace_10")["final_state"]["external_fragmentation"] == 0.0


def test_t10_int_frag():
    f = tr("trace_10")["final_state"]["internal_fragmentation"]
    assert math.isclose(f, 0.004348, abs_tol=FLOAT_TOL)


def test_t10_high_water_mark():
    assert tr("trace_10")["high_water_mark"] == 900


def test_t10_peak_live():
    assert tr("trace_10")["peak_live_blocks"] == 4


def test_t10_largest_free():
    assert tr("trace_10")["final_state"]["largest_free_usable"] == 88


def test_t10_total_free():
    assert tr("trace_10")["final_state"]["total_free_usable"] == 88


# ─── Trace 11: Realloc with split boundary and OOM retry ────────────────────


def test_t11_operations():
    assert tr("trace_11")["total_operations"] == 12


def test_t11_allocs():
    assert tr("trace_11")["successful_allocs"] == 4
    assert tr("trace_11")["failed_allocs"] == 0


def test_t11_reallocs():
    assert tr("trace_11")["successful_reallocs"] == 3
    assert tr("trace_11")["failed_reallocs"] == 1


def test_t11_deallocs():
    assert tr("trace_11")["deallocs"] == 4


def test_t11_error_count():
    assert len(tr("trace_11")["errors"]) == 1


def test_t11_oom_error():
    e = tr("trace_11")["errors"][0]
    assert e["operation_index"] == 8
    assert e["error_type"] == "oom"
    assert e["id"] == "a"


def test_t11_fully_freed():
    assert tr("trace_11")["final_state"]["live_allocations"] == 0


def test_t11_single_free_block():
    assert tr("trace_11")["final_state"]["free_blocks"] == 1


def test_t11_high_water_mark():
    assert tr("trace_11")["high_water_mark"] == 800


def test_t11_peak_live():
    assert tr("trace_11")["peak_live_blocks"] == 4


def test_t11_largest_free():
    assert tr("trace_11")["final_state"]["largest_free_usable"] == 1008


def test_t11_total_free():
    assert tr("trace_11")["final_state"]["total_free_usable"] == 1008


# ─── Trace 12: Realloc OOM with retry after coalescing ──────────────────────


def test_t12_operations():
    assert tr("trace_12")["total_operations"] == 11


def test_t12_allocs():
    assert tr("trace_12")["successful_allocs"] == 4
    assert tr("trace_12")["failed_allocs"] == 0


def test_t12_reallocs():
    assert tr("trace_12")["successful_reallocs"] == 2
    assert tr("trace_12")["failed_reallocs"] == 1


def test_t12_deallocs():
    assert tr("trace_12")["deallocs"] == 4


def test_t12_error_count():
    assert len(tr("trace_12")["errors"]) == 1


def test_t12_oom_error():
    e = tr("trace_12")["errors"][0]
    assert e["operation_index"] == 6
    assert e["error_type"] == "oom"
    assert e["id"] == "z"


def test_t12_fully_freed():
    assert tr("trace_12")["final_state"]["live_allocations"] == 0


def test_t12_single_free_block():
    assert tr("trace_12")["final_state"]["free_blocks"] == 1


def test_t12_high_water_mark():
    assert tr("trace_12")["high_water_mark"] == 800


def test_t12_peak_live():
    assert tr("trace_12")["peak_live_blocks"] == 4


# ─── Cross-consistency tests ────────────────────────────────────────────────


def test_operations_consistency():
    for t in R["traces"]:
        ops = (t["successful_allocs"] + t["failed_allocs"]
               + t["successful_reallocs"] + t["failed_reallocs"]
               + t["deallocs"])
        error_only_ops = sum(1 for e in t["errors"]
                             if e["error_type"] in ("double_free",))
        assert ops + error_only_ops == t["total_operations"], (
            f"{t['trace_id']}: ops={ops}+err_ops={error_only_ops} != {t['total_operations']}")


def test_pool_utilization_range():
    for t in R["traces"]:
        u = t["final_state"]["pool_utilization"]
        assert 0.0 <= u <= 1.0, f"{t['trace_id']}: utilization={u}"


def test_ext_frag_range():
    for t in R["traces"]:
        f = t["final_state"]["external_fragmentation"]
        assert 0.0 <= f <= 1.0, f"{t['trace_id']}: ext_frag={f}"


def test_int_frag_range():
    for t in R["traces"]:
        f = t["final_state"]["internal_fragmentation"]
        assert 0.0 <= f <= 1.0, f"{t['trace_id']}: int_frag={f}"


def test_allocated_plus_free_equals_pool():
    pool = R["pool_config"]["pool_size"]
    hdr = R["pool_config"]["header_size"]
    for t in R["traces"]:
        fs = t["final_state"]
        total_free_total = fs["total_free_usable"] + fs["free_blocks"] * hdr
        total = fs["total_allocated_bytes"] + total_free_total
        assert total == pool, (
            f"{t['trace_id']}: alloc={fs['total_allocated_bytes']} + "
            f"free_total={total_free_total} = {total} != {pool}")


def test_high_water_mark_positive():
    for t in R["traces"]:
        assert t["high_water_mark"] >= 0


def test_peak_live_positive():
    for t in R["traces"]:
        assert t["peak_live_blocks"] >= 0


def test_error_indices_valid():
    for t in R["traces"]:
        for e in t["errors"]:
            assert 0 <= e["operation_index"] < t["total_operations"]


def test_error_types_valid():
    valid = {"double_free", "use_after_free", "oom"}
    for t in R["traces"]:
        for e in t["errors"]:
            assert e["error_type"] in valid


# ─── Precision trap tests ───────────────────────────────────────────────────


def test_trap_01_hdr_overhead_t01():
    assert tr("trace_01")["high_water_mark"] == 224
    assert tr("trace_01")["high_water_mark"] != 288


def test_trap_02_hdr_overhead_t09():
    assert tr("trace_09")["high_water_mark"] == 336
    assert tr("trace_09")["high_water_mark"] != 1008


def test_trap_03_free_usable_excludes_hdr():
    t = tr("trace_01")
    assert t["final_state"]["largest_free_usable"] == 1008
    assert t["final_state"]["largest_free_usable"] != 1024


def test_trap_04_ext_frag_denominator():
    f = tr("trace_03")["final_state"]["external_fragmentation"]
    wrong = 1.0 - (688 / 1024)
    assert not math.isclose(f, wrong, abs_tol=0.01)
    assert math.isclose(f, 0.245614, abs_tol=FLOAT_TOL)


def test_trap_05_int_frag_denominator():
    f = tr("trace_09")["final_state"]["internal_fragmentation"]
    assert math.isclose(f, 0.015625, abs_tol=FLOAT_TOL)


def test_trap_06_coalesce_reclaims_headers():
    assert tr("trace_01")["final_state"]["free_blocks"] == 1
    assert tr("trace_01")["final_state"]["largest_free_usable"] == 1008


def test_trap_07_coalesce_bidirectional():
    t = tr("trace_03")
    assert t["final_state"]["free_blocks"] == 2


def test_trap_08_realloc_oom_preserves_block():
    t11 = tr("trace_11")
    assert t11["errors"][0]["error_type"] == "oom"
    assert t11["successful_reallocs"] == 3


def test_trap_09_realloc_retry_after_coalesce():
    t12 = tr("trace_12")
    assert t12["successful_reallocs"] == 2
    assert t12["failed_reallocs"] == 1


def test_trap_10_split_boundary_exact():
    t11 = tr("trace_11")
    assert t11["final_state"]["free_blocks"] == 1
    assert t11["final_state"]["largest_free_usable"] == 1008


# ─── Input file verification ────────────────────────────────────────────────


def test_input_config_exists():
    assert (DATA_DIR / "pool_config.json").is_file()


def test_input_traces_exist():
    traces_dir = DATA_DIR / "traces"
    for i in range(1, 13):
        assert (traces_dir / f"trace_{i:02d}.json").is_file()


# ─── Rust binary verification ───────────────────────────────────────────────


def test_build_directory_exists():
    assert BUILD.is_dir()


def test_binary_exists():
    assert (BUILD / "allocator").is_file(), "Binary /app/build/allocator not found"


def test_binary_is_elf():
    binary = BUILD / "allocator"
    assert binary.is_file(), "Binary not found"
    with open(binary, "rb") as f:
        magic = f.read(4)
    assert magic == b'\x7fELF', (
        f"Binary is not a native ELF executable (magic={magic!r}). "
        "The solution must be compiled Rust, not a script wrapper."
    )


def test_binary_not_script():
    binary = BUILD / "allocator"
    assert binary.is_file(), "Binary not found"
    with open(binary, "rb") as f:
        head = f.read(2)
    assert head != b'#!', "Binary is a script, not a compiled Rust executable"


def test_cargo_project_compiles():
    result = subprocess.run(
        ["cargo", "build", "--release"],
        capture_output=True, timeout=120, cwd="/app",
    )
    assert result.returncode == 0, (
        f"Cargo build failed:\n{result.stderr.decode(errors='replace')[:800]}")


def test_binary_generates_valid_report():
    binary = BUILD / "allocator"
    assert binary.is_file(), "Binary not found"

    report_path = OUT_DIR / "allocator_report.json"
    backup_path = OUT_DIR / "allocator_report.json.verify_bak"

    had_original = report_path.is_file()
    if had_original:
        shutil.copy2(str(report_path), str(backup_path))
        report_path.unlink()

    try:
        subprocess.run(
            [str(binary)], capture_output=True, timeout=30, check=False,
        )
        assert report_path.is_file(), (
            "Binary did not produce /app/output/allocator_report.json"
        )
        rpt = json.loads(report_path.read_text(encoding="utf-8"))

        assert rpt["pool_config"]["pool_size"] == 1024
        assert rpt["pool_config"]["header_size"] == 16
        assert rpt["pool_config"]["min_alignment"] == 8
        assert len(rpt["traces"]) == 12
        assert rpt["summary"]["total_operations"] == 158
        assert rpt["summary"]["total_errors"] == 10
        assert rpt["summary"]["total_oom_events"] == 5

        t01 = next(t for t in rpt["traces"] if t["trace_id"] == "trace_01")
        assert t01["total_operations"] == 8
        assert t01["high_water_mark"] == 224
        assert t01["final_state"]["live_allocations"] == 0
        assert t01["final_state"]["largest_free_usable"] == 1008

        t09 = next(t for t in rpt["traces"] if t["trace_id"] == "trace_09")
        assert t09["successful_allocs"] == 42
        assert t09["final_state"]["pool_utilization"] == 1.0
        assert t09["final_state"]["total_allocated_bytes"] == 1024

        t11 = next(t for t in rpt["traces"] if t["trace_id"] == "trace_11")
        assert t11["successful_reallocs"] == 3
        assert t11["failed_reallocs"] == 1
        assert t11["high_water_mark"] == 800

        t12 = next(t for t in rpt["traces"] if t["trace_id"] == "trace_12")
        assert t12["successful_reallocs"] == 2
        assert t12["errors"][0]["error_type"] == "oom"
    finally:
        if backup_path.is_file():
            shutil.copy2(str(backup_path), str(report_path))
            backup_path.unlink()
        elif not had_original and report_path.is_file():
            pass


def test_no_python_solution():
    py_build = list(BUILD.glob("*.py")) if BUILD.is_dir() else []
    py_out = list(OUT_DIR.glob("*.py")) if OUT_DIR.is_dir() else []
    py_src = list((ROOT / "src").glob("*.py")) if (ROOT / "src").is_dir() else []
    total = len(py_build) + len(py_out) + len(py_src)
    assert total == 0, "Solution must use Rust, not Python"
