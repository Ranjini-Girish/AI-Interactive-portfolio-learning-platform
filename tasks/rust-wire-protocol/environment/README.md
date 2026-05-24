# wire-protocol

A Rust implementation of a custom binary TLV wire protocol parser and serializer.

## Building

```bash
cargo build --release
```

## Usage

```bash
./target/release/wire-protocol decode <input.json>
```

Reads JSON containing hex-encoded binary messages and outputs decoded field data.

## Protocol

See `docs/PROTOCOL.md` for the full wire format specification.

## Test Data

Sample messages are in `data/`. Each `test_*.json` has corresponding
`expected_*.json` with the correct decoded output.
