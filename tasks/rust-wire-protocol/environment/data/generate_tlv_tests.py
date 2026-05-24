#!/usr/bin/env python3
"""Generate TLV wire-protocol test vectors (hex) and expected decoded JSON."""

from __future__ import annotations

import binascii
import json
from pathlib import Path

MAGIC = 0xAB
VERSION = 0x01

TYPE_U8 = 0
TYPE_U16 = 1
TYPE_U32 = 2
TYPE_U64 = 3
TYPE_I32 = 4
TYPE_I64 = 5
TYPE_STR = 6
TYPE_BYTES = 7
TYPE_NESTED = 8


def crc32_le_append(payload: bytes) -> bytes:
    c = binascii.crc32(payload) & 0xFFFFFFFF
    return payload + c.to_bytes(4, "little")


def encode_field_body(field_id: int, field_type: int, value_bytes: bytes) -> bytes:
    return bytes([field_id & 0xFF, field_type & 0xFF]) + value_bytes


def encode_u8(field_id: int, v: int) -> bytes:
    return encode_field_body(field_id, TYPE_U8, bytes([v & 0xFF]))


def encode_u16(field_id: int, v: int) -> bytes:
    return encode_field_body(field_id, TYPE_U16, (v & 0xFFFF).to_bytes(2, "little"))


def encode_u32(field_id: int, v: int) -> bytes:
    return encode_field_body(field_id, TYPE_U32, (v & 0xFFFFFFFF).to_bytes(4, "little"))


def encode_u64(field_id: int, v: int) -> bytes:
    return encode_field_body(field_id, TYPE_U64, (v & 0xFFFFFFFFFFFFFFFF).to_bytes(8, "little"))


def encode_i32(field_id: int, v: int) -> bytes:
    return encode_field_body(field_id, TYPE_I32, int(v).to_bytes(4, "little", signed=True))


def encode_i64(field_id: int, v: int) -> bytes:
    return encode_field_body(field_id, TYPE_I64, int(v).to_bytes(8, "little", signed=True))


def encode_str(field_id: int, s: str) -> bytes:
    b = s.encode("utf-8")
    return encode_field_body(field_id, TYPE_STR, len(b).to_bytes(2, "little") + b)


def encode_bytes(field_id: int, data: bytes) -> bytes:
    return encode_field_body(field_id, TYPE_BYTES, len(data).to_bytes(2, "little") + data)


def encode_nested(field_id: int, inner_fields: bytes) -> bytes:
    ln = len(inner_fields).to_bytes(4, "little")
    return encode_field_body(field_id, TYPE_NESTED, ln + inner_fields)


def build_message(msg_type: int, field_payloads: list[bytes]) -> bytes:
    header = bytes([MAGIC, VERSION, msg_type & 0xFF, len(field_payloads) & 0xFF])
    body = header + b"".join(field_payloads)
    return crc32_le_append(body)


def hex_upper(msg: bytes) -> str:
    return msg.hex().upper()


def write_json(path: Path, obj: object) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    out_dir = Path(__file__).resolve().parent

    # --- test_simple ---
    simple_fields_b = [
        encode_u8(1, 42),
        encode_u32(2, 1000),
    ]
    simple_msg = build_message(5, simple_fields_b)
    simple_expected = {
        "messages": [
            {
                "magic": MAGIC,
                "version": VERSION,
                "msg_type": 5,
                "field_count": 2,
                "fields": [
                    {"id": 1, "type_name": "u8", "value": 42},
                    {"id": 2, "type_name": "u32", "value": 1000},
                ],
                "crc_valid": True,
            }
        ]
    }
    write_json(out_dir / "test_simple.json", {"messages": [{"hex": hex_upper(simple_msg)}]})
    write_json(out_dir / "expected_simple.json", simple_expected)

    # --- test_types ---
    types_fields_b = [
        encode_u16(1, 500),
        encode_u64(2, 123456789012345),
        encode_i32(3, -42),
        encode_i64(4, -100000),
    ]
    types_msg = build_message(3, types_fields_b)
    types_expected = {
        "messages": [
            {
                "magic": MAGIC,
                "version": VERSION,
                "msg_type": 3,
                "field_count": 4,
                "fields": [
                    {"id": 1, "type_name": "u16", "value": 500},
                    {"id": 2, "type_name": "u64", "value": 123456789012345},
                    {"id": 3, "type_name": "i32", "value": -42},
                    {"id": 4, "type_name": "i64", "value": -100000},
                ],
                "crc_valid": True,
            }
        ]
    }
    write_json(out_dir / "test_types.json", {"messages": [{"hex": hex_upper(types_msg)}]})
    write_json(out_dir / "expected_types.json", types_expected)

    # --- test_strings ---
    strings_fields_b = [
        encode_str(1, "hello"),
        encode_u8(2, 99),
        encode_str(3, "world"),
    ]
    strings_msg = build_message(7, strings_fields_b)
    strings_expected = {
        "messages": [
            {
                "magic": MAGIC,
                "version": VERSION,
                "msg_type": 7,
                "field_count": 3,
                "fields": [
                    {"id": 1, "type_name": "str", "value": "hello"},
                    {"id": 2, "type_name": "u8", "value": 99},
                    {"id": 3, "type_name": "str", "value": "world"},
                ],
                "crc_valid": True,
            }
        ]
    }
    write_json(out_dir / "test_strings.json", {"messages": [{"hex": hex_upper(strings_msg)}]})
    write_json(out_dir / "expected_strings.json", strings_expected)

    # --- test_nested ---
    nested_inner = encode_u8(10, 1) + encode_u16(11, 500)
    nested_fields_b = [
        encode_nested(1, nested_inner),
        encode_u32(2, 42),
    ]
    nested_msg = build_message(10, nested_fields_b)
    nested_expected = {
        "messages": [
            {
                "magic": MAGIC,
                "version": VERSION,
                "msg_type": 10,
                "field_count": 2,
                "fields": [
                    {
                        "id": 1,
                        "type_name": "nested",
                        "value": [
                            {"id": 10, "type_name": "u8", "value": 1},
                            {"id": 11, "type_name": "u16", "value": 500},
                        ],
                    },
                    {"id": 2, "type_name": "u32", "value": 42},
                ],
                "crc_valid": True,
            }
        ]
    }
    write_json(out_dir / "test_nested.json", {"messages": [{"hex": hex_upper(nested_msg)}]})
    write_json(out_dir / "expected_nested.json", nested_expected)

    # --- test_mixed ---
    mixed_fields_b = [
        encode_u8(1, 255),
        encode_str(2, "test"),
        encode_i32(3, -1),
        encode_u64(4, 999999999999),
        encode_bytes(5, bytes([0xDE, 0xAD, 0xBE, 0xEF])),
    ]
    mixed_msg = build_message(15, mixed_fields_b)
    mixed_expected = {
        "messages": [
            {
                "magic": MAGIC,
                "version": VERSION,
                "msg_type": 15,
                "field_count": 5,
                "fields": [
                    {"id": 1, "type_name": "u8", "value": 255},
                    {"id": 2, "type_name": "str", "value": "test"},
                    {"id": 3, "type_name": "i32", "value": -1},
                    {"id": 4, "type_name": "u64", "value": 999999999999},
                    {"id": 5, "type_name": "bytes", "value": [222, 173, 190, 239]},
                ],
                "crc_valid": True,
            }
        ]
    }
    write_json(out_dir / "test_mixed.json", {"messages": [{"hex": hex_upper(mixed_msg)}]})
    write_json(out_dir / "expected_mixed.json", mixed_expected)

    # --- test_edge ---
    edge_fields_b = [
        encode_u32(1, 0),
        encode_i32(2, -(2**31)),
        encode_u64(3, 2**64 - 1),
    ]
    edge_msg = build_message(1, edge_fields_b)
    edge_expected = {
        "messages": [
            {
                "magic": MAGIC,
                "version": VERSION,
                "msg_type": 1,
                "field_count": 3,
                "fields": [
                    {"id": 1, "type_name": "u32", "value": 0},
                    {"id": 2, "type_name": "i32", "value": -2147483648},
                    {"id": 3, "type_name": "u64", "value": 18446744073709551615},
                ],
                "crc_valid": True,
            }
        ]
    }
    write_json(out_dir / "test_edge.json", {"messages": [{"hex": hex_upper(edge_msg)}]})
    write_json(out_dir / "expected_edge.json", edge_expected)

    # Print summary hex strings
    labels = [
        ("simple", simple_msg),
        ("types", types_msg),
        ("strings", strings_msg),
        ("nested", nested_msg),
        ("mixed", mixed_msg),
        ("edge", edge_msg),
    ]
    print("Generated files in:", out_dir)
    for name, msg in labels:
        print(f"{name}: {hex_upper(msg)}")


if __name__ == "__main__":
    main()
