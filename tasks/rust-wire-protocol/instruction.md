A TypeScript on Node 22 implementation of a custom binary wire protocol parser is located at `/app/`. The protocol uses a TLV (Type-Length-Value) format whose specification is in `/app/docs/PROTOCOL.md`. The implementation spans multiple source modules under `/app/src/`, including core protocol definitions, parsing logic, and various helper utilities.

The parser is a command-line tool that accepts a JSON input file containing hex-encoded binary messages and decodes each message into structured JSON output. The expected output for each input file is provided as a corresponding `expected_*.json` file in `/app/data/`.

The decoded JSON output is an object with a `messages` array. Each message entry contains:
- `magic` (integer): the magic byte value from the header
- `version` (integer): the protocol version from the header
- `msg_type` (integer): the application message type from the header
- `field_count` (integer): the number of fields declared in the header
- `fields` (array): decoded fields, each with `id` (integer), `type_name` (string), and `value` (type-dependent: integer for numeric types, string for str, array of bytes for bytes, array of nested fields for nested)
- `crc_valid` (boolean): whether the CRC32 checksum matches

The current implementation contains bugs that cause incorrect decoding of certain field types and message structures. The parser compiles and runs without errors, but its output does not match the protocol specification for several cases. The bugs affect header field extraction, numeric value interpretation, string length handling, and nested message parsing across the source modules.

Fix all bugs in the source files under `/app/src/` so that the decoded output matches the protocol specification in `/app/docs/PROTOCOL.md` and the expected results in `/app/data/expected_*.json`.
