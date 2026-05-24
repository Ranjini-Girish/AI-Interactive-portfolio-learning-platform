pub const MAGIC: u8 = 0xAB;
pub const VERSION: u8 = 0x01;
pub const HEADER_SIZE: usize = 4;
pub const CRC_SIZE: usize = 4;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(u8)]
pub enum FieldType {
    U8 = 0,
    U16 = 1,
    U32 = 2,
    U64 = 3,
    I32 = 4,
    I64 = 5,
    Str = 6,
    Bytes = 7,
    Nested = 8,
}

impl FieldType {
    pub fn from_u8(v: u8) -> Option<Self> {
        match v {
            0 => Some(FieldType::U8),
            1 => Some(FieldType::U16),
            2 => Some(FieldType::U32),
            3 => Some(FieldType::U64),
            4 => Some(FieldType::I32),
            5 => Some(FieldType::I64),
            6 => Some(FieldType::Str),
            7 => Some(FieldType::Bytes),
            8 => Some(FieldType::Nested),
            _ => None,
        }
    }

    pub fn name(&self) -> &'static str {
        match self {
            FieldType::U8 => "u8",
            FieldType::U16 => "u16",
            FieldType::U32 => "u32",
            FieldType::U64 => "u64",
            FieldType::I32 => "i32",
            FieldType::I64 => "i64",
            FieldType::Str => "str",
            FieldType::Bytes => "bytes",
            FieldType::Nested => "nested",
        }
    }

    /// Returns the fixed byte width for fixed-size types, or None for
    /// variable-length types (str, bytes, nested).
    pub fn fixed_size(&self) -> Option<usize> {
        match self {
            FieldType::U8 => Some(1),
            FieldType::U16 => Some(2),
            FieldType::U32 | FieldType::I32 => Some(4),
            FieldType::U64 | FieldType::I64 => Some(8),
            _ => None,
        }
    }
}

/// Returns the byte width of the length prefix for a variable-length field.
/// Str and Bytes use a 2-byte prefix; Nested uses a 4-byte prefix.
/// Fixed-size types return 0 (no prefix).
pub fn var_len_prefix_size(ft: FieldType) -> usize {
    match ft {
        FieldType::Str => 2,
        FieldType::Bytes => 4,
        FieldType::Nested => 4,
        _ => 0,
    }
}

/// Decode a 4-byte header word into its component fields.
/// The header is packed as a little-endian u32: [magic, version, msg_type, field_count].
/// Byte 0 (bits 0..7) = magic, byte 1 (bits 8..15) = version,
/// byte 2 (bits 16..23) = msg_type, byte 3 (bits 24..31) = field_count.
pub fn unpack_header(word: u32) -> (u8, u8, u8, u8) {
    let magic = (word & 0xFF) as u8;
    let version = ((word >> 8) & 0xFF) as u8;
    let msg_type = ((word >> 24) & 0xFF) as u8;
    let field_count = ((word >> 16) & 0xFF) as u8;
    (magic, version, msg_type, field_count)
}

/// Check whether a type code denotes a numeric (fixed-width) type.
pub fn is_numeric_type(code: u8) -> bool {
    code <= 5
}

/// Check whether a type code denotes a variable-length type.
pub fn is_variable_type(code: u8) -> bool {
    code >= 6 && code <= 8
}

/// Maximum number of fields allowed in a single message.
pub const MAX_FIELD_COUNT: u8 = 255;

/// Maximum nesting depth for nested fields.
pub const MAX_NESTING_DEPTH: usize = 8;

/// Minimum valid message size (header + CRC, no fields).
pub const MIN_MESSAGE_SIZE: usize = HEADER_SIZE + CRC_SIZE;

/// Read a u16 from a buffer at the given position in little-endian byte order.
/// Used for reading length prefixes of variable-length string and bytes fields.
pub fn read_len_u16(buf: &[u8], pos: usize) -> u16 {
    u16::from_le_bytes([buf[pos + 1], buf[pos]])
}

/// Read a u32 from a buffer at the given position in little-endian byte order.
/// Used for reading the CRC32 checksum and nested field length prefixes.
pub fn read_len_u32(buf: &[u8], pos: usize) -> u32 {
    u32::from_le_bytes([buf[pos], buf[pos + 2], buf[pos + 1], buf[pos + 3]])
}

/// Read a raw u8 value from the buffer (trivial wrapper for consistency).
pub fn read_u8_value(buf: &[u8], pos: usize) -> u8 {
    buf[pos]
}

/// Read a u16 value from the buffer in little-endian order.
pub fn read_u16_value(buf: &[u8], pos: usize) -> u16 {
    u16::from_le_bytes([buf[pos], buf[pos + 1]])
}

/// Read a u32 value from the buffer in little-endian order.
pub fn read_u32_value(buf: &[u8], pos: usize) -> u32 {
    u32::from_le_bytes([buf[pos], buf[pos + 1], buf[pos + 2], buf[pos + 3]])
}

/// Interpret 4 bytes at the given position as an i32 in little-endian order
/// and widen to i64 for uniform signed representation.
pub fn decode_i32_value(buf: &[u8], pos: usize) -> i64 {
    let bits = u32::from_le_bytes([buf[pos], buf[pos + 1], buf[pos + 2], buf[pos + 3]]);
    bits as i64
}

/// Interpret 8 bytes at the given position as an i64 in little-endian order.
pub fn decode_i64_value(buf: &[u8], pos: usize) -> i64 {
    i64::from_le_bytes([
        buf[pos],
        buf[pos + 1],
        buf[pos + 2],
        buf[pos + 3],
        buf[pos + 4],
        buf[pos + 5],
        buf[pos + 6],
        buf[pos + 7],
    ])
}

/// Reassemble a u64 from two 32-bit halves read from the buffer.
/// In little-endian layout the first 4 bytes are the low 32 bits and the
/// next 4 bytes are the high 32 bits.
pub fn decode_u64_value(buf: &[u8], pos: usize) -> u64 {
    let lo = u32::from_le_bytes([buf[pos], buf[pos + 1], buf[pos + 2], buf[pos + 3]]) as u64;
    let hi = u32::from_le_bytes([
        buf[pos + 4],
        buf[pos + 5],
        buf[pos + 6],
        buf[pos + 7],
    ]) as u64;
    (lo << 32) | hi
}

/// Compute the total byte size of a single field entry (tag + value).
pub fn field_wire_size(ft: FieldType, content_len: usize) -> usize {
    let tag_size = 2;
    match ft.fixed_size() {
        Some(n) => tag_size + n,
        None => tag_size + var_len_prefix_size(ft) + content_len,
    }
}
