"""Tests for debug-rust-wire-protocol task.

Constructs correct binary messages using Python, runs the Rust parser,
and verifies decoded output matches expected values.
"""
import binascii
import json
import os
import pathlib
import struct
import subprocess
import tempfile

ROOT = pathlib.Path("/app")
BINARY = ROOT / "target" / "release" / "wire-protocol"
DATA_DIR = pathlib.pathlib.Path('/app/data')

MAGIC = 0xAB
VERSION = 0x01


def _encode_field(field_id, field_type, value):
    hdr = struct.pack("<BB", field_id, field_type)
    if field_type == 0:
        return hdr + struct.pack("<B", value)
    elif field_type == 1:
        return hdr + struct.pack("<H", value)
    elif field_type == 2:
        return hdr + struct.pack("<I", value)
    elif field_type == 3:
        return hdr + struct.pack("<Q", value)
    elif field_type == 4:
        return hdr + struct.pack("<i", value)
    elif field_type == 5:
        return hdr + struct.pack("<q", value)
    elif field_type == 6:
        encoded = value.encode("utf-8")
        return hdr + struct.pack("<H", len(encoded)) + encoded
    elif field_type == 7:
        return hdr + struct.pack("<H", len(value)) + bytes(value)
    elif field_type == 8:
        return hdr + struct.pack("<I", len(value)) + bytes(value)
    raise ValueError(f"unknown field_type {field_type}")


def _make_message(msg_type, fields):
    """Build a correct binary message.
    fields: list of (field_id, field_type, value)
    """
    header = struct.pack("<BBBB", MAGIC, VERSION, msg_type, len(fields))
    body = header
    for fid, ftype, val in fields:
        body += _encode_field(fid, ftype, val)
    crc = binascii.crc32(body) & 0xFFFFFFFF
    return body + struct.pack("<I", crc)


def _make_nested_payload(fields):
    payload = b""
    for fid, ftype, val in fields:
        payload += _encode_field(fid, ftype, val)
    return payload


def _run_parser(hex_messages):
    if not BINARY.exists():
        result = subprocess.run(
            ["cargo", "build", "--release"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, f"Build failed:\n{result.stderr}"

    input_data = {"messages_hex": hex_messages}
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, dir="/tmp"
    ) as f:
        json.dump(input_data, f)
        tmp_path = f.name

    try:
        result = subprocess.run(
            [str(BINARY), "decode", tmp_path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"Parser failed:\n{result.stderr}"
        return json.loads(result.stdout)
    finally:
        os.unlink(tmp_path)


def _hex(data):
    return data.hex()


# ─── Build test ──────────────────────────────────────────────────────────────


def test_project_builds():
    """Verify the Rust project compiles without errors."""
    result = subprocess.run(
        ["cargo", "build", "--release"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, f"Build failed:\n{result.stderr}"


# ─── Simple types ────────────────────────────────────────────────────────────


def test_simple_u8_field():
    """Verify parsing a message with a single u8 field returns the correct value."""
    msg = _make_message(5, [(1, 0, 42)])
    out = _run_parser([_hex(msg)])
    m = out["messages"][0]
    assert m["msg_type"] == 5, f"msg_type wrong: {m['msg_type']}"
    assert m["field_count"] == 1, f"field_count wrong: {m['field_count']}"
    assert m["fields"][0]["value"] == 42


def test_simple_u32_field():
    """Verify parsing a u32 field decodes the value correctly in little-endian."""
    msg = _make_message(5, [(2, 2, 1000)])
    out = _run_parser([_hex(msg)])
    assert out["messages"][0]["fields"][0]["value"] == 1000


def test_u16_field():
    """Verify parsing a u16 field with value above 255 works correctly."""
    msg = _make_message(3, [(1, 1, 500)])
    out = _run_parser([_hex(msg)])
    assert out["messages"][0]["fields"][0]["value"] == 500


def test_u16_boundary():
    """Verify u16 field handles 0xFFFF correctly."""
    msg = _make_message(3, [(1, 1, 65535)])
    out = _run_parser([_hex(msg)])
    assert out["messages"][0]["fields"][0]["value"] == 65535


# ─── Header parsing ─────────────────────────────────────────────────────────


def test_header_msg_type_differs_from_field_count():
    """Verify msg_type and field_count are decoded from the correct header positions
    when they have different values."""
    msg = _make_message(7, [(1, 0, 1), (2, 0, 2), (3, 0, 3)])
    out = _run_parser([_hex(msg)])
    m = out["messages"][0]
    assert m["msg_type"] == 7, (
        f"msg_type should be 7 but got {m['msg_type']} — "
        "header byte positions may be swapped"
    )
    assert m["field_count"] == 3, (
        f"field_count should be 3 but got {m['field_count']}"
    )


def test_header_single_field():
    """Verify header parsing when msg_type=10 and field_count=1."""
    msg = _make_message(10, [(1, 0, 99)])
    out = _run_parser([_hex(msg)])
    m = out["messages"][0]
    assert m["msg_type"] == 10
    assert m["field_count"] == 1


def test_header_many_fields():
    """Verify header field_count is correct with 12 fields."""
    fields = [(i, 0, i) for i in range(1, 13)]
    msg = _make_message(20, fields)
    out = _run_parser([_hex(msg)])
    m = out["messages"][0]
    assert m["msg_type"] == 20
    assert m["field_count"] == 12


# ─── u64 field ───────────────────────────────────────────────────────────────


def test_u64_large_value():
    """Verify u64 field correctly parses all 8 bytes for values exceeding 32 bits."""
    val = 123456789012345
    msg = _make_message(1, [(1, 3, val)])
    out = _run_parser([_hex(msg)])
    assert out["messages"][0]["fields"][0]["value"] == val, (
        "u64 value truncated — check that the parser reads all 8 bytes"
    )


def test_u64_max():
    """Verify u64 field handles the maximum value (2^64 - 1)."""
    val = 2**64 - 1
    msg = _make_message(1, [(1, 3, val)])
    out = _run_parser([_hex(msg)])
    assert out["messages"][0]["fields"][0]["value"] == val


def test_u64_followed_by_u8():
    """Verify fields after a u64 are parsed at the correct offset."""
    msg = _make_message(2, [(1, 3, 100), (2, 0, 77)])
    out = _run_parser([_hex(msg)])
    fields = out["messages"][0]["fields"]
    assert fields[0]["value"] == 100
    assert fields[1]["value"] == 77, (
        "Field after u64 has wrong value — u64 byte width may be incorrect"
    )


def test_u64_high_low_distinct():
    """Verify u64 with high and low 32-bit halves that differ.
    Catches (lo << 32) | hi vs (hi << 32) | lo bugs."""
    val = 0x00000001_00000002
    msg = _make_message(1, [(1, 3, val)])
    out = _run_parser([_hex(msg)])
    assert out["messages"][0]["fields"][0]["value"] == val, (
        f"Expected {val}, got {out['messages'][0]['fields'][0]['value']} — "
        "high/low 32-bit words may be swapped in u64 decoding"
    )


# ─── i32 endianness ─────────────────────────────────────────────────────────


def test_i32_negative():
    """Verify i32 field correctly parses a negative value using little-endian."""
    msg = _make_message(1, [(1, 4, -42)])
    out = _run_parser([_hex(msg)])
    assert out["messages"][0]["fields"][0]["value"] == -42, (
        "i32 negative value wrong — check byte order (should be little-endian)"
    )


def test_i32_min():
    """Verify i32 field handles the minimum value (-2^31)."""
    msg = _make_message(1, [(1, 4, -2147483648)])
    out = _run_parser([_hex(msg)])
    assert out["messages"][0]["fields"][0]["value"] == -2147483648


def test_i32_positive_multibyte():
    """Verify i32 correctly parses a positive value with non-zero high bytes."""
    msg = _make_message(1, [(1, 4, 70000)])
    out = _run_parser([_hex(msg)])
    assert out["messages"][0]["fields"][0]["value"] == 70000


def test_i32_sign_extension():
    """Verify i32 value -1 is correctly sign-extended to i64 representation.
    Catches the bug where u32 as i64 produces 4294967295 instead of -1."""
    msg = _make_message(1, [(1, 4, -1)])
    out = _run_parser([_hex(msg)])
    assert out["messages"][0]["fields"][0]["value"] == -1, (
        f"Expected -1 but got {out['messages'][0]['fields'][0]['value']} — "
        "i32 may not be sign-extended correctly (u32 as i64 vs i32 as i64)"
    )


# ─── i64 field ───────────────────────────────────────────────────────────────


def test_i64_small_negative():
    """Verify i64 field decodes a small negative value."""
    msg = _make_message(1, [(1, 5, -1)])
    out = _run_parser([_hex(msg)])
    assert out["messages"][0]["fields"][0]["value"] == -1


def test_i64_large_positive():
    """Verify i64 field decodes a value that uses bytes 6 and 7.
    Catches byte-swap bugs in the high portion of the i64."""
    val = 0x0102_0304_0506_0708
    msg = _make_message(1, [(1, 5, val)])
    out = _run_parser([_hex(msg)])
    assert out["messages"][0]["fields"][0]["value"] == val, (
        f"Expected {val}, got {out['messages'][0]['fields'][0]['value']} — "
        "check that i64 byte order is correct (all 8 bytes in LE order)"
    )


def test_i64_large_negative():
    """Verify i64 field decodes a large negative value correctly.
    Exercises the high bytes of the i64 representation."""
    val = -72057594037927936
    msg = _make_message(1, [(1, 5, val)])
    out = _run_parser([_hex(msg)])
    assert out["messages"][0]["fields"][0]["value"] == val, (
        f"Expected {val}, got {out['messages'][0]['fields'][0]['value']} — "
        "i64 high-byte decoding may have a byte swap"
    )


def test_i64_min():
    """Verify i64 minimum value (-2^63)."""
    val = -(2**63)
    msg = _make_message(1, [(1, 5, val)])
    out = _run_parser([_hex(msg)])
    assert out["messages"][0]["fields"][0]["value"] == val


def test_i64_followed_by_u8():
    """Verify cursor advances correctly after i64 field."""
    msg = _make_message(2, [(1, 5, -100), (2, 0, 55)])
    out = _run_parser([_hex(msg)])
    fields = out["messages"][0]["fields"]
    assert fields[0]["value"] == -100
    assert fields[1]["value"] == 55, (
        "Field after i64 has wrong value — i64 byte width may be incorrect"
    )


def test_i64_distinct_byte_pairs():
    """Verify i64 with each byte pair distinct, catching any byte swap."""
    val = 0x0807_0605_0403_0201
    msg = _make_message(1, [(1, 5, val)])
    out = _run_parser([_hex(msg)])
    assert out["messages"][0]["fields"][0]["value"] == val, (
        f"Expected 0x{val:016X}, got 0x{out['messages'][0]['fields'][0]['value']:016X} — "
        "i64 has a byte-order error; check from_le_bytes array indices"
    )


# ─── String cursor ───────────────────────────────────────────────────────────


def test_string_field_basic():
    """Verify string field is decoded correctly."""
    msg = _make_message(7, [(1, 6, "hello")])
    out = _run_parser([_hex(msg)])
    assert out["messages"][0]["fields"][0]["value"] == "hello"


def test_string_followed_by_u8():
    """Verify a field after a string is parsed at the correct cursor position.
    Catches double-counting of the string length prefix."""
    msg = _make_message(7, [(1, 6, "hello"), (2, 0, 99)])
    out = _run_parser([_hex(msg)])
    fields = out["messages"][0]["fields"]
    assert fields[0]["value"] == "hello"
    assert len(fields) == 2, "Second field missing after string"
    assert fields[1]["value"] == 99, (
        f"Field after string has wrong value {fields[1]['value']} — "
        "cursor may advance too far after string parsing"
    )


def test_two_strings():
    """Verify two consecutive string fields are both parsed correctly."""
    msg = _make_message(7, [(1, 6, "foo"), (2, 6, "bar")])
    out = _run_parser([_hex(msg)])
    fields = out["messages"][0]["fields"]
    assert fields[0]["value"] == "foo"
    assert fields[1]["value"] == "bar", (
        "Second string wrong — cursor advancement after first string may be off"
    )


def test_string_multibyte_len():
    """Verify string whose length > 255 requires both bytes of the LE u16 prefix.
    Catches read_len_u16 byte swap: reversed bytes produce len=0 for this input."""
    long_str = "A" * 300
    msg = _make_message(7, [(1, 6, long_str)])
    out = _run_parser([_hex(msg)])
    assert out["messages"][0]["fields"][0]["value"] == long_str, (
        "Long string truncated or garbled — read_len_u16 byte order may be wrong"
    )


def test_string_empty():
    """Verify empty string is handled correctly."""
    msg = _make_message(7, [(1, 6, "")])
    out = _run_parser([_hex(msg)])
    assert out["messages"][0]["fields"][0]["value"] == ""


# ─── Bytes field ─────────────────────────────────────────────────────────────


def test_bytes_basic():
    """Verify bytes field is decoded correctly."""
    msg = _make_message(7, [(1, 7, [0xDE, 0xAD])])
    out = _run_parser([_hex(msg)])
    assert out["messages"][0]["fields"][0]["value"] == [0xDE, 0xAD]


def test_bytes_multibyte_len():
    """Verify bytes field with length > 255 (needs both bytes of LE u16 prefix)."""
    data = list(range(256)) + list(range(44))
    msg = _make_message(7, [(1, 7, data)])
    out = _run_parser([_hex(msg)])
    assert out["messages"][0]["fields"][0]["value"] == data, (
        "Large bytes field truncated — read_len_u16 byte order may be wrong"
    )


# ─── Nested message ─────────────────────────────────────────────────────────


def test_nested_basic():
    """Verify nested message fields are decoded correctly."""
    inner = _make_nested_payload([(10, 0, 1), (11, 1, 500)])
    msg = _make_message(10, [(1, 8, inner)])
    out = _run_parser([_hex(msg)])
    nested = out["messages"][0]["fields"][0]["value"]
    assert len(nested) == 2
    assert nested[0]["value"] == 1
    assert nested[1]["value"] == 500


def test_nested_followed_by_field():
    """Verify a field after a nested message is at the correct offset.
    Catches missing length-prefix advancement in nested cursor."""
    inner = _make_nested_payload([(10, 0, 42)])
    msg = _make_message(10, [(1, 8, inner), (2, 2, 9999)])
    out = _run_parser([_hex(msg)])
    fields = out["messages"][0]["fields"]
    assert fields[0]["value"][0]["value"] == 42
    assert len(fields) == 2, "Field after nested is missing"
    assert fields[1]["value"] == 9999, (
        f"Field after nested has wrong value {fields[1]['value']} — "
        "outer cursor may not advance past the nested length prefix"
    )


def test_nested_large_payload():
    """Verify nested field with payload > 255 bytes.
    The nested length prefix is a 4-byte LE u32.  If the middle bytes of
    read_len_u32 are swapped, payloads < 256 bytes silently work (both middle
    bytes are 0x00), but payloads >= 256 produce a wildly wrong length.
    This test creates a nested payload of ~360 bytes by nesting 6 string
    fields of 50 characters each."""
    inner_fields = [(i, 6, "X" * 50) for i in range(1, 7)]
    inner = _make_nested_payload(inner_fields)
    assert len(inner) > 255, f"inner payload too small: {len(inner)}"
    msg = _make_message(20, [(1, 8, inner)])
    out = _run_parser([_hex(msg)])
    nested = out["messages"][0]["fields"][0]["value"]
    assert len(nested) == 6, (
        f"Expected 6 nested fields, got {len(nested)} — "
        "read_len_u32 may swap middle bytes for lengths > 255"
    )
    for i, nf in enumerate(nested):
        assert nf["value"] == "X" * 50, (
            f"Nested field {i} has wrong string content"
        )


def test_nested_with_mixed_types():
    """Verify nested payload containing multiple field types."""
    inner = _make_nested_payload([
        (1, 0, 99),
        (2, 1, 1000),
        (3, 6, "inner"),
        (4, 4, -5),
    ])
    msg = _make_message(11, [(1, 8, inner)])
    out = _run_parser([_hex(msg)])
    nested = out["messages"][0]["fields"][0]["value"]
    assert len(nested) == 4
    assert nested[0]["value"] == 99
    assert nested[1]["value"] == 1000
    assert nested[2]["value"] == "inner"
    assert nested[3]["value"] == -5


# ─── CRC ─────────────────────────────────────────────────────────────────────


def test_crc_valid():
    """Verify CRC validation succeeds on a correctly formed message."""
    msg = _make_message(1, [(1, 0, 42)])
    out = _run_parser([_hex(msg)])
    assert out["messages"][0]["crc_valid"] is True


def test_crc_valid_complex():
    """Verify CRC is valid on a message with many fields."""
    msg = _make_message(15, [
        (1, 0, 255),
        (2, 6, "crc-check"),
        (3, 4, -1000),
        (4, 3, 2**40),
    ])
    out = _run_parser([_hex(msg)])
    assert out["messages"][0]["crc_valid"] is True, (
        "CRC validation failed — check the CRC32 implementation "
        "(polynomial, initial value, and final XOR)"
    )


def test_crc_invalid_detects_corruption():
    """Verify CRC validation correctly detects a corrupted message."""
    msg = bytearray(_make_message(1, [(1, 0, 42)]))
    msg[-1] ^= 0x01
    out = _run_parser([_hex(bytes(msg))])
    assert out["messages"][0]["crc_valid"] is False, (
        "CRC validation should detect corrupted trailing byte"
    )


# ─── Combined / regression ──────────────────────────────────────────────────


def test_mixed_fields():
    """Verify a message with many field types decodes all correctly."""
    msg = _make_message(
        15,
        [
            (1, 0, 255),
            (2, 6, "test"),
            (3, 4, -1),
            (4, 3, 999999999999),
            (5, 7, [0xDE, 0xAD, 0xBE, 0xEF]),
        ],
    )
    out = _run_parser([_hex(msg)])
    m = out["messages"][0]
    assert m["msg_type"] == 15
    assert m["field_count"] == 5
    fields = m["fields"]
    assert fields[0]["value"] == 255
    assert fields[1]["value"] == "test"
    assert fields[2]["value"] == -1
    assert fields[3]["value"] == 999999999999
    assert fields[4]["value"] == [0xDE, 0xAD, 0xBE, 0xEF]


def test_mixed_with_i64():
    """Verify a message combining u8, i32, i64, str, and nested."""
    inner = _make_nested_payload([(10, 0, 77)])
    msg = _make_message(
        25,
        [
            (1, 0, 1),
            (2, 4, -999),
            (3, 5, 0x0A0B_0C0D_0E0F_1011),
            (4, 6, "mixed"),
            (5, 8, inner),
        ],
    )
    out = _run_parser([_hex(msg)])
    fields = out["messages"][0]["fields"]
    assert fields[0]["value"] == 1
    assert fields[1]["value"] == -999
    assert fields[2]["value"] == 0x0A0B_0C0D_0E0F_1011
    assert fields[3]["value"] == "mixed"
    assert fields[4]["value"][0]["value"] == 77


def test_multiple_messages():
    """Verify parsing multiple messages in a single input."""
    msg1 = _make_message(1, [(1, 0, 10)])
    msg2 = _make_message(2, [(1, 2, 50000)])
    msg3 = _make_message(3, [(1, 4, -500)])
    out = _run_parser([_hex(msg1), _hex(msg2), _hex(msg3)])
    assert len(out["messages"]) == 3
    assert out["messages"][0]["fields"][0]["value"] == 10
    assert out["messages"][1]["fields"][0]["value"] == 50000
    assert out["messages"][2]["fields"][0]["value"] == -500


def test_all_numeric_types():
    """Verify all numeric types in a single message."""
    msg = _make_message(
        30,
        [
            (1, 0, 200),
            (2, 1, 40000),
            (3, 2, 3000000000),
            (4, 3, 2**50),
            (5, 4, -100000),
            (6, 5, -(2**50)),
        ],
    )
    out = _run_parser([_hex(msg)])
    fields = out["messages"][0]["fields"]
    assert fields[0]["value"] == 200
    assert fields[1]["value"] == 40000
    assert fields[2]["value"] == 3000000000
    assert fields[3]["value"] == 2**50
    assert fields[4]["value"] == -100000
    assert fields[5]["value"] == -(2**50)


# ─── Dynamic tests (binary responsiveness) ──────────────────────────────────
# These rebuild the binary after modifying a source file and verify the parser
# still works, preventing hardcoded output.


def test_dynamic_extra_field():
    """Modify a test message to include an extra field and verify the parser
    decodes it.  This prevents hardcoded output — the binary must actually
    parse whatever input is given."""
    msg = _make_message(
        99,
        [
            (1, 0, 111),
            (2, 0, 222),
            (3, 2, 12345),
            (4, 6, "dynamic"),
        ],
    )
    out = _run_parser([_hex(msg)])
    m = out["messages"][0]
    assert m["msg_type"] == 99
    assert m["field_count"] == 4
    assert m["fields"][0]["value"] == 111
    assert m["fields"][1]["value"] == 222
    assert m["fields"][2]["value"] == 12345
    assert m["fields"][3]["value"] == "dynamic"
    assert m["crc_valid"] is True


def test_dynamic_varying_string_length():
    """Verify the parser handles strings of various lengths correctly."""
    for length in [0, 1, 127, 128, 255, 256, 512]:
        s = "Q" * length
        msg = _make_message(50, [(1, 6, s)])
        out = _run_parser([_hex(msg)])
        assert out["messages"][0]["fields"][0]["value"] == s, (
            f"Failed for string length {length}"
        )


def test_dynamic_nested_depth():
    """Verify nested-inside-nested parsing works."""
    inner2 = _make_nested_payload([(20, 0, 42)])
    inner1 = _make_nested_payload([(10, 8, inner2)])
    msg = _make_message(40, [(1, 8, inner1)])
    out = _run_parser([_hex(msg)])
    nested1 = out["messages"][0]["fields"][0]["value"]
    assert len(nested1) == 1
    nested2 = nested1[0]["value"]
    assert len(nested2) == 1
    assert nested2[0]["value"] == 42
