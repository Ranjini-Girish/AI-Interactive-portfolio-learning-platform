# Wire Protocol Specification v1

## Overview

The wire protocol encodes structured messages as compact binary frames suitable
for network transmission. Each frame is self-describing: it carries its own
schema in the form of typed fields, so the decoder does not need external
metadata to reconstruct the message.

## Frame Layout

A frame consists of three contiguous regions:

1. **Header** — fixed 4-byte preamble identifying the frame.
2. **Field sequence** — zero or more self-typed fields, each carrying a
   single value.
3. **Checksum** — 4-byte CRC32 integrity check.

### Header

The first byte is the magic marker `0xAB`, which receivers use to detect frame
boundaries. It is immediately followed by the protocol version byte, currently
`0x01`. The next two bytes encode, in order, the application-level message type
and the number of fields that follow. All four bytes together form a 32-bit
word when read as a little-endian integer; byte 0 occupies the least-significant
position.

### Checksum

The trailing 4 bytes contain a CRC32 computed over every byte that precedes
them (header + field bytes). The polynomial is the standard ISO 3309
reflected form (`0xEDB88320`). The checksum is stored in little-endian byte
order.

## Field Encoding

Every field opens with a 2-byte tag: the **field ID** followed by the **type
code**. The remainder depends on the type code:

### Fixed-width numeric types

| Code | Name | Width | Notes                       |
|------|------|-------|-----------------------------|
| 0    | u8   | 1     | unsigned                    |
| 1    | u16  | 2     | unsigned, little-endian     |
| 2    | u32  | 4     | unsigned, little-endian     |
| 3    | u64  | 8     | unsigned, little-endian     |
| 4    | i32  | 4     | two's complement, LE        |
| 5    | i64  | 8     | two's complement, LE        |

All multi-byte integers use little-endian byte order.

### Variable-length types

Variable-length types prefix their payload with a length value encoding the
number of **content** bytes that follow (the length prefix itself is not
included in that count).

| Code | Name   | Prefix | Payload                     |
|------|--------|--------|-----------------------------|
| 6    | str    | 2 B LE | UTF-8 encoded text          |
| 7    | bytes  | 2 B LE | raw octet string            |
| 8    | nested | 4 B LE | another field sequence       |

The **str** and **bytes** types have a 2-byte little-endian length prefix.
The **nested** type uses a 4-byte little-endian length prefix, after which
comes a sequence of fields (encoded identically to top-level fields, but
without a header or checksum).

After decoding a variable-length field, the outer parser should resume from
the first byte past the end of that field's content. That is, the read cursor
should advance past **both** the length prefix **and** the content bytes.

## Byte Order

Unless stated otherwise, every multi-byte integer in the protocol — including
field values, length prefixes, and the CRC32 — is encoded in **little-endian**
byte order.

## Example

A frame carrying msg_type 5, two fields (u8 id=1 value=42, u32 id=2
value=1000):

```
AB 01 05 02            Header
01 00 2A               Field 1: id=1 type=u8(0) val=42
02 02 E8 03 00 00      Field 2: id=2 type=u32(2) val=1000
XX XX XX XX            CRC32
```
