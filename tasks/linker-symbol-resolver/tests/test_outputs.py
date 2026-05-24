"""Tests for the cpp-linker-symbol-resolver task."""
import hashlib
import json
import subprocess
import pathlib

import pytest

ROOT = pathlib.Path("/app")


OUT_DIR = pathlib.pathlib.Path('/app/output')
DATA_DIR = pathlib.pathlib.Path('/app/data')
BUILD = ROOT / "build"
REPORT = OUT_DIR / "link_report.json"

EXPECTED_HASHES = {
    "data/link_config.json": "c334377ef03311e387b0412bfecc53650e51fa107e28b7493d25ef9f75ddf487",
    "data/objects/main.json": "7a2e5c5491c9457184f246d2cd402d6984363d1fa7f5f06a6fe2ff86cc6551e9",
    "data/objects/math_utils.json": "2c0d03d69efcb16eb0ff95914625a618586f212cf3bc7b942812f16e176f549b",
    "data/objects/string_utils.json": "01e3bae72f9d652acd920f2ebdc623128ecca0464920348be8a715ff58235753",
    "data/objects/io_handler.json": "791d92f6edc67f2a7f5afb68d7170f17323fe3fe80d02e10bdd03c1d82f755f3",
    "data/objects/logger.json": "27be6bdd95b5ae6ab783da21dab5570d1453eda5d573e3443a19f128b02da012",
}


@pytest.fixture(scope="session")
def report():
    """Load and return the parsed link_report.json."""
    assert REPORT.is_file(), f"Missing output file: {REPORT}"
    return json.loads(REPORT.read_text(encoding="utf-8"))


def _sym(report, name):
    """Look up a symbol by name in the symbol table."""
    for s in report["symbol_table"]:
        if s["name"] == name:
            return s
    raise AssertionError(f"Symbol '{name}' not in symbol_table")


def _sec(report, name):
    """Look up a merged section by name."""
    for s in report["merged_sections"]:
        if s["name"] == name:
            return s
    raise AssertionError(f"Section '{name}' not in merged_sections")


def _reloc(report, obj, offset):
    """Look up a relocation by object name and offset."""
    for r in report["relocations"]:
        if r["object"] == obj and r["offset"] == offset:
            return r
    raise AssertionError(f"Relocation at {obj}+{offset} not found")


# ─── Binary enforcement ──────────────────────────────────────────────────────

def test_compiled_binary_exists():
    """The compiled C++ binary must exist at /app/build/linker."""
    binary = BUILD / "linker"
    assert binary.is_file(), f"Binary not found at {binary}"


def test_binary_is_native_elf():
    """The binary must be a real ELF executable, not a script wrapper."""
    binary = BUILD / "linker"
    if not binary.is_file():
        pytest.skip("Binary not built")
    with open(binary, "rb") as f:
        magic = f.read(4)
    assert magic == b"\x7fELF", (
        f"Binary is not an ELF executable (magic: {magic!r})"
    )


def test_object_files_exist():
    """C++ compilation must produce .o object files."""
    obj_dir = BUILD / "obj"
    if not obj_dir.is_dir():
        pytest.skip("Build directory missing")
    obj_files = list(obj_dir.glob("*.o"))
    assert len(obj_files) > 0, "No .o object files found"


def test_binary_produces_report():
    """Running the binary must regenerate link_report.json from input data."""
    binary = BUILD / "linker"
    if not binary.is_file():
        pytest.skip("Binary not built")
    backup = None
    if REPORT.is_file():
        backup = REPORT.read_bytes()
    try:
        REPORT.unlink(missing_ok=True)
        result = subprocess.run(
            [str(binary)],
            capture_output=True,
            timeout=30,
            cwd=str(ROOT),
        )
        assert result.returncode == 0, (
            f"Linker exited {result.returncode}: {result.stderr.decode(errors='replace')}"
        )
        assert REPORT.is_file(), "Binary did not produce link_report.json"
        data = json.loads(REPORT.read_text(encoding="utf-8"))
        assert "symbol_table" in data, "Regenerated report missing symbol_table"
    finally:
        if backup is not None:
            REPORT.write_bytes(backup)


# ─── Input immutability ──────────────────────────────────────────────────────

def test_input_files_not_modified():
    """Data files under /app/data/ must not be modified."""
    for rel, expected in EXPECTED_HASHES.items():
        p = ROOT / rel
        assert p.is_file(), f"Missing: {p}"
        actual = hashlib.sha256(p.read_bytes()).hexdigest()
        assert actual == expected, f"{rel} was modified"


# ─── Output structure ────────────────────────────────────────────────────────

def test_output_file_exists():
    """The output report file must exist."""
    assert REPORT.is_file(), f"Missing: {REPORT}"


def test_json_valid(report):
    """Report must be a valid JSON object."""
    assert isinstance(report, dict)


def test_json_two_space_indent():
    """JSON output must use two-space indentation."""
    raw = REPORT.read_text(encoding="utf-8")
    assert raw.startswith("{\n  "), "JSON must use two-space indent"


def test_json_trailing_newline():
    """JSON must end with a trailing newline."""
    raw = REPORT.read_text(encoding="utf-8")
    assert raw.endswith("\n"), "JSON must end with trailing newline"


def test_top_level_keys(report):
    """Report must contain all required top-level keys."""
    required = {"entry_point", "errors", "merged_sections", "relocations",
                "stats", "status", "symbol_table", "warnings"}
    assert set(report.keys()) == required, f"Keys: {sorted(report.keys())}"


def test_status_success(report):
    """Status must be 'success' for the provided input set."""
    assert report["status"] == "success"


def test_entry_point_address(report):
    """Entry point 'main' must be at base_address 4096."""
    assert report["entry_point"]["symbol"] == "main"
    assert report["entry_point"]["address"] == 4096


# ─── Section merging ─────────────────────────────────────────────────────────

def test_section_count(report):
    """Four sections must be merged: .text, .rodata, .data, .bss."""
    assert len(report["merged_sections"]) == 4


def test_text_section_address(report):
    """.text starts at base_address 4096."""
    assert _sec(report, ".text")["address"] == 4096


def test_text_section_size(report):
    """.text total size: 100+pad+128+80+128+80 = 528 (with alignment gaps)."""
    assert _sec(report, ".text")["total_size"] == 528


def test_text_contributions(report):
    """Five object files contribute to .text in file order."""
    contribs = _sec(report, ".text")["contributions"]
    names = [c["object"] for c in contribs]
    assert names == ["main.o", "math_utils.o", "string_utils.o", "io_handler.o", "logger.o"]


def test_text_alignment_gap(report):
    """main.o is 100 bytes; math_utils.o must be aligned to 16, starting at offset 112."""
    contribs = _sec(report, ".text")["contributions"]
    assert contribs[1]["offset"] == 112


def test_rodata_section_address(report):
    """.rodata starts after .text ends (4096+528=4624)."""
    assert _sec(report, ".rodata")["address"] == 4624


def test_rodata_section_size(report):
    """.rodata total size: 32 (only string_utils.o contributes)."""
    assert _sec(report, ".rodata")["total_size"] == 32


def test_data_section_address(report):
    """.data starts after .rodata (4624+32=4656)."""
    assert _sec(report, ".data")["address"] == 4656


def test_data_section_size(report):
    """.data total size: 24 (math_utils 16 + logger 8, logger aligned to 4)."""
    assert _sec(report, ".data")["total_size"] == 24


def test_bss_section_address(report):
    """.bss: 4656+24=4680, aligned to 32 = 4704."""
    assert _sec(report, ".bss")["address"] == 4704


def test_bss_section_size(report):
    """.bss total size: 256 (only io_handler.o contributes)."""
    assert _sec(report, ".bss")["total_size"] == 256


# ─── Symbol resolution ───────────────────────────────────────────────────────

def test_symbol_count(report):
    """12 global/weak symbols in the final table."""
    assert len(report["symbol_table"]) == 12


def test_main_address(report):
    """main at .text base + 0 = 4096."""
    assert _sym(report, "main")["address"] == 4096


def test_start_address(report):
    """_start at .text base + 48 = 4144."""
    assert _sym(report, "_start")["address"] == 4144


def test_compute_sum_address(report):
    """compute_sum at math_utils.o .text (4208) + 0."""
    s = _sym(report, "compute_sum")
    assert s["address"] == 4208
    assert s["source"] == "math_utils.o"


def test_compute_avg_global_wins(report):
    """compute_avg: math_utils.o GLOBAL beats logger.o WEAK."""
    s = _sym(report, "compute_avg")
    assert s["address"] == 4272
    assert s["source"] == "math_utils.o"
    assert s["binding"] == "GLOBAL"


def test_format_string_address(report):
    """format_string at string_utils.o .text (4336) + 0."""
    assert _sym(report, "format_string")["address"] == 4336


def test_str_compare_address(report):
    """str_compare at string_utils.o .text + 48 = 4384."""
    assert _sym(report, "str_compare")["address"] == 4384


def test_write_output_address(report):
    """write_output at io_handler.o .text (4416) + 0."""
    assert _sym(report, "write_output")["address"] == 4416


def test_log_message_global_wins(report):
    """log_message: logger.o GLOBAL beats io_handler.o WEAK."""
    s = _sym(report, "log_message")
    assert s["address"] == 4544
    assert s["source"] == "logger.o"
    assert s["binding"] == "GLOBAL"


def test_math_pi_address(report):
    """math_pi at math_utils.o .data (4656) + 0."""
    assert _sym(report, "math_pi")["address"] == 4656


def test_math_e_address(report):
    """math_e at math_utils.o .data (4656) + 8."""
    assert _sym(report, "math_e")["address"] == 4664


def test_log_level_address(report):
    """log_level at logger.o .data (4672) + 0."""
    assert _sym(report, "log_level")["address"] == 4672


def test_io_buffer_address(report):
    """io_buffer at io_handler.o .bss (4704) + 0."""
    assert _sym(report, "io_buffer")["address"] == 4704


def test_symbols_sorted_by_address(report):
    """Symbol table must be sorted by address."""
    addrs = [s["address"] for s in report["symbol_table"]]
    assert addrs == sorted(addrs)


# ─── Weak resolution count ───────────────────────────────────────────────────

def test_weak_resolution_count(report):
    """Two weak resolutions: log_message and compute_avg."""
    assert report["stats"]["weak_resolutions"] == 2


# ─── Relocations ─────────────────────────────────────────────────────────────

def test_relocation_count(report):
    """9 relocations total across all object files."""
    assert len(report["relocations"]) == 9


def test_reloc_main_compute_sum(report):
    """main.o offset 16 R_ABS_32 compute_sum -> 4208."""
    r = _reloc(report, "main.o", 16)
    assert r["type"] == "R_ABS_32"
    assert r["symbol"] == "compute_sum"
    assert r["value"] == 4208


def test_reloc_main_format_string(report):
    """main.o offset 32 R_ABS_32 format_string -> 4336."""
    r = _reloc(report, "main.o", 32)
    assert r["value"] == 4336


def test_reloc_main_log_message(report):
    """main.o offset 64 R_ABS_32 log_message -> 4544 (from logger.o, not io_handler.o)."""
    r = _reloc(report, "main.o", 64)
    assert r["symbol"] == "log_message"
    assert r["value"] == 4544


def test_reloc_math_pi(report):
    """math_utils.o offset 72 R_ABS_32 math_pi -> 4656."""
    r = _reloc(report, "math_utils.o", 72)
    assert r["value"] == 4656


def test_reloc_fmt_template_local(report):
    """string_utils.o offset 8 R_ABS_32 fmt_template (LOCAL) -> 4624."""
    r = _reloc(report, "string_utils.o", 8)
    assert r["symbol"] == "fmt_template"
    assert r["value"] == 4624


def test_reloc_io_buffer(report):
    """io_handler.o offset 24 R_ABS_32 io_buffer -> 4704."""
    r = _reloc(report, "io_handler.o", 24)
    assert r["value"] == 4704


def test_reloc_logger_format_string(report):
    """logger.o offset 8 R_ABS_32 format_string -> 4336."""
    r = _reloc(report, "logger.o", 8)
    assert r["value"] == 4336


def test_reloc_logger_write_output(report):
    """logger.o offset 28 R_ABS_32 write_output -> 4416."""
    r = _reloc(report, "logger.o", 28)
    assert r["value"] == 4416


def test_reloc_pc_relative(report):
    """logger.o offset 56 R_PC_32 log_level: 4672 + (-4) - (4544+56) = 68."""
    r = _reloc(report, "logger.o", 56)
    assert r["type"] == "R_PC_32"
    assert r["symbol"] == "log_level"
    assert r["symbol_address"] == 4672
    assert r["value"] == 68


# ─── Warnings ────────────────────────────────────────────────────────────────

def test_unused_symbols_detected(report):
    """Unused symbols: _start, compute_avg, math_e, str_compare."""
    unused = {w["symbol"] for w in report["warnings"]}
    expected = {"_start", "compute_avg", "math_e", "str_compare"}
    assert unused == expected, f"Expected {expected}, got {unused}"


def test_warnings_sorted(report):
    """Warnings must be sorted by symbol name."""
    syms = [w["symbol"] for w in report["warnings"]]
    assert syms == sorted(syms)


def test_no_errors(report):
    """No errors for the provided input set."""
    assert report["errors"] == []


# ─── Stats ────────────────────────────────────────────────────────────────────

def test_stats_total_objects(report):
    """5 object files loaded."""
    assert report["stats"]["total_objects"] == 5


def test_stats_total_sections(report):
    """4 merged sections."""
    assert report["stats"]["total_sections"] == 4


def test_stats_total_symbols(report):
    """12 symbols in the final table."""
    assert report["stats"]["total_symbols"] == 12


def test_stats_total_relocations(report):
    """9 relocations applied."""
    assert report["stats"]["total_relocations"] == 9


def test_stats_total_size(report):
    """Total size: 528 + 32 + 24 + 256 = 840."""
    assert report["stats"]["total_size"] == 840
