use crate::error::ProtocolError;
use crate::field::FieldValue;
use crate::protocol::FieldType;

/// Trait for encoding a field value into bytes.
pub trait FieldEncoder {
    fn encode(&self, value: &FieldValue) -> Result<Vec<u8>, ProtocolError>;
    fn field_type(&self) -> FieldType;
}

/// Trait for decoding a field value from bytes at a given position.
pub trait FieldDecoder {
    fn decode(&self, buf: &[u8], pos: usize) -> Result<(FieldValue, usize), ProtocolError>;
    fn field_type(&self) -> FieldType;
}

pub struct U8Codec;
pub struct U16Codec;
pub struct U32Codec;
pub struct U64Codec;
pub struct I32Codec;
pub struct I64Codec;

impl FieldDecoder for U8Codec {
    fn decode(&self, buf: &[u8], pos: usize) -> Result<(FieldValue, usize), ProtocolError> {
        if pos >= buf.len() {
            return Err(ProtocolError::BufferTooShort {
                needed: pos + 1,
                available: buf.len(),
            });
        }
        Ok((FieldValue::Unsigned(buf[pos] as u64), pos + 1))
    }

    fn field_type(&self) -> FieldType {
        FieldType::U8
    }
}

impl FieldDecoder for U16Codec {
    fn decode(&self, buf: &[u8], pos: usize) -> Result<(FieldValue, usize), ProtocolError> {
        if pos + 2 > buf.len() {
            return Err(ProtocolError::BufferTooShort {
                needed: pos + 2,
                available: buf.len(),
            });
        }
        let v = u16::from_le_bytes([buf[pos], buf[pos + 1]]);
        Ok((FieldValue::Unsigned(v as u64), pos + 2))
    }

    fn field_type(&self) -> FieldType {
        FieldType::U16
    }
}

impl FieldDecoder for U32Codec {
    fn decode(&self, buf: &[u8], pos: usize) -> Result<(FieldValue, usize), ProtocolError> {
        if pos + 4 > buf.len() {
            return Err(ProtocolError::BufferTooShort {
                needed: pos + 4,
                available: buf.len(),
            });
        }
        let v = u32::from_le_bytes([buf[pos], buf[pos + 1], buf[pos + 2], buf[pos + 3]]);
        Ok((FieldValue::Unsigned(v as u64), pos + 4))
    }

    fn field_type(&self) -> FieldType {
        FieldType::U32
    }
}

impl FieldDecoder for U64Codec {
    fn decode(&self, buf: &[u8], pos: usize) -> Result<(FieldValue, usize), ProtocolError> {
        if pos + 8 > buf.len() {
            return Err(ProtocolError::BufferTooShort {
                needed: pos + 8,
                available: buf.len(),
            });
        }
        let v = u64::from_le_bytes([
            buf[pos],
            buf[pos + 1],
            buf[pos + 2],
            buf[pos + 3],
            buf[pos + 4],
            buf[pos + 5],
            buf[pos + 6],
            buf[pos + 7],
        ]);
        Ok((FieldValue::Unsigned(v), pos + 8))
    }

    fn field_type(&self) -> FieldType {
        FieldType::U64
    }
}

impl FieldDecoder for I32Codec {
    fn decode(&self, buf: &[u8], pos: usize) -> Result<(FieldValue, usize), ProtocolError> {
        if pos + 4 > buf.len() {
            return Err(ProtocolError::BufferTooShort {
                needed: pos + 4,
                available: buf.len(),
            });
        }
        let v = i32::from_le_bytes([buf[pos], buf[pos + 1], buf[pos + 2], buf[pos + 3]]);
        Ok((FieldValue::Signed(v as i64), pos + 4))
    }

    fn field_type(&self) -> FieldType {
        FieldType::I32
    }
}

impl FieldDecoder for I64Codec {
    fn decode(&self, buf: &[u8], pos: usize) -> Result<(FieldValue, usize), ProtocolError> {
        if pos + 8 > buf.len() {
            return Err(ProtocolError::BufferTooShort {
                needed: pos + 8,
                available: buf.len(),
            });
        }
        let v = i64::from_le_bytes([
            buf[pos],
            buf[pos + 1],
            buf[pos + 2],
            buf[pos + 3],
            buf[pos + 4],
            buf[pos + 5],
            buf[pos + 6],
            buf[pos + 7],
        ]);
        Ok((FieldValue::Signed(v), pos + 8))
    }

    fn field_type(&self) -> FieldType {
        FieldType::I64
    }
}
