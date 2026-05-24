# Architecture

## Module Layout

- `protocol.rs` — Protocol constants, field type definitions, size lookups
- `message.rs` — Message and Header structs
- `field.rs` — Field and FieldValue types
- `parser.rs` — Binary message parsing (bytes → Message)
- `serializer.rs` — Message serialization (Message → bytes)
- `crc32.rs` — CRC32 checksum implementation
- `hexutil.rs` — Hex encoding/decoding utilities
- `error.rs` — Error type definitions
- `validate.rs` — Message validation helpers
- `display.rs` — Display formatting for messages
- `builder.rs` — Fluent API for constructing messages
- `main.rs` — CLI entry point

## Data Flow

1. JSON input containing hex-encoded messages is read
2. Hex strings are decoded to byte arrays
3. Each byte array is parsed according to the TLV protocol
4. Parsed messages are serialized to JSON and printed to stdout

## CLI Interface

```
wire-protocol decode <input.json>
```

Input JSON format:
```json
{
  "messages_hex": ["ab01...", "ab01..."]
}
```
