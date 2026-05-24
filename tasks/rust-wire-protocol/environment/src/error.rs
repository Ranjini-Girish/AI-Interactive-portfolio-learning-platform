use std::fmt;

#[derive(Debug)]
pub enum ProtocolError {
    InvalidMagic(u8),
    UnsupportedVersion(u8),
    UnknownFieldType(u8),
    BufferTooShort { needed: usize, available: usize },
    InvalidUtf8,
    CrcMismatch { expected: u32, computed: u32 },
    InvalidHex(String),
}

impl fmt::Display for ProtocolError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            ProtocolError::InvalidMagic(m) => write!(f, "invalid magic byte: 0x{:02X}", m),
            ProtocolError::UnsupportedVersion(v) => write!(f, "unsupported version: {}", v),
            ProtocolError::UnknownFieldType(t) => write!(f, "unknown field type: {}", t),
            ProtocolError::BufferTooShort { needed, available } => {
                write!(f, "buffer too short: need {} bytes, have {}", needed, available)
            }
            ProtocolError::InvalidUtf8 => write!(f, "invalid UTF-8 in string field"),
            ProtocolError::CrcMismatch { expected, computed } => {
                write!(f, "CRC mismatch: expected 0x{:08X}, computed 0x{:08X}", expected, computed)
            }
            ProtocolError::InvalidHex(s) => write!(f, "invalid hex string: {}", s),
        }
    }
}

impl std::error::Error for ProtocolError {}
