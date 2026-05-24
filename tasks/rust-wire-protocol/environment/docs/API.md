# API Reference

## Parser

```rust
pub fn parse_message(buf: &[u8]) -> Result<Message, ProtocolError>
```

Parses a complete binary message from the given buffer. The buffer must
contain the full message including header, fields, and CRC32 checksum.

## Serializer

```rust
pub fn serialize_message(msg_type: u8, fields: &[Field]) -> Vec<u8>
```

Serializes fields into a complete binary message with header and CRC32.

## Builder

```rust
let msg = MessageBuilder::new(5)
    .add_u8(1, 42)
    .add_u32(2, 1000)
    .build();
```

Fluent API for constructing binary messages.

## Hex Utilities

```rust
pub fn decode_hex(hex: &str) -> Result<Vec<u8>, ProtocolError>
pub fn encode_hex(data: &[u8]) -> String
```
