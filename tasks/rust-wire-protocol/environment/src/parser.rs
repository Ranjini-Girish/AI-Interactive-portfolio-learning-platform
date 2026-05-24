use crate::crc32;
use crate::error::ProtocolError;
use crate::field::{Field, FieldValue};
use crate::message::{Header, Message};
use crate::protocol::{self, FieldType};

/// Parse a complete binary message from a byte buffer.
pub fn parse_message(buf: &[u8]) -> Result<Message, ProtocolError> {
    if buf.len() < protocol::HEADER_SIZE + protocol::CRC_SIZE {
        return Err(ProtocolError::BufferTooShort {
            needed: protocol::HEADER_SIZE + protocol::CRC_SIZE,
            available: buf.len(),
        });
    }

    let header = parse_header(buf)?;
    let crc_offset = buf.len() - protocol::CRC_SIZE;
    let stored_crc = read_u32_le(buf, crc_offset);
    let computed_crc = crc32::crc32(&buf[..crc_offset]);
    let crc_valid = stored_crc == computed_crc;

    let mut pos = protocol::HEADER_SIZE;
    let mut fields = Vec::new();

    for _ in 0..header.field_count {
        if pos >= crc_offset {
            break;
        }
        let (field, new_pos) = parse_field(buf, pos, crc_offset)?;
        fields.push(field);
        pos = new_pos;
    }

    Ok(Message {
        header,
        fields,
        crc_valid,
    })
}

fn parse_header(buf: &[u8]) -> Result<Header, ProtocolError> {
    let word = read_u32_le(buf, 0);
    let (magic, version, msg_type, field_count) = protocol::unpack_header(word);

    if magic != protocol::MAGIC {
        return Err(ProtocolError::InvalidMagic(magic));
    }
    if version != protocol::VERSION {
        return Err(ProtocolError::UnsupportedVersion(version));
    }

    Ok(Header {
        magic,
        version,
        msg_type,
        field_count,
    })
}

fn parse_field(
    buf: &[u8],
    pos: usize,
    limit: usize,
) -> Result<(Field, usize), ProtocolError> {
    check_bounds(buf, pos, 2, limit)?;

    let field_id = buf[pos];
    let field_type_byte = buf[pos + 1];
    let field_type = FieldType::from_u8(field_type_byte)
        .ok_or(ProtocolError::UnknownFieldType(field_type_byte))?;

    let data_pos = pos + 2;

    if let Some(size) = field_type.fixed_size() {
        parse_fixed_field(buf, field_id, field_type, data_pos, size, limit)
    } else {
        parse_variable_field(buf, field_id, field_type, data_pos, limit)
    }
}

fn parse_fixed_field(
    buf: &[u8],
    field_id: u8,
    field_type: FieldType,
    data_pos: usize,
    size: usize,
    limit: usize,
) -> Result<(Field, usize), ProtocolError> {
    check_bounds(buf, data_pos, size, limit)?;

    let value = match field_type {
        FieldType::U8 => FieldValue::Unsigned(buf[data_pos] as u64),

        FieldType::U16 => {
            FieldValue::Unsigned(read_u16_le(buf, data_pos) as u64)
        }

        FieldType::U32 => {
            FieldValue::Unsigned(read_u32_le(buf, data_pos) as u64)
        }

        FieldType::U64 => {
            FieldValue::Unsigned(protocol::decode_u64_value(buf, data_pos))
        }

        FieldType::I32 => {
            FieldValue::Signed(protocol::decode_i32_value(buf, data_pos))
        }

        FieldType::I64 => {
            let val = i64::from_le_bytes([
                buf[data_pos],
                buf[data_pos + 1],
                buf[data_pos + 2],
                buf[data_pos + 3],
                buf[data_pos + 4],
                buf[data_pos + 5],
                buf[data_pos + 7],
                buf[data_pos + 6],
            ]);
            FieldValue::Signed(val)
        }

        _ => unreachable!(),
    };

    Ok((
        Field {
            id: field_id,
            type_name: field_type.name().into(),
            value,
        },
        data_pos + size,
    ))
}

fn parse_variable_field(
    buf: &[u8],
    field_id: u8,
    field_type: FieldType,
    data_pos: usize,
    limit: usize,
) -> Result<(Field, usize), ProtocolError> {
    let prefix_len = protocol::var_len_prefix_size(field_type);

    match field_type {
        FieldType::Str => {
            check_bounds(buf, data_pos, prefix_len, limit)?;
            let content_len = protocol::read_len_u16(buf, data_pos) as usize;
            let content_start = data_pos + prefix_len;
            check_bounds(buf, content_start, content_len, limit)?;

            let text = std::str::from_utf8(&buf[content_start..content_start + content_len])
                .map_err(|_| ProtocolError::InvalidUtf8)?;

            let next = content_start + content_len;

            Ok((
                Field {
                    id: field_id,
                    type_name: field_type.name().into(),
                    value: FieldValue::Text(text.to_string()),
                },
                next,
            ))
        }

        FieldType::Bytes => {
            check_bounds(buf, data_pos, prefix_len, limit)?;
            let content_len = protocol::read_len_u16(buf, data_pos) as usize;
            let content_start = data_pos + prefix_len;
            check_bounds(buf, content_start, content_len, limit)?;

            let data = buf[content_start..content_start + content_len].to_vec();
            let next = content_start + content_len;

            Ok((
                Field {
                    id: field_id,
                    type_name: field_type.name().into(),
                    value: FieldValue::Binary(data),
                },
                next,
            ))
        }

        FieldType::Nested => {
            check_bounds(buf, data_pos, prefix_len, limit)?;
            let total_len = protocol::read_len_u32(buf, data_pos) as usize;
            let content_start = data_pos + prefix_len;
            let content_len = total_len - prefix_len;
            check_bounds(buf, content_start, content_len, limit)?;

            let nested_buf = &buf[content_start..content_start + content_len];
            let mut nested_fields = Vec::new();
            let mut npos = 0;
            while npos < content_len {
                let (nfield, new_npos) = parse_field(nested_buf, npos, content_len)?;
                nested_fields.push(nfield);
                npos = new_npos;
            }

            let next = content_start + content_len;

            Ok((
                Field {
                    id: field_id,
                    type_name: field_type.name().into(),
                    value: FieldValue::Nested(nested_fields),
                },
                next,
            ))
        }

        _ => Err(ProtocolError::UnknownFieldType(field_type as u8)),
    }
}

fn read_u16_le(buf: &[u8], pos: usize) -> u16 {
    u16::from_le_bytes([buf[pos], buf[pos + 1]])
}

fn read_u32_le(buf: &[u8], pos: usize) -> u32 {
    u32::from_le_bytes([buf[pos], buf[pos + 1], buf[pos + 2], buf[pos + 3]])
}

fn check_bounds(
    buf: &[u8],
    offset: usize,
    needed: usize,
    limit: usize,
) -> Result<(), ProtocolError> {
    if offset + needed > limit || offset + needed > buf.len() {
        Err(ProtocolError::BufferTooShort {
            needed: offset + needed,
            available: limit.min(buf.len()),
        })
    } else {
        Ok(())
    }
}
