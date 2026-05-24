"""
Tests for the cpp-vm-emulator-hard task.
Validates the execution_report.json produced by the agent's C++ VM emulator.
"""
import json
import os
import stat
from pathlib import Path

ROOT = Path("/app")
OUT_DIR = Path('/app/output')
BUILD  = ROOT / "build"
REPORT = OUT_DIR / "execution_report.json"


def _load():
    assert REPORT.is_file(), f"Missing output file: {REPORT}"
    with open(REPORT) as f:
        return json.load(f)


def _prog(name):
    data = _load()
    for p in data["program_results"]:
        if p["program"] == name:
            return p
    raise AssertionError(f"Program '{name}' not found in results")


# ─── C++ binary enforcement ─────────────────────────────────────────────────
def test_cpp_binary_exists():
    if os.name == "nt":
        return
    binary = BUILD / "vm"
    assert binary.is_file(), f"Missing compiled C++ binary: {binary}"


def test_cpp_binary_executable():
    if os.name == "nt":
        return
    binary = BUILD / "vm"
    assert binary.is_file(), f"Binary not found: {binary}"
    mode = binary.stat().st_mode
    assert mode & stat.S_IXUSR, f"Binary lacks execute permission: {oct(mode)}"


def test_cpp_binary_is_elf():
    if os.name == "nt":
        return
    binary = BUILD / "vm"
    assert binary.is_file(), f"Binary not found: {binary}"
    with open(binary, "rb") as f:
        magic = f.read(4)
    assert magic == b'\x7fELF', "Binary is not a compiled ELF executable"


# ─── Output file structure ───────────────────────────────────────────────────
def test_output_file_exists():
    assert REPORT.is_file(), f"Missing: {REPORT}"


def test_top_level_keys():
    d = _load()
    for k in ["schema_version", "machine_config", "program_results", "summary"]:
        assert k in d, f"Missing top-level key: {k}"


def test_schema_version():
    assert _load()["schema_version"] == 1


def test_program_results_is_list():
    assert isinstance(_load()["program_results"], list)


def test_program_results_count():
    assert len(_load()["program_results"]) == 15


# ─── Machine config ─────────────────────────────────────────────────────────
def test_machine_config_registers():
    assert _load()["machine_config"]["registers"] == 8


def test_machine_config_memory():
    assert _load()["machine_config"]["memory_bytes"] == 4096


def test_machine_config_max_cycles():
    assert _load()["machine_config"]["max_cycles"] == 10000


def test_machine_config_stack_start():
    assert _load()["machine_config"]["stack_start"] == 4096


# ─── Summary ────────────────────────────────────────────────────────────────
def test_summary_total_programs():
    assert _load()["summary"]["total_programs"] == 15


def test_summary_halted():
    assert _load()["summary"]["halted"] == 14


def test_summary_timeout():
    assert _load()["summary"]["timeout"] == 1


def test_summary_total_cycles():
    assert _load()["summary"]["total_cycles"] == 10226


def test_summary_total_errors():
    assert _load()["summary"]["total_errors"] == 6


# ─── Program ordering ───────────────────────────────────────────────────────
def test_program_results_sorted():
    names = [p["program"] for p in _load()["program_results"]]
    assert names == sorted(names), "program_results must be sorted by name"


# ─── sum_loop ────────────────────────────────────────────────────────────────
def test_sum_loop_status():
    assert _prog("sum_loop")["status"] == "halted"


def test_sum_loop_cycles():
    assert _prog("sum_loop")["cycles"] == 57


def test_sum_loop_registers():
    assert _prog("sum_loop")["registers"] == [55, 55, 11, 0, 0, 0, 0, 0]


def test_sum_loop_flags():
    f = _prog("sum_loop")["flags"]
    assert f == {"zero": False, "negative": False, "overflow": False, "error": False}


def test_sum_loop_stack_pointer():
    assert _prog("sum_loop")["stack_pointer"] == 4096


def test_sum_loop_memory_writes():
    assert _prog("sum_loop")["memory_writes"] == 0


# ─── factorial_call ──────────────────────────────────────────────────────────
def test_factorial_call_status():
    assert _prog("factorial_call")["status"] == "halted"


def test_factorial_call_cycles():
    assert _prog("factorial_call")["cycles"] == 41


def test_factorial_call_r0():
    assert _prog("factorial_call")["registers"][0] == 120


def test_factorial_call_r1():
    assert _prog("factorial_call")["registers"][1] == 5


def test_factorial_call_flags():
    f = _prog("factorial_call")["flags"]
    assert f["error"] is False


def test_factorial_call_stack_restored():
    assert _prog("factorial_call")["stack_pointer"] == 4096


def test_factorial_call_memory_writes():
    assert _prog("factorial_call")["memory_writes"] == 10


# ─── overflow_test ───────────────────────────────────────────────────────────
def test_overflow_add_wraps():
    r = _prog("overflow_test")["registers"]
    assert r[0] == 2147483647, "SUB MIN_INT-1 should wrap to MAX_INT"
    assert r[1] == -2147483648, "ADD MAX_INT+1 should wrap to MIN_INT"


def test_overflow_sub_wraps():
    assert _prog("overflow_test")["registers"][2] == 2147483647


def test_overflow_v_flag():
    assert _prog("overflow_test")["flags"]["overflow"] is True


def test_overflow_cycles():
    assert _prog("overflow_test")["cycles"] == 7


# ─── div_zero_test ───────────────────────────────────────────────────────────
def test_div_zero_status():
    assert _prog("div_zero_test")["status"] == "halted"


def test_div_zero_preserves_dst():
    """On div-by-zero the destination register must be unchanged."""
    assert _prog("div_zero_test")["registers"][2] == 42


def test_div_zero_subsequent_div():
    assert _prog("div_zero_test")["registers"][3] == 14


def test_div_negative_truncates():
    """Signed division truncates toward zero: -7/2 = -3."""
    assert _prog("div_zero_test")["registers"][4] == -3


def test_div_zero_sticky_error():
    """E flag must stay set after a subsequent successful DIV."""
    assert _prog("div_zero_test")["flags"]["error"] is True


def test_div_zero_error_log():
    errs = _prog("div_zero_test")["error_log"]
    assert len(errs) == 1
    assert errs[0]["cycle"] == 3
    assert errs[0]["pc"] == 2
    assert errs[0]["error"] == "division_by_zero"


def test_div_zero_cycles():
    assert _prog("div_zero_test")["cycles"] == 13


def test_div_zero_n_flag():
    """Last successful DIV was -7/2=-3 (negative), so N should be true."""
    assert _prog("div_zero_test")["flags"]["negative"] is True


# ─── memory_ops ──────────────────────────────────────────────────────────────
def test_memory_store_load_roundtrip():
    r = _prog("memory_ops")["registers"]
    assert r[1] == 255, "LOAD from addr 4092 should return stored 255"


def test_memory_oob_store():
    assert _prog("memory_ops")["flags"]["error"] is True


def test_memory_oob_load_preserves():
    """Out-of-bounds LOAD must leave dst unchanged."""
    assert _prog("memory_ops")["registers"][2] == 0


def test_memory_ops_error_count():
    assert len(_prog("memory_ops")["error_log"]) == 2


def test_memory_ops_error_types():
    for e in _prog("memory_ops")["error_log"]:
        assert e["error"] == "memory_out_of_bounds"


def test_memory_ops_writes():
    assert _prog("memory_ops")["memory_writes"] == 2


def test_memory_ops_cycles():
    assert _prog("memory_ops")["cycles"] == 14


# ─── bitwise_ops ─────────────────────────────────────────────────────────────
def test_bitwise_and():
    assert _prog("bitwise_ops")["registers"][2] == 136


def test_bitwise_or():
    assert _prog("bitwise_ops")["registers"][3] == 238


def test_bitwise_xor():
    assert _prog("bitwise_ops")["registers"][4] == 102


def test_bitwise_not():
    assert _prog("bitwise_ops")["registers"][5] == -171


def test_bitwise_shl_31():
    assert _prog("bitwise_ops")["registers"][6] == -2147483648


def test_shr_logical_not_arithmetic():
    """SHR must be logical (unsigned) shift, not arithmetic.
    0x80000000 >> 31 should give 1, not -1."""
    assert _prog("bitwise_ops")["registers"][7] == 1


def test_bitwise_cycles():
    assert _prog("bitwise_ops")["cycles"] == 15


# ─── stack_underflow ─────────────────────────────────────────────────────────
def test_stack_underflow_pop_empty():
    """POP on empty stack must set E and leave register unchanged."""
    p = _prog("stack_underflow")
    assert p["flags"]["error"] is True
    assert p["registers"][2] == 0  # R2 from failed second POP


def test_stack_underflow_push_pop():
    """PUSH then POP should roundtrip correctly."""
    assert _prog("stack_underflow")["registers"][0] == 42


def test_stack_underflow_error_count():
    assert len(_prog("stack_underflow")["error_log"]) == 2


def test_stack_underflow_error_cycles():
    errs = _prog("stack_underflow")["error_log"]
    assert errs[0]["cycle"] == 1
    assert errs[1]["cycle"] == 5


def test_stack_underflow_memory_writes():
    assert _prog("stack_underflow")["memory_writes"] == 1


def test_stack_underflow_sp_restored():
    assert _prog("stack_underflow")["stack_pointer"] == 4096


# ─── mod_test ────────────────────────────────────────────────────────────────
def test_mod_positive():
    assert _prog("mod_test")["registers"][2] == 2


def test_mod_negative_truncation():
    """Signed MOD truncates toward zero: -17 % 5 = -2."""
    assert _prog("mod_test")["registers"][3] == -2


def test_mod_by_zero_preserves():
    assert _prog("mod_test")["registers"][4] == 10


def test_mod_error_log():
    errs = _prog("mod_test")["error_log"]
    assert len(errs) == 1
    assert errs[0]["error"] == "division_by_zero"


def test_mod_n_flag():
    """Last successful MOD was -17%5=-2, so N should be true."""
    assert _prog("mod_test")["flags"]["negative"] is True


def test_mod_cycles():
    assert _prog("mod_test")["cycles"] == 13


# ─── conditional_jumps ───────────────────────────────────────────────────────
def test_conditional_all_taken():
    """R2 is set to 1 only if all 6 conditional jumps succeeded."""
    assert _prog("conditional_jumps")["registers"][2] == 1


def test_conditional_r0_final():
    assert _prog("conditional_jumps")["registers"][0] == 42


def test_conditional_cycles():
    assert _prog("conditional_jumps")["cycles"] == 17


def test_conditional_no_errors():
    assert _prog("conditional_jumps")["flags"]["error"] is False


# ─── shift_test ──────────────────────────────────────────────────────────────
def test_shift_shr_16():
    """(unsigned)-1 >> 16 = 0x0000FFFF = 65535."""
    assert _prog("shift_test")["registers"][1] == 65535


def test_shift_shl_16():
    """-1 << 16 = 0xFFFF0000 = -65536."""
    assert _prog("shift_test")["registers"][2] == -65536


def test_shift_shl_31():
    assert _prog("shift_test")["registers"][3] == -2147483648


def test_shift_shr_31():
    """Logical SHR: 0x80000000 >> 31 = 1."""
    assert _prog("shift_test")["registers"][4] == 1


def test_shift_cycles():
    assert _prog("shift_test")["cycles"] == 12


# ─── infinite_loop ───────────────────────────────────────────────────────────
def test_infinite_loop_timeout():
    assert _prog("infinite_loop")["status"] == "timeout"


def test_infinite_loop_cycles():
    assert _prog("infinite_loop")["cycles"] == 10000


def test_infinite_loop_regs_zero():
    assert _prog("infinite_loop")["registers"] == [0, 0, 0, 0, 0, 0, 0, 0]


def test_infinite_loop_no_errors():
    assert len(_prog("infinite_loop")["error_log"]) == 0


# ─── call_chain ──────────────────────────────────────────────────────────────
def test_call_chain_result():
    p = _prog("call_chain")
    assert p["registers"][0] == 3
    assert p["registers"][7] == 3


def test_call_chain_stack_restored():
    assert _prog("call_chain")["stack_pointer"] == 4096


def test_call_chain_memory_writes():
    assert _prog("call_chain")["memory_writes"] == 3


def test_call_chain_cycles():
    assert _prog("call_chain")["cycles"] == 12


# ─── nop_test ────────────────────────────────────────────────────────────────
def test_nop_test_status():
    assert _prog("nop_test")["status"] == "halted"


def test_nop_test_cycles():
    assert _prog("nop_test")["cycles"] == 4


def test_nop_test_regs_zero():
    assert _prog("nop_test")["registers"] == [0, 0, 0, 0, 0, 0, 0, 0]


def test_nop_test_flags():
    f = _prog("nop_test")["flags"]
    assert f == {"zero": False, "negative": False, "overflow": False, "error": False}


# ─── mul_overflow ────────────────────────────────────────────────────────────
def test_mul_overflow_low32():
    """MUL keeps only the low 32 bits: 100000*100000=10^10, low32=1410065408."""
    assert _prog("mul_overflow")["registers"][0] == 1410065408


def test_mul_overflow_saved():
    assert _prog("mul_overflow")["registers"][2] == 1410065408


def test_mul_overflow_cycles():
    assert _prog("mul_overflow")["cycles"] == 5


def test_mul_overflow_no_error():
    assert _prog("mul_overflow")["flags"]["error"] is False


# ─── register_chain ──────────────────────────────────────────────────────────
def test_register_chain_doubling():
    """Each register should be double the previous: 1, 2, 4, 8, 16."""
    r = _prog("register_chain")["registers"]
    assert r == [1, 2, 4, 8, 16, 0, 0, 0]


def test_register_chain_cycles():
    assert _prog("register_chain")["cycles"] == 10


def test_register_chain_no_error():
    assert _prog("register_chain")["flags"]["error"] is False


# ─── Cross-cutting gotcha tests ─────────────────────────────────────────────
def test_call_pushes_pc_plus_one():
    """CALL must push the NEXT instruction address (PC+1), not the current PC.
    Verified by factorial_call returning correct 5! = 120."""
    assert _prog("factorial_call")["registers"][0] == 120


def test_error_is_noop_for_call():
    """On CALL error (stack overflow), CALL must NOT jump to target.
    Verified indirectly: if it jumped on error, factorial would loop."""
    assert _prog("factorial_call")["status"] == "halted"


def test_sticky_error_persists():
    """Once E is set, it stays set even after successful operations."""
    assert _prog("div_zero_test")["flags"]["error"] is True
    assert _prog("div_zero_test")["registers"][3] == 14  # successful DIV after error


def test_json_two_space_indent():
    with open(REPORT) as f:
        raw = f.read()
    assert raw.startswith("{\n  "), "JSON must use two-space indent"


def test_json_trailing_newline():
    with open(REPORT) as f:
        raw = f.read()
    assert raw.endswith("\n"), "JSON must end with trailing newline"
